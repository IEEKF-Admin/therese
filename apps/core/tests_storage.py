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

    def test_display_name_prefers_original_filename(self):
        upload = SimpleUploadedFile(
            'Original Report Name.pdf',
            b'%PDF',
            content_type='application/pdf',
        )
        path = ThereseFileService.save('tests/uuid-looking-name.pdf', upload)
        self.assertEqual(
            ThereseFileService.display_name(path),
            'Original Report Name.pdf',
        )

    def test_get_available_name_renames_when_path_exceeds_max_length(self):
        """FileField default max_length=100; long original names must be renamed."""
        from django.core.files.storage import default_storage

        long_name = (
            'finances/psp/third_party_funding/2026/07/'
            + ('sehr_langer_dateiname_der_den_standard_filefield_pfad_sprengt_' * 3)
            + '.pdf'
        )
        self.assertGreater(len(long_name), 100)

        available = default_storage.get_available_name(long_name, max_length=100)
        self.assertLessEqual(len(available), 100)
        self.assertTrue(available.startswith('finances/psp/third_party_funding/2026/07/'))
        self.assertTrue(available.endswith('.pdf'))
        # Renamed to a short UUID basename rather than a truncated original.
        basename = available.rsplit('/', 1)[-1]
        self.assertRegex(basename, r'^[0-9a-f]{32}\.pdf$')

    def test_get_available_name_keeps_short_unused_names(self):
        from django.core.files.storage import default_storage

        name = 'finances/psp/third_party_funding/2026/07/zusage.pdf'
        self.assertEqual(
            default_storage.get_available_name(name, max_length=100),
            name,
        )

    def test_get_available_name_renames_on_collision(self):
        from django.core.files.storage import default_storage

        upload = SimpleUploadedFile('zusage.pdf', b'%PDF-1', content_type='application/pdf')
        existing = ThereseFileService.save(
            'finances/psp/third_party_funding/2026/07/zusage.pdf',
            upload,
        )
        available = default_storage.get_available_name(existing, max_length=100)
        self.assertNotEqual(available, existing)
        self.assertTrue(available.endswith('.pdf'))
        self.assertLessEqual(len(available), 100)

    def test_filefield_accepts_very_long_original_filename(self):
        """PSP-style FileField must save even when the client filename is very long."""
        from apps.finances.models import CostCenter, WBSElement

        cost_center = CostCenter.objects.create(cost_center='LONG/2026')
        # Exceed FileField max_length including upload_to prefix → storage renames.
        # Client name must stay within form max_length (255); path can still overflow.
        long_filename = ('x' * 230) + '.pdf'
        field_max = WBSElement._meta.get_field('third_party_funding_commitment').max_length
        self.assertLessEqual(len(long_filename), field_max)
        self.assertGreater(
            len('finances/psp/third_party_funding/2026/07/' + long_filename),
            field_max,
        )
        upload = SimpleUploadedFile(
            long_filename,
            b'%PDF-1.4 long name',
            content_type='application/pdf',
        )
        psp = WBSElement.objects.create(
            wbs_code='D-LONG.0001.1',
            title='Long filename test',
            cost_center=cost_center,
            third_party_funding_commitment=upload,
        )

        self.assertTrue(psp.third_party_funding_commitment.name)
        self.assertLessEqual(len(psp.third_party_funding_commitment.name), field_max)
        self.assertTrue(psp.third_party_funding_commitment.name.endswith('.pdf'))
        basename = psp.third_party_funding_commitment.name.rsplit('/', 1)[-1]
        self.assertRegex(basename, r'^[0-9a-f]{32}\.pdf$')
        stored = StoredFile.objects.get(name=psp.third_party_funding_commitment.name)
        self.assertEqual(stored.original_filename, long_filename)
        self.assertEqual(bytes(stored.content), b'%PDF-1.4 long name')

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

        self.superuser = CustomUser.objects.create_superuser(
            'filesuper', password='test', email='super@example.com',
        )
        self.superuser.password_changed = True
        self.superuser.save(update_fields=['password_changed'])

        # Unknown prefix path — must be denied for non-superusers (deny-by-default).
        upload = SimpleUploadedFile('serve.pdf', b'%PDF served', content_type='application/pdf')
        self.unknown_path = ThereseFileService.save('tests/serve.pdf', upload)

        # Document path under allowlisted prefix; superuser always allowed.
        doc_upload = SimpleUploadedFile('policy.pdf', b'%PDF policy', content_type='application/pdf')
        self.document_path = ThereseFileService.save('documents/policy.pdf', doc_upload)

    def test_requires_login(self):
        url = reverse('core:stored_file', kwargs={'file_path': self.unknown_path})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_authenticated_user_denied_unknown_prefix(self):
        """Logged-in users must not download arbitrary media paths."""
        self.client.login(username='fileuser', password='test')
        url = reverse('core:stored_file', kwargs={'file_path': self.unknown_path})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_superuser_can_download_document_path(self):
        self.client.login(username='filesuper', password='test')
        url = reverse('core:stored_file', kwargs={'file_path': self.document_path})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'%PDF policy')

    def test_regular_user_denied_document_without_attachment_link(self):
        """Document-prefix files without a linked attachment are manager-only."""
        task_ct = ContentType.objects.get_for_model(Task)
        # Even with unrelated perms, unlinked document paths stay closed.
        perm = Permission.objects.get(codename='view_all_personnel_tasks', content_type=task_ct)
        self.user.user_permissions.add(perm)

        self.client.login(username='fileuser', password='test')
        url = reverse('core:stored_file', kwargs={'file_path': self.document_path})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
