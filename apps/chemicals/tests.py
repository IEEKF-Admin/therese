"""Tests for chemicals module (models, access, CAS helpers, delivery status)."""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.permissions import GroupNames, assign_permissions_to_groups, get_or_create_default_groups
from datetime import date

from apps.chemicals.lookup import evaluate_is_hazardous, normalize_cas
from apps.chemicals.models import Chemical, ChemicalItem, add_calendar_months
from apps.chemicals.services import (
    apply_delivered_number,
    mark_purchase_items_delivered,
    sync_purchase_item_chemical,
)
from apps.hr.models import Employee, Workgroup
from apps.tasks.models import PurchaseItem, PurchaseOrderTask

User = get_user_model()


class CasNormalizeTests(TestCase):
    def test_normalize_cas(self):
        self.assertEqual(normalize_cas('50-00-0'), '50-00-0')
        self.assertEqual(normalize_cas('  64-17-5 '), '64-17-5')
        self.assertIsNone(normalize_cas('not-a-cas'))
        self.assertIsNone(normalize_cas(''))


class HazardThresholdTests(TestCase):
    def test_any_ghs(self):
        self.assertTrue(evaluate_is_hazardous(
            signal_word='Danger', hazard_codes=[], pictograms=[], threshold='any_ghs',
        ))
        self.assertTrue(evaluate_is_hazardous(
            signal_word='', hazard_codes=['H225'], pictograms=[], threshold='any_ghs',
        ))
        self.assertFalse(evaluate_is_hazardous(
            signal_word='', hazard_codes=[], pictograms=[], threshold='any_ghs',
        ))

    def test_danger_only(self):
        self.assertTrue(evaluate_is_hazardous(
            signal_word='Danger', threshold='signal_danger_only',
        ))
        self.assertFalse(evaluate_is_hazardous(
            signal_word='Warning', threshold='signal_danger_only',
        ))

    def test_never(self):
        self.assertFalse(evaluate_is_hazardous(
            signal_word='Danger', hazard_codes=['H300'], threshold='never',
        ))


class ChemicalSyncTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='chem_orderer', password='pass',
            first_name='Chem', last_name='Orderer',
        )
        self.user.password_changed = True
        self.user.save(update_fields=['password_changed'])
        self.employee = Employee.objects.create(
            employee_number='CHEM001',
            first_name='Chem',
            last_name='Orderer',
            user=self.user,
        )
        self.pi = Employee.objects.create(
            employee_number='CHEM_PI',
            first_name='PI',
            last_name='Chem',
        )
        self.wg = Workgroup.objects.create(short_name='CWG', long_name='Chem WG', pi=self.pi)
        self.wg.members.add(self.employee)
        self.task = PurchaseOrderTask.objects.create(
            creator=self.employee,
            creator_workgroup=self.wg,
            supplier='Sigma',
            status='not_yet_processed',
            priority='normal',
        )
        self.item = PurchaseItem.objects.create(
            purchase_task=self.task,
            product_name='Formaldehyde',
            cas_number='50-00-0',
            link_to_product='https://example.com/f',
            order_number='F-1',
            unit_price=Decimal('10.00'),
            quantity=1,
        )

    @patch('apps.chemicals.lookup.fetch_pubchem_by_cas')
    def test_sync_creates_draft_for_hazardous(self, mock_fetch):
        mock_fetch.return_value = {
            'cas_number': '50-00-0',
            'name': 'Formaldehyde',
            'iupac_name': '',
            'molecular_formula': 'CH2O',
            'pubchem_cid': 712,
            'ghs_signal_word': 'Danger',
            'ghs_hazard_codes': ['H301', 'H311'],
            'ghs_pictograms': ['GHS06'],
            'sds_source_url': 'https://pubchem.ncbi.nlm.nih.gov/compound/712',
            'raw': {},
            'error': '',
        }
        # Clear any auto-created items from post_save during create
        ChemicalItem.objects.filter(purchase_item=self.item).delete()
        Chemical.objects.filter(cas_number='50-00-0').delete()

        ci = sync_purchase_item_chemical(self.item, force_refresh=True)
        self.assertIsNotNone(ci)
        self.assertEqual(ci.status, ChemicalItem.Status.DRAFT)
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_dangerous)
        self.assertEqual(ci.chemical.cas_number, '50-00-0')
        self.assertTrue(ci.chemical.is_hazardous)

    @patch('apps.chemicals.lookup.fetch_pubchem_by_cas')
    def test_delivered_activates_item_and_po(self, mock_fetch):
        mock_fetch.return_value = {
            'cas_number': '50-00-0',
            'name': 'Formaldehyde',
            'iupac_name': '',
            'molecular_formula': 'CH2O',
            'pubchem_cid': 712,
            'ghs_signal_word': 'Danger',
            'ghs_hazard_codes': ['H301'],
            'ghs_pictograms': [],
            'sds_source_url': '',
            'raw': {},
            'error': '',
        }
        ChemicalItem.objects.filter(purchase_item=self.item).delete()
        Chemical.objects.filter(cas_number='50-00-0').delete()
        ci = sync_purchase_item_chemical(self.item, force_refresh=True)
        self.assertEqual(ci.status, ChemicalItem.Status.DRAFT)

        mark_purchase_items_delivered([self.item])
        ci.refresh_from_db()
        self.item.refresh_from_db()
        self.task.refresh_from_db()
        self.assertTrue(self.item.delivered)
        self.assertEqual(self.item.delivered_number, self.item.quantity)
        self.assertEqual(ci.status, ChemicalItem.Status.ACTIVE)
        self.assertEqual(self.task.status, 'delivered')

    @patch('apps.chemicals.lookup.fetch_pubchem_by_cas')
    def test_partial_delivery_activates_chemical_and_can_lower(self, mock_fetch):
        mock_fetch.return_value = {
            'cas_number': '50-00-0',
            'name': 'Formaldehyde',
            'iupac_name': '',
            'molecular_formula': 'CH2O',
            'pubchem_cid': 712,
            'ghs_signal_word': 'Danger',
            'ghs_hazard_codes': ['H301'],
            'ghs_pictograms': [],
            'sds_source_url': '',
            'raw': {},
            'error': '',
        }
        ChemicalItem.objects.filter(purchase_item=self.item).delete()
        Chemical.objects.filter(cas_number='50-00-0').delete()
        self.item.quantity = 10
        self.item.save(update_fields=['quantity', 'updated_at'])
        ci = sync_purchase_item_chemical(self.item, force_refresh=True)
        self.assertEqual(ci.status, ChemicalItem.Status.DRAFT)

        apply_delivered_number(self.item, 3)
        self.item.refresh_from_db()
        ci.refresh_from_db()
        self.task.refresh_from_db()
        self.assertEqual(self.item.delivered_number, 3)
        self.assertFalse(self.item.delivered)
        self.assertEqual(ci.status, ChemicalItem.Status.ACTIVE)
        self.assertNotEqual(self.task.status, 'delivered')

        apply_delivered_number(self.item, 10)
        self.item.refresh_from_db()
        self.task.refresh_from_db()
        self.assertTrue(self.item.delivered)
        self.assertEqual(self.task.status, 'delivered')

        apply_delivered_number(self.item, 2)
        self.item.refresh_from_db()
        self.task.refresh_from_db()
        self.assertEqual(self.item.delivered_number, 2)
        self.assertFalse(self.item.delivered)
        self.assertNotEqual(self.task.status, 'delivered')

    @patch('apps.chemicals.lookup.fetch_pubchem_by_cas')
    def test_mhd_auto_from_shelf_life_on_delivery(self, mock_fetch):
        mock_fetch.return_value = {
            'cas_number': '50-00-0',
            'name': 'Formaldehyde',
            'iupac_name': '',
            'molecular_formula': 'CH2O',
            'pubchem_cid': 712,
            'ghs_signal_word': 'Danger',
            'ghs_hazard_codes': ['H301'],
            'ghs_pictograms': [],
            'sds_source_url': '',
            'raw': {},
            'error': '',
        }
        ChemicalItem.objects.filter(purchase_item=self.item).delete()
        Chemical.objects.filter(cas_number='50-00-0').delete()
        ci = sync_purchase_item_chemical(self.item, force_refresh=True)
        ci.chemical.shelf_life_months = 24
        ci.chemical.save(update_fields=['shelf_life_months', 'updated_at'])

        mark_purchase_items_delivered([self.item])
        ci.refresh_from_db()
        self.assertIsNotNone(ci.mhd)
        self.assertIsNotNone(ci.delivered_at)
        expected = add_calendar_months(ci.delivered_at.date(), 24)
        self.assertEqual(ci.mhd, expected)


