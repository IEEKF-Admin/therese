"""
Collect and serve downloadable documents for personnel tasks.
"""

import io
import re
import zipfile
from dataclasses import dataclass
from django.utils import timezone

PERSONNEL_TASK_TYPES = (
    'personnel_recruitment',
    'personnel_reallocation',
    'personnel_contract_extension',
)

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class PersonnelTaskDocument:
    key: str
    label: str
    download_filename: str
    file_name: str

    def open(self):
        from apps.core.file_service import ThereseFileService

        return ThereseFileService.open(self.file_name, 'rb')


def can_download_personnel_documents(user):
    """Only Personnel Coordination or Approval rights (not creator/assignee alone)."""
    if not user or not user.is_authenticated:
        return False
    return (
        user.has_perm('tasks.view_all_personnel_tasks')
        or user.has_perm('tasks.approve_personnel_task')
    )


def _sanitize_filename_part(value):
    cleaned = _INVALID_FILENAME_CHARS.sub('', (value or '').strip())
    return cleaned or 'Unbekannt'


def _person_title(prefix, last_name):
    prefix = (prefix or '').strip()
    last_name = (last_name or '').strip()
    if prefix and last_name:
        return f'{prefix} {last_name}'
    return last_name or prefix or 'Unbekannt'


def _format_task_date(task):
    created_at = task.created_at
    if timezone.is_aware(created_at):
        created_at = timezone.localtime(created_at)
    return created_at.strftime('%d.%m.%Y')


def _file_extension(file_field):
    if not file_field or not file_field.name:
        return ''
    name = file_field.name.rsplit('/', 1)[-1]
    if '.' not in name:
        return ''
    return name.rsplit('.', 1)[-1].lower()


def build_download_filename(category, prefix, last_name, task, extension):
    title = _sanitize_filename_part(_person_title(prefix, last_name))
    category = _sanitize_filename_part(category)
    date_part = _format_task_date(task)
    ext = (extension or 'bin').lstrip('.')
    return f'{category} - {title} - {date_part}.{ext}'


def _add_file_document(documents, *, key, label, file_field, prefix, last_name, task):
    if not file_field or not file_field.name:
        return
    documents.append(
        PersonnelTaskDocument(
            key=key,
            label=label,
            download_filename=build_download_filename(
                label,
                prefix,
                last_name,
                task,
                _file_extension(file_field),
            ),
            file_name=file_field.name,
        )
    )


def _recruitment_documents(task):
    documents = []
    prefix = task.prefix
    last_name = task.last_name

    _add_file_document(
        documents,
        key='cv',
        label='Lebenslauf',
        file_field=task.cv_file,
        prefix=prefix,
        last_name=last_name,
        task=task,
    )
    _add_file_document(
        documents,
        key='degree_certificate',
        label='Zeugnis des letzten Abschlusses',
        file_field=task.latest_degree_certificate_file,
        prefix=prefix,
        last_name=last_name,
        task=task,
    )

    seen_wbs_ids = set()
    for allocation in task.funding_allocations.select_related('wbs_element').all():
        wbs = allocation.wbs_element
        if wbs.pk in seen_wbs_ids:
            continue
        seen_wbs_ids.add(wbs.pk)
        category = f'Drittmittelzusage {wbs.wbs_code}'
        _add_file_document(
            documents,
            key=f'psp_{wbs.pk}',
            label=category,
            file_field=wbs.third_party_funding_commitment,
            prefix=prefix,
            last_name=last_name,
            task=task,
        )

    return documents


def _reallocation_documents(task):
    documents = []
    employee = task.employee
    prefix = getattr(employee, 'prefix', '') or ''
    last_name = employee.last_name
    wbs = task.target_wbs
    if wbs and wbs.third_party_funding_commitment:
        category = f'Drittmittelzusage {wbs.wbs_code}'
        _add_file_document(
            documents,
            key=f'psp_{wbs.pk}',
            label=category,
            file_field=wbs.third_party_funding_commitment,
            prefix=prefix,
            last_name=last_name,
            task=task,
        )
    return documents


def get_personnel_task_documents(task):
    if task.task_type not in PERSONNEL_TASK_TYPES:
        return []

    if task.task_type == 'personnel_recruitment':
        return _recruitment_documents(task)
    if task.task_type == 'personnel_reallocation':
        return _reallocation_documents(task)
    return []


def get_personnel_document_by_key(task, doc_key):
    for document in get_personnel_task_documents(task):
        if document.key == doc_key:
            return document
    return None


def build_zip_filename(task):
    if task.task_type == 'personnel_recruitment':
        title = _person_title(task.prefix, task.last_name)
    elif hasattr(task, 'employee') and task.employee_id:
        employee = task.employee
        title = _person_title(getattr(employee, 'prefix', ''), employee.last_name)
    else:
        title = task.task_number or task.title or 'Task'

    title = _sanitize_filename_part(title)
    task_ref = _sanitize_filename_part(task.task_number or str(task.pk))
    return f'Personalunterlagen {task_ref} - {title}.zip'


def build_zip_response(task):
    documents = get_personnel_task_documents(task)
    if not documents:
        return None

    buffer = io.BytesIO()
    used_names = set()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for document in documents:
            archive_name = document.download_filename
            if archive_name in used_names:
                stem, dot, ext = archive_name.rpartition('.')
                counter = 2
                while archive_name in used_names:
                    archive_name = f'{stem} ({counter}).{ext}' if dot else f'{archive_name} ({counter})'
                    counter += 1
            used_names.add(archive_name)
            with document.open() as file_handle:
                archive.writestr(archive_name, file_handle.read())

    buffer.seek(0)
    return buffer, build_zip_filename(task)