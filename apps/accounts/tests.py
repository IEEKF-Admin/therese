from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.test import TestCase

from apps.accounts.login_popups import (
    acknowledge_popup,
    evaluate_login_popups,
    user_matches_audience,
)
from apps.accounts.models import CustomUser, LoginPopupAcknowledgement, LoginPopupConfig
from apps.hr.models import Contract, Employee, Workgroup


class LoginPopupAudienceTests(TestCase):
    def setUp(self):
        self.user_a = CustomUser.objects.create_user('user_a', password='test')
        self.user_b = CustomUser.objects.create_user('user_b', password='test')
        self.group = Group.objects.create(name='Test Group')
        self.user_a.groups.add(self.group)

        self.employee_a = Employee.objects.create(
            employee_number='E-100',
            first_name='Anna',
            last_name='Alpha',
            user=self.user_a,
        )
        self.pi = Employee.objects.create(
            employee_number='E-PI',
            first_name='PI',
            last_name='Leader',
        )
        self.workgroup = Workgroup.objects.create(
            short_name='WG-1',
            long_name='Work Group One',
            pi=self.pi,
        )
        self.workgroup.members.add(self.employee_a)

        self.config = LoginPopupConfig.objects.create(
            name='Targeted welcome',
            trigger='first_login',
            text='Hello',
            enabled=True,
        )

    def test_empty_audience_matches_everyone(self):
        self.assertTrue(user_matches_audience(self.user_a, self.config))
        self.assertTrue(user_matches_audience(self.user_b, self.config))

    def test_target_user_restricts_audience(self):
        self.config.target_users.add(self.user_a)
        self.assertTrue(user_matches_audience(self.user_a, self.config))
        self.assertFalse(user_matches_audience(self.user_b, self.config))

    def test_target_group_matches_group_member(self):
        self.config.target_groups.add(self.group)
        self.assertTrue(user_matches_audience(self.user_a, self.config))
        self.assertFalse(user_matches_audience(self.user_b, self.config))

    def test_target_workgroup_matches_member(self):
        self.config.target_workgroups.add(self.workgroup)
        self.assertTrue(user_matches_audience(self.user_a, self.config))
        self.assertFalse(user_matches_audience(self.user_b, self.config))

    def test_or_mode_matches_any_criterion(self):
        self.config.audience_match_mode = 'or'
        self.config.save()
        self.config.target_users.add(self.user_b)
        self.config.target_groups.add(self.group)
        self.assertTrue(user_matches_audience(self.user_a, self.config))
        self.assertTrue(user_matches_audience(self.user_b, self.config))

    def test_and_mode_requires_all_criteria(self):
        self.config.audience_match_mode = 'and'
        self.config.save()
        self.config.target_users.add(self.user_a)
        self.config.target_groups.add(self.group)
        self.assertTrue(user_matches_audience(self.user_a, self.config))

        self.user_a.groups.clear()
        self.assertFalse(user_matches_audience(self.user_a, self.config))

    def test_and_mode_user_and_workgroup(self):
        self.config.audience_match_mode = 'and'
        self.config.save()
        self.config.target_users.add(self.user_a)
        self.config.target_workgroups.add(self.workgroup)
        self.assertTrue(user_matches_audience(self.user_a, self.config))

        self.workgroup.members.remove(self.employee_a)
        self.assertFalse(user_matches_audience(self.user_a, self.config))


class LoginPopupContractTriggerTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user('contract_user', password='test')
        self.employee = Employee.objects.create(
            employee_number='E-200',
            first_name='Ben',
            last_name='Beta',
            user=self.user,
        )
        self.config = LoginPopupConfig.objects.create(
            name='Own contract ending',
            trigger='contract_ending_soon',
            text='Contract ends {{ contract_end }}',
            x_months=6,
            enabled=True,
        )

    def _add_contract(self, valid_until):
        return Contract.objects.create(
            employee=self.employee,
            pay_scale_group='E13',
            experience_level=3,
            weekly_hours=Decimal('39.00'),
            valid_from=date.today() - timedelta(days=365),
            valid_until=valid_until,
        )

    def test_contract_popup_shows_for_unacknowledged_contract(self):
        end_date = date.today() + timedelta(days=60)
        self._add_contract(end_date)

        popups = evaluate_login_popups(self.user, employee=self.employee)
        self.assertEqual(len(popups), 1)
        self.assertIn(end_date.strftime('%d.%m.%Y'), popups[0]['text'])

    def test_acknowledged_contract_does_not_show_again(self):
        end_date = date.today() + timedelta(days=60)
        contract = self._add_contract(end_date)
        acknowledge_popup(
            self.user,
            self.config,
            [LoginPopupAcknowledgement.contract_reference(contract)],
        )

        popups = evaluate_login_popups(self.user, employee=self.employee)
        self.assertEqual(len(popups), 0)

    def test_new_contract_triggers_popup_again(self):
        old_end = date.today() + timedelta(days=30)
        old_contract = self._add_contract(old_end)
        acknowledge_popup(
            self.user,
            self.config,
            [LoginPopupAcknowledgement.contract_reference(old_contract)],
        )

        new_end = date.today() + timedelta(days=90)
        self._add_contract(new_end)

        popups = evaluate_login_popups(self.user, employee=self.employee)
        self.assertEqual(len(popups), 1)
        self.assertIn(new_end.strftime('%d.%m.%Y'), popups[0]['text'])