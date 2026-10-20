from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, redirect

from apps.core.models import DocumentSource, ExtractedDocumentImage
from apps.core.services.document_image_extractor import run_extraction, get_allowed_roots, validate_source_path


def is_admin_or_staff(user):
    return user.is_staff or user.is_superuser


@login_required
@user_passes_test(is_admin_or_staff)
def extracted_document_images_list(request):
    allowed_roots = [str(path) for path in get_allowed_roots()]

    if request.method == 'POST':
        selected_root = (request.POST.get('selected_root') or '').strip()
        relative_subpath = (request.POST.get('relative_subpath') or '').strip().lstrip('/\\')
        dry_run = request.POST.get('dry_run') == 'on'
        skip_duplicates = request.POST.get('skip_duplicates') == 'on'
        recursive = request.POST.get('recursive') != 'off'
        limit_raw = (request.POST.get('limit') or '').strip()
        extensions = request.POST.getlist('extensions') or ['pdf', 'docx', 'doc']

        try:
            if selected_root not in allowed_roots:
                raise ValueError("Racine non autorisee")
            source_path = Path(selected_root)
            if relative_subpath:
                source_path = (source_path / relative_subpath).resolve()
            validate_source_path(str(source_path))
            limit = int(limit_raw) if limit_raw else None
            stats = run_extraction(
                str(source_path),
                recursive=recursive,
                extensions=extensions,
                limit=limit,
                dry_run=dry_run,
                skip_duplicates=skip_duplicates,
            )
            messages.success(
                request,
                f"Extraction terminee. Fichiers: {stats.found_files}, PDF: {stats.pdf_files}, DOCX: {stats.docx_files}, "
                f"images: {stats.extracted_images}, doublons: {stats.duplicate_images}, erreurs: {stats.errors}."
            )
        except Exception as exc:
            messages.error(request, f"Echec extraction: {exc}")
        return redirect('core:extracted_document_images_list')

    queryset = ExtractedDocumentImage.objects.select_related('document_source', 'duplicate_of').all()

    source_folder = request.GET.get('source_folder', '').strip()
    source_file = request.GET.get('source_file', '').strip()
    file_type = request.GET.get('file_type', '').strip()
    status = request.GET.get('status', '').strip()
    duplicate = request.GET.get('duplicate', '').strip()
    q = request.GET.get('q', '').strip()

    if source_folder:
        queryset = queryset.filter(document_source__source_folder_path=source_folder)
    if source_file:
        queryset = queryset.filter(document_source__source_file_name=source_file)
    if file_type:
        queryset = queryset.filter(document_source__file_type=file_type)
    if status:
        queryset = queryset.filter(status=status)
    if duplicate == 'yes':
        queryset = queryset.filter(is_duplicate=True)
    elif duplicate == 'no':
        queryset = queryset.filter(is_duplicate=False)
    if q:
        queryset = queryset.filter(
            Q(extracted_file_name__icontains=q) |
            Q(original_internal_name__icontains=q) |
            Q(document_source__source_file_name__icontains=q) |
            Q(document_source__source_file_path__icontains=q) |
            Q(document_source__relative_path__icontains=q)
        )

    paginator = Paginator(queryset, 40)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'source_folders': DocumentSource.objects.order_by().values_list('source_folder_path', flat=True).distinct(),
        'source_files': DocumentSource.objects.order_by().values_list('source_file_name', flat=True).distinct()[:200],
        'allowed_roots': allowed_roots,
        'filters': {
            'source_folder': source_folder,
            'source_file': source_file,
            'file_type': file_type,
            'status': status,
            'duplicate': duplicate,
            'q': q,
        },
    }
    return render(request, 'core/extracted_document_images_list.html', context)
