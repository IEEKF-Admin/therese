"""Generate and attach Limitation Reason PDFs from free text."""

from __future__ import annotations

import io
import re

from django.core.files.base import ContentFile
from django.db.models.fields.files import FieldFile
from django.template.loader import render_to_string

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def is_new_limitation_file(value) -> bool:
    if value in (None, False, ''):
        return False
    return not isinstance(value, FieldFile)


def limitation_subject_last_name(task) -> str:
    last = (getattr(task, 'last_name', None) or '').strip()
    if last:
        return last
    employee = getattr(task, 'employee', None)
    if employee is not None:
        return (getattr(employee, 'last_name', '') or '').strip()
    return ''


def limitation_pdf_filename(last_name: str) -> str:
    cleaned = _INVALID_FILENAME_CHARS.sub('', (last_name or '').strip()) or 'Unknown'
    return f'Limitation Reason {cleaned}.pdf'


def render_limitation_reason_pdf(text: str, *, last_name: str = '') -> bytes:
    from apps.core.models import GlobalSetting

    setting = GlobalSetting.get_solo()
    html = render_to_string('tasks/limitation_reason_pdf.html', {
        'letterhead': setting.limitation_pdf_letterhead or '',
        'text': text or '',
        'last_name': last_name or '',
    })
    from xhtml2pdf import pisa

    result = io.BytesIO()
    pdf = pisa.CreatePDF(html, dest=result, encoding='utf-8')
    if pdf.err:
        raise ValueError('PDF generation failed')
    return result.getvalue()


def attach_generated_limitation_pdf(task, text: str) -> None:
    last_name = limitation_subject_last_name(task)
    pdf_bytes = render_limitation_reason_pdf(text, last_name=last_name)
    filename = limitation_pdf_filename(last_name)
    if task.limitation_reason_file:
        task.limitation_reason_file.delete(save=False)
    task.limitation_reason_file.save(filename, ContentFile(pdf_bytes, name=filename), save=False)
    task.limitation_reason_generated = True


def apply_limitation_reason_pdf(task, cleaned_data: dict) -> None:
    text = (cleaned_data.get('limitation_reason') or '').strip()
    file_value = cleaned_data.get('limitation_reason_file')

    if is_new_limitation_file(file_value):
        task.limitation_reason_generated = False
        return

    if file_value is False:
        task.limitation_reason_generated = False
        if text:
            attach_generated_limitation_pdf(task, text)
        else:
            if task.limitation_reason_file:
                task.limitation_reason_file.delete(save=False)
            task.limitation_reason_file = None
        return

    has_existing = bool(getattr(task.limitation_reason_file, 'name', ''))
    if has_existing and not task.limitation_reason_generated:
        return

    if text:
        attach_generated_limitation_pdf(task, text)
        return

    if task.limitation_reason_generated:
        if task.limitation_reason_file:
            task.limitation_reason_file.delete(save=False)
        task.limitation_reason_file = None
        task.limitation_reason_generated = False
