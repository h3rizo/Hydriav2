import tempfile
import zipfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings

from apps.core.models import DocumentSource, ExtractedDocumentImage
from apps.core.services.document_image_extractor import (
    safe_output_filename,
    validate_source_path,
    process_document_file,
)


class DocumentExtractionUtilityTests(SimpleTestCase):
    def test_safe_output_filename_adds_hash_suffix_on_collision(self):
        filename = safe_output_filename('report_page_1_image_1', 'jpg', 'a8f32c123', exists_checker=lambda _: True)
        self.assertEqual(filename, 'report_page_1_image_1_a8f32c.jpg')

    @override_settings(DOCUMENT_EXTRACTION_ALLOWED_ROOTS=['C:/allowed'])
    def test_validate_source_path_rejects_outside_allowed_root(self):
        with self.assertRaises(ValueError):
            validate_source_path('C:/forbidden')


@override_settings(MEDIA_ROOT=Path(tempfile.gettempdir()) / 'hydria_test_media')
class DocumentExtractionPersistenceTests(TestCase):
    def test_doc_file_is_marked_unsupported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_root = Path(tmpdir)
            doc_path = source_root / 'sample.doc'
            doc_path.write_bytes(b'test')
            document_source, extracted, duplicates, errors = process_document_file(source_root, doc_path, dry_run=False)
            self.assertEqual(document_source.status, DocumentSource.STATUS_UNSUPPORTED)
            self.assertEqual(extracted, 0)
            self.assertEqual(duplicates, 0)
            self.assertEqual(errors, 0)

    def test_docx_duplicate_detection(self):
        png_bytes = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?'
            b'\x00\x05\xfe\x02\xfeA\xd9\x8f\xb1\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            source_root = Path(tmpdir)
            docx1 = source_root / 'a.docx'
            docx2 = source_root / 'b.docx'
            for docx_path in (docx1, docx2):
                with zipfile.ZipFile(docx_path, 'w') as archive:
                    archive.writestr('word/media/image1.png', png_bytes)
            process_document_file(source_root, docx1, dry_run=False)
            process_document_file(source_root, docx2, dry_run=False)
            self.assertEqual(ExtractedDocumentImage.objects.count(), 2)
            self.assertEqual(ExtractedDocumentImage.objects.filter(is_duplicate=True).count(), 1)
