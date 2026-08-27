from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.checklists.access import (
    checklists_menu_needs_attention,
    editor_work_complete,
    instances_editable_by_user,
    user_can_edit_node,
    user_can_fill_instance,
    user_has_active_checklists,
)
from apps.checklists.services import (
    assign_instance,
    compute_progress,
    copy_template_latest_version,
    publish_version,
    save_field_response,
)
from apps.checklists.models import (
    ChecklistEditorArchive,
    ChecklistInstance,
    ChecklistTemplate,
    ChecklistTemplateNode,
    ChecklistTemplateVersion,
)

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


class InstituteProgressTests(TestCase):
    def setUp(self):
        self.viewer = _user('inst-viewer')
        group, _ = Group.objects.get_or_create(name='Checklists - Institute Progress')
        ct = ContentType.objects.get_for_model(ChecklistTemplate)
        perm = Permission.objects.get(codename='view_institute_progress', content_type=ct)
        group.permissions.add(perm)
        self.viewer.groups.add(group)
        self.version = ChecklistTemplateVersion.objects.create(
            template=ChecklistTemplate.objects.create(
                slug='safety-inst',
                name_en='Safety Inst',
                name_de='Sicherheit Inst',
            ),
            version_number=1,
            status=ChecklistTemplateVersion.Status.PUBLISHED,
        )

    def test_lists_only_employees_with_open_assignments(self):
        open_emp = Employee.objects.create(
            employee_number='CL-OP', first_name='Open', last_name='Person',
        )
        done_emp = Employee.objects.create(
            employee_number='CL-DN', first_name='Done', last_name='Person',
        )
        Employee.objects.create(
            employee_number='CL-NO', first_name='None', last_name='Person',
        )
        ChecklistInstance.objects.create(
            subject=open_emp, template_version=self.version,
        )
        ChecklistInstance.objects.create(
            subject=done_emp,
            template_version=self.version,
            status=ChecklistInstance.Status.COMPLETED,
        )
        self.client.login(username='inst-viewer', password='test')
        response = self.client.get(reverse('checklists:progress_institute'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Open Person')
        self.assertNotContains(response, 'Done Person')
        self.assertNotContains(response, 'None Person')
        self.assertContains(response, 'All people with open checklists')

    def test_employee_detail_and_template_filter(self):
        open_emp = Employee.objects.create(
            employee_number='CL-OP2', first_name='Open', last_name='Filter',
        )
        other = Employee.objects.create(
            employee_number='CL-OT2', first_name='Other', last_name='Filter',
        )
        instance = ChecklistInstance.objects.create(
            subject=open_emp, template_version=self.version,
        )
        other_version = ChecklistTemplateVersion.objects.create(
            template=ChecklistTemplate.objects.create(
                slug='kit-inst',
                name_en='Kit Inst',
                name_de='Kit Inst DE',
            ),
            version_number=1,
            status=ChecklistTemplateVersion.Status.PUBLISHED,
        )
        ChecklistInstance.objects.create(subject=other, template_version=other_version)
        self.client.login(username='inst-viewer', password='test')

        person = self.client.get(
            reverse('checklists:progress_institute') + f'?employee={open_emp.pk}',
        )
        self.assertContains(person, 'Open Filter')
        self.assertContains(person, 'Safety Inst')
        self.assertContains(person, reverse('checklists:instance_view', args=[instance.pk]))
        self.assertNotContains(person, 'Kit Inst')

        filtered = self.client.get(
            reverse('checklists:progress_institute') + f'?template={self.version.template_id}',
        )
        self.assertContains(filtered, 'Safety Inst')
        self.assertContains(filtered, 'Open Filter')
        self.assertNotContains(filtered, 'Other Filter')


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

    def test_assign_uses_dual_list_and_per_template_link(self):
        template = ChecklistTemplate.objects.create(slug='asg', name_en='Assign Me', name_de='Zuweisen')
        published = ChecklistTemplateVersion.objects.create(
            template=template, version_number=1, status=ChecklistTemplateVersion.Status.PUBLISHED,
        )
        employee = Employee.objects.create(
            employee_number='CL-ASG-1', first_name='Pat', last_name='Assignee',
        )
        listing = self.client.get(reverse('checklists:manage_template_list'))
        self.assertContains(listing, reverse('checklists:manage_template_assign', args=[template.pk]))
        url = reverse('checklists:manage_template_assign', args=[template.pk])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Not selected')
        self.assertContains(page, 'Selected')
        self.assertContains(page, 'dual-list-widget')
        self.assertContains(page, published.version_label)
        self.assertNotContains(page, 'name="employees" required')
        self.assertNotContains(page, "name='employees' required")
        posted = self.client.post(url, {
            'template_version': str(published.pk),
            'employees': [str(employee.pk)],
        })
        self.assertEqual(posted.status_code, 302)
        self.assertTrue(
            ChecklistInstance.objects.filter(subject=employee, template_version=published).exists()
        )
        again = self.client.get(url)
        self.assertEqual(again.status_code, 200)
        self.assertRegex(
            again.content.decode(),
            rf'value="{employee.pk}"[^>]*selected|selected[^>]*value="{employee.pk}"',
        )
        self.client.post(url, {
            'template_version': str(published.pk),
            'employees': [str(employee.pk)],
        })
        self.assertEqual(
            ChecklistInstance.objects.filter(subject=employee, template_version=published).count(),
            1,
        )

    def test_assign_requires_published_version(self):
        template = ChecklistTemplate.objects.create(slug='draft-only', name_en='Draft', name_de='Entwurf')
        ChecklistTemplateVersion.objects.create(
            template=template, version_number=1, status=ChecklistTemplateVersion.Status.DRAFT,
        )
        response = self.client.get(reverse('checklists:manage_template_assign', args=[template.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('checklists:manage_template_detail', args=[template.pk]))

    def test_version_edit_shows_inline_settings_and_copy(self):
        template = ChecklistTemplate.objects.create(slug='ed1', name_en='Ed', name_de='Ed')
        version = ChecklistTemplateVersion.objects.create(
            template=template, version_number=1, status=ChecklistTemplateVersion.Status.DRAFT,
        )
        section = ChecklistTemplateNode.objects.create(
            version=version,
            node_kind=ChecklistTemplateNode.NodeKind.SECTION,
            label_en='Section A',
            sort_order=0,
        )
        ChecklistTemplateNode.objects.create(
            version=version,
            parent=section,
            node_kind=ChecklistTemplateNode.NodeKind.FIELD,
            field_type=ChecklistTemplateNode.FieldType.CHECKBOX,
            label_en='Item',
            sort_order=0,
        )
        url = reverse('checklists:manage_version_edit', args=[template.pk, version.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Node settings')
        self.assertContains(response, 'Add node')
        self.assertContains(response, 'Copy')
        self.assertContains(response, 'checklist-nodes-section')
        self.assertContains(response, 'checklist-nodes-section-header')
        self.assertContains(response, 'Section A')
        self.assertContains(response, 'Item')
        self.assertNotContains(response, f'/nodes/{section.pk}/edit/')
        selected = self.client.get(url + f'?node={section.pk}')
        self.assertEqual(selected.status_code, 200)
        self.assertContains(selected, 'Section A')
        copied = self.client.post(url, {'action': 'copy_node', 'node_pk': str(section.pk)})
        self.assertEqual(copied.status_code, 302)
        self.assertEqual(version.nodes.filter(node_kind='section').count(), 2)
        self.assertEqual(version.nodes.filter(node_kind='field').count(), 2)
        copied_section = version.nodes.filter(node_kind='section').exclude(pk=section.pk).get()
        self.assertEqual(copied_section.parent_id, section.parent_id)
        self.assertGreater(copied_section.sort_order, section.sort_order)
        self.assertTrue(version.nodes.filter(parent=copied_section, node_kind='field').exists())
        self.assertContains(selected, 'dual-list-widget')
        self.assertContains(selected, 'Editable by Django groups')
        self.assertContains(response, 'checklist-node-select')

    def test_add_node_defaults_visible_to_subject(self):
        template = ChecklistTemplate.objects.create(slug='vis', name_en='Vis', name_de='Vis')
        version = ChecklistTemplateVersion.objects.create(
            template=template, version_number=1, status=ChecklistTemplateVersion.Status.DRAFT,
        )
        section = ChecklistTemplateNode.objects.create(
            version=version, node_kind=ChecklistTemplateNode.NodeKind.SECTION, label_en='S',
        )
        url = reverse('checklists:manage_version_edit', args=[template.pk, version.pk])
        response = self.client.post(url, {
            'action': 'add_node',
            'node_kind': ChecklistTemplateNode.NodeKind.FIELD,
            'field_type': ChecklistTemplateNode.FieldType.CHECKBOX,
            'parent': str(section.pk),
            'sort_order': 1,
            'label_en': 'Seen',
            'label_de': 'Sichtbar',
        })
        self.assertEqual(response.status_code, 302)
        node = version.nodes.get(label_en='Seen')
        self.assertTrue(node.visible_to_subject)
        self.assertTrue(node.editable_by_subject)
        self.assertTrue(node.editable_by_coordinators)

    def test_bulk_edit_shared_field_settings(self):
        template = ChecklistTemplate.objects.create(slug='bulk', name_en='Bulk', name_de='Bulk')
        version = ChecklistTemplateVersion.objects.create(
            template=template, version_number=1, status=ChecklistTemplateVersion.Status.DRAFT,
        )
        section = ChecklistTemplateNode.objects.create(
            version=version, node_kind=ChecklistTemplateNode.NodeKind.SECTION, label_en='S',
        )
        a = ChecklistTemplateNode.objects.create(
            version=version, parent=section, node_kind=ChecklistTemplateNode.NodeKind.FIELD,
            field_type=ChecklistTemplateNode.FieldType.CHECKBOX, label_en='A',
            required_for_completion=False, visible_to_subject=True,
        )
        b = ChecklistTemplateNode.objects.create(
            version=version, parent=section, node_kind=ChecklistTemplateNode.NodeKind.FIELD,
            field_type=ChecklistTemplateNode.FieldType.CHECKBOX, label_en='B',
            required_for_completion=False, visible_to_subject=True,
        )
        url = reverse('checklists:manage_version_edit', args=[template.pk, version.pk])
        page = self.client.get(url + f'?nodes={a.pk},{b.pk}')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Edit 2 nodes')
        self.assertContains(page, 'Required for completion')
        posted = self.client.post(url + f'?nodes={a.pk},{b.pk}', {
            'action': 'save_bulk',
            'node_pks': [str(a.pk), str(b.pk)],
            'required_for_completion': '1',
            'allow_not_applicable': '__unchanged__',
            'editable_by_subject': '__unchanged__',
            'editable_by_coordinators': '__unchanged__',
            'visible_to_subject': '0',
            'parent': '__unchanged__',
        })
        self.assertEqual(posted.status_code, 302)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertTrue(a.required_for_completion)
        self.assertTrue(b.required_for_completion)
        self.assertFalse(a.visible_to_subject)
        self.assertFalse(b.visible_to_subject)

    def test_version_edit_nests_section_cards(self):
        template = ChecklistTemplate.objects.create(slug='nest', name_en='Nest', name_de='Nest')
        version = ChecklistTemplateVersion.objects.create(
            template=template, version_number=1, status=ChecklistTemplateVersion.Status.DRAFT,
        )
        outer = ChecklistTemplateNode.objects.create(
            version=version,
            node_kind=ChecklistTemplateNode.NodeKind.SECTION,
            label_en='Outer',
            sort_order=0,
        )
        ChecklistTemplateNode.objects.create(
            version=version,
            parent=outer,
            node_kind=ChecklistTemplateNode.NodeKind.SECTION,
            label_en='Inner',
            sort_order=0,
        )
        ChecklistTemplateNode.objects.create(
            version=version,
            parent=outer,
            node_kind=ChecklistTemplateNode.NodeKind.FIELD,
            field_type=ChecklistTemplateNode.FieldType.CHECKBOX,
            label_en='Outer item',
            sort_order=1,
        )
        url = reverse('checklists:manage_version_edit', args=[template.pk, version.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('checklist-nodes-section', content)
        self.assertIn('Outer', content)
        self.assertIn('Inner', content)
        self.assertIn('Outer item', content)
        outer_header = content.index('checklist-nodes-section-header')
        inner_pos = content.index('Inner')
        self.assertLess(outer_header, inner_pos)

    def test_copy_template_uses_latest_version(self):
        template = ChecklistTemplate.objects.create(
            slug='src', name_en='Source', name_de='Quelle',
        )
        v1 = ChecklistTemplateVersion.objects.create(
            template=template, version_number=1, status=ChecklistTemplateVersion.Status.PUBLISHED,
        )
        ChecklistTemplateNode.objects.create(
            version=v1, node_kind=ChecklistTemplateNode.NodeKind.SECTION, label_en='Old',
        )
        v2 = ChecklistTemplateVersion.objects.create(
            template=template, version_number=2, status=ChecklistTemplateVersion.Status.DRAFT,
        )
        ChecklistTemplateNode.objects.create(
            version=v2, node_kind=ChecklistTemplateNode.NodeKind.SECTION, label_en='Latest',
        )
        url = reverse('checklists:manage_template_copy', args=[template.pk])
        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, 'src-copy')
        response = self.client.post(url, {
            'slug': 'src-copy',
            'name_en': 'Source copy',
            'name_de': 'Quelle Kopie',
            'description_en': '',
            'description_de': '',
        })
        self.assertEqual(response.status_code, 302)
        copied = ChecklistTemplate.objects.get(slug='src-copy')
        draft = copied.versions.get()
        self.assertEqual(draft.version_number, 1)
        self.assertEqual(draft.status, ChecklistTemplateVersion.Status.DRAFT)
        self.assertTrue(draft.nodes.filter(label_en='Latest').exists())
        self.assertFalse(draft.nodes.filter(label_en='Old').exists())
        self.assertContains(get_response, 'Copies the latest version')


class ChecklistEditAccessTests(TestCase):
    def setUp(self):
        self.manager = _user('mgr-acc')
        self.subject_user = _user('subj-acc')
        self.subject = Employee.objects.create(
            employee_number='CL-ACC-1',
            first_name='Subj',
            last_name='Acc',
            user=self.subject_user,
        )
        self.template = ChecklistTemplate.objects.create(
            slug='acc', name_en='Access', name_de='Zugriff',
        )
        self.version = ChecklistTemplateVersion.objects.create(
            template=self.template,
            version_number=1,
            status=ChecklistTemplateVersion.Status.DRAFT,
            created_by=self.manager,
        )
        self.field = ChecklistTemplateNode.objects.create(
            version=self.version,
            node_kind=ChecklistTemplateNode.NodeKind.FIELD,
            field_type=ChecklistTemplateNode.FieldType.CHECKBOX,
            label_en='Group item',
            editable_by_subject=False,
            editable_by_coordinators=False,
            sort_order=0,
        )
        self.group = Group.objects.create(name='Checklist Editors')
        self.field.editable_by_groups.add(self.group)
        publish_version(self.version, self.manager)
        self.instance = assign_instance(self.subject, self.version, assigned_by=self.manager)

    def test_django_group_can_edit_node(self):
        editor = _user('group-editor')
        editor.groups.add(self.group)
        self.assertTrue(user_can_edit_node(editor, self.instance, self.field))
        self.assertTrue(user_can_fill_instance(editor, self.instance))
        outsider = _user('outsider')
        self.assertFalse(user_can_edit_node(outsider, self.instance, self.field))
        self.assertFalse(user_can_fill_instance(outsider, self.instance))
        self.assertFalse(user_can_edit_node(self.subject_user, self.instance, self.field))

    def test_group_member_can_open_fill(self):
        editor = _user('group-fill')
        editor.groups.add(self.group)
        self.client.login(username='group-fill', password='test')
        response = self.client.get(reverse('checklists:instance_fill', args=[self.instance.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Group item')
        self.assertContains(response, 'Done / Erledigt')

    def test_copy_template_preserves_groups(self):
        new_template, new_version = copy_template_latest_version(
            self.template,
            self.manager,
            slug='acc-copy',
            name_en='Access copy',
            name_de='Zugriff Kopie',
        )
        copied_field = new_version.nodes.get(label_en='Group item')
        self.assertEqual(
            set(copied_field.editable_by_groups.values_list('pk', flat=True)),
            {self.group.pk},
        )


class ChecklistHtmlNodeTests(TestCase):
    def test_radio_option_displays_choice_key_fallback(self):
        radio_field = ChecklistTemplateNode.objects.create(
            version=self.version,
            node_kind=ChecklistTemplateNode.NodeKind.FIELD,
            field_type=ChecklistTemplateNode.FieldType.RADIO_GROUP,
            label_en='Choose',
            sort_order=0,
        )
        ChecklistTemplateNode.objects.create(
            version=self.version,
            parent=radio_field,
            node_kind=ChecklistTemplateNode.NodeKind.RADIO_OPTION,
            choice_key='option_a',
            sort_order=0,
        )
        publish_version(self.version, self.manager)
        instance = assign_instance(self.subject, self.version, assigned_by=self.manager)
        self.client.login(username='subj-html', password='test')
        response = self.client.get(reverse('checklists:instance_fill', args=[instance.pk]))
        self.assertContains(response, 'option_a')

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

    def test_instance_fill_uses_standard_layout(self):
        ChecklistTemplateNode.objects.create(
            version=self.version,
            parent=self.section,
            node_kind=ChecklistTemplateNode.NodeKind.FIELD,
            field_type=ChecklistTemplateNode.FieldType.CHECKBOX,
            label_en='Confirm',
            sort_order=1,
        )
        publish_version(self.version, self.manager)
        instance = assign_instance(self.subject, self.version, assigned_by=self.manager)
        self.client.login(username='subj-html', password='test')
        response = self.client.get(reverse('checklists:instance_fill', args=[instance.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aligned-field')
        self.assertContains(response, 'form-actions')
        self.assertContains(response, 'card checklist-section')
        self.assertContains(response, 'checklist-section-title')
        self.assertContains(response, 'checklist-field')
        self.assertContains(response, 'checklist-field-label')
        self.assertContains(response, 'form-check-row')
        self.assertContains(response, 'Done / Erledigt')

    def test_section_groups_heading_and_fields_in_one_card(self):
        ChecklistTemplateNode.objects.create(
            version=self.version,
            parent=self.section,
            node_kind=ChecklistTemplateNode.NodeKind.HTML,
            label_en='Instructions',
            help_en='<p>Read this first</p>',
            sort_order=1,
        )
        ChecklistTemplateNode.objects.create(
            version=self.version,
            parent=self.section,
            node_kind=ChecklistTemplateNode.NodeKind.FIELD,
            field_type=ChecklistTemplateNode.FieldType.CHECKBOX,
            label_en='Confirm',
            sort_order=2,
        )
        publish_version(self.version, self.manager)
        instance = assign_instance(self.subject, self.version, assigned_by=self.manager)
        self.client.login(username='subj-html', password='test')
        response = self.client.get(reverse('checklists:instance_fill', args=[instance.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'card checklist-section', count=1)
        self.assertNotContains(response, 'form-section checklist-section')
        self.assertNotContains(response, 'form-section checklist-html-block')
        content = response.content.decode()
        section_pos = content.index('card checklist-section')
        title_pos = content.index('checklist-section-title', section_pos)
        html_pos = content.index('checklist-html-block', title_pos)
        field_pos = content.index('aligned-field', html_pos)
        self.assertLess(title_pos, html_pos)
        self.assertLess(html_pos, field_pos)
        self.assertIn('Confirm', content[field_pos:field_pos + 500])

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

class ChecklistPreviewTests(TestCase):
    def setUp(self):
        self.manager = _user('mgr-prev')
        group, _ = Group.objects.get_or_create(name='Checklists - Manage')
        ct = ContentType.objects.get_for_model(ChecklistTemplate)
        perm = Permission.objects.get(codename='manage_checklist', content_type=ct)
        group.permissions.add(perm)
        self.manager.groups.add(group)
        self.client.login(username='mgr-prev', password='test')
        self.template = ChecklistTemplate.objects.create(slug='preview-test', name_en='Preview Test', name_de='Vorschau Test')
        self.draft = ChecklistTemplateVersion.objects.create(template=self.template, version_number=1, status=ChecklistTemplateVersion.Status.DRAFT, created_by=self.manager)
        self.section = ChecklistTemplateNode.objects.create(version=self.draft, node_kind=ChecklistTemplateNode.NodeKind.SECTION, label_en='Steps', sort_order=0)
        ChecklistTemplateNode.objects.create(version=self.draft, parent=self.section, node_kind=ChecklistTemplateNode.NodeKind.FIELD, field_type=ChecklistTemplateNode.FieldType.CHECKBOX, label_en='Acknowledge', required_for_completion=True, sort_order=1)

    def test_preview_requires_draft(self):
        published = ChecklistTemplateVersion.objects.create(template=self.template, version_number=2, status=ChecklistTemplateVersion.Status.PUBLISHED)
        url = reverse('checklists:manage_version_preview', args=[self.template.pk, published.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_preview_renders_checklist_layout(self):
        url = reverse('checklists:manage_version_preview', args=[self.template.pk, self.draft.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Preview')
        self.assertContains(response, 'Acknowledge')
        self.assertContains(response, 'disabled')


    def test_section_name_required_and_used_as_parent_label(self):
        template = ChecklistTemplate.objects.create(slug='named', name_en='Named', name_de='Named')
        version = ChecklistTemplateVersion.objects.create(
            template=template, version_number=1, status=ChecklistTemplateVersion.Status.DRAFT,
        )
        url = reverse('checklists:manage_version_edit', args=[template.pk, version.pk])
        empty = self.client.post(url, {
            'action': 'add_node',
            'node_kind': ChecklistTemplateNode.NodeKind.SECTION,
            'parent': '',
            'sort_order': 0,
            'label_en': '',
            'label_de': '',
            'field_type': '',
            'choice_key': '',
        })
        self.assertEqual(empty.status_code, 200)
        self.assertContains(empty, 'Name (EN or DE) is required for sections.')
        self.assertFalse(version.nodes.exists())

        created = self.client.post(url, {
            'action': 'add_node',
            'node_kind': ChecklistTemplateNode.NodeKind.SECTION,
            'parent': '',
            'sort_order': 0,
            'label_en': 'Onboarding',
            'label_de': 'Einarbeitung',
            'field_type': '',
            'choice_key': '',
        })
        self.assertEqual(created.status_code, 302)
        section = version.nodes.get(node_kind='section')
        self.assertEqual(section.display_name, 'Onboarding')
        nested = ChecklistTemplateNode.objects.create(
            version=version,
            parent=section,
            node_kind=ChecklistTemplateNode.NodeKind.SECTION,
            label_en='Documents',
            sort_order=1,
        )
        self.assertEqual(nested.parent_choice_label, 'Onboarding / Documents')
        page = self.client.get(url)
        self.assertContains(page, 'Onboarding')
        self.assertContains(page, 'Onboarding / Documents')
        self.assertContains(page, 'Name (EN)')
        self.assertNotContains(page, f'Section {section.pk}')

    def test_version_edit_parent_choices_include_radio_group(self):
        radio_field = ChecklistTemplateNode.objects.create(
            version=self.draft,
            parent=self.section,
            node_kind=ChecklistTemplateNode.NodeKind.FIELD,
            field_type=ChecklistTemplateNode.FieldType.RADIO_GROUP,
            label_en='Pick one',
            sort_order=2,
        )
        ChecklistTemplateNode.objects.create(
            version=self.draft,
            parent=radio_field,
            node_kind=ChecklistTemplateNode.NodeKind.RADIO_OPTION,
            choice_key='a',
            label_en='Option A',
            sort_order=0,
        )
        url = reverse('checklists:manage_version_edit', args=[self.template.pk, self.draft.pk])
        response = self.client.get(url)
        self.assertContains(response, 'CHECKLIST_PARENT_CHOICES')
        self.assertContains(response, 'Pick one')
        self.assertContains(response, 'radio_option')


    def test_manage_forms_use_standard_layout(self):
        url = reverse('checklists:manage_version_edit', args=[self.template.pk, self.draft.pk])
        response = self.client.get(url)
        self.assertContains(response, 'aligned-field')
        self.assertContains(response, 'form-actions')
        self.assertContains(response, 'form-section')

    def test_preview_button_on_version_edit(self):
        url = reverse('checklists:manage_version_edit', args=[self.template.pk, self.draft.pk])
        self.assertContains(self.client.get(url), 'Preview')


class YourChecklistsEditorTests(TestCase):
    def setUp(self):
        self.subject_user = _user('cl-subject')
        self.subject = Employee.objects.create(
            employee_number='CL-SUB',
            first_name='Sam',
            last_name='Subject',
            user=self.subject_user,
        )
        self.editor_user = _user('cl-editor')
        self.editor = Employee.objects.create(
            employee_number='CL-ED',
            first_name='Eve',
            last_name='Editor',
            user=self.editor_user,
        )
        self.template = ChecklistTemplate.objects.create(
            slug='kit',
            name_en='Kit checklist',
            name_de='Kit-Checkliste',
        )
        self.version = ChecklistTemplateVersion.objects.create(
            template=self.template,
            version_number=1,
            status=ChecklistTemplateVersion.Status.DRAFT,
        )
        self.field = ChecklistTemplateNode.objects.create(
            version=self.version,
            node_kind=ChecklistTemplateNode.NodeKind.FIELD,
            field_type=ChecklistTemplateNode.FieldType.CHECKBOX,
            label_en='Kit received',
            required_for_completion=True,
            editable_by_subject=False,
            editable_by_coordinators=False,
        )
        self.field.editable_by_employees.add(self.editor)
        publish_version(self.version, self.editor_user)
        self.version.refresh_from_db()
        self.instance = assign_instance(self.subject, self.version, assigned_by=self.editor_user)

    def test_editor_sees_subject_grouped_list(self):
        self.client.login(username='cl-editor', password='test')
        response = self.client.get(reverse('checklists:my_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your Checklists')
        self.assertContains(response, 'Assigned to you')
        self.assertContains(response, 'You can edit')
        self.assertContains(response, 'Sam Subject')
        self.assertContains(response, 'Kit checklist')
        self.assertTrue(instances_editable_by_user(self.editor_user).filter(pk=self.instance.pk).exists())

    def test_menu_dot_for_unseen_editor_checklist(self):
        self.assertTrue(checklists_menu_needs_attention(self.editor_user))
        self.client.login(username='cl-editor', password='test')
        self.client.get(reverse('checklists:instance_fill', args=[self.instance.pk]))
        self.assertFalse(checklists_menu_needs_attention(self.editor_user))

    def test_archives_when_editor_fields_are_filled(self):
        other = _user('cl-other')
        other_emp = Employee.objects.create(
            employee_number='CL-OT',
            first_name='Ollie',
            last_name='Other',
            user=other,
        )
        self.field.editable_by_employees.add(other_emp)
        save_field_response(
            other,
            self.instance,
            self.field,
            data={'value_bool': True},
        )
        self.assertTrue(editor_work_complete(self.editor_user, self.instance))
        self.client.login(username='cl-editor', password='test')
        response = self.client.get(reverse('checklists:my_list'))
        self.assertContains(response, 'No checklists for others are waiting')
        self.assertTrue(
            ChecklistEditorArchive.objects.filter(
                user=self.editor_user, instance=self.instance,
            ).exists()
        )
        archive = self.client.get(reverse('checklists:my_list') + '?editor_archive=1')
        self.assertContains(archive, 'Kit checklist')

    def test_group_edit_rights_include_instance(self):
        group = Group.objects.create(name='CL Editors')
        self.editor_user.groups.add(group)
        self.field.editable_by_employees.clear()
        self.field.editable_by_groups.add(group)
        self.assertTrue(user_can_edit_node(self.editor_user, self.instance, self.field))
        self.assertTrue(instances_editable_by_user(self.editor_user).filter(pk=self.instance.pk).exists())

    def test_coordinator_sees_editable_by_coordinators_instances(self):
        coord = _user('cl-coord')
        Employee.objects.create(
            employee_number='CL-CO',
            first_name='Cora',
            last_name='Coord',
            user=coord,
        )
        group, _ = Group.objects.get_or_create(name='Checklists - Manage')
        ct = ContentType.objects.get_for_model(ChecklistTemplate)
        perm = Permission.objects.get(codename='manage_checklist', content_type=ct)
        group.permissions.add(perm)
        coord.groups.add(group)
        self.field.editable_by_employees.clear()
        self.field.editable_by_coordinators = True
        self.field.save(update_fields=['editable_by_coordinators'])
        self.assertTrue(instances_editable_by_user(coord).filter(pk=self.instance.pk).exists())
        self.client.login(username='cl-coord', password='test')
        response = self.client.get(reverse('checklists:my_list'))
        self.assertContains(response, 'Sam Subject')
        self.assertContains(response, 'Kit checklist')

    def test_fill_greys_fields_editor_cannot_edit(self):
        subject_only = ChecklistTemplateNode.objects.create(
            version=self.version,
            node_kind=ChecklistTemplateNode.NodeKind.FIELD,
            field_type=ChecklistTemplateNode.FieldType.TEXT,
            label_en='Subject notes',
            required_for_completion=False,
            editable_by_subject=True,
            editable_by_coordinators=False,
            sort_order=2,
        )
        self.client.login(username='cl-editor', password='test')
        response = self.client.get(reverse('checklists:instance_fill', args=[self.instance.pk]))
        self.assertContains(response, 'checklist-field-readonly')
        self.assertContains(response, 'Subject notes')
        self.assertContains(response, f'name="field_{self.field.pk}"')
        self.assertNotContains(response, f'name="field_{subject_only.pk}"')

    def test_editor_save_archives_when_own_fields_complete(self):
        self.client.login(username='cl-editor', password='test')
        response = self.client.post(
            reverse('checklists:instance_fill', args=[self.instance.pk]),
            {f'field_{self.field.pk}': 'on'},
        )
        self.assertRedirects(response, reverse('checklists:my_list'))
        self.assertTrue(
            ChecklistEditorArchive.objects.filter(
                user=self.editor_user, instance=self.instance,
            ).exists()
        )

