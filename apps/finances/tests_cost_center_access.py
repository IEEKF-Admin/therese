"""Workgroup-scoped vs institute-wide cost center access."""

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory, TestCase

from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames, assign_permissions_to_groups
from apps.finances.cost_center_access import (
    filter_cost_centers_for_user,
    user_can_manage_cost_center_object,
)
from apps.finances.models import CostCenter
from apps.finances.views.cost_center_crud import CostCenterListView
from apps.hr.models import Employee, Workgroup
from django.contrib.auth.models import Group


def _grant(user, *codenames):
    ct = ContentType.objects.get_for_model(CostCenter)
    for code in codenames:
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename=code))


class CostCenterAccessHelperTests(TestCase):
    def setUp(self):
        self.pi = Employee.objects.create(
            employee_number='CC-PI', first_name='P', last_name='I',
        )
        self.wg_a = Workgroup.objects.create(short_name='CA', long_name='A', pi=self.pi)
        self.wg_b = Workgroup.objects.create(short_name='CB', long_name='B', pi=self.pi)

        self.user = CustomUser.objects.create_user('cc-scoped', password='test')
        self.emp = Employee.objects.create(
            employee_number='CC-U', first_name='U', last_name='S', user=self.user,
        )
        self.wg_a.members.add(self.emp)
        _grant(self.user, 'manage_cost_center')

        self.global_user = CustomUser.objects.create_user('cc-global', password='test')
        _grant(self.global_user, 'manage_all_cost_centers')

        self.cc_a = CostCenter.objects.create(cost_center='CC-A', work_group=self.wg_a)
        self.cc_b = CostCenter.objects.create(cost_center='CC-B', work_group=self.wg_b)
        self.cc_orphan = CostCenter.objects.create(cost_center='CC-X', work_group=None)

    def test_scoped_hides_other_and_orphan(self):
        qs = filter_cost_centers_for_user(CostCenter.objects.all(), self.user)
        pks = set(qs.values_list('pk', flat=True))
        self.assertIn(self.cc_a.pk, pks)
        self.assertNotIn(self.cc_b.pk, pks)
        self.assertNotIn(self.cc_orphan.pk, pks)
        self.assertFalse(user_can_manage_cost_center_object(self.user, self.cc_orphan))

    def test_all_sees_orphan_and_other_groups(self):
        qs = filter_cost_centers_for_user(CostCenter.objects.all(), self.global_user)
        pks = set(qs.values_list('pk', flat=True))
        self.assertEqual(pks, {self.cc_a.pk, self.cc_b.pk, self.cc_orphan.pk})
        self.assertTrue(user_can_manage_cost_center_object(self.global_user, self.cc_orphan))


class CostCenterManageAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        assign_permissions_to_groups()

    def setUp(self):
        self.pi = Employee.objects.create(
            employee_number='E-CC-PI',
            first_name='Pat',
            last_name='Principal',
        )
        self.workgroup_a = Workgroup.objects.create(
            short_name='CC-Lab-A',
            long_name='Lab A',
            pi=self.pi,
        )
        self.workgroup_b = Workgroup.objects.create(
            short_name='CC-Lab-B',
            long_name='Lab B',
            pi=self.pi,
        )
        self.cc_a = CostCenter.objects.create(
            cost_center='CC-MGR-A',
            work_group=self.workgroup_a,
        )
        self.cc_b = CostCenter.objects.create(
            cost_center='CC-MGR-B',
            work_group=self.workgroup_b,
        )

        self.group_manager = CustomUser.objects.create_user('cc-group-manager', password='test')
        self.group_manager.password_changed = True
        self.group_manager.save(update_fields=['password_changed'])
        self.group_manager.groups.add(Group.objects.get(name=GroupNames.FINANCES_ASSISTANT))
        self.group_employee = Employee.objects.create(
            employee_number='E-CC-MGR',
            first_name='Manager',
            last_name='User',
            user=self.group_manager,
        )
        self.workgroup_a.members.add(self.group_employee)

    def test_group_manager_only_sees_own_workgroup_cost_centers(self):
        factory = RequestFactory()
        request = factory.get('/finances/cost-centers/manage/')
        request.user = self.group_manager

        view = CostCenterListView()
        view.request = request
        queryset = view.get_queryset()
        pks = set(queryset.values_list('pk', flat=True))
        self.assertIn(self.cc_a.pk, pks)
        self.assertNotIn(self.cc_b.pk, pks)
