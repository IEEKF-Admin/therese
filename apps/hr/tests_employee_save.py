"""Employee save/paste hardening: clipboard cells, dates, decimals, duplicate phones."""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.permissions import assign_permissions_to_groups, get_or_create_default_groups
from apps.hr.models import Building, Contract, Employee, PhoneNumber, Room
from apps.hr.paste_normalize import (
    first_clipboard_cell,
    looks_like_table,
    normalize_pasted_date,
    normalize_pasted_decimal,
)


def _ready(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class PasteNormalizeTests(TestCase):
    def test_first_cell_from_excel_block(self):
        self.assertEqual(first_clipboard_cell('a\tb\nc\td'), 'a')
        self.assertEqual(first_clipboard_cell('0,5'), '0,5')
        self.assertEqual(first_clipboard_cell('  15.09.26 \tnext'), '15.09.26')
        self.assertTrue(looks_like_table('a\tb\n1\t2'))
        self.assertFalse(looks_like_table('only'))

    def test_date_two_digit_year(self):
        self.assertEqual(normalize_pasted_date('15.09.26'), '15.09.2026')
        self.assertEqual(normalize_pasted_date('15.09.2026\tother'), '15.09.2026')
        block = '15.09.26\t' + '\t'.join(['x'] * 10) + '\n' + '\n'.join(['a\tb'] * 100)
        self.assertEqual(normalize_pasted_date(block), '15.09.2026')

    def test_decimal_from_excel(self):
        self.assertEqual(normalize_pasted_decimal('0,5'), '0.5')
        self.assertEqual(normalize_pasted_decimal('1.234,56'), '1234.56')


class DuplicateOfficePhoneSaveTests(TestCase):
    def setUp(self):
        get_or_create_default_groups()
        assign_permissions_to_groups()
        self.user = _ready('hr-phone')
        perm = Permission.objects.get(
            content_type=ContentType.objects.get_for_model(Employee),
            codename='manage_all_employees',
        )
        self.user.user_permissions.add(perm)
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Employee),
                codename='manage_employee',
            )
        )
        self.employee = Employee.objects.create(
            employee_number='PH-1',
            first_name='Phone',
            last_name='Dup',
            gender='X',
            country='Germany',
        )
        self.contract = Contract.objects.create(
            employee=self.employee,
            weekly_hours=Decimal('39.000'),
            valid_from=date(2020, 1, 1),
            is_active=True,
        )
        self.building = Building.objects.create(number='B1', name='Main')
        self.room = Room.objects.create(building=self.building, room_number='101')
        self.phone_a = PhoneNumber.objects.create(room=self.room, phone_number='0123-456')
        self.phone_b = PhoneNumber.objects.create(room=self.room, phone_number='0123-456')
        self.employee.room = self.room
        self.employee.phone_number = '0123-456'
        self.employee.save(update_fields=['room', 'phone_number'])
        self.client = Client()

    def test_duplicate_office_phone_post_does_not_500(self):
        self.client.login(username='hr-phone', password='test')
        url = reverse('hr:employee_update', args=[self.employee.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(
            url,
            {
                'employee_number': 'PH-1',
                'first_name': 'Phone',
                'last_name': 'Dup',
                'gender': 'X',
                'country': 'Germany',
                'building': str(self.building.pk),
                'room': str(self.room.pk),
                'phone_number': str(self.phone_b.pk),
                'contracts-TOTAL_FORMS': '1',
                'contracts-INITIAL_FORMS': '1',
                'contracts-MIN_NUM_FORMS': '0',
                'contracts-MAX_NUM_FORMS': '1000',
                'contracts-0-id': str(self.contract.pk),
                'contracts-0-weekly_hours': '39.000',
                'contracts-0-valid_from': '01.01.2020',
                'Workgroup_members-TOTAL_FORMS': '0',
                'Workgroup_members-INITIAL_FORMS': '0',
                'Workgroup_members-MIN_NUM_FORMS': '0',
                'Workgroup_members-MAX_NUM_FORMS': '1000',
            },
        )
        self.assertNotEqual(response.status_code, 500)
        self.assertIn(response.status_code, (200, 302, 303), getattr(response, 'context', None))
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.phone_number, '0123-456')
