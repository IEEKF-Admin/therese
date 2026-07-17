import zipfile
from datetime import date
from io import BytesIO

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.finances.models import WBSElement
from apps.hr.models import Employee
from apps.tasks.models import (
    PersonnelRecruitmentTask,
    PersonnelReallocationTask,
    RecruitmentFundingAllocation,
    RecruitmentJob,
    Task,
)
from apps.tasks.personnel_documents import (
    build_download_filename,
    can_download_personnel_documents,
    get_personnel_task_documents,
)


class PersonnelDocumentHelpersTests(TestCase):
    def setUp(self):
        self.job = RecruitmentJob.objects.create(name='Scientist')
        self.creator = Employee.objects.create(
            employee_number='E-900',
            first_name='Creator',
            last_name='User',
        )
        self.cv = SimpleUploadedFile('cv.pdf', b'%PDF cv', content_type='application/pdf')
        self.degree = SimpleUploadedFile('degree.pdf', b'%PDF degree', content_type='application/pdf')
        self.task = PersonnelRecruitmentTask.objects.create(
            task_type='personnel_recruitment',
            creator=self.creator,
            prefix='Dr.',
            first_name='Anna',
            last_name='Muster',
            gender='F',
            date_of_birth=date(1995, 5, 5),
            country_of_origin='Germany',
            place_of_birth='Hamburg',
            email_private='anna@example.com',
            street='Testweg',
            house_number='12',
            postal_code='20095',
            city='Hamburg',
            job=self.job,
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
            cv_file=self.cv,
            latest_degree_certificate_file=self.degree,
        )
        PersonnelRecruitmentTask.objects.filter(pk=self.task.pk).update(
            created_at=timezone.datetime(2026, 7, 9, 10, 0, tzinfo=timezone.get_current_timezone()),
        )
        self.task.refresh_from_db()

    def test_build_download_filename_uses_german_date_and_title(self):
        filename = build_download_filename(
            'Lebenslauf',
            'Dr.',
            'Muster',
            self.task,
            'pdf',
        )
        self.assertEqual(filename, 'Lebenslauf - Dr. Muster - 09.07.2026.pdf')

    def test_recruitment_collects_cv_degree_and_unique_psp_files(self):
        psp_a = WBSElement.objects.create(
            wbs_code='D-111.0001.1',
            title='Project A',
            third_party_funding_commitment=SimpleUploadedFile(
                'zusage-a.pdf', b'%PDF a', content_type='application/pdf',
            ),
        )
        psp_b = WBSElement.objects.create(
            wbs_code='D-222.0002.1',
            title='Project B',
            third_party_funding_commitment=SimpleUploadedFile(
                'zusage-b.pdf', b'%PDF b', content_type='application/pdf',
            ),
        )
        RecruitmentFundingAllocation.objects.create(
            recruitment_task=self.task,
            wbs_element=psp_a,
            workhours_percentage='50.00',
        )
        RecruitmentFundingAllocation.objects.create(
            recruitment_task=self.task,
            wbs_element=psp_b,
            workhours_percentage='49.00',
        )
        RecruitmentFundingAllocation.objects.create(
            recruitment_task=self.task,
            wbs_element=psp_a,
            workhours_percentage='25.00',
        )

        documents = get_personnel_task_documents(self.task)
        keys = {doc.key for doc in documents}
        labels = {doc.label for doc in documents}

        self.assertEqual(keys, {'cv', 'degree_certificate', f'psp_{psp_a.pk}', f'psp_{psp_b.pk}'})
        self.assertIn('Lebenslauf', labels)
        self.assertIn('Zeugnis des letzten Abschlusses', labels)
        self.assertIn('Drittmittelzusage D-111.0001.1', labels)
        self.assertIn('Drittmittelzusage D-222.0002.1', labels)


