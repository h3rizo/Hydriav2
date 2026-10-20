from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, Http404
from django.db.models import Q
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
import uuid
import os
from .models import FileUpload, Tag
from .services import storage_service, generate_unique_filename, get_file_category


@login_required
def file_list(request):
    """
    Vue principale pour lister les fichiers avec recherche
    """
    files = FileUpload.objects.filter(is_active=True).select_related('uploaded_by').prefetch_related('tags')
    tags = Tag.objects.all().order_by('name')
    
    # Recherche par tags
    search_tags = request.GET.get('tags', '').strip()
    if search_tags:
        tag_names = [tag.strip() for tag in search_tags.split(',') if tag.strip()]
        if tag_names:
            files = files.filter(tags__name__in=tag_names).distinct()
    
    # Recherche par nom de fichier
    search_name = request.GET.get('name', '').strip()
    if search_name:
        files = files.filter(
            Q(filename__icontains=search_name) | 
            Q(original_filename__icontains=search_name) |
            Q(description__icontains=search_name)
        )
    
    # Pagination
    paginator = Paginator(files, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'files': page_obj.object_list,
        'tags': tags,
        'search_tags': search_tags,
        'search_name': search_name,
        'total_files': files.count(),
    }
    
    return render(request, 'filemanager/file_list.html', context)


@login_required
@require_http_methods(["POST"])
def file_upload(request):
    """
    Vue pour l'upload de fichiers
    """
    if not request.FILES.get('file'):
        messages.error(request, "Aucun fichier sélectionné")
        return redirect('filemanager:file_list')
    
    uploaded_file = request.FILES['file']
    description = request.POST.get('description', '').strip()
    tag_names = request.POST.get('tags', '').strip()
    is_public = request.POST.get('is_public') == 'on'
    
    # Validation de la taille (100MB max)
    if uploaded_file.size > 100 * 1024 * 1024:
        messages.error(request, "Le fichier ne peut pas dépasser 100MB")
        return redirect('filemanager:file_list')
    
    try:
        # Générer un nom unique et définir le chemin
        unique_filename = generate_unique_filename(uploaded_file.name)
        content_type = uploaded_file.content_type or 'application/octet-stream'
        file_category = get_file_category(content_type)
        supabase_path = f"{file_category}/{unique_filename}"
        
        # Upload vers Supabase Storage
        upload_success, upload_error = storage_service.upload_file(uploaded_file, supabase_path)
        
        if not upload_success:
            messages.error(request, f"Erreur lors de l'upload vers Supabase: {upload_error}")
            return redirect('filemanager:file_list')
        
        # Créer l'objet FileUpload seulement si l'upload Supabase a réussi
        file_obj = FileUpload.objects.create(
            filename=unique_filename,
            original_filename=uploaded_file.name,
            file_size=uploaded_file.size,
            content_type=content_type,
            supabase_path=supabase_path,
            description=description,
            uploaded_by=request.user,
            is_public=is_public
        )
        
        # Traiter les tags
        if tag_names:
            tag_list = [name.strip() for name in tag_names.split(',') if name.strip()]
            for tag_name in tag_list:
                tag, created = Tag.objects.get_or_create(
                    name=tag_name,
                    defaults={'created_by': request.user}
                )
                file_obj.tags.add(tag)
        
        messages.success(request, f"Fichier '{uploaded_file.name}' uploadé avec succès vers Supabase")
        
    except Exception as e:
        messages.error(request, f"Erreur lors de l'upload: {str(e)}")
    
    return redirect('filemanager:file_list')


@login_required
def file_download(request, file_id):
    """
    Vue pour télécharger un fichier depuis Supabase Storage
    """
    file_obj = get_object_or_404(FileUpload, id=file_id, is_active=True)
    
    # Vérifier les permissions
    if not file_obj.is_public and file_obj.uploaded_by != request.user:
        raise Http404("Fichier non trouvé")
    
    try:
        # Télécharger depuis Supabase Storage
        download_success, file_content, download_error = storage_service.download_file(file_obj.supabase_path)
        
        if not download_success:
            # Fallback: essayer de servir depuis local si Supabase échoue
            local_path = os.path.join('media', 'uploads', file_obj.filename)
            if os.path.exists(local_path):
                with open(local_path, 'rb') as f:
                    file_content = f.read()
            else:
                raise Http404("Fichier non trouvé")
        
        # Créer la réponse HTTP
        response = HttpResponse(file_content, content_type=file_obj.content_type)
        response['Content-Disposition'] = f'attachment; filename="{file_obj.original_filename}"'
        response['Content-Length'] = str(len(file_content))
        
        return response
        
    except Exception as e:
        raise Http404(f"Erreur lors du téléchargement: {str(e)}")


@login_required
@require_http_methods(["POST"])
def file_delete(request, file_id):
    """
    Vue pour supprimer un fichier
    """
    file_obj = get_object_or_404(FileUpload, id=file_id)
    
    # Vérifier les permissions
    if file_obj.uploaded_by != request.user and not request.user.is_staff:
        messages.error(request, "Vous n'avez pas le droit de supprimer ce fichier")
        return redirect('filemanager:file_list')
    
    filename = file_obj.original_filename
    file_obj.is_active = False
    file_obj.save()
    
    messages.success(request, f"Fichier '{filename}' supprimé avec succès")
    return redirect('filemanager:file_list')


def api_search_files(request):
    """
    API pour recherche AJAX de fichiers
    """
    search_tags = request.GET.get('tags', '').strip()
    search_name = request.GET.get('name', '').strip()
    
    files = FileUpload.objects.filter(is_active=True).select_related('uploaded_by').prefetch_related('tags')
    
    if search_tags:
        tag_names = [tag.strip() for tag in search_tags.split(',') if tag.strip()]
        if tag_names:
            files = files.filter(tags__name__in=tag_names).distinct()
    
    if search_name:
        files = files.filter(
            Q(filename__icontains=search_name) | 
            Q(original_filename__icontains=search_name) |
            Q(description__icontains=search_name)
        )
    
    # Limiter à 50 résultats pour l'API
    files = files[:50]
    
    results = []
    for file_obj in files:
        results.append({
            'id': str(file_obj.id),
            'filename': file_obj.filename,
            'original_filename': file_obj.original_filename,
            'file_size_mb': file_obj.file_size_mb,
            'tags': file_obj.tags_list,
            'uploaded_at': file_obj.uploaded_at.strftime('%d/%m/%Y %H:%M'),
            'uploaded_by': file_obj.uploaded_by.get_full_name() or file_obj.uploaded_by.username,
            'download_url': file_obj.get_download_url(),
        })
    
    return JsonResponse({
        'files': results,
        'count': len(results)
    })


def api_tags(request):
    """
    API pour autocomplete des tags
    """
    query = request.GET.get('q', '').strip()
    tags = Tag.objects.all()
    
    if query:
        tags = tags.filter(name__icontains=query)
    
    results = []
    for tag in tags[:20]:  # Limiter à 20 résultats
        results.append({
            'name': tag.name,
            'color': tag.color
        })
    
    return JsonResponse({'tags': results})