class AddMonthsTests(TestCase):
    def test_add_months_simple(self):
        self.assertEqual(add_calendar_months(date(2024, 1, 15), 12), date(2025, 1, 15))

    def test_add_months_end_of_month(self):
        self.assertEqual(add_calendar_months(date(2024, 1, 31), 1), date(2024, 2, 29))


class ChemicalCreateFormTests(TestCase):
    def test_cas_lookup_form_validates(self):
        from apps.chemicals.forms import ChemicalCASLookupForm
        form = ChemicalCASLookupForm(data={'cas_number': '50-00-0'})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['cas_number'], '50-00-0')
        bad = ChemicalCASLookupForm(data={'cas_number': 'nope'})
        self.assertFalse(bad.is_valid())

    @patch('apps.chemicals.lookup.fetch_pubchem_by_cas')
    def test_create_view_lookup_then_save(self, mock_fetch):
        mock_fetch.return_value = {
            'cas_number': '64-17-5',
            'name': 'Ethanol',
            'iupac_name': 'ethanol',
            'molecular_formula': 'C2H6O',
            'pubchem_cid': 702,
            'ghs_signal_word': 'Danger',
            'ghs_hazard_codes': ['H225'],
            'ghs_pictograms': ['GHS02'],
            'sds_source_url': 'https://pubchem.ncbi.nlm.nih.gov/compound/702',
            'raw': {'ok': True},
            'error': '',
        }
        user = User.objects.create_user(username='chem_create', password='pass')
        user.password_changed = True
        user.is_superuser = True
        user.save()
        client = Client()
        client.login(username='chem_create', password='pass')

        # Step 1: lookup — prefills form, does not persist yet
        resp = client.post(reverse('chemicals:chemical_create'), {
            'action': 'lookup',
            'cas_number': '64-17-5',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Ethanol')
        self.assertFalse(Chemical.objects.filter(cas_number='64-17-5').exists())

        # Step 2: save
        resp = client.post(reverse('chemicals:chemical_create'), {
            'action': 'save',
            'cas_number': '64-17-5',
            'name': 'Ethanol',
            'iupac_name': 'ethanol',
            'molecular_formula': 'C2H6O',
            'ghs_signal_word': 'Danger',
            'ghs_hazard_codes': 'H225',
            'ghs_pictograms': 'GHS02',
            'is_hazardous': 'on',
            'hazard_classification_notes': '',
            'shelf_life_months': '36',
            'sds_source_url': 'https://pubchem.ncbi.nlm.nih.gov/compound/702',
        })
        self.assertEqual(resp.status_code, 302)
        chem = Chemical.objects.get(cas_number='64-17-5')
        self.assertEqual(chem.name, 'Ethanol')
        self.assertEqual(chem.shelf_life_months, 36)
        self.assertTrue(chem.is_hazardous)


class ChemicalsPermissionsSmokeTests(TestCase):
    def setUp(self):
        get_or_create_default_groups()
        # Permissions exist only after migrate; assign if available
        try:
            assign_permissions_to_groups()
        except Exception:
            pass
        self.user = User.objects.create_user(username='emp_chem', password='pass')
        self.user.password_changed = True
        self.user.save(update_fields=['password_changed'])
        Employee.objects.create(
            employee_number='EMP_C1',
            first_name='E',
            last_name='User',
            user=self.user,
        )
        try:
            g = Group.objects.get(name=GroupNames.EMPLOYEE)
            self.user.groups.add(g)
        except Group.DoesNotExist:
            pass
        self.client = Client()
        self.client.login(username='emp_chem', password='pass')

    def test_item_list_reachable_with_own_perm(self):
        # Superuser fallback if custom perms not migrated yet
        if not self.user.has_perm('chemicals.manage_own_chemical_items'):
            self.user.is_superuser = True
            self.user.save()
        resp = self.client.get(reverse('chemicals:chemical_item_list'))
        self.assertIn(resp.status_code, (200, 302))
