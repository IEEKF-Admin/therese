from decimal import Decimal

from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames, assign_permissions_to_groups, get_or_create_default_groups
from apps.core.models import GlobalSetting


def _ready(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class GlobalSettingsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        self.client = Client()
        self.admin = _ready('sysadmin-gs')
        self.admin.groups.add(Group.objects.get(name=GroupNames.SYSTEMADMIN))
        self.hr = _ready('hr-gs')
        self.hr.groups.add(Group.objects.get(name=GroupNames.HR_SUPERASSISTANT))
        GlobalSetting.objects.update_or_create(
            pk=1,
            defaults={
                'default_weekly_hours': Decimal('39.00'),
                'true_cost_multiplicator': Decimal('1.300'),
                'personnel_import_tolerance': Decimal('0.0250'),
                'irresponsible': False,
                'show_add_employee_on_reallocation': True,
                'chemical_hazard_threshold': 'any_ghs',
            },
        )

    def test_systemadmin_can_view_and_save(self):
        self.client.login(username='sysadmin-gs', password='test')
        url = reverse('core_settings:global_settings')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Global Settings')
        self.assertContains(response, 'System Administration')
        self.assertNotContains(response, 'Document Categories')
        self.assertContains(response, 'Default Weekly Working Hours')
        self.assertContains(response, 'Limitation Reason PDF letterhead')
        self.assertContains(response, 'Account emails')
        self.assertContains(response, 'Chemicals module')
        self.assertContains(response, 'Inventory module')
        self.assertContains(response, 'Request email subject')
        self.assertContains(response, 'Cancellation email subject')
        self.assertContains(response, 'approver_name')
        self.assertContains(response, 'annual_leave')
        posted = self.client.post(url, {
            'action': 'save_general',
            'default_weekly_hours': '40.00',
            'show_add_employee_on_reallocation': 'on',
        })
        self.assertEqual(posted.status_code, 302)
        posted = self.client.post(url, {
            'action': 'save_personnel',
            'true_cost_multiplicator': '1.250',
            'personnel_import_tolerance': '0.0300',
            'employee_expiring_soon_days': '60',
        })
        self.assertEqual(posted.status_code, 302)
        posted = self.client.post(url, {
            'action': 'save_chemicals',
            'chemicals_enabled': 'on',
            'chemical_hazard_threshold': 'signal_danger_only',
        })
        self.assertEqual(posted.status_code, 302)
        setting = GlobalSetting.get_solo()
        self.assertEqual(setting.default_weekly_hours, Decimal('40.00'))
        self.assertEqual(setting.true_cost_multiplicator, Decimal('1.250'))
        self.assertEqual(setting.employee_expiring_soon_days, 60)
        self.assertEqual(setting.chemical_hazard_threshold, 'signal_danger_only')
        self.assertTrue(setting.chemicals_enabled)
        self.assertTrue(setting.show_add_employee_on_reallocation)
        self.assertFalse(setting.irresponsible)

    def test_systemadmin_can_disable_chemicals_module(self):
        self.client.login(username='sysadmin-gs', password='test')
        url = reverse('core_settings:global_settings')
        posted = self.client.post(url, {
            'action': 'save_chemicals',
            'chemical_hazard_threshold': 'any_ghs',
        })
        self.assertEqual(posted.status_code, 302)
        self.assertFalse(GlobalSetting.get_solo().chemicals_enabled)

    def test_save_half_hours_with_localized_entitlement(self):
        from apps.holidays.models import HolidayEntitlementRate
        from apps.holidays.services import ensure_default_rates

        ensure_default_rates()
        self.client.login(username='sysadmin-gs', password='test')
        url = reverse('core_settings:global_settings')
        hours = self.client.post(url, {
            'action': 'save_general',
            'default_weekly_hours': '38.5',
            'show_add_employee_on_reallocation': 'on',
        })
        self.assertEqual(hours.status_code, 302, getattr(hours, 'context', None))
        response = self.client.post(url, {
            'action': 'save_holidays',
            'holidays_enabled': 'on',
            'holiday_half_day_rounding': 'up',
            'form-TOTAL_FORMS': '2',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'entitlement_5_12': '30,0',
            'entitlement_5_11': '27,5',
        })
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None))
        setting = GlobalSetting.get_solo()
        self.assertEqual(setting.default_weekly_hours, Decimal('38.50'))
        rate = HolidayEntitlementRate.objects.get(weekdays=5, contract_months=12)
        self.assertEqual(rate.days, Decimal('30.0'))

    def test_hr_superassistant_sees_workflow_tab_only(self):
        self.client.login(username='hr-gs', password='test')
        url = reverse('core_settings:global_settings')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Task Workflow Coordinators')
        self.assertNotContains(response, 'Default Weekly Working Hours')
        self.assertEqual(
            self.client.post(url, {'action': 'save_general', 'default_weekly_hours': '10'}).status_code,
            403,
        )

    def test_saving_one_tab_does_not_wipe_another(self):
        self.client.login(username='sysadmin-gs', password='test')
        url = reverse('core_settings:global_settings')
        GlobalSetting.objects.filter(pk=1).update(
            true_cost_multiplicator=Decimal('1.300'),
            chemicals_enabled=True,
        )
        posted = self.client.post(url, {
            'action': 'save_general',
            'default_weekly_hours': '37.00',
        })
        self.assertEqual(posted.status_code, 302)
        setting = GlobalSetting.get_solo()
        self.assertEqual(setting.default_weekly_hours, Decimal('37.00'))
        self.assertEqual(setting.true_cost_multiplicator, Decimal('1.300'))
        self.assertTrue(setting.chemicals_enabled)

    def test_systemadmin_sees_workflow_tab(self):
        self.client.login(username='sysadmin-gs', password='test')
        response = self.client.get(reverse('core_settings:global_settings') + '?tab=workflow')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Task Workflow')
        self.assertContains(response, 'Task Workflow Coordinators')
