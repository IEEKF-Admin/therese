from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.accounts.permissions import (
    GroupNames,
    assign_permissions_to_groups,
    get_or_create_default_groups,
)
from apps.feedback.forms import FeedbackItemForm
from apps.feedback.models import FeedbackComment, FeedbackItem, FeedbackVote
from apps.hr.models import Employee


PNG_BYTES = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
    b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
    b'\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05'
    b'\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
)


def _ready(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class FeedbackModuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_or_create_default_groups()
        assign_permissions_to_groups()

    def setUp(self):
        self.client = Client()
        self.reporter_user = _ready('fb-rep')
        self.reporter = Employee.objects.create(
            employee_number='E-FB-1',
            first_name='Rita',
            last_name='Reporter',
            user=self.reporter_user,
        )
        self.other_user = _ready('fb-oth')
        self.other = Employee.objects.create(
            employee_number='E-FB-2',
            first_name='Otto',
            last_name='Other',
            user=self.other_user,
        )
        self.admin_user = _ready('fb-adm')
        self.admin_user.groups.add(Group.objects.get(name=GroupNames.BUGS_FEATURES_MANAGE))
        self.admin = Employee.objects.create(
            employee_number='E-FB-3',
            first_name='Ada',
            last_name='Admin',
            user=self.admin_user,
        )
        self.no_emp_user = _ready('fb-none')

    def _login(self, user):
        self.client.login(username=user.username, password='test')

    def _create_item(self, **kwargs):
        data = {
            'kind': FeedbackItem.Kind.BUG,
            'title': 'Broken filter',
            'description': 'The year filter does nothing.',
            'page_url': '/finances/psp-elements/',
            'created_by': self.reporter,
            'status': FeedbackItem.Status.OPEN,
        }
        data.update(kwargs)
        return FeedbackItem.objects.create(**data)

    def test_no_employee_is_redirected(self):
        self._login(self.no_emp_user)
        response = self.client.get(reverse('feedback:item_list'))
        self.assertIn(response.status_code, (302, 303))

    def test_employee_sees_list_and_create(self):
        self._login(self.reporter_user)
        response = self.client.get(reverse('feedback:item_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'New report')
        create = self.client.get(reverse('feedback:item_create'))
        self.assertEqual(create.status_code, 200)
        self.assertContains(create, 'Page URL')
        self.assertContains(create, 'wysiwyg-editor')
        self.assertNotContains(create, '---------')
        kind_values = [value for value, _label in FeedbackItemForm().fields['kind'].choices]
        self.assertEqual(kind_values, ['bug', 'feature'])

    def test_bug_requires_url(self):
        self._login(self.reporter_user)
        response = self.client.post(
            reverse('feedback:item_create'),
            {
                'kind': 'bug',
                'title': 'Crash',
                'description': 'It crashed.',
                'page_url': '',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FeedbackItem.objects.count(), 0)

    def test_feature_without_url_is_ok(self):
        self._login(self.reporter_user)
        response = self.client.post(
            reverse('feedback:item_create'),
            {
                'kind': 'feature',
                'title': 'Dark mode',
                'description': 'Please add dark mode.',
                'page_url': '',
            },
        )
        self.assertIn(response.status_code, (302, 303))
        item = FeedbackItem.objects.get()
        self.assertEqual(item.kind, FeedbackItem.Kind.FEATURE)
        self.assertEqual(item.created_by, self.reporter)
        self.assertEqual(item.page_url, '')
        detail = self.client.get(reverse('feedback:item_detail', args=[item.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, 'Page URL')

    def test_feature_post_clears_page_url(self):
        self._login(self.reporter_user)
        response = self.client.post(
            reverse('feedback:item_create'),
            {
                'kind': 'feature',
                'title': 'Export CSV',
                'description': '<p>Please add CSV export.</p>',
                'page_url': '/tasks/',
            },
        )
        self.assertIn(response.status_code, (302, 303))
        item = FeedbackItem.objects.get()
        self.assertEqual(item.page_url, '')
        self.assertEqual(item.description, '<p>Please add CSV export.</p>')

    def test_description_sanitizes_html_and_rejects_empty(self):
        self._login(self.reporter_user)
        response = self.client.post(
            reverse('feedback:item_create'),
            {
                'kind': 'bug',
                'title': 'XSS',
                'description': '<p>Broken</p><script>alert(1)</script>',
                'page_url': '/tasks/',
            },
        )
        self.assertIn(response.status_code, (302, 303))
        item = FeedbackItem.objects.get()
        self.assertIn('<p>Broken</p>', item.description)
        self.assertNotIn('<script>', item.description)
        empty = self.client.post(
            reverse('feedback:item_create'),
            {
                'kind': 'bug',
                'title': 'Empty HTML',
                'description': '<p></p><p><br></p>',
                'page_url': '/tasks/',
            },
        )
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(FeedbackItem.objects.count(), 1)

    def test_feature_edit_hides_page_url(self):
        item = self._create_item(kind=FeedbackItem.Kind.FEATURE, page_url='')
        self._login(self.reporter_user)
        response = self.client.get(reverse('feedback:item_edit', args=[item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="page-url-wrap"')
        self.assertContains(response, 'style="display:none"')

    def test_create_bug_with_screenshot(self):
        self._login(self.reporter_user)
        upload = SimpleUploadedFile('shot.png', PNG_BYTES, content_type='image/png')
        response = self.client.post(
            reverse('feedback:item_create'),
            {
                'kind': 'bug',
                'title': 'Button missing',
                'description': 'Save is gone.',
                'page_url': '/tasks/',
                'screenshot': upload,
            },
        )
        self.assertIn(response.status_code, (302, 303), getattr(response, 'context', None))
        item = FeedbackItem.objects.get()
        self.assertTrue(item.screenshot)

    def test_owner_can_edit_other_cannot(self):
        item = self._create_item()
        self._login(self.other_user)
        response = self.client.post(
            reverse('feedback:item_edit', args=[item.pk]),
            {
                'kind': 'bug',
                'title': 'Hijacked',
                'description': 'Nope',
                'page_url': '/tasks/',
            },
        )
        self.assertIn(response.status_code, (302, 303))
        item.refresh_from_db()
        self.assertEqual(item.title, 'Broken filter')

        self._login(self.reporter_user)
        response = self.client.post(
            reverse('feedback:item_edit', args=[item.pk]),
            {
                'kind': 'bug',
                'title': 'Year filter ignored',
                'description': 'Still broken.',
                'page_url': '/finances/psp-elements/?year=2026',
            },
        )
        self.assertIn(response.status_code, (302, 303))
        item.refresh_from_db()
        self.assertEqual(item.title, 'Year filter ignored')

    def test_comment_and_vote(self):
        item = self._create_item()
        self._login(self.other_user)
        self.client.post(
            reverse('feedback:item_comment', args=[item.pk]),
            {'body': 'Same here.'},
        )
        self.assertEqual(item.comments.count(), 1)
        self.client.post(reverse('feedback:item_vote', args=[item.pk]))
        self.assertEqual(item.votes.count(), 1)
        self.client.post(reverse('feedback:item_vote', args=[item.pk]))
        self.assertEqual(item.votes.count(), 0)

    def test_non_admin_cannot_delete_or_set_status(self):
        item = self._create_item()
        self._login(self.reporter_user)
        self.client.post(
            reverse('feedback:item_admin', args=[item.pk]),
            {'status': 'done', 'target_date': '01.12.2026'},
        )
        item.refresh_from_db()
        self.assertEqual(item.status, FeedbackItem.Status.OPEN)
        self.client.post(reverse('feedback:item_delete', args=[item.pk]))
        self.assertTrue(FeedbackItem.objects.filter(pk=item.pk).exists())

    def test_admin_sets_status_and_target_date(self):
        item = self._create_item()
        self._login(self.admin_user)
        response = self.client.post(
            reverse('feedback:item_admin', args=[item.pk]),
            {'status': 'planned', 'target_date': '15.10.2026'},
        )
        self.assertIn(response.status_code, (302, 303))
        item.refresh_from_db()
        self.assertEqual(item.status, FeedbackItem.Status.PLANNED)
        self.assertEqual(item.target_date.isoformat(), '2026-10-15')

    def test_admin_merges_votes_and_comments(self):
        keep = self._create_item(title='Original')
        dup = self._create_item(title='Duplicate')
        FeedbackComment.objects.create(item=dup, author=self.other, body='Also happens to me.')
        FeedbackVote.objects.create(item=dup, employee=self.other)
        FeedbackVote.objects.create(item=keep, employee=self.other)
        self._login(self.admin_user)
        response = self.client.post(
            reverse('feedback:item_merge', args=[dup.pk]),
            {'target': str(keep.pk)},
        )
        self.assertIn(response.status_code, (302, 303))
        dup.refresh_from_db()
        self.assertEqual(dup.merged_into_id, keep.pk)
        self.assertEqual(keep.comments.count(), 2)
        self.assertEqual(keep.votes.count(), 1)
        list_response = self.client.get(reverse('feedback:item_list'))
        self.assertContains(list_response, 'Original')
        self.assertNotContains(list_response, 'Duplicate')
        redirect = self.client.get(reverse('feedback:item_detail', args=[dup.pk]))
        self.assertIn(redirect.status_code, (302, 303))
        self.assertEqual(redirect.url, reverse('feedback:item_detail', args=[keep.pk]))

    def test_admin_deletes(self):
        item = self._create_item()
        self._login(self.admin_user)
        response = self.client.post(reverse('feedback:item_delete', args=[item.pk]))
        self.assertIn(response.status_code, (302, 303))
        self.assertFalse(FeedbackItem.objects.filter(pk=item.pk).exists())

    def test_done_hidden_by_default(self):
        self._create_item(title='Still open')
        self._create_item(title='Finished', status=FeedbackItem.Status.DONE)
        self._login(self.reporter_user)
        response = self.client.get(reverse('feedback:item_list'))
        self.assertContains(response, 'Still open')
        self.assertNotContains(response, 'Finished')
        all_resp = self.client.get(reverse('feedback:item_list') + '?status=all')
        self.assertContains(all_resp, 'Finished')
