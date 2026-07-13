from datetime import date

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.core.file_service import ThereseFileService
from apps.core.models import StoredFile
from apps.hr.models import Employee
from apps.tasks.models import PersonnelRecruitmentTask, RecruitmentJob, Task


class DatabaseStorageTests(TestCase):
    def test_save_and_open_roundtrip(self):
        upload = SimpleUploadedFile('test.pdf', b'%PDF-1.4 hello', content_type='application/pdf')
        path = ThereseFileService.save('tests/sample.pdf', upload)

        self.assertTrue(StoredFile.objects.filter(name=path).exists())
        stored = StoredFile.objects.get(name=path)
        self.assertEqual(stored.original_filename, 'test.pdf')
        self.assertEqual(bytes(stored.content), b'%PDF-1.4 hello')

        with ThereseFileService.open(path, 'rb') as handle:
            self.assertEqual(handle.read(), b'%PDF-1.4 hello')

    def test_delete_removes_database_record(self):
        upload = SimpleUploadedFile('gone.pdf', b'data', content_type='application/pdf')
        path = ThereseFileService.save('tests/gone.pdf', upload)
        ThereseFileService.delete(path)
        self.assertFalse(StoredFile.objects.filter(name=path).exists())

    def test_filefield_uses_database_storage(self):
        job = RecruitmentJob.objects.create(name='Scientist')
        creator = Employee.objects.create(
            employee_number='E-800',
            first_name='Test',
            last_name='Creator',
        )
        cv = SimpleUploadedFile('cv.pdf', b'%PDF cv', content_type='application/pdf')
        degree = SimpleUploadedFile('degree.pdf', b'%PDF degree', content_type='application/pdf')

        task = PersonnelRecruitmentTask.objects.create(
            task_type='personnel_recruitment',
            creator=creator,
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
            job=job,
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
            cv_file=cv,
            latest_degree_certificate_file=degree,
        )

        self.assertTrue(StoredFile.objects.filter(name=task.cv_file.name).exists())
        self.assertTrue(StoredFile.objects.filter(name=task.latest_degree_certificate_file.name).exists())


class StoredFileServeViewTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user('fileuser', password='test')
        self.user.password_changed = True
        self.user.save(update_fields=['password_changed'])
        task_ct = ContentType.objects.get_for_model(Task)
        perm = Permission.objects.get(codename='view_all_personnel_tasks', content_type=task_ct)
        self.user.user_permissions.add(perm)

        upload = SimpleUploadedFile('serve.pdf', b'%PDF served', content_type='application/pdf')
        self.storage_path = ThereseFileService.save('tests/serve.pdf', upload)

    def test_requires_login(self):
        url = reverse('core:stored_file', kwargs={'file_path': self.storage_path})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_authenticated_user_can_download(self):
        self.client.login(username='fileuser', password='test')
        url = reverse('core:stored_file', kwargs={'file_path': self.storage_path})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'%PDF served')