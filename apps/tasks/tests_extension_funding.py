from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.finances.models import WBSElement
from apps.hr.models import Contract, Employee, FundingAllocation
from apps.tasks.models import (
    ExtensionFundingAllocation,
    PersonnelContractExtensionTask,
    PurchaseOrderTask,
    Task,
)
from apps.tasks.personnel_documents import get_personnel_task_documents


def _ready(username):
    user = CustomUser.objects.create_user(username, password='test')
    user.password_changed = True
    user.save(update_fields=['password_changed'])
    return user


class ExtensionCreateFundingTests(TestCase):
    def setUp(self):
        self.creator_user = _ready('ext-fund-cre')
        self.approver_user = _ready('ext-fund-apr')
        po_ct = ContentType.objects.get_for_model(PurchaseOrderTask)
        task_ct = ContentType.objects.get_for_model(Task)
        self.creator_user.user_permissions.add(
            Permission.objects.get(content_type=po_ct, codename='create_personnel_task'),
        )
        self.approver_user.user_permissions.add(
            Permission.objects.get(content_type=po_ct, codename='create_personnel_task'),
            Permission.objects.get(content_type=task_ct, codename='approve_personnel_task'),
        )
        self.creator = Employee.objects.create(
            employee_number='E-EXTF-CRE',
            first_name='Chris',
            last_name='Creator',
            user=self.creator_user,
        )
        self.approver = Employee.objects.create(
            employee_number='E-EXTF-APR',
            first_name='Ann',
            last_name='Approver',
            user=self.approver_user,
        )
        self.person = Employee.objects.create(
            employee_number='E-EXTF-EMP',
            first_name='Pat',
            last_name='Person',
        )
        self.wbs = WBSElement.objects.create(wbs_code='EXTF-1', title='Extension funding PSP')
        self.url = reverse('tasks:task_create') + '?type=personnel_contract_extension'

    def test_create_page_has_funding_inline_and_project_description(self):
        self.client.login(username='ext-fund-cre', password='test')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Funding Allocations')
        self.assertContains(response, 'Project Description')
        self.assertContains(response, 'name="project_description_file"')
        self.assertNotContains(response, 'name="funding_allocations-0-job_number"')

    def test_approver_create_page_shows_job_number(self):
        self.client.login(username='ext-fund-apr', password='test')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="funding_allocations-0-job_number"')

    def test_create_saves_funding_and_project_description(self):
        self.client.login(username='ext-fund-cre', password='test')
        upload = SimpleUploadedFile(
            'projekt.pdf', b'%PDF project', content_type='application/pdf',
        )
        response = self.client.post(
            self.url,
            {
                'task_type': 'personnel_contract_extension',
                'employee': str(self.person.pk),
                'plan_position_number': 'P-9',
                'valid_from': '01.10.2026',
                'valid_until': '31.12.2026',
                'is_limited': 'on',
                'limitation_reason': 'Befristung',
                'status': 'not_yet_processed',
                'confirm_info': 'on',
                'funding_allocations-TOTAL_FORMS': '1',
                'funding_allocations-INITIAL_FORMS': '0',
                'funding_allocations-MIN_NUM_FORMS': '0',
                'funding_allocations-MAX_NUM_FORMS': '1000',
                'funding_allocations-0-funding_source': f'wbs:{self.wbs.pk}',
                'funding_allocations-0-workhours_percentage': '100',
                'funding_allocations-0-plan_position_number': 'P-9',
                'funding_allocations-0-notes': '',
                'project_description_file': upload,
            },
        )
        self.assertIn(response.status_code, (302, 303), getattr(response, 'context', None))
        task = PersonnelContractExtensionTask.objects.get(employee=self.person)
        self.assertTrue(task.project_description_file)
        row = ExtensionFundingAllocation.objects.get(extension_task=task)
        self.assertEqual(row.wbs_element_id, self.wbs.pk)
        self.assertEqual(row.workhours_percentage, Decimal('100.00'))
        self.assertEqual(task.original_funding_snapshot, [])

    def test_create_page_prefills_current_employee_funding(self):
        contract = Contract.objects.create(
            employee=self.person,
            weekly_hours=Decimal('39.000'),
            valid_from=date(2025, 1, 1),
            is_active=True,
        )
        allocation = FundingAllocation.objects.create(
            contract=contract,
            employee=self.person,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('80.00'),
            plan_position_number='PP-80',
            job_number='J-80',
            comments='from employee',
            start_date=date(2025, 1, 1),
            is_active=True,
        )
        self.client.login(username='ext-fund-cre', password='test')
        response = self.client.get(self.url + f'&employee={self.person.pk}')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'wbs:{self.wbs.pk}')
        self.assertContains(response, '80')
        self.assertContains(response, 'PP-80')
        self.assertContains(response, str(allocation.pk))
        self.assertNotContains(response, 'name="funding_allocations-0-job_number"')

    def test_ajax_returns_current_employee_funding(self):
        contract = Contract.objects.create(
            employee=self.person,
            weekly_hours=Decimal('39.000'),
            valid_from=date(2025, 1, 1),
            is_active=True,
        )
        allocation = FundingAllocation.objects.create(
            contract=contract,
            employee=self.person,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('80.00'),
            plan_position_number='PP-80',
            start_date=date(2025, 1, 1),
            is_active=True,
        )
        self.client.login(username='ext-fund-cre', password='test')
        response = self.client.get(
            reverse('tasks:ajax_employee_current_funding'),
            {'employee': str(self.person.pk)},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['allocations']), 1)
        self.assertEqual(data['allocations'][0]['source_id'], allocation.pk)
        self.assertEqual(data['allocations'][0]['funding_source'], f'wbs:{self.wbs.pk}')
        self.assertEqual(data['allocations'][0]['plan_position_number'], 'PP-80')

    def test_create_copies_hidden_job_number_from_snapshot(self):
        contract = Contract.objects.create(
            employee=self.person,
            weekly_hours=Decimal('39.000'),
            valid_from=date(2025, 1, 1),
            is_active=True,
        )
        allocation = FundingAllocation.objects.create(
            contract=contract,
            employee=self.person,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('100.00'),
            job_number='J-KEEP',
            start_date=date(2025, 1, 1),
            is_active=True,
        )
        self.client.login(username='ext-fund-cre', password='test')
        response = self.client.post(
            self.url,
            {
                'task_type': 'personnel_contract_extension',
                'employee': str(self.person.pk),
                'plan_position_number': 'P-9',
                'valid_from': '01.10.2026',
                'is_limited': 'on',
                'limitation_reason': 'Befristung',
                'status': 'not_yet_processed',
                'confirm_info': 'on',
                'funding_allocations-TOTAL_FORMS': '1',
                'funding_allocations-INITIAL_FORMS': '0',
                'funding_allocations-MIN_NUM_FORMS': '0',
                'funding_allocations-MAX_NUM_FORMS': '1000',
                'funding_allocations-0-funding_source': f'wbs:{self.wbs.pk}',
                'funding_allocations-0-workhours_percentage': '100',
                'funding_allocations-0-plan_position_number': '',
                'funding_allocations-0-notes': '',
                'funding_allocations-0-source_allocation_id': str(allocation.pk),
            },
        )
        self.assertIn(response.status_code, (302, 303), getattr(response, 'context', None))
        task = PersonnelContractExtensionTask.objects.get(employee=self.person)
        self.assertEqual(len(task.original_funding_snapshot), 1)
        row = ExtensionFundingAllocation.objects.get(extension_task=task)
        self.assertEqual(row.job_number, 'J-KEEP')
        self.assertEqual(row.source_allocation_id, allocation.pk)


