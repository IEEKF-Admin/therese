from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, RequestFactory
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.documents.models import (
    Document,
    DocumentCategory,
    DocumentPublishPopupAck,
    DocumentReadAcknowledgement,
    DocumentVersion,
)
from apps.documents.sidebar_notifications import (
    documents_menu_needs_attention,
    get_pending_read_ack_document_ids,
    get_unseen_publish_version_ids,
    mark_publish_notifications_seen,
)
from therese.context_processors import user_groups


def _create_user(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class DocumentSidebarNotificationTests(TestCase):
    def setUp(self):
        self.viewer = _create_user('reader')
        view_group, _ = Group.objects.get_or_create(name='Documents & SOPs - View')
        ct = ContentType.objects.get_for_model(Document)
        view_group.permissions.add(Permission.objects.get(codename='view_document', content_type=ct))
        self.viewer.groups.add(view_group)

        self.category = DocumentCategory.objects.create(name='Policies')
        self.document = Document.objects.create(
            title='Safety policy',
            category=self.category,
            requires_read_acknowledgement=True,
        )
        self.version = DocumentVersion.objects.create(
            document=self.document,
            version_number=1,
            status=DocumentVersion.Status.PUBLISHED,
            content_html='<p>Policy</p>',
        )
        self.document.current_published_version = self.version
        self.document.save()

    def test_unseen_publish_version_shows_menu_attention(self):
        self.assertTrue(documents_menu_needs_attention(self.viewer))

    def test_mark_publish_notifications_seen_clears_publish_attention(self):
        mark_publish_notifications_seen(self.viewer)
        self.assertFalse(get_unseen_publish_version_ids(self.viewer))
        self.assertTrue(documents_menu_needs_attention(self.viewer))

    def test_read_ack_confirmation_clears_menu_attention(self):
        mark_publish_notifications_seen(self.viewer)
        DocumentReadAcknowledgement.objects.create(
            version=self.version,
            user=self.viewer,
            status=DocumentReadAcknowledgement.Status.CONFIRMED,
        )
        self.assertFalse(documents_menu_needs_attention(self.viewer))

    def test_document_list_marks_publish_notifications_seen(self):
        self.client.force_login(self.viewer)
        self.client.get(reverse('documents:list'))
        self.assertTrue(
            DocumentPublishPopupAck.objects.filter(user=self.viewer, version=self.version).exists()
        )

    def test_context_processor_exposes_menu_flag(self):
        request = RequestFactory().get('/')
        request.user = self.viewer
        context = user_groups(request)
        self.assertTrue(context['documents_menu_needs_attention'])

    def test_pending_read_ack_ids_include_unconfirmed_document(self):
        mark_publish_notifications_seen(self.viewer)
        self.assertIn(self.document.pk, get_pending_read_ack_document_ids(self.viewer))