from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from apps.accounts.models import CustomUser
from apps.finances.models import WBSElement
from apps.hr.models import Employee
from apps.tasks.forms import (
    GenericTextTaskForm,
    PersonnelContractExtensionTaskForm,
    PersonnelReallocationTaskForm,
    PurchaseItemForm,
    PurchaseOrderTaskForm,
    RecruitmentFundingFormSet,
)
from apps.tasks.models import PurchaseOrderTask
from apps.tasks.forms import PurchaseItemFormSet


class PurchaseOrderValidationTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user('buyer', password='test')
        perm = Permission.objects.get(
            codename='create_purchase_order',
            content_type=ContentType.objects.get_for_model(PurchaseOrderTask),
        )
        self.user.user_permissions.add(perm)
        Employee.objects.create(
            employee_number='E-PO-VAL',
            first_name='Buyer',
            last_name='User',
            user=self.user,
        )

    def test_blank_supplier_rejected(self):
        form = PurchaseOrderTaskForm(
            data={
                'supplier': '   ',
                'priority': 'medium',
                'status': 'not_yet_processed',
            },
            user=self.user,
            is_creation=True,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('supplier', form.errors)

    def test_invalid_item_quantity_rejected(self):
        form = PurchaseItemForm(
            data={
                'product_name': 'Widget',
                'link_to_product': 'https://example.com',
                'order_number': '1',
                'unit_price': '10.00',
                'quantity': '0',
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn('quantity', form.errors)

    def test_invalid_item_unit_price_rejected(self):
        form = PurchaseItemForm(
            data={
                'product_name': 'Widget',
                'link_to_product': 'https://example.com',
                'order_number': '1',
                'unit_price': '-1',
                'quantity': '1',
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn('unit_price', form.errors)

    def test_empty_formset_rejected(self):
        data = {
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product_name': '',
            'items-0-link_to_product': '',
            'items-0-order_number': '',
            'items-0-unit_price': '',
            'items-0-quantity': '',
        }
        formset = PurchaseItemFormSet(data)
        self.assertFalse(formset.is_valid())


class PersonnelTaskValidationTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user('hr', password='test')
        self.employee = Employee.objects.create(
            employee_number='E-HR-1',
            first_name='Max',
            last_name='Mustermann',
            user=self.user,
        )
        self.wbs = WBSElement.objects.create(
            wbs_code='TEST-1.1.1',
            title='Test WBS',
        )

    def test_reallocation_end_before_start_rejected(self):
        form = PersonnelReallocationTaskForm(
            data={
                'employee': self.employee.pk,
                'target_wbs': self.wbs.pk,
                'valid_from': '01.06.2026',
                'valid_until': '01.01.2026',
                'plan_position_number': 'POS-1',
                'status': 'not_yet_processed',
            },
            user=self.user,
            is_creation=True,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('valid_until', form.errors)

    def test_extension_requires_limitation_reason_when_limited(self):
        form = PersonnelContractExtensionTaskForm(
            data={
                'employee': self.employee.pk,
                'plan_position_number': 'POS-2',
                'valid_from': '01.01.2026',
                'valid_until': '31.12.2026',
                'is_limited': True,
                'limitation_reason': '   ',
                'status': 'not_yet_processed',
            },
            user=self.user,
            is_creation=True,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('limitation_reason', form.errors)

    def test_extension_unlimited_without_reason_allowed(self):
        form = PersonnelContractExtensionTaskForm(
            data={
                'employee': self.employee.pk,
                'plan_position_number': 'POS-3',
                'valid_from': '01.01.2026',
                'valid_until': '31.12.2026',
                'is_limited': False,
                'limitation_reason': '',
                'status': 'not_yet_processed',
            },
            user=self.user,
            is_creation=True,
        )
        self.assertTrue(form.is_valid(), form.errors)


class RecruitmentFundingFormsetTests(TestCase):
    def setUp(self):
        self.wbs = WBSElement.objects.create(
            wbs_code='FUND-1.1.1',
            title='Funding WBS',
        )

    def _funding_data(self, **overrides):
        data = {
            'funding_allocations-TOTAL_FORMS': '1',
            'funding_allocations-INITIAL_FORMS': '0',
            'funding_allocations-MIN_NUM_FORMS': '0',
            'funding_allocations-MAX_NUM_FORMS': '1000',
            'funding_allocations-0-wbs_element': str(self.wbs.pk),
            'funding_allocations-0-weekly_hours_allocated': '20',
        }
        data.update(overrides)
        return data

    def test_formset_does_not_require_id_for_new_allocations(self):
        formset = RecruitmentFundingFormSet(self._funding_data(), is_creation=True)
        self.assertTrue(formset.is_valid(), formset.errors)
        self.assertNotIn('id', formset.forms[0].errors)

    def test_formset_accepts_empty_id(self):
        formset = RecruitmentFundingFormSet(
            self._funding_data(**{'funding_allocations-0-id': ''}),
            is_creation=True,
        )
        self.assertTrue(formset.is_valid(), formset.errors)
        self.assertNotIn('id', formset.forms[0].errors)

    def test_formset_ignores_invalid_id_on_empty_extra_row(self):
        data = {
            'funding_allocations-TOTAL_FORMS': '2',
            'funding_allocations-INITIAL_FORMS': '0',
            'funding_allocations-MIN_NUM_FORMS': '0',
            'funding_allocations-MAX_NUM_FORMS': '1000',
            'funding_allocations-0-wbs_element': str(self.wbs.pk),
            'funding_allocations-0-weekly_hours_allocated': '20',
            'funding_allocations-1-id': '0',
            'funding_allocations-1-wbs_element': '',
            'funding_allocations-1-weekly_hours_allocated': '',
        }
        formset = RecruitmentFundingFormSet(data, is_creation=True)
        self.assertTrue(formset.is_valid(), formset.errors)
        self.assertNotIn('id', formset.forms[1].errors)

    def test_formset_accepts_multiple_new_rows_without_id(self):
        data = {
            'funding_allocations-TOTAL_FORMS': '2',
            'funding_allocations-INITIAL_FORMS': '0',
            'funding_allocations-MIN_NUM_FORMS': '0',
            'funding_allocations-MAX_NUM_FORMS': '1000',
            'funding_allocations-0-wbs_element': str(self.wbs.pk),
            'funding_allocations-0-weekly_hours_allocated': '20',
            'funding_allocations-1-wbs_element': str(self.wbs.pk),
            'funding_allocations-1-weekly_hours_allocated': '10',
        }
        formset = RecruitmentFundingFormSet(data, is_creation=True)
        self.assertTrue(formset.is_valid(), formset.errors)
        self.assertEqual([dict(f.errors) for f in formset.forms], [{}, {}])


class GenericRequestValidationTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user('req', password='test')
        self.recipient = Employee.objects.create(
            employee_number='E-REC-1',
            first_name='Recipient',
            last_name='Person',
        )

    def test_title_required_on_creation(self):
        form = GenericTextTaskForm(
            data={
                'title': '',
                'recipient': self.recipient.pk,
                'initial_message': 'Need help with something.',
                'status': 'seen',
            },
            user=self.user,
            is_creation=True,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('title', form.errors)

    def test_initial_message_required_on_creation(self):
        form = GenericTextTaskForm(
            data={
                'title': 'Office supplies',
                'recipient': self.recipient.pk,
                'initial_message': '',
                'status': 'seen',
            },
            user=self.user,
            is_creation=True,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('initial_message', form.errors)

    def test_valid_generic_request_accepted(self):
        form = GenericTextTaskForm(
            data={
                'title': 'Office supplies',
                'recipient': self.recipient.pk,
                'priority': 'medium',
                'initial_message': 'Please order paper.',
                'due_date': (date.today() + timedelta(days=7)).strftime('%d.%m.%Y'),
                'status': 'seen',
            },
            user=self.user,
            is_creation=True,
        )
        self.assertTrue(form.is_valid(), form.errors)