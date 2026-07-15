from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.checklists.access import user_can_fill_instance, user_has_active_checklists
from apps.checklists.models import (
    ChecklistInstance,
    ChecklistTemplate,
    ChecklistTemplateNode,
    ChecklistTemplateVersion,
)
from apps.checklists.services import assign_instance, compute_progress, publish_version
from apps.hr.models import Employee


def _user(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class ChecklistServicesTests(TestCase):
    def setUp(self):
        self.manager = _user('mgr')
        self.subject_user = _user('subject')
        self.subject = Employee.objects.create(
            employee_number='CL-001',
            first_name='Anna',
            last_name='Test',
            user=self.subject_user,
        )
        self.template = ChecklistTemplate.objects.create(
            slug='onboarding',
            name_en='Onboarding',
            name_de='Einarbeitung',
        )
        self.version = ChecklistTemplateVersion.objects.create(
            template=self.template,
            version_number=1,
            status=ChecklistTemplateVersion.Status.DRAFT,
            created_by=self.manager,
        )
        ChecklistTemplateNode.objects.create(
            version=self.version,
            node_kind=ChecklistTemplateNode.NodeKind.SECTION,
            label_en='Basics',
            label_de='Grundlagen',
            sort_order=0,
        )
        self.field = ChecklistTemplateNode.objects.create(
            version=self.version,
            node_kind=ChecklistTemplateNode.NodeKind.FIELD,
            field_type=ChecklistTemplateNode.FieldType.CHECKBOX,
            label_en='Read handbook',
            label_de='Handbuch gelesen',
            required_for_completion=True,
            sort_order=1,
        )
        publish_version(self.version, self.manager)

    def test_assign_instance(self):
        instance = assign_instance(self.subject, self.version, assigned_by=self.manager)
        self.assertEqual(instance.subject, self.subject)
        self.assertEqual(instance.assigned_by, self.manager)
        self.assertEqual(instance.status, ChecklistInstance.Status.NOT_STARTED)

    def test_compute_progress_empty(self):
        instance = assign_instance(self.subject, self.version, assigned_by=self.manager)
        percent, fulfilled, total = compute_progress(instance)
        self.assertEqual(total, 1)
        self.assertEqual(fulfilled, 0)
        self.assertEqual(percent, 0)

    def test_user_has_active_checklists(self):
        assign_instance(self.subject, self.version, assigned_by=self.manager)
        self.assertTrue(user_has_active_checklists(self.subject_user))
        self.assertTrue(user_can_fill_instance(self.subject_user, ChecklistInstance.objects.first()))


class ChecklistViewTests(TestCase):
    def setUp(self):
        self.user = _user('viewer')
        self.employee = Employee.objects.create(
            employee_number='CL-002',
            first_name='Bob',
            last_name='View',
            user=self.user,
        )
        self.template = ChecklistTemplate.objects.create(
            slug='safety',
            name_en='Safety',
            name_de='Sicherheit',
        )
        self.version = ChecklistTemplateVersion.objects.create(
            template=self.template,
            version_number=1,
            status=ChecklistTemplateVersion.Status.PUBLISHED,
        )
        self.instance = ChecklistInstance.objects.create(
            subject=self.employee,
            template_version=self.version,
        )

    def test_my_list_requires_active_checklists(self):
        self.client.login(username='viewer', password='test')
        response = self.client.get(reverse('checklists:my_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Safety')

    def test_manage_requires_permission(self):
        self.client.login(username='viewer', password='test')
        response = self.client.get(reverse('checklists:manage_template_list'))
        self.assertEqual(response.status_code, 403)

    def test_manage_allowed_with_permission(self):
        group, _ = Group.objects.get_or_create(name='Checklists - Manage')
        ct = ContentType.objects.get_for_model(ChecklistTemplate)
        perm = Permission.objects.get(codename='manage_checklist', content_type=ct)
        group.permissions.add(perm)
        self.user.groups.add(group)
        self.client.login(username='viewer', password='test')
        response = self.client.get(reverse('checklists:manage_template_list'))
        self.assertEqual(response.status_code, 200)

class ChecklistManageUITests(TestCase):
    def setUp(self):
        self.manager = _user('mgr-ui')
        group, _ = Group.objects.get_or_create(name='Checklists - Manage')
        ct = ContentType.objects.get_for_model(ChecklistTemplate)
        perm = Permission.objects.get(codename='manage_checklist', content_type=ct)
        group.permissions.add(perm)
        self.manager.groups.add(group)
        self.client.login(username='mgr-ui', password='test')

    def test_manage_template_create(self):
        url = reverse('checklists:manage_template_create')
        response = self.client.post(url, {
            'slug': 'welcome',
            'name_en': 'Welcome',
            'name_de': 'Willkommen',
            'description_en': '',
            'description_de': '',
        })
        self.assertEqual(response.status_code, 302)
        template = ChecklistTemplate.objects.get(slug='welcome')
        version = template.versions.get(version_number=1)
        self.assertEqual(version.status, ChecklistTemplateVersion.Status.DRAFT)
        self.assertIn(f'/versions/{version.pk}/edit/', response.url)

    def test_manage_version_edit_draft_only(self):
        template = ChecklistTemplate.objects.create(slug='t1', name_en='T1', name_de='T1')
        draft = ChecklistTemplateVersion.objects.create(
            template=template, version_number=1, status=ChecklistTemplateVersion.Status.DRAFT,
        )
        published = ChecklistTemplateVersion.objects.create(
            template=template, version_number=2, status=ChecklistTemplateVersion.Status.PUBLISHED,
        )
        ok = self.client.get(reverse('checklists:manage_version_edit', args=[template.pk, draft.pk]))
        self.assertEqual(ok.status_code, 200)
        blocked = self.client.get(reverse('checklists:manage_version_edit', args=[template.pk, published.pk]))
        self.assertEqual(blocked.status_code, 404)

    def test_manage_template_list_has_new_button(self):
        response = self.client.get(reverse('checklists:manage_template_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'New Template')
        self.assertNotContains(response, 'Admin bearbeiten')
class ChecklistHtmlNodeTests(TestCase):
    def setUp(self):
        self.manager = _user("mgr-html")
        group, _ = Group.objects.get_or_create(name="Checklists - Manage")
        ct = ContentType.objects.get_for_model(ChecklistTemplate)
        perm = Permission.objects.get(codename="manage_checklist", content_type=ct)
        group.permissions.add(perm)
        self.manager.groups.add(group)

        self.subject_user = _user("subj-html")
        self.subject = Employee.objects.create(
            employee_number="CL-HTML-1",
            first_name="Chris",
            last_name="Html",
            user=self.subject_user,
        )

        self.template = ChecklistTemplate.objects.create(
            slug="html-test",
            name_en="HTML Test",
            name_de="HTML Test DE",
        )
        self.version = ChecklistTemplateVersion.objects.create(
            template=self.template,
            version_number=1,
            status=ChecklistTemplateVersion.Status.DRAFT,
            created_by=self.manager,
        )
        self.section = ChecklistTemplateNode.objects.create(
            version=self.version,
            node_kind=ChecklistTemplateNode.NodeKind.SECTION,
            label_en="Intro",
            label_de="Einleitung",
            sort_order=0,
        )

    def test_add_html_node_via_manage_ui(self):
        self.client.login(username="mgr-html", password="test")
        url = reverse(
            "checklists:manage_version_edit",
            args=[self.template.pk, self.version.pk],
        )
        response = self.client.post(url, {
            "action": "add_node",
            "node_kind": ChecklistTemplateNode.NodeKind.HTML,
            "parent": self.section.pk,
            "sort_order": 1,
            "label_en": "Note",
            "label_de": "Hinweis",
            "help_en": "<p>Please read this.</p>",
            "help_de": "<p>Bitte lesen.</p>",
            "field_type": "",
            "choice_key": "",
            "required_for_completion": "",
        })
        self.assertEqual(response.status_code, 302)
        node = self.version.nodes.get(node_kind=ChecklistTemplateNode.NodeKind.HTML)
        self.assertIn("Please read", node.help_en)
        self.assertEqual(node.field_type, "")

    def test_html_node_renders_in_instance_fill(self):
        ChecklistTemplateNode.objects.create(
            version=self.version,
            parent=self.section,
            node_kind=ChecklistTemplateNode.NodeKind.HTML,
            label_en="Info",
            help_en="<strong>Important</strong>",
            sort_order=1,
        )
        publish_version(self.version, self.manager)
        instance = assign_instance(self.subject, self.version, assigned_by=self.manager)
        self.client.login(username="subj-html", password="test")
        response = self.client.get(reverse("checklists:instance_fill", args=[instance.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Important")

    def test_html_node_excluded_from_progress(self):
        ChecklistTemplateNode.objects.create(
            version=self.version,
            parent=self.section,
            node_kind=ChecklistTemplateNode.NodeKind.HTML,
            help_en="<p>Info</p>",
            required_for_completion=True,
            sort_order=1,
        )
        field = ChecklistTemplateNode.objects.create(
            version=self.version,
            parent=self.section,
            node_kind=ChecklistTemplateNode.NodeKind.FIELD,
            field_type=ChecklistTemplateNode.FieldType.CHECKBOX,
            label_en="Done",
            required_for_completion=True,
            sort_order=2,
        )
        publish_version(self.version, self.manager)
        instance = assign_instance(self.subject, self.version, assigned_by=self.manager)
        percent, fulfilled, total = compute_progress(instance)
        self.assertEqual(total, 1)
        self.assertEqual(fulfilled, 0)
        self.assertEqual(percent, 0)
        self.assertNotEqual(field.node_kind, ChecklistTemplateNode.NodeKind.HTML)

