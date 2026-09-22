import base64
import re
import zlib
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.accounts.models import CustomUser
from apps.core.models import GlobalSetting
from apps.finances.models import PayScale
from apps.hr.models import Employee
from apps.tasks.forms import PersonnelContractExtensionTaskForm, PersonnelRecruitmentTaskForm
from apps.tasks.models import (
    PersonnelContractExtensionTask,
    PersonnelRecruitmentTask,
    RecruitmentJob,
    RecruitmentJobFieldRule,
)
from apps.tasks.personnel_documents import get_personnel_task_documents
from apps.tasks.recruitment_config import RequiredMode, VisibilityMode


def _pdf(name='reason.pdf', body=b'%PDF-1.4 test'):
    return SimpleUploadedFile(name, body, content_type='application/pdf')


def _pdf_payload(content: bytes) -> str:
    chunks = re.findall(br'stream\r?\n(.*?)endstream', content, re.S)
    out = []
    for chunk in chunks:
        data = chunk
        try:
            data = base64.a85decode(data, adobe=True)
        except Exception:
            pass
        try:
            data = zlib.decompress(data)
        except Exception:
            pass
        out.append(data.decode('latin-1', errors='ignore'))
    return '\n'.join(out)


def _recruitment_files():
    return {
        'cv_file': _pdf('cv.pdf', b'%PDF cv'),
        'latest_degree_certificate_file': _pdf('degree.pdf', b'%PDF degree'),
    }


def _recruitment_data(job, **overrides):
    data = {
        'job': job.pk,
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
        'status': 'not_yet_processed',
    }
    data.update(overrides)
    return data


