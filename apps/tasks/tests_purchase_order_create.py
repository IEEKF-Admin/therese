from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from apps.accounts.models import CustomUser
from apps.hr.models import Employee
from apps.tasks.forms import PurchaseOrderTaskForm
from apps.tasks.models import PurchaseOrderTask
from apps.tasks.forms import PurchaseItemFormSet


class PurchaseOrderCreateFormTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user('buyer', password='test')
        create_perm = Permission.objects.get(
            codename='create_purchase_order',
            content_type=ContentType.objects.get_for_model(PurchaseOrderTask),
        )
        self.user.user_permissions.add(create_perm)
        Employee.objects.create(
            employee_number='E-PO-1',
            first_name='Buyer',
            last_name='User',
            user=self.user,
        )

    def test_initial_message_optional_on_creation(self):
        form = PurchaseOrderTaskForm(
            data={
                'supplier': 'Test Supplier GmbH',
                'priority': 'medium',
                'status': 'not_yet_processed',
                'initial_message': '',
            },
            user=self.user,
            is_creation=True,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_coordinator_does_not_require_wbs_on_creation(self):
        view_perm = Permission.objects.get(
            codename='view_all_purchase_orders',
            content_type=ContentType.objects.get_for_model(PurchaseOrderTask),
        )
        self.user.user_permissions.add(view_perm)

        form = PurchaseOrderTaskForm(
            data={
                'supplier': 'Test Supplier GmbH',
                'priority': 'medium',
                'status': 'not_yet_processed',
                'initial_message': '',
            },
            user=self.user,
            is_creation=True,
        )
        form.is_valid()
        self.assertNotIn('wbs_element', form.errors)

    def test_item_formset_does_not_require_id_for_new_items(self):
        data = {
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product_name': 'Test Product',
            'items-0-product_description': '',
            'items-0-link_to_product': 'https://example.com/product',
            'items-0-order_number': 'ABC-123',
            'items-0-unit_price': '19.99',
            'items-0-quantity': '2',
        }
        formset = PurchaseItemFormSet(data)
        self.assertTrue(formset.is_valid(), formset.errors)
        self.assertNotIn('id', formset.forms[0].errors)