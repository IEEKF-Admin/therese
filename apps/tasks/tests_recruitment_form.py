from datetime import date
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.models import CustomUser
from apps.hr.models import Employee
from apps.tasks.forms import PersonnelRecruitmentTaskForm
from apps.tasks.models import LimitationReason, RecruitmentJob, Task
from apps.tasks.recruitment_upload_cache import (
    apply_stashed_uploads,
    clear_stashed_uploads,
    stash_recruitment_uploads,
)


@override_settings(MEDIA_ROOT='/tmp/therese_test_media')
class LimitationReasonTemplateTests(TestCase):
    def setUp(self):
        self.job = RecruitmentJob.objects.create(name='Scientist')
        LimitationReason.objects.create(
            title='Template A',
            text='Reason text A',
            applies_to_all_jobs=True,
        )

    def test_template_dropdown_does_not_block_save(self):
        form = PersonnelRecruitmentTaskForm(
            data={
                'job': self.job.pk,
                'first_name': 'Anna',
                'last_name': 'Muster',
                'gender': 'F',
                'date_of_birth': '01.01.1995',
                'country_of_origin': 'Germany',
                'place_of_birth': 'Bonn',
                'email_private': 'anna@example.com',
                'street': 'Main Street',
                'house_number': '1',
                'postal_code': '53111',
                'city': 'Bonn',
                'country': 'Germany',
                'valid_from': '01.01.2026',
                'valid_until': '31.12.2026',
                'limitation_reason': 'Custom reason only',
                'limitation_reason_template': '999',
                'status': 'not_yet_processed',
            },
            user=CustomUser.objects.create_user('creator', password='test'),
            is_creation=True,
        )
        self.assertNotIn('limitation_reason_template', form.errors)

    def test_limitation_reason_is_saved_on_create(self):
        files = {
            'cv_file': SimpleUploadedFile('cv.pdf', b'%PDF cv', content_type='application/pdf'),
            'latest_degree_certificate_file': SimpleUploadedFile(
                'degree.pdf', b'%PDF degree', content_type='application/pdf',
            ),
        }
        form = PersonnelRecruitmentTaskForm(
            data={
                'job': self.job.pk,
                'first_name': 'Anna',
                'last_name': 'Muster',
                'gender': 'F',
                'date_of_birth': '01.01.1995',
                'country_of_origin': 'Germany',
                'place_of_birth': 'Bonn',
                'email_private': 'anna@example.com',
                'street': 'Main Street',
                'house_number': '1',
                'postal_code': '53111',
                'city': 'Bonn',
                'country': 'Germany',
                'valid_from': '01.01.2026',
                'valid_until': '31.12.2026',
                'limitation_reason': 'Project funding ends',
                'status': 'not_yet_processed',
            },
            files=files,
            user=CustomUser.objects.create_user('creator2', password='test'),
            is_creation=True,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save(commit=False)
        self.assertEqual(saved.limitation_reason, 'Project funding ends')

    def test_plan_position_number_visible_and_job_configurable_on_create(self):
        form = PersonnelRecruitmentTaskForm(
            user=CustomUser.objects.create_user('creator3', password='test'),
            is_creation=True,
        )
        widget = form.fields['plan_position_number'].widget
        self.assertNotIsInstance(widget, type(form.fields['status'].widget))  # not hidden
        self.assertFalse(form.fields['plan_position_number'].required)
        self.assertEqual(
            form.fields['plan_position_number'].widget.attrs.get('data-recruitment-field'),
            'plan_position_number',
        )

    def test_plan_position_number_optional_on_edit(self):
        from apps.tasks.models import PersonnelRecruitmentTask

        task = PersonnelRecruitmentTask.objects.create(
            task_type='personnel_recruitment',
            creator=Employee.objects.create(
                employee_number='E-EDIT-1',
                first_name='Creator',
                last_name='User',
            ),
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
            limitation_reason='Existing reason',
            cv_file=SimpleUploadedFile('cv.pdf', b'%PDF cv', content_type='application/pdf'),
            latest_degree_certificate_file=SimpleUploadedFile(
                'degree.pdf', b'%PDF degree', content_type='application/pdf',
            ),
        )
        form = PersonnelRecruitmentTaskForm(
            instance=task,
            data={
                'job': self.job.pk,
                'first_name': 'Anna',
                'last_name': 'Muster',
                'gender': 'F',
                'date_of_birth': '01.01.1995',
                'country_of_origin': 'Germany',
                'place_of_birth': 'Bonn',
                'email_private': 'anna@example.com',
                'street': 'Main Street',
                'house_number': '1',
                'postal_code': '53111',
                'city': 'Bonn',
                'country': 'Germany',
                'valid_from': '01.01.2026',
                'valid_until': '31.12.2026',
                'limitation_reason': 'Existing reason',
                'plan_position_number': '',
                'status': task.status,
            },
            user=CustomUser.objects.create_user('coord', password='test'),
            is_creation=False,
        )
        self.assertFalse(form.fields['plan_position_number'].required)
        self.assertTrue(form.is_valid(), form.errors)


@override_settings(MEDIA_ROOT='/tmp/therese_test_media')
class RecruitmentUploadCacheTests(TestCase):
    def test_stashed_upload_is_reused_after_validation_error(self):
        factory = RequestFactory()
        request = factory.post('/tasks/create/new/?type=personnel_recruitment')
        session = SessionStore()
        session.create()
        request.session = session
        request.FILES['cv_file'] = SimpleUploadedFile(
            'cv.pdf',
            b'%PDF cv content',
            content_type='application/pdf',
        )

        uploads = stash_recruitment_uploads(request)
        self.assertIn('cv_file', uploads)

        cleaned_data = {}
        apply_stashed_uploads(cleaned_data, uploads)
        self.assertIn('cv_file', cleaned_data)
        self.assertEqual(cleaned_data['cv_file'].name, 'cv.pdf')

        clear_stashed_uploads(request)
        self.assertEqual(request.session.get('recruitment_draft_uploads'), None)


class TaskCreateViewImportTests(TestCase):
    def test_task_model_imported_for_personnel_task_number_generation(self):
        from apps.tasks.views import create as create_view_module

        self.assertIs(create_view_module.Task, Task)