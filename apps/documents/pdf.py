from django.template.loader import render_to_string
from django.http import HttpResponse


def render_document_pdf_response(version):
    html = render_to_string('documents/document_pdf.html', {'version': version})
    try:
        from xhtml2pdf import pisa
        import io

        result = io.BytesIO()
        pdf = pisa.CreatePDF(html, dest=result, encoding='utf-8')
        if pdf.err:
            raise ValueError('PDF generation failed')
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        filename = f'{version.document.title}_{version.version_label}.pdf'.replace(' ', '_')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception:
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = 'inline'
        return response