"""Scoped vs institute-wide PSP access helpers."""

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from apps.accounts.models import CustomUser
from apps.finances.models import CostCenter, WBSElement
from apps.finances.psp_access import filter_psp_for_user, user_can_view_psp
from apps.hr.models import Employee, Workgroup


def _grant(user, *codenames):
    ct = ContentType.objects.get_for_model(WBSElement)
    for code in codenames:
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename=code))


class PSPAccessHelperTests(TestCase):
    def setUp(self):
        self.cc = CostCenter.objects.create(cost_center='CC-PSP-ACC')
        self.pi = Employee.objects.create(
            employee_number='PSP-PI', first_name='P', last_name='I',
        )
        self.wg_a = Workgroup.objects.create(short_name='PA', long_name='A', pi=self.pi)
        self.wg_b = Workgroup.objects.create(short_name='PB', long_name='B', pi=self.pi)

        self.user = CustomUser.objects.create_user('psp-scoped', password='test')
        self.emp = Employee.objects.create(
            employee_number='PSP-U', first_name='U', last_name='S', user=self.user,
        )
        self.wg_a.members.add(self.emp)
        _grant(self.user, 'view_psp_overview')

        self.global_user = CustomUser.objects.create_user('psp-global', password='test')
        _grant(self.global_user, 'view_all_psp_elements')

        self.psp_a = WBSElement.objects.create(
            wbs_code='PA-1', title='A', cost_center=self.cc, work_group=self.wg_a,
        )
        self.psp_b = WBSElement.objects.create(
            wbs_code='PB-1', title='B', cost_center=self.cc, work_group=self.wg_b,
        )
        self.psp_orphan = WBSElement.objects.create(
            wbs_code='PX-1', title='X', cost_center=self.cc, work_group=None,
        )

    def test_scoped_hides_other_and_orphan(self):
        qs = filter_psp_for_user(WBSElement.objects.all(), self.user)
        pks = set(qs.values_list('pk', flat=True))
        self.assertIn(self.psp_a.pk, pks)
        self.assertNotIn(self.psp_b.pk, pks)
        self.assertNotIn(self.psp_orphan.pk, pks)
        self.assertFalse(user_can_view_psp(self.user, self.psp_orphan))

    def test_all_sees_orphan_and_other_groups(self):
        qs = filter_psp_for_user(WBSElement.objects.all(), self.global_user)
        pks = set(qs.values_list('pk', flat=True))
        self.assertEqual(pks, {self.psp_a.pk, self.psp_b.pk, self.psp_orphan.pk})
        self.assertTrue(user_can_view_psp(self.global_user, self.psp_orphan))
