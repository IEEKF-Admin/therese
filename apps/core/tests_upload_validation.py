from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.core.upload_validation import PDF_EXT, validate_upload
from apps.hr.document_utils import validate_personnel_document


class UploadValidationTests(TestCase):
    def test_pdf_valid_after_file_was_already_read(self):
        uploaded = SimpleUploadedFile(
            'doc.pdf',
            b'%PDF-1.7 content',
            content_type='application/pdf',
        )
        uploaded.read()
        self.assertEqual(uploaded.tell(), uploaded.size)
        validate_personnel_document(uploaded)

    def test_pdf_with_utf8_bom_is_accepted(self):
        uploaded = SimpleUploadedFile(
            'doc.pdf',
            b'\xef\xbb\xbf%PDF-1.4 content',
            content_type='application/pdf',
        )
        validate_upload(uploaded, allowed_extensions=PDF_EXT)

    def test_non_pdf_payload_is_rejected(self):
        uploaded = SimpleUploadedFile(
            'doc.pdf',
            b'<html>not a pdf</html>',
            content_type='application/pdf',
        )
        with self.assertRaises(ValidationError):
            validate_personnel_document(uploaded)
