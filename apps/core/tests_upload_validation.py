from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile, SimpleUploadedFile
from django.test import TestCase

from apps.core.upload_validation import (
    PDF_EXT,
    sanitize_upload_name,
    upload_basename,
    validate_upload,
)
from apps.hr.document_utils import validate_personnel_document

TINY_PNG = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
    '0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082'
)


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

    def test_windows_client_path_is_basename(self):
        path = r'W:\office\Bilder Webseite\Beck\Katherina Abdo - Final.png'
        self.assertEqual(upload_basename(path), 'Katherina Abdo - Final.png')
        uploaded = SimpleUploadedFile(path, TINY_PNG, content_type='image/png')
        # Simulate Linux: os.path.basename does not strip backslashes.
        object.__setattr__(uploaded, '_name', path)
        sanitize_upload_name(uploaded)
        self.assertEqual(uploaded.name, 'Katherina Abdo - Final.png')
        validate_personnel_document(uploaded)

    def test_oversized_png_is_validation_error_not_crash(self):
        from io import BytesIO

        from apps.core.upload_validation import MAX_DEFAULT_UPLOAD_BYTES

        uploaded = InMemoryUploadedFile(
            BytesIO(TINY_PNG),
            None,
            'Katherina Abdo - Final.png',
            'image/png',
            MAX_DEFAULT_UPLOAD_BYTES + 1,
            None,
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_personnel_document(uploaded)
        self.assertIn('10 MB', str(ctx.exception))
