import hashlib
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image

from apps.core.models import DocumentSource, ExtractedDocumentImage


SUPPORTED_DOCX_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp'}


@dataclass
class ExtractionStats:
    found_files: int = 0
    pdf_files: int = 0
    docx_files: int = 0
    ignored_files: int = 0
    extracted_images: int = 0
    duplicate_images: int = 0
    errors: int = 0
    unsupported_files: int = 0


def get_allowed_roots():
    roots = getattr(settings, 'DOCUMENT_EXTRACTION_ALLOWED_ROOTS', None)
    if roots:
        return [Path(root).resolve() for root in roots]
    return [settings.BASE_DIR.resolve()]


def validate_source_path(source):
    source_path = Path(source).expanduser().resolve()
    allowed_roots = get_allowed_roots()
    if not any(_is_relative_to(source_path, root) for root in allowed_roots):
        raise ValueError("Source path is outside allowed roots")
    if not source_path.exists() or not source_path.is_dir():
        raise ValueError("Source path does not exist or is not a directory")
    return source_path


def _is_relative_to(target: Path, parent: Path) -> bool:
    try:
        target.relative_to(parent)
        return True
    except ValueError:
        return False


def calculate_file_hash(file_path):
    sha = hashlib.sha256()
    with open(file_path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def calculate_bytes_hash(data):
    return hashlib.sha256(data).hexdigest()


def get_image_dimensions(data):
    try:
        with Image.open(BytesIO(data)) as image:
            return image.size
    except Exception:
        return None, None


def safe_output_filename(base_name, extension, hash_value='', exists_checker=None):
    ext = extension if str(extension).startswith('.') else f'.{extension}'
    candidate = f"{base_name}{ext}"
    if exists_checker and exists_checker(candidate):
        suffix = (hash_value or '')[:6] or datetime.now().strftime('%H%M%S')
        candidate = f"{base_name}_{suffix}{ext}"
    return candidate


def _build_storage_relpath(document_source, filename):
    source_name = Path(document_source.source_file_name).stem
    month_path = datetime.now().strftime('%Y/%m')
    return Path('extracted_documents') / month_path / source_name / filename


def _save_extracted_image(document_source, image_bytes, image_extension, base_name, image_index, page_number=None,
                          original_internal_name='', dry_run=False, skip_duplicates=False):
    image_hash = calculate_bytes_hash(image_bytes)
    width, height = get_image_dimensions(image_bytes)
    existing = ExtractedDocumentImage.objects.filter(image_hash_sha256=image_hash).first()
    is_duplicate = existing is not None
    status = ExtractedDocumentImage.STATUS_DUPLICATE if is_duplicate else ExtractedDocumentImage.STATUS_EXTRACTED

    normalized_ext = image_extension.lower().lstrip('.')
    output_dir = Path(settings.MEDIA_ROOT) / _build_storage_relpath(document_source, '').parent
    filename_base = base_name
    filename = safe_output_filename(
        filename_base,
        normalized_ext,
        image_hash,
        exists_checker=lambda candidate: (output_dir / candidate).exists(),
    )

    image_record = ExtractedDocumentImage(
        document_source=document_source,
        extracted_file_name=filename,
        original_internal_name=original_internal_name or '',
        source_page_number=page_number,
        image_index=image_index,
        image_extension=normalized_ext,
        image_size=len(image_bytes),
        width=width,
        height=height,
        image_hash_sha256=image_hash,
        is_duplicate=is_duplicate,
        duplicate_of=existing if is_duplicate else None,
        status=status,
    )

    if not dry_run and not (is_duplicate and skip_duplicates):
        image_record.image_file.save(filename, ContentFile(image_bytes), save=False)

    if not dry_run:
        image_record.save()

    return image_record, is_duplicate


def extract_pdf_images(document_source, file_path, dry_run=False, skip_duplicates=False):
    import fitz
    extracted = 0
    duplicates = 0
    with fitz.open(file_path) as document:
        for page_number in range(len(document)):
            page = document.load_page(page_number)
            for image_index, image_info in enumerate(page.get_images(full=True), start=1):
                xref = image_info[0]
                image_dict = document.extract_image(xref)
                image_bytes = image_dict.get('image')
                extension = image_dict.get('ext') or 'png'
                if not image_bytes:
                    continue
                base_name = f"{Path(document_source.source_file_name).stem}_page_{page_number + 1}_image_{image_index}"
                _, is_duplicate = _save_extracted_image(
                    document_source=document_source,
                    image_bytes=image_bytes,
                    image_extension=extension,
                    base_name=base_name,
                    image_index=image_index,
                    page_number=page_number + 1,
                    original_internal_name=f"xref:{xref}",
                    dry_run=dry_run,
                    skip_duplicates=skip_duplicates,
                )
                extracted += 1
                if is_duplicate:
                    duplicates += 1
    return extracted, duplicates


def extract_docx_images(document_source, file_path, dry_run=False, skip_duplicates=False):
    extracted = 0
    duplicates = 0
    with zipfile.ZipFile(file_path, 'r') as archive:
        media_entries = [name for name in archive.namelist() if name.startswith('word/media/')]
        for image_index, internal_name in enumerate(media_entries, start=1):
            extension = Path(internal_name).suffix.lower()
            if extension not in SUPPORTED_DOCX_IMAGE_EXTENSIONS:
                continue
            image_bytes = archive.read(internal_name)
            base_name = f"{Path(document_source.source_file_name).stem}_image_{image_index}"
            _, is_duplicate = _save_extracted_image(
                document_source=document_source,
                image_bytes=image_bytes,
                image_extension=extension,
                base_name=base_name,
                image_index=image_index,
                original_internal_name=internal_name,
                dry_run=dry_run,
                skip_duplicates=skip_duplicates,
            )
            extracted += 1
            if is_duplicate:
                duplicates += 1
    return extracted, duplicates


def process_document_file(source_root, file_path, dry_run=False, skip_duplicates=False):
    source_root = Path(source_root).resolve()
    file_path = Path(file_path).resolve()
    relative_path = str(file_path.relative_to(source_root))
    file_type = file_path.suffix.lower().lstrip('.')
    defaults = {
        'source_file_name': file_path.name,
        'source_folder_path': str(file_path.parent),
        'relative_path': relative_path,
        'file_type': file_type,
        'file_size': file_path.stat().st_size if file_path.exists() else 0,
        'file_hash_sha256': calculate_file_hash(file_path) if file_path.exists() else '',
        'status': DocumentSource.STATUS_PENDING,
        'error_message': '',
    }

    if dry_run:
        document_source = DocumentSource(
            source_file_path=str(file_path),
            **defaults,
        )
    else:
        document_source, _ = DocumentSource.objects.update_or_create(
            source_file_path=str(file_path),
            defaults=defaults,
        )

    if file_type == 'doc':
        document_source.status = DocumentSource.STATUS_UNSUPPORTED
        document_source.error_message = "Format .doc non pris en charge. Convertir en .docx avant extraction."
        if not dry_run:
            document_source.save(update_fields=['status', 'error_message'])
        return document_source, 0, 0, 0

    try:
        if file_type == 'pdf':
            extracted, duplicates = extract_pdf_images(document_source, file_path, dry_run=dry_run, skip_duplicates=skip_duplicates)
        elif file_type == 'docx':
            extracted, duplicates = extract_docx_images(document_source, file_path, dry_run=dry_run, skip_duplicates=skip_duplicates)
        else:
            document_source.status = DocumentSource.STATUS_UNSUPPORTED
            document_source.error_message = f"Unsupported extension: .{file_type}"
            if not dry_run:
                document_source.save(update_fields=['status', 'error_message'])
            return document_source, 0, 0, 0

        document_source.images_count = extracted
        document_source.status = DocumentSource.STATUS_EXTRACTED
        if not dry_run:
            document_source.save(update_fields=['images_count', 'status'])
        return document_source, extracted, duplicates, 0
    except Exception as exc:
        document_source.status = DocumentSource.STATUS_ERROR
        document_source.error_message = str(exc)
        if not dry_run:
            document_source.save(update_fields=['status', 'error_message'])
        return document_source, 0, 0, 1


def iter_source_files(source_root, recursive=True, extensions=None, limit=None):
    source_root = Path(source_root).resolve()
    patterns = ('**/*' if recursive else '*')
    normalized_extensions = {f".{ext.lower().lstrip('.')}" for ext in (extensions or ['pdf', 'docx', 'doc'])}
    count = 0
    for file_path in source_root.glob(patterns):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in normalized_extensions:
            continue
        yield file_path
        count += 1
        if limit and count >= limit:
            break


def run_extraction(source_root, recursive=True, extensions=None, limit=None, dry_run=False, skip_duplicates=False):
    validated_root = validate_source_path(source_root)
    stats = ExtractionStats()
    for file_path in iter_source_files(validated_root, recursive=recursive, extensions=extensions, limit=limit):
        stats.found_files += 1
        suffix = file_path.suffix.lower()
        if suffix == '.pdf':
            stats.pdf_files += 1
        elif suffix == '.docx':
            stats.docx_files += 1
        elif suffix == '.doc':
            stats.unsupported_files += 1
        _, extracted, duplicates, errors = process_document_file(
            validated_root,
            file_path,
            dry_run=dry_run,
            skip_duplicates=skip_duplicates,
        )
        stats.extracted_images += extracted
        stats.duplicate_images += duplicates
        stats.errors += errors
    return stats
