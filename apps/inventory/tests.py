from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames, assign_permissions_to_groups, get_or_create_default_groups
from apps.core.models import GlobalSetting
from apps.hr.models import Employee
from apps.inventory.models import InventoryIssuance, InventoryItem, InventoryItemType


def _ready(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class InventoryModuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        self.client = Client()
        GlobalSetting.objects.update_or_create(pk=1, defaults={'inventory_enabled': True})
        self.item_type = InventoryItemType.objects.create(name='Storage media', prefix='SM')
        self.manager = _ready('inv-mgr')
        self.manager.groups.add(Group.objects.get(name=GroupNames.INVENTORY_MANAGE))
        self.viewer = _ready('inv-view')
        self.viewer.groups.add(Group.objects.get(name=GroupNames.INVENTORY_VIEW_ALL))
        self.own = _ready('inv-own')
        self.own.groups.add(Group.objects.get(name=GroupNames.INVENTORY_VIEW_OWN))
        self.holder = Employee.objects.create(
            employee_number='E-INV-1',
            first_name='Pat',
            last_name='Person',
            user=self.own,
        )
        self.other = Employee.objects.create(
            employee_number='E-INV-2',
            first_name='Other',
            last_name='User',
        )

    def test_disabled_module_is_forbidden(self):
        setting = GlobalSetting.get_solo()
        setting.inventory_enabled = False
        setting.save(update_fields=['inventory_enabled'])
        self.client.login(username='inv-mgr', password='test')
        response = self.client.get(reverse('inventory:item_list'))
        self.assertEqual(response.status_code, 403)

    def test_manage_creates_item_with_prefixed_id_and_issuance(self):
        self.client.login(username='inv-mgr', password='test')
        response = self.client.post(
            reverse('inventory:item_create'),
            {
                'item_type': str(self.item_type.pk),
                'name': 'USB stick 32GB',
                'purchase_date': '15.03.2026',
                'purchase_price': '19,90',
                'description': 'Office spare',
                'current_holder': str(self.holder.pk),
            },
        )
        self.assertIn(response.status_code, (302, 303), getattr(response, 'context', None))
        item = InventoryItem.objects.get(name='USB stick 32GB')
        self.assertEqual(item.code, 'SM-0001')
        self.assertEqual(item.purchase_price, Decimal('19.90'))
        self.assertEqual(item.purchase_date, date(2026, 3, 15))
        self.assertEqual(item.current_holder, self.holder)
        issuance = InventoryIssuance.objects.get(item=item)
        self.assertEqual(issuance.employee, self.holder)
        self.assertIsNone(issuance.returned_at)
        self.item_type.refresh_from_db()
        self.assertEqual(self.item_type.next_number, 2)

        second = self.client.post(
            reverse('inventory:item_create'),
            {
                'item_type': str(self.item_type.pk),
                'name': 'USB stick 64GB',
            },
        )
        self.assertIn(second.status_code, (302, 303))
        self.assertEqual(InventoryItem.objects.get(name='USB stick 64GB').code, 'SM-0002')

    def test_reassign_closes_previous_issuance(self):
        self.client.login(username='inv-mgr', password='test')
        self.client.post(
            reverse('inventory:item_create'),
            {
                'item_type': str(self.item_type.pk),
                'name': 'Laptop lock',
                'current_holder': str(self.holder.pk),
            },
        )
        item = InventoryItem.objects.get(name='Laptop lock')
        self.client.post(
            reverse('inventory:item_detail', args=[item.pk]),
            {
                'name': 'Laptop lock',
                'current_holder': str(self.other.pk),
            },
        )
        item.refresh_from_db()
        self.assertEqual(item.current_holder, self.other)
        rows = list(item.issuances.order_by('pk'))
        self.assertEqual(len(rows), 2)
        self.assertIsNotNone(rows[0].returned_at)
        self.assertEqual(rows[0].employee, self.holder)
        self.assertIsNone(rows[1].returned_at)
        self.assertEqual(rows[1].employee, self.other)

        self.client.post(
            reverse('inventory:item_detail', args=[item.pk]),
            {'name': 'Laptop lock', 'current_holder': ''},
        )
        item.refresh_from_db()
        self.assertIsNone(item.current_holder)
        self.assertTrue(all(row.returned_at for row in item.issuances.all()))

    def test_view_own_sees_only_held_items(self):
        mine = InventoryItem.objects.create(
            item_type=self.item_type, code='SM-0100', name='Mine', current_holder=self.holder,
        )
        InventoryItem.objects.create(
            item_type=self.item_type, code='SM-0101', name='Theirs', current_holder=self.other,
        )
        self.client.login(username='inv-own', password='test')
        listing = self.client.get(reverse('inventory:item_list'))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, 'Mine')
        self.assertNotContains(listing, 'Theirs')
        self.assertEqual(self.client.get(reverse('inventory:item_detail', args=[mine.pk])).status_code, 200)
        other = InventoryItem.objects.get(code='SM-0101')
        blocked = self.client.get(reverse('inventory:item_detail', args=[other.pk]))
        self.assertEqual(blocked.status_code, 302)

    def test_view_all_cannot_create(self):
        self.client.login(username='inv-view', password='test')
        listing = self.client.get(reverse('inventory:item_list'))
        self.assertEqual(listing.status_code, 200)
        self.assertNotContains(listing, '+ New item')
        created = self.client.post(
            reverse('inventory:item_create'),
            {'item_type': str(self.item_type.pk), 'name': 'Nope'},
        )
        self.assertEqual(created.status_code, 302)
        self.assertFalse(InventoryItem.objects.filter(name='Nope').exists())

    def test_global_settings_saves_types(self):
        admin = _ready('inv-admin')
        admin.groups.add(Group.objects.get(name=GroupNames.SYSTEMADMIN))
        self.client.login(username='inv-admin', password='test')
        url = reverse('core_settings:global_settings')
        response = self.client.get(url)
        self.assertContains(response, 'Inventory module')
        self.assertContains(response, 'Item types')
        posted = self.client.post(url, {
            'action': 'save_inventory',
            'inventory_enabled': 'on',
            'inv_types_present': '1',
            'inv_type_0_id': str(self.item_type.pk),
            'inv_type_0_name': 'Storage media',
            'inv_type_0_prefix': 'SM',
            'inv_type_1_id': '',
            'inv_type_1_name': 'Laptop',
            'inv_type_1_prefix': 'lt',
        })
        self.assertEqual(posted.status_code, 302)
        self.assertTrue(GlobalSetting.get_solo().inventory_enabled)
        laptop = InventoryItemType.objects.get(name='Laptop')
        self.assertEqual(laptop.prefix, 'LT')
