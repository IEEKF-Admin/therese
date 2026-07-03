from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.documents.audience import user_matches_document_audience
from apps.documents.models import (
    Document,
    DocumentCategory,
    DocumentPublishPopupAck,
    DocumentReadAcknowledgement,
    DocumentVersion,
)
from apps.documents.utils import copy_attachments_to_version, create_next_version, publish_version
from apps.hr.models import Employee, Workgroup


def _create_user(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class DocumentAudienceTests(TestCase):
    def setUp(self):
        self.viewer = _create_user('viewer')
        self.other = _create_user('other')
        self.group = Group.objects.create(name='Doc Viewers')
        self.viewer.groups.add(self.group)

        ct = ContentType.objects.get_for_model(Document)
        view_perm = Permission.objects.get(codename='view_document', content_type=ct)
        self.group.permissions.add(view_perm)

        self.employee = Employee.objects.create(
            employee_number='E-200',
            first_name='Vera',
            last_name='Viewer',
            user=self.viewer,
        )
        self.pi = Employee.objects.create(
            employee_number='E-PI2',
            first_name='PI',
            last_name='Boss',
        )
        self.workgroup = Workgroup.objects.create(
            short_name='WG-DOC',
            long_name='Document WG',
            pi=self.pi,
        )
        self.workgroup.members.add(self.employee)

        self.category = DocumentCategory.objects.create(name='SOPs')
        self.document = Document.objects.create(
            title='Safety procedure',
            category=self.category,
            created_by=self.viewer,
        )

    def test_empty_audience_matches_everyone(self):
        self.assertTrue(user_matches_document_audience(self.viewer, self.document))
        self.assertTrue(user_matches_document_audience(self.other, self.document))

    def test_target_user_restricts_audience(self):
        self.document.target_users.add(self.viewer)
        self.assertTrue(user_matches_document_audience(self.viewer, self.document))
        self.assertFalse(user_matches_document_audience(self.other, self.document))

    def test_target_workgroup_matches_member(self):
        self.document.target_workgroups.add(self.workgroup)
        self.assertTrue(user_matches_document_audience(self.viewer, self.document))
        self.assertFalse(user_matches_document_audience(self.other, self.document))

    def test_and_mode_requires_all_criteria(self):
        self.document.audience_match_mode = 'and'
        self.document.save()
        self.document.target_users.add(self.viewer)
        self.document.target_groups.add(self.group)
        self.assertTrue(user_matches_document_audience(self.viewer, self.document))
        self.document.target_users.clear()
        self.document.target_users.add(self.other)
        self.assertFalse(user_matches_document_audience(self.viewer, self.document))


class DocumentVersioningTests(TestCase):
    def setUp(self):
        self.manager = _create_user('manager')
        manage_group, _ = Group.objects.get_or_create(name='Documents & SOPs - Manage')
        ct = ContentType.objects.get_for_model(Document)
        for codename in ('view_document', 'manage_document'):
            manage_group.permissions.add(
                Permission.objects.get(codename=codename, content_type=ct)
            )
        self.manager.groups.add(manage_group)

        self.category = DocumentCategory.objects.create(name='Guides')
        self.document = Document.objects.create(
            title='Onboarding',
            category=self.category,
            created_by=self.manager,
        )
        self.v1 = DocumentVersion.objects.create(
            document=self.document,
            version_number=1,
            status=DocumentVersion.Status.DRAFT,
            content_html='<p>Version 1</p>',
            created_by=self.manager,
        )
        self.file = SimpleUploadedFile('guide.pdf', b'pdf-content', content_type='application/pdf')
        self.v1.attachments.create(label='Guide PDF', file=self.file)

    def test_publish_sets_current_version(self):
        publish_version(self.v1, self.manager)
        self.v1.refresh_from_db()
        self.document.refresh_from_db()
        self.assertEqual(self.v1.status, DocumentVersion.Status.PUBLISHED)
        self.assertEqual(self.document.current_published_version_id, self.v1.pk)

    def test_new_version_copies_content_and_attachments(self):
        publish_version(self.v1, self.manager)
        v2 = create_next_version(self.document, self.manager, copy_from_version=self.v1)
        self.assertEqual(v2.version_number, 2)
        self.assertEqual(v2.status, DocumentVersion.Status.DRAFT)
        self.assertEqual(v2.content_html, self.v1.content_html)
        self.assertEqual(v2.attachments.count(), 1)
        self.assertNotEqual(v2.attachments.first().pk, self.v1.attachments.first().pk)

    def test_editor_image_upload(self):
        self.client.force_login(self.manager)
        image = SimpleUploadedFile(
            'diagram.png',
            (
                b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
                b'\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
                b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01'
                b'\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
            ),
            content_type='image/png',
        )
        response = self.client.post(
            reverse('documents:upload_editor_image'),
            {'file': image},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('location', payload)
        self.assertTrue(payload['location'].endswith('.png'))

    def test_immediate_attachment_delete(self):
        self.client.force_login(self.manager)
        url = reverse(
            'documents:manage_attachment_delete',
            args=[self.document.pk, self.v1.attachments.first().pk],
        )
        response = self.client.post(
            url,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.v1.attachments.exists())

    def test_copy_attachments_creates_separate_files(self):
        target = DocumentVersion.objects.create(
            document=self.document,
            version_number=99,
            status=DocumentVersion.Status.DRAFT,
            created_by=self.manager,
        )
        copy_attachments_to_version(self.v1, target)
        self.assertEqual(target.attachments.count(), 1)
        self.assertNotEqual(
            target.attachments.first().file.name,
            self.v1.attachments.first().file.name,
        )


class DocumentViewTests(TestCase):
    def setUp(self):
        self.viewer = _create_user('reader')
        view_group, _ = Group.objects.get_or_create(name='Documents & SOPs - View')
        ct = ContentType.objects.get_for_model(Document)
        view_group.permissions.add(Permission.objects.get(codename='view_document', content_type=ct))
        self.viewer.groups.add(view_group)

        self.category = DocumentCategory.objects.create(name='Policies')
        self.document = Document.objects.create(
            title='Leave policy',
            category=self.category,
            requires_read_acknowledgement=True,
            created_by=self.viewer,
        )
        self.version = DocumentVersion.objects.create(
            document=self.document,
            version_number=1,
            status=DocumentVersion.Status.PUBLISHED,
            content_html='<p>Policy text</p>',
            created_by=self.viewer,
        )
        self.document.current_published_version = self.version
        self.document.save()

    def test_reader_sees_published_document(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('documents:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Leave policy')

    def test_read_ack_confirm_and_reconsider(self):
        self.client.force_login(self.viewer)
        response = self.client.post(reverse('documents:ack_decline', args=[self.document.pk]))
        self.assertEqual(response.status_code, 302)
        ack = DocumentReadAcknowledgement.objects.get(version=self.version, user=self.viewer)
        self.assertEqual(ack.status, DocumentReadAcknowledgement.Status.DECLINED)

        self.client.post(reverse('documents:ack_reconsider', args=[self.document.pk]))
        ack.refresh_from_db()
        self.assertEqual(ack.status, DocumentReadAcknowledgement.Status.CONFIRMED)

    def test_publish_popup_ack(self):
        from apps.documents.popups import evaluate_document_publish_popups, persist_document_publish_popup_acks

        popups = evaluate_document_publish_popups(self.viewer)
        self.assertEqual(len(popups), 1)
        persist_document_publish_popup_acks(self.viewer, popups)
        self.assertTrue(
            DocumentPublishPopupAck.objects.filter(user=self.viewer, version=self.version).exists()
        )
        self.assertEqual(len(evaluate_document_publish_popups(self.viewer)), 0)