class ExtensionApproverDocumentAndCopyTests(TestCase):
    def setUp(self):
        self.approver_user = _ready('ext-doc-apr')
        self.creator_user = _ready('ext-doc-cre')
        task_ct = ContentType.objects.get_for_model(Task)
        self.approver_user.user_permissions.add(
            Permission.objects.get(
                content_type=task_ct, codename='approve_personnel_task',
            ),
        )
        self.approver = Employee.objects.create(
            employee_number='E-EXTD-APR',
            prefix='Dr.',
            first_name='Ann',
            last_name='Approver',
            user=self.approver_user,
        )
        self.creator = Employee.objects.create(
            employee_number='E-EXTD-CRE',
            first_name='Chris',
            last_name='Creator',
            user=self.creator_user,
        )
        self.person = Employee.objects.create(
            employee_number='E-EXTD-EMP',
            prefix='Prof.',
            first_name='Pat',
            last_name='Person',
        )
        self.task = PersonnelContractExtensionTask.objects.create(
            task_type='personnel_contract_extension',
            creator=self.creator,
            assignee=self.approver,
            employee=self.person,
            plan_position_number='P-1',
            valid_from=date(2026, 10, 1),
            project_description_file=SimpleUploadedFile(
                'projekt.pdf', b'%PDF project', content_type='application/pdf',
            ),
        )

    def test_project_description_is_downloadable(self):
        documents = get_personnel_task_documents(self.task)
        keys = {doc.key for doc in documents}
        self.assertIn('project_description', keys)
        self.client.login(username='ext-doc-apr', password='test')
        response = self.client.get(reverse('tasks:task_detail', args=[self.task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Project Description')
        self.assertContains(response, 'Herunterladen')
        self.assertContains(response, 'enctype="multipart/form-data" data-show-copy="1"')

    def test_creator_does_not_get_copy_buttons_or_download(self):
        self.client.login(username='ext-doc-cre', password='test')
        response = self.client.get(reverse('tasks:task_detail', args=[self.task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'enctype="multipart/form-data" data-show-copy="1"')
        self.assertNotContains(response, 'Herunterladen')


class ExtensionFundingHighlightTests(TestCase):
    def setUp(self):
        self.approver_user = _ready('ext-hl-apr')
        task_ct = ContentType.objects.get_for_model(Task)
        self.approver_user.user_permissions.add(
            Permission.objects.get(
                content_type=task_ct, codename='approve_personnel_task',
            ),
        )
        self.approver = Employee.objects.create(
            employee_number='E-EXTH-APR',
            first_name='Ann',
            last_name='Approver',
            user=self.approver_user,
        )
        self.person = Employee.objects.create(
            employee_number='E-EXTH-EMP',
            first_name='Pat',
            last_name='Person',
        )
        self.wbs = WBSElement.objects.create(wbs_code='EXTH-1', title='Highlight PSP')
        self.wbs_new = WBSElement.objects.create(wbs_code='EXTH-2', title='New PSP')
        self.wbs_removed = WBSElement.objects.create(wbs_code='EXTH-3', title='Removed PSP')
        self.creator_user = _ready('ext-hl-cre')
        self.creator = Employee.objects.create(
            employee_number='E-EXTH-CRE',
            first_name='Chris',
            last_name='Creator',
            user=self.creator_user,
        )
        self.task = PersonnelContractExtensionTask.objects.create(
            task_type='personnel_contract_extension',
            creator=self.creator,
            assignee=self.approver,
            employee=self.person,
            plan_position_number='P-1',
            valid_from=date(2026, 10, 1),
            original_funding_snapshot=[
                {
                    'source_id': 91,
                    'wbs_element_id': self.wbs.pk,
                    'cost_center_id': None,
                    'funding_source': f'wbs:{self.wbs.pk}',
                    'funding_target_label': str(self.wbs),
                    'workhours_percentage': '100',
                    'plan_position_number': 'PP-OLD',
                    'job_number': 'J-OLD',
                    'notes': '',
                },
                {
                    'source_id': 92,
                    'wbs_element_id': self.wbs_removed.pk,
                    'cost_center_id': None,
                    'funding_source': f'wbs:{self.wbs_removed.pk}',
                    'funding_target_label': str(self.wbs_removed),
                    'workhours_percentage': '20',
                    'plan_position_number': 'PP-GONE',
                    'job_number': 'J-GONE',
                    'notes': '',
                },
            ],
        )
        self.kept = ExtensionFundingAllocation.objects.create(
            extension_task=self.task,
            wbs_element=self.wbs,
            workhours_percentage=Decimal('50.00'),
            plan_position_number='PP-OLD',
            job_number='J-OLD',
            source_allocation_id=91,
        )
        self.added = ExtensionFundingAllocation.objects.create(
            extension_task=self.task,
            wbs_element=self.wbs_new,
            workhours_percentage=Decimal('50.00'),
            plan_position_number='PP-NEW',
            job_number='J-NEW',
        )

    def test_detail_highlights_changed_added_and_removed(self):
        self.client.login(username='ext-hl-apr', password='test')
        response = self.client.get(reverse('tasks:task_detail', args=[self.task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'funding-field-changed')
        self.assertContains(response, 'funding-row-added')
        self.assertContains(response, 'funding-row-removed')
        self.assertContains(response, 'PP-OLD')
        self.assertContains(response, 'PP-NEW')
        self.assertContains(response, 'PP-GONE')

    def test_readonly_detail_highlights_changed_added_and_removed(self):
        self.client.login(username='ext-hl-cre', password='test')
        response = self.client.get(reverse('tasks:task_detail', args=[self.task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'funding-field-changed')
        self.assertContains(response, 'funding-row-added')
        self.assertContains(response, 'class="funding-row-removed"')
        self.assertContains(response, 'PP-GONE')
