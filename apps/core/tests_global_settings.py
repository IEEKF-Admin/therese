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
        self.assertContains(response, 'Default Weekly Working Hours')
        self.assertContains(response, 'Account emails')
        posted = self.client.post(url, {
            'action': 'save_global',
            'default_weekly_hours': '40.00',
            'true_cost_multiplicator': '1.250',
            'personnel_import_tolerance': '0.0300',
            'chemical_hazard_threshold': 'signal_danger_only',
            'show_add_employee_on_reallocation': 'on',
        })
        self.assertEqual(posted.status_code, 302)
        setting = GlobalSetting.get_solo()
        self.assertEqual(setting.default_weekly_hours, Decimal('40.00'))
        self.assertEqual(setting.true_cost_multiplicator, Decimal('1.250'))
        self.assertEqual(setting.chemical_hazard_threshold, 'signal_danger_only')
        self.assertTrue(setting.show_add_employee_on_reallocation)
        self.assertFalse(setting.irresponsible)

    def test_hr_superassistant_is_forbidden(self):
        self.client.login(username='hr-gs', password='test')
        url = reverse('core_settings:global_settings')
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(
            self.client.post(url, {'action': 'save_global', 'default_weekly_hours': '10'}).status_code,
            403,
        )
