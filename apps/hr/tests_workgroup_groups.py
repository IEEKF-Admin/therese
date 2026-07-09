from django.contrib.auth.models import Group
from django.test import TestCase

from apps.accounts.models import CustomUser
from apps.finances.models import WBSElement
from apps.hr.forms import WorkgroupForm
from apps.hr.models import Employee, Workgroup
from apps.hr.workgroup_access import filter_by_user_workgroups
from apps.hr.workgroup_groups import sync_auth_group_for_workgroup


class WorkgroupGroupSyncTests(TestCase):
    def setUp(self):
        self.pi = Employee.objects.create(
            employee_number='E-WG-PI',
            first_name='Pat',
            last_name='Principal',
        )

    def test_create_workgroup_creates_django_group(self):
        workgroup = Workgroup.objects.create(
            short_name='AI-Lab',
            long_name='Artificial Intelligence Lab',
            pi=self.pi,
        )
        sync_auth_group_for_workgroup(workgroup)
        workgroup.refresh_from_db()
        self.assertTrue(Group.objects.filter(name='AI-Lab').exists())
        self.assertEqual(workgroup.auth_group.name, 'AI-Lab')

    def test_rename_workgroup_renames_django_group(self):
        workgroup = Workgroup.objects.create(
            short_name='Old-Lab',
            long_name='Old Lab',
            pi=self.pi,
        )
        sync_auth_group_for_workgroup(workgroup)
        workgroup.short_name = 'New-Lab'
        workgroup.save()
        sync_auth_group_for_workgroup(workgroup, old_short_name='Old-Lab')
        workgroup.refresh_from_db()
        self.assertFalse(Group.objects.filter(name='Old-Lab').exists())
        self.assertTrue(Group.objects.filter(name='New-Lab').exists())

    def test_delete_workgroup_keeps_django_group(self):
        workgroup = Workgroup.objects.create(
            short_name='Keep-Group',
            long_name='Keep Group',
            pi=self.pi,
        )
        sync_auth_group_for_workgroup(workgroup)
        group_id = workgroup.auth_group_id
        workgroup.delete()
        self.assertTrue(Group.objects.filter(pk=group_id).exists())

    def test_workgroup_form_syncs_group_on_save(self):
        form = WorkgroupForm(data={
            'short_name': 'Form-Lab',
            'long_name': 'Form Lab',
            'pi': self.pi.pk,
            'members': [],
        })
        self.assertTrue(form.is_valid(), form.errors)
        workgroup = form.save()
        self.assertEqual(workgroup.auth_group.name, 'Form-Lab')


class WorkgroupPspAccessTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user('psp-user', password='test')
        self.employee = Employee.objects.create(
            employee_number='E-WG-1',
            first_name='Member',
            last_name='One',
            user=self.user,
        )
        self.pi = Employee.objects.create(
            employee_number='E-WG-PI2',
            first_name='PI',
            last_name='Leader',
        )
        self.workgroup_a = Workgroup.objects.create(
            short_name='Lab-A',
            long_name='Lab A',
            pi=self.pi,
        )
        self.workgroup_b = Workgroup.objects.create(
            short_name='Lab-B',
            long_name='Lab B',
            pi=self.pi,
        )
        self.workgroup_a.members.add(self.employee)
        self.wbs_a = WBSElement.objects.create(wbs_code='WBS-A', title='A', work_group=self.workgroup_a)
        self.wbs_b = WBSElement.objects.create(wbs_code='WBS-B', title='B', work_group=self.workgroup_b)

    def test_user_sees_only_own_workgroup_psp_elements(self):
        visible = filter_by_user_workgroups(WBSElement.objects.all(), self.user)
        self.assertEqual(list(visible), [self.wbs_a])