class PersonnelDocumentDownloadViewTests(TestCase):
    @staticmethod
    def _create_ready_user(username):
        user = CustomUser.objects.create_user(username, password='test')
        user.password_changed = True
        user.save(update_fields=['password_changed'])
        return user

    def setUp(self):
        self.job = RecruitmentJob.objects.create(name='Scientist')
        self.creator_user = self._create_ready_user('creator')
        self.coordinator_user = self._create_ready_user('coordinator')
        self.approver_user = self._create_ready_user('approver')
        self.other_user = self._create_ready_user('other')

        task_ct = ContentType.objects.get_for_model(Task)
        view_perm = Permission.objects.get(
            codename='view_all_personnel_tasks',
            content_type=task_ct,
        )
        approve_perm = Permission.objects.get(
            codename='approve_personnel_task',
            content_type=task_ct,
        )
        self.coordinator_user.user_permissions.add(view_perm)
        self.approver_user.user_permissions.add(approve_perm)

        self.creator = Employee.objects.create(
            employee_number='E-901',
            first_name='Creator',
            last_name='User',
            user=self.creator_user,
        )
        Employee.objects.create(
            employee_number='E-902',
            first_name='Coordinator',
            last_name='User',
            user=self.coordinator_user,
        )
        Employee.objects.create(
            employee_number='E-903',
            first_name='Approver',
            last_name='User',
            user=self.approver_user,
        )

        self.task = PersonnelRecruitmentTask.objects.create(
            task_type='personnel_recruitment',
            creator=self.creator,
            prefix='Dr.',
            first_name='Anna',
            last_name='Muster',
            gender='F',
            date_of_birth=date(1995, 5, 5),
            country_of_origin='Germany',
            place_of_birth='Hamburg',
            email_private='anna@example.com',
            street='Testweg',
            house_number='12',
            postal_code='20095',
            city='Hamburg',
            job=self.job,
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
            cv_file=SimpleUploadedFile('cv.pdf', b'%PDF cv', content_type='application/pdf'),
            latest_degree_certificate_file=SimpleUploadedFile(
                'degree.pdf', b'%PDF degree', content_type='application/pdf',
            ),
        )
        PersonnelRecruitmentTask.objects.filter(pk=self.task.pk).update(
            created_at=timezone.datetime(2026, 7, 9, 10, 0, tzinfo=timezone.get_current_timezone()),
        )
        self.task.refresh_from_db()

    def test_permission_only_for_coordination_and_approval_groups(self):
        self.assertFalse(can_download_personnel_documents(self.creator_user))
        self.assertFalse(can_download_personnel_documents(self.other_user))
        self.assertTrue(can_download_personnel_documents(self.coordinator_user))
        self.assertTrue(can_download_personnel_documents(self.approver_user))

    def test_creator_cannot_download_single_document(self):
        self.client.login(username='creator', password='test')
        url = reverse('tasks:personnel_task_document_download', args=[self.task.pk, 'cv'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.url, reverse('tasks:my_tasks'))

    def test_coordinator_can_download_with_german_filename(self):
        self.client.login(username='coordinator', password='test')
        url = reverse('tasks:personnel_task_document_download', args=[self.task.pk, 'cv'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('Lebenslauf - Dr. Muster - 09.07.2026.pdf', response['Content-Disposition'])

    def test_coordinator_can_download_zip_with_all_documents(self):
        psp = WBSElement.objects.create(
            wbs_code='D-333.0003.1',
            title='Project C',
            third_party_funding_commitment=SimpleUploadedFile(
                'zusage.pdf', b'%PDF zusage', content_type='application/pdf',
            ),
        )
        RecruitmentFundingAllocation.objects.create(
            recruitment_task=self.task,
            wbs_element=psp,
            workhours_percentage='50.00',
        )

        self.client.login(username='coordinator', password='test')
        url = reverse('tasks:personnel_task_documents_zip', args=[self.task.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')

        archive = zipfile.ZipFile(BytesIO(b''.join(response.streaming_content)))
        names = set(archive.namelist())
        self.assertIn('Lebenslauf - Dr. Muster - 09.07.2026.pdf', names)
        self.assertIn('Zeugnis des letzten Abschlusses - Dr. Muster - 09.07.2026.pdf', names)
        self.assertIn('Drittmittelzusage D-333.0003.1 - Dr. Muster - 09.07.2026.pdf', names)

    def test_reallocation_includes_target_wbs_commitment(self):
        from apps.tasks.models import ReallocationFundingAllocation

        employee = Employee.objects.create(
            employee_number='E-904',
            prefix='Prof.',
            first_name='Erika',
            last_name='Beispiel',
        )
        target_wbs = WBSElement.objects.create(
            wbs_code='D-444.0004.1',
            title='Target PSP',
            third_party_funding_commitment=SimpleUploadedFile(
                'zusage.pdf', b'%PDF zusage', content_type='application/pdf',
            ),
        )
        reallocation = PersonnelReallocationTask.objects.create(
            task_type='personnel_reallocation',
            creator=self.creator,
            employee=employee,
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
        )
        ReallocationFundingAllocation.objects.create(
            reallocation_task=reallocation,
            wbs_element=target_wbs,
            workhours_percentage='100.00',
            plan_position_number='POS-1',
        )
        PersonnelReallocationTask.objects.filter(pk=reallocation.pk).update(
            created_at=timezone.datetime(2026, 7, 9, 10, 0, tzinfo=timezone.get_current_timezone()),
        )
        reallocation.refresh_from_db()

        documents = get_personnel_task_documents(reallocation)
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].key, f'psp_{target_wbs.pk}')
        self.assertEqual(
            documents[0].download_filename,
            'Drittmittelzusage D-444.0004.1 - Prof. Beispiel - 09.07.2026.pdf',
        )