@override_settings(MEDIA_ROOT='/tmp/therese_limitation_pdf')
class LimitationReasonPdfTests(TestCase):
    def setUp(self):
        PayScale.objects.create(
            pay_scale_group='E13',
            experience_level=3,
            monthly_salary='4500.00',
            effective_as_of=date(2026, 1, 1),
        )
        self.job = RecruitmentJob.objects.create(
            name='Scientist',
            pay_scale_group='E13',
            experience_level=3,
        )
        self.creator = Employee.objects.create(
            employee_number='E-LIM-1',
            first_name='Creator',
            last_name='User',
        )
        self.user = CustomUser.objects.create_user('lim-user', password='test')

    def _save_recruitment(self, form):
        self.assertTrue(form.is_valid(), form.errors)
        task = form.save(commit=False)
        task.creator = self.creator
        task.task_type = 'personnel_recruitment'
        task.save()
        return task

    def test_text_generates_pdf_with_letterhead_and_last_name(self):
        setting = GlobalSetting.get_solo()
        setting.limitation_pdf_letterhead = '<p>Institute Header</p>'
        setting.save(update_fields=['limitation_pdf_letterhead'])

        form = PersonnelRecruitmentTaskForm(
            data=_recruitment_data(self.job, limitation_reason='Project funding ends'),
            files=_recruitment_files(),
            user=self.user,
            is_creation=True,
        )
        task = self._save_recruitment(form)
        self.assertTrue(task.limitation_reason_generated)
        self.assertTrue(task.limitation_reason_file)
        self.assertIn('Limitation_Reason_Muster.pdf', task.limitation_reason_file.name)
        content = task.limitation_reason_file.read()
        self.assertTrue(content.startswith(b'%PDF'))
        self.assertIn(b'/Title (Limitation Reason Muster)', content)
        payload = _pdf_payload(content)
        self.assertIn('Project funding ends', payload)
        self.assertIn('Institute Header', payload)

        documents = get_personnel_task_documents(task)
        labels = {doc.label for doc in documents}
        self.assertIn('Limitation Reason Muster', labels)

    def test_uploaded_pdf_satisfies_required_without_text(self):
        RecruitmentJobFieldRule.objects.create(
            job=self.job,
            field_key='limitation_reason',
            visibility_mode=VisibilityMode.ALWAYS,
            required_mode=RequiredMode.ALWAYS,
        )
        files = _recruitment_files()
        files['limitation_reason_file'] = _pdf('upload.pdf', b'%PDF uploaded reason')
        form = PersonnelRecruitmentTaskForm(
            data=_recruitment_data(self.job, limitation_reason=''),
            files=files,
            user=self.user,
            is_creation=True,
        )
        task = self._save_recruitment(form)
        self.assertFalse(task.limitation_reason_generated)
        self.assertEqual(task.limitation_reason, '')
        self.assertTrue(task.limitation_reason_file)
        self.assertTrue(task.limitation_reason_file.read().startswith(b'%PDF'))

    def test_non_pdf_upload_is_rejected(self):
        RecruitmentJobFieldRule.objects.create(
            job=self.job,
            field_key='limitation_reason',
            visibility_mode=VisibilityMode.ALWAYS,
            required_mode=RequiredMode.ALWAYS,
        )
        files = _recruitment_files()
        files['limitation_reason_file'] = SimpleUploadedFile(
            'reason.txt', b'not a pdf', content_type='text/plain',
        )
        form = PersonnelRecruitmentTaskForm(
            data=_recruitment_data(self.job, limitation_reason=''),
            files=files,
            user=self.user,
            is_creation=True,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('limitation_reason_file', form.errors)

    def test_text_change_regenerates_generated_pdf(self):
        form = PersonnelRecruitmentTaskForm(
            data=_recruitment_data(self.job, limitation_reason='First reason'),
            files=_recruitment_files(),
            user=self.user,
            is_creation=True,
        )
        task = self._save_recruitment(form)

        form = PersonnelRecruitmentTaskForm(
            data=_recruitment_data(self.job, limitation_reason='Second reason'),
            instance=task,
            user=self.user,
            is_creation=False,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        saved.refresh_from_db()
        self.assertTrue(saved.limitation_reason_generated)
        self.assertEqual(saved.limitation_reason, 'Second reason')
        payload = _pdf_payload(saved.limitation_reason_file.read())
        self.assertIn('Second reason', payload)
        self.assertNotIn('First reason', payload)

    def test_user_upload_is_not_replaced_by_empty_text(self):
        files = _recruitment_files()
        files['limitation_reason_file'] = _pdf('kept.pdf', b'%PDF keep-me')
        form = PersonnelRecruitmentTaskForm(
            data=_recruitment_data(self.job, limitation_reason=''),
            files=files,
            user=self.user,
            is_creation=True,
        )
        task = self._save_recruitment(form)
        original = task.limitation_reason_file.name

        form = PersonnelRecruitmentTaskForm(
            data=_recruitment_data(self.job, limitation_reason=''),
            instance=task,
            user=self.user,
            is_creation=False,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertFalse(saved.limitation_reason_generated)
        self.assertEqual(saved.limitation_reason_file.name, original)
        self.assertEqual(saved.limitation_reason_file.read(), b'%PDF keep-me')


@override_settings(MEDIA_ROOT='/tmp/therese_limitation_pdf_ext')
class ExtensionLimitationReasonPdfTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user('lim-ext', password='test')
        self.employee = Employee.objects.create(
            employee_number='E-LIM-EXT',
            first_name='Pat',
            last_name='Person',
            user=self.user,
        )
        self.creator = Employee.objects.create(
            employee_number='E-LIM-CRE',
            first_name='Creator',
            last_name='User',
        )

    def test_file_satisfies_required_when_limited(self):
        form = PersonnelContractExtensionTaskForm(
            data={
                'employee': self.employee.pk,
                'plan_position_number': 'POS-2',
                'valid_from': '01.01.2026',
                'valid_until': '31.12.2026',
                'is_limited': True,
                'limitation_reason': '',
                'status': 'not_yet_processed',
            },
            files={'limitation_reason_file': _pdf('ext.pdf', b'%PDF extension')},
            user=self.user,
            is_creation=True,
        )
        self.assertTrue(form.is_valid(), form.errors)
        task = form.save(commit=False)
        task.creator = self.creator
        task.task_type = 'personnel_contract_extension'
        task.save()
        self.assertFalse(task.limitation_reason_generated)
        self.assertTrue(task.limitation_reason_file)
        labels = {doc.label for doc in get_personnel_task_documents(task)}
        self.assertIn('Limitation Reason Person', labels)

    def test_text_generates_pdf_when_limited(self):
        form = PersonnelContractExtensionTaskForm(
            data={
                'employee': self.employee.pk,
                'plan_position_number': 'POS-2',
                'valid_from': '01.01.2026',
                'valid_until': '31.12.2026',
                'is_limited': True,
                'limitation_reason': 'Drittmittel enden',
                'status': 'not_yet_processed',
            },
            user=self.user,
            is_creation=True,
        )
        self.assertTrue(form.is_valid(), form.errors)
        task = form.save(commit=False)
        task.creator = self.creator
        task.task_type = 'personnel_contract_extension'
        task.save()
        self.assertTrue(task.limitation_reason_generated)
        content = task.limitation_reason_file.read()
        self.assertTrue(content.startswith(b'%PDF'))
        self.assertIn('Drittmittel enden', _pdf_payload(content))
