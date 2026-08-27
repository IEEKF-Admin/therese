"""Generate a printable holiday request PDF."""

import io

from django.template.loader import render_to_string


def render_request_pdf(request, *, signed=False):
    from apps.holidays.models import HolidayProfile

    applicant_sig = ''
    approver_sig = ''
    profile = HolidayProfile.objects.filter(employee=request.employee).first()
    if signed and profile and profile.signature:
        applicant_sig = profile.signature.url if hasattr(profile.signature, 'url') else ''
        # xhtml2pdf cannot fetch /media/ easily; embed via storage path later if needed.
        applicant_sig = _data_uri(profile.signature)
    if signed and request.decided_by:
        approver_emp = getattr(request.decided_by, 'employee', None)
        if approver_emp:
            ap = HolidayProfile.objects.filter(employee=approver_emp).first()
            if ap and ap.signature:
                approver_sig = _data_uri(ap.signature)

    html = render_to_string('holidays/pdf_request.html', {
        'request': request,
        'employee': request.employee,
        'signed': signed,
        'applicant_sig': applicant_sig,
        'approver_sig': approver_sig,
        'counted': request.counted_dates or [],
    })
    try:
        from xhtml2pdf import pisa
        result = io.BytesIO()
        pdf = pisa.CreatePDF(html, dest=result, encoding='utf-8')
        if pdf.err:
            raise ValueError('PDF generation failed')
        return result.getvalue()
    except Exception:
        return html.encode('utf-8')


def _data_uri(image_field):
    try:
        image_field.open('rb')
        data = image_field.read()
        image_field.close()
    except Exception:
        return ''
    import base64
    b64 = base64.b64encode(data).decode('ascii')
    return f'data:image/png;base64,{b64}'
