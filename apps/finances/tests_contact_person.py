"""Tests for Contact Person list and manage views."""

from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase

from apps.accounts.models import CustomUser
from apps.accounts.permissions import GroupNames, assign_permissions_to_groups
from apps.finances.models import ContactPerson


class ContactPersonViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        assign_permissions_to_groups()
        ContactPerson.objects.create(
            last_name='Muster',
            first_name='Erika',
            business_area='Administration',
            phone='0123',
            email='erika@example.com',
        )

    def _user_with_group(self, username, group_name, codenames):
        user = CustomUser.objects.create_user(username, password='test')
        user.password_changed = True
        user.save(update_fields=['password_changed'])
        group = Group.objects.get(name=group_name)
        for code in codenames:
            perm = Permission.objects.filter(codename=code).first()
            if perm:
                group.permissions.add(perm)
        user.groups.add(group)
        return user

    def test_view_list_requires_permission(self):
        user = CustomUser.objects.create_user('noperm', password='test')
        user.password_changed = True
        user.save(update_fields=['password_changed'])
        client = Client()
        client.login(username='noperm', password='test')
        response = client.get('/finances/contact-persons/')
        self.assertEqual(response.status_code, 403)

    def test_view_list_ok_for_view_group(self):
        self._user_with_group(
            'viewer',
            GroupNames.CONTACT_PERSONS_VIEW,
            ['view_contact_person_list'],
        )
        client = Client()
        client.login(username='viewer', password='test')
        response = client.get('/finances/contact-persons/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Muster')
        self.assertContains(response, 'Erika')
        self.assertContains(response, 'erika@example.com')
        self.assertNotContains(response, 'Delete selected')

    def test_manage_create_and_edit(self):
        self._user_with_group(
            'manager',
            GroupNames.CONTACT_PERSONS_MANAGE,
            ['view_contact_person_list', 'manage_contact_person'],
        )
        client = Client()
        client.login(username='manager', password='test')

        response = client.get('/finances/contact-persons/manage/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'New contact person')

        response = client.post(
            '/finances/contact-persons/manage/new/',
            {
                'last_name': 'Schmidt',
                'first_name': 'Hans',
                'business_area': 'Finance',
                'phone': '',
                'email': 'hans@example.com',
                'comments': 'Imported from funding report',
            },
        )
        self.assertEqual(response.status_code, 302)
        person = ContactPerson.objects.get(last_name='Schmidt', first_name='Hans')
        self.assertEqual(person.email, 'hans@example.com')
        self.assertEqual(person.comments, 'Imported from funding report')

        response = client.post(
            f'/finances/contact-persons/manage/{person.pk}/edit/',
            {
                'last_name': 'Schmidt',
                'first_name': 'Hans',
                'business_area': 'Controlling',
                'phone': '555',
                'email': 'hans@example.com',
                'comments': 'Updated note',
            },
        )
        self.assertEqual(response.status_code, 302)
        person.refresh_from_db()
        self.assertEqual(person.business_area, 'Controlling')
        self.assertEqual(person.phone, '555')
        self.assertEqual(person.comments, 'Updated note')
