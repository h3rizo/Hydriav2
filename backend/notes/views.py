import json
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_GET, require_POST

from apps.organization.models import Base, Ouvrage
from apps.billing.models import PointEau
from apps.employees.models import Employe
from apps.geography.models import Commune, Village
from apps.inventory.models import Stock
from apps.inventory.models_vehicles import ReparationVehicule
from apps.organization.models import Magasin, Organisation
from apps.planning.models import Planning, Designation

from .models import (
    Note,
    NoteAttachment,
    NoteComment,
    NoteDecision,
    NoteLink,
    NoteTask,
    NoteVersion,
    Tag,
)


DEFAULT_TAGS = [
    ('Recouvrement', '#0f766e'),
    ('Réparation', '#dc2626'),
    ('Exploitation', '#2563eb'),
    ('Planning', '#7c3aed'),
    ('Stock', '#b45309'),
    ('RH', '#db2777'),
    ('Finance', '#1d4ed8'),
    ('Relation commune', '#0d9488'),
    ('Partenaire', '#4f46e5'),
    ('Réclamation', '#ea580c'),
    ('Qualité de service', '#16a34a'),
    ('Décision stratégique', '#4338ca'),
    ('Suivi terrain', '#0891b2'),
    ('Urgence', '#b91c1c'),
]

ENTITY_REGISTRY = {
    'ouvrage': {
        'model': Ouvrage,
        'label': lambda obj: getattr(obj, 'nom_ouvrage', None) or str(obj),
        'url': lambda obj: reverse('core:search_detail', args=['ouvrage', str(obj.id)]),
    },
    'point_eau': {
        'model': PointEau,
        'label': lambda obj: getattr(obj, 'nomabonne', None) or getattr(obj, 'code_point_eau', None) or str(obj),
        'url': lambda obj: reverse('core:search_detail', args=['point_eau', str(obj.id)]),
    },
    'abonne': {
        'model': PointEau,
        'label': lambda obj: getattr(obj, 'nomabonne', None) or getattr(obj, 'code_point_eau', None) or str(obj),
        'url': lambda obj: reverse('core:search_detail', args=['point_eau', str(obj.id)]),
    },
    'village': {
        'model': Village,
        'label': lambda obj: getattr(obj, 'nom_village', None) or str(obj),
        'url': lambda obj: reverse('core:search_detail', args=['village', str(obj.id)]),
    },
    'commune': {
        'model': Commune,
        'label': lambda obj: getattr(obj, 'nom_commune', None) or str(obj),
        'url': lambda obj: reverse('core:search_detail', args=['commune', str(obj.id)]),
    },
    'planning': {
        'model': Planning,
        'label': lambda obj: getattr(obj, 'activite_display', None) or f'Planning {obj.id}',
        'url': lambda obj: reverse('core:search_detail', args=['planning', str(obj.id)]),
    },
    'agent': {
        'model': Employe,
        'label': lambda obj: getattr(obj, 'nom_affichage', None) or getattr(obj, 'nom_complet', None) or str(obj),
        'url': lambda obj: reverse('core:search_detail', args=['employe', str(obj.id)]),
    },
    'magasin': {
        'model': Magasin,
        'label': lambda obj: getattr(obj, 'nom_magasin', None) or str(obj),
        'url': None,
    },
    'article_stock': {
        'model': Designation,
        'label': lambda obj: getattr(obj, 'nom', None) or str(obj),
        'url': lambda obj: reverse('core:search_detail', args=['designation', str(obj.id)]),
    },
    'reparation': {
        'model': ReparationVehicule,
        'label': lambda obj: getattr(obj, 'libelle', None) or f'Réparation {obj.id}',
        'url': lambda obj: reverse('inventory:reparation_planifiee_detail', args=[str(obj.id)]),
    },
    'partenaire': {
        'model': Organisation,
        'label': lambda obj: getattr(obj, 'nom_organisation', None) or str(obj),
        'url': None,
    },
    'stock': {
        'model': Stock,
        'label': lambda obj: getattr(getattr(obj, 'designation', None), 'nom', None) or str(obj),
        'url': None,
    },
}


def _seed_default_tags():
    for name, color in DEFAULT_TAGS:
        Tag.objects.get_or_create(
            slug=slugify(name),
            defaults={'name': name, 'color': color, 'is_system': True}
        )


def _normalize_blocks(raw_blocks):
    if isinstance(raw_blocks, str):
        try:
            raw_blocks = json.loads(raw_blocks)
        except json.JSONDecodeError:
            raw_blocks = []
    if not isinstance(raw_blocks, list):
        raw_blocks = []

    normalized = []
    for index, block in enumerate(raw_blocks, start=1):
        if not isinstance(block, dict):
            continue
        block_type = (block.get('type') or 'paragraph').strip().lower()
        text = str(block.get('text') or '').strip()
        checked = bool(block.get('checked'))
        meta = block.get('meta') or {}
        normalized.append({
            'id': block.get('id') or f'block-{index}',
            'type': block_type,
            'text': text,
            'checked': checked,
            'meta': meta if isinstance(meta, dict) else {},
        })
    return normalized


def _blocks_to_text(blocks):
    lines = []
    for block in blocks:
        text = block.get('text', '').strip()
        meta = block.get('meta') or {}
        block_type = block.get('type')
        if block_type == 'checklist':
            prefix = '[x]' if block.get('checked') else '[ ]'
            lines.append(f'{prefix} {text}'.strip())
        elif block_type == 'hydria_link':
            entity_type = meta.get('entity_type') or ''
            entity_id = meta.get('entity_id') or ''
            label = meta.get('label') or text
            lines.append(f'{label} ({entity_type}:{entity_id})'.strip())
        else:
            if text:
                lines.append(text)
    return '\n'.join(lines).strip()


def _user_base(user):
    employe = getattr(user, 'employe', None)
    return getattr(employe, 'base', None)


def _user_role_name(user):
    employe = getattr(user, 'employe', None)
    poste = getattr(employe, 'poste', None)
    return (getattr(poste, 'nom_poste', '') or '').strip()


def _accessible_notes_queryset(user):
    qs = Note.objects.select_related(
        'parent',
        'created_by',
        'updated_by',
        'shared_with_base',
    ).prefetch_related(
        'tags',
        'links',
        'favorited_by',
    )
    if getattr(user, 'is_superuser', False):
        return qs

    filters = Q(created_by=user) | Q(visibility='all')
    base = _user_base(user)
    role_name = _user_role_name(user)
    if base:
        filters |= Q(visibility='antenne', shared_with_base=base)
        filters |= Q(visibility='team', shared_with_base=base)
    if role_name:
        filters |= Q(visibility='role', visible_role_name__iexact=role_name)
    return qs.filter(filters).distinct()


def _resolved_link_payload(link):
    registry = ENTITY_REGISTRY.get(link.entity_type)
    url = ''
    resolved_label = link.label
    if registry:
        model = registry['model']
        obj = model.objects.filter(pk=link.entity_id).first()
        if obj:
            resolved_label = registry['label'](obj)
            url_builder = registry.get('url')
            if callable(url_builder):
                url = url_builder(obj)
    return {
        'entity_type': link.entity_type,
        'entity_id': link.entity_id,
        'label': resolved_label or link.label or f'{link.entity_type}:{link.entity_id}',
        'url': url,
    }


def _sync_blocks_support_objects(note, user):
    note.tasks.all().delete()
    note.decisions.all().delete()

    for block in note.content_json or []:
        block_type = block.get('type')
        text = (block.get('text') or '').strip()
        meta = block.get('meta') or {}
        if block_type == 'action' and text:
            NoteTask.objects.create(
                note=note,
                title=text[:255],
                description=meta.get('description', ''),
                due_date=meta.get('due_date') or None,
                status=meta.get('status') or 'todo',
                entity_type=meta.get('entity_type', ''),
                entity_id=meta.get('entity_id', ''),
            )
        if block_type == 'decision' and text:
            NoteDecision.objects.create(
                note=note,
                decision_text=text,
                context=meta.get('context', ''),
                justification=meta.get('justification', ''),
                status=meta.get('status') or 'draft',
                entity_type=meta.get('entity_type', ''),
                entity_id=meta.get('entity_id', ''),
            )


def _replace_tags(note, raw_tags):
    tag_names = []
    for value in (raw_tags or '').split(','):
        cleaned = value.strip()
        if cleaned:
            tag_names.append(cleaned)

    tags = []
    for name in tag_names:
        tag, _ = Tag.objects.get_or_create(
            slug=slugify(name),
            defaults={'name': name, 'color': '#2563eb'}
        )
        if tag.name != name:
            tag.name = name
            tag.save(update_fields=['name'])
        tags.append(tag)
    note.tags.set(tags)


def _replace_links(note, raw_links):
    if isinstance(raw_links, str):
        try:
            raw_links = json.loads(raw_links)
        except json.JSONDecodeError:
            raw_links = []
    if not isinstance(raw_links, list):
        raw_links = []

    note.links.all().delete()
    for item in raw_links:
        if not isinstance(item, dict):
            continue
        entity_type = str(item.get('entity_type') or '').strip().lower()
        entity_id = str(item.get('entity_id') or '').strip()
        label = str(item.get('label') or '').strip()
        if not entity_type or not entity_id:
            continue
        NoteLink.objects.create(
            note=note,
            entity_type=entity_type,
            entity_id=entity_id,
            label=label,
        )


def _append_attachments(note, request):
    for uploaded_file in request.FILES.getlist('attachments'):
        NoteAttachment.objects.create(
            note=note,
            file=uploaded_file,
            label=getattr(uploaded_file, 'name', '')[:255],
            uploaded_by=request.user,
        )


def _build_note_tree(notes):
    children_map = defaultdict(list)
    roots = []
    for note in notes:
        if note.parent_id:
            children_map[str(note.parent_id)].append(note)
        else:
            roots.append(note)

    flat = []

    def walk(node, depth):
        flat.append((node, depth))
        for child in sorted(children_map.get(str(node.id), []), key=lambda item: item.title.lower()):
            walk(child, depth + 1)

    for root in sorted(roots, key=lambda item: item.title.lower()):
        walk(root, 0)
    return flat


def _note_from_request(request, note=None):
    note = note or Note(created_by=request.user, updated_by=request.user)
    blocks = _normalize_blocks(request.POST.get('content_json', '[]'))
    note.title = (request.POST.get('title') or '').strip() or 'Sans titre'
    note.parent_id = (request.POST.get('parent_id') or '') or None
    note.note_type = (request.POST.get('note_type') or 'note').strip()
    note.visibility = (request.POST.get('visibility') or 'private').strip()
    note.status = (request.POST.get('status') or 'active').strip()
    note.content_json = blocks
    note.content_text = _blocks_to_text(blocks)
    note.is_archived = str(request.POST.get('is_archived', '')).lower() in ('1', 'true', 'on', 'yes')
    note.is_favorite = str(request.POST.get('is_favorite', '')).lower() in ('1', 'true', 'on', 'yes')
    note.team_label = (request.POST.get('team_label') or '').strip()
    note.visible_role_name = (request.POST.get('visible_role_name') or '').strip()
    shared_with_base_id = (request.POST.get('shared_with_base_id') or '').strip()
    note.shared_with_base = Base.objects.filter(id=shared_with_base_id).first() if shared_with_base_id else None
    note.updated_by = request.user
    note.save()
    _replace_tags(note, request.POST.get('tags', ''))
    _replace_links(note, request.POST.get('linked_entities_json', '[]'))
    _sync_blocks_support_objects(note, request.user)
    _append_attachments(note, request)
    return note


@login_required
def workspace(request):
    _seed_default_tags()
    notes_qs = _accessible_notes_queryset(request.user)

    q = (request.GET.get('q') or '').strip()
    tag_filter = (request.GET.get('tag') or '').strip()
    note_type_filter = (request.GET.get('note_type') or '').strip()
    entity_type_filter = (request.GET.get('entity_type') or '').strip()
    creator_filter = (request.GET.get('creator') or '').strip()
    archive_filter = request.GET.get('archive') == '1'
    favorites_only = request.GET.get('favorites') == '1'
    open_actions_only = request.GET.get('open_actions') == '1'

    if not archive_filter:
        notes_qs = notes_qs.filter(is_archived=False)
    if q:
        notes_qs = notes_qs.filter(
            Q(title__icontains=q) |
            Q(content_text__icontains=q) |
            Q(tags__name__icontains=q) |
            Q(links__label__icontains=q)
        ).distinct()
    if tag_filter:
        notes_qs = notes_qs.filter(tags__slug=tag_filter)
    if note_type_filter:
        notes_qs = notes_qs.filter(note_type=note_type_filter)
    if entity_type_filter:
        notes_qs = notes_qs.filter(links__entity_type=entity_type_filter)
    if creator_filter:
        notes_qs = notes_qs.filter(created_by_id=creator_filter)
    if favorites_only:
        notes_qs = notes_qs.filter(favorited_by=request.user)
    if open_actions_only:
        notes_qs = notes_qs.filter(tasks__status__in=['todo', 'in_progress']).distinct()

    note_id = (request.GET.get('note_id') or '').strip()
    selected_note = notes_qs.filter(id=note_id).first() if note_id else None
    if not selected_note:
        selected_note = notes_qs.order_by('-updated_at').first()

    selected_payload = None
    if selected_note:
        selected_payload = {
            'note': selected_note,
            'blocks': selected_note.content_json or [],
            'tags_csv': ', '.join(selected_note.tags.values_list('name', flat=True)),
            'resolved_links': [_resolved_link_payload(link) for link in selected_note.links.all()],
            'versions': selected_note.versions.select_related('saved_by')[:10],
            'tasks': selected_note.tasks.select_related('assignee').all(),
            'decisions': selected_note.decisions.select_related('responsible').all(),
            'comments': selected_note.comments.select_related('author').all(),
            'attachments': selected_note.attachments.select_related('uploaded_by').all(),
        }

    notes_for_tree = list(
        _accessible_notes_queryset(request.user)
        .filter(is_archived=False)
        .order_by('title')
    )

    context = {
        'title': 'Notes Hydria',
        'notes_tree': _build_note_tree(notes_for_tree),
        'selected_note_payload': selected_payload,
        'recent_notes': _accessible_notes_queryset(request.user).filter(is_archived=False).order_by('-updated_at')[:8],
        'favorite_notes': _accessible_notes_queryset(request.user).filter(favorited_by=request.user, is_archived=False).order_by('-updated_at')[:8],
        'archived_notes': _accessible_notes_queryset(request.user).filter(is_archived=True).order_by('-updated_at')[:8],
        'template_notes': _accessible_notes_queryset(request.user).filter(is_template=True, is_archived=False).order_by('title')[:20],
        'all_tags': Tag.objects.all(),
        'bases': Base.objects.all().order_by('nom_base'),
        'employees': Employe.objects.filter(date_debauchage__isnull=True, user__isnull=False).select_related('user').order_by('surnom', 'nom_employe'),
        'creators': _accessible_notes_queryset(request.user).exclude(created_by__isnull=True).values('created_by_id', 'created_by__username').distinct(),
        'filters': {
            'q': q,
            'tag': tag_filter,
            'note_type': note_type_filter,
            'entity_type': entity_type_filter,
            'creator': creator_filter,
            'archive': archive_filter,
            'favorites': favorites_only,
            'open_actions': open_actions_only,
        },
        'note_type_choices': Note.NOTE_TYPE_CHOICES,
        'status_choices': Note.STATUS_CHOICES,
        'visibility_choices': Note.VISIBILITY_CHOICES,
        'entity_type_choices': sorted(ENTITY_REGISTRY.keys()),
        'prefill_entity': {
            'entity_type': (request.GET.get('entity_type') or '').strip(),
            'entity_id': (request.GET.get('entity_id') or '').strip(),
            'label': (request.GET.get('label') or '').strip(),
        },
    }
    return render(request, 'notes/workspace.html', context)


@login_required
@require_POST
def create_note(request):
    note = _note_from_request(request)
    note.is_template = str(request.POST.get('is_template', '')).lower() in ('1', 'true', 'on', 'yes')
    note.save(update_fields=['is_template'])
    if request.POST.get('mark_favorite'):
        note.favorited_by.add(request.user)
    messages.success(request, 'Note créée.')
    return redirect(f"{reverse('notes:workspace')}?note_id={note.id}")


@login_required
@require_POST
def update_note(request, note_id):
    note = get_object_or_404(_accessible_notes_queryset(request.user), id=note_id)
    NoteVersion.objects.create(
        note=note,
        title=note.title,
        content_json=note.content_json,
        content_text=note.content_text,
        saved_by=request.user,
    )
    updated_note = _note_from_request(request, note=note)
    updated_note.is_template = str(request.POST.get('is_template', '')).lower() in ('1', 'true', 'on', 'yes')
    updated_note.save(update_fields=['is_template'])
    messages.success(request, 'Note mise à jour.')
    return redirect(f"{reverse('notes:workspace')}?note_id={updated_note.id}")


@login_required
@require_POST
def restore_version(request, version_id):
    version = get_object_or_404(
        NoteVersion.objects.select_related('note'),
        id=version_id,
        note__in=_accessible_notes_queryset(request.user),
    )
    note = version.note
    NoteVersion.objects.create(
        note=note,
        title=note.title,
        content_json=note.content_json,
        content_text=note.content_text,
        saved_by=request.user,
    )
    note.title = version.title or note.title
    note.content_json = version.content_json or []
    note.content_text = version.content_text or ''
    note.updated_by = request.user
    note.save(update_fields=['title', 'content_json', 'content_text', 'updated_by', 'updated_at'])
    _sync_blocks_support_objects(note, request.user)
    messages.success(request, 'Version restaurée.')
    return redirect(f"{reverse('notes:workspace')}?note_id={note.id}")


@login_required
@require_POST
def toggle_favorite(request, note_id):
    note = get_object_or_404(_accessible_notes_queryset(request.user), id=note_id)
    if note.favorited_by.filter(id=request.user.id).exists():
        note.favorited_by.remove(request.user)
        messages.info(request, 'Note retirée des favoris.')
    else:
        note.favorited_by.add(request.user)
        messages.success(request, 'Note ajoutée aux favoris.')
    return redirect(f"{reverse('notes:workspace')}?note_id={note.id}")


@login_required
@require_POST
def archive_note(request, note_id):
    note = get_object_or_404(_accessible_notes_queryset(request.user), id=note_id)
    note.is_archived = True
    note.status = 'archived'
    note.updated_by = request.user
    note.save(update_fields=['is_archived', 'status', 'updated_by', 'updated_at'])
    messages.success(request, 'Note archivée.')
    return redirect(reverse('notes:workspace'))


@login_required
@require_GET
def entity_notes_json(request, entity_type, entity_id):
    notes_qs = _accessible_notes_queryset(request.user).filter(
        is_archived=False,
        links__entity_type=entity_type,
        links__entity_id=entity_id,
    ).distinct().order_by('-updated_at')
    data = [
        {
            'id': str(note.id),
            'title': note.title,
            'note_type': note.note_type,
            'updated_at': note.updated_at.strftime('%d/%m/%Y %H:%M'),
            'url': f"{reverse('notes:workspace')}?note_id={note.id}",
            'tags': list(note.tags.values_list('name', flat=True)),
            'open_task_count': note.tasks.filter(status__in=['todo', 'in_progress']).count(),
            'decision_count': note.decisions.count(),
            'attachment_count': note.attachments.count(),
        }
        for note in notes_qs[:20]
    ]
    return JsonResponse({'results': data})


@login_required
@require_POST
def entity_quick_create(request):
    entity_type = (request.POST.get('entity_type') or '').strip().lower()
    entity_id = (request.POST.get('entity_id') or '').strip()
    label = (request.POST.get('label') or '').strip()
    title = (request.POST.get('title') or '').strip()
    content = (request.POST.get('content') or '').strip()
    tags = (request.POST.get('tags') or '').strip()

    if not entity_type or not entity_id or not title:
        return JsonResponse({'success': False, 'error': 'Entité et titre requis.'}, status=400)

    note = Note.objects.create(
        title=title,
        note_type='note',
        status='active',
        visibility='private',
        content_json=[{'id': 'block-1', 'type': 'paragraph', 'text': content, 'meta': {}}],
        content_text=content,
        created_by=request.user,
        updated_by=request.user,
    )
    _replace_tags(note, tags)
    NoteLink.objects.create(
        note=note,
        entity_type=entity_type,
        entity_id=entity_id,
        label=label,
    )
    return JsonResponse({
        'success': True,
        'note_id': str(note.id),
        'workspace_url': f"{reverse('notes:workspace')}?note_id={note.id}",
    })


@login_required
@require_POST
def create_comment(request, note_id):
    note = get_object_or_404(_accessible_notes_queryset(request.user), id=note_id)
    content = (request.POST.get('content') or '').strip()
    if not content:
        messages.error(request, 'Commentaire vide.')
        return redirect(f"{reverse('notes:workspace')}?note_id={note.id}")
    NoteComment.objects.create(note=note, author=request.user, content=content)
    messages.success(request, 'Commentaire ajouté.')
    return redirect(f"{reverse('notes:workspace')}?note_id={note.id}")


@login_required
@require_POST
def create_task(request, note_id):
    note = get_object_or_404(_accessible_notes_queryset(request.user), id=note_id)
    title = (request.POST.get('title') or '').strip()
    if not title:
        messages.error(request, 'Titre de tâche requis.')
        return redirect(f"{reverse('notes:workspace')}?note_id={note.id}")
    assignee_id = (request.POST.get('assignee_id') or '').strip()
    user_model = Note._meta.get_field('created_by').remote_field.model
    assigned_user = user_model.objects.filter(id=assignee_id).first() if assignee_id else None
    NoteTask.objects.create(
        note=note,
        title=title[:255],
        description=(request.POST.get('description') or '').strip(),
        due_date=(request.POST.get('due_date') or None),
        status=(request.POST.get('status') or 'todo').strip(),
        assignee=assigned_user,
        entity_type=(request.POST.get('entity_type') or '').strip(),
        entity_id=(request.POST.get('entity_id') or '').strip(),
    )
    messages.success(request, 'Tâche ajoutée.')
    return redirect(f"{reverse('notes:workspace')}?note_id={note.id}")


@login_required
@require_POST
def update_task_status(request, task_id):
    task = get_object_or_404(NoteTask.objects.select_related('note'), id=task_id, note__in=_accessible_notes_queryset(request.user))
    task.status = (request.POST.get('status') or task.status).strip()
    task.save(update_fields=['status', 'updated_at'])
    messages.success(request, 'Statut de tâche mis à jour.')
    return redirect(f"{reverse('notes:workspace')}?note_id={task.note_id}")


@login_required
@require_POST
def delete_attachment(request, attachment_id):
    attachment = get_object_or_404(
        NoteAttachment.objects.select_related('note'),
        id=attachment_id,
        note__in=_accessible_notes_queryset(request.user),
    )
    note_id = attachment.note_id
    file_name = attachment.file.name
    attachment.delete()
    if file_name:
        try:
            default_storage.delete(file_name)
        except Exception:
            pass
    messages.success(request, 'PiÃ¨ce jointe supprimée.')
    return redirect(f"{reverse('notes:workspace')}?note_id={note_id}")


@login_required
@require_POST
def create_decision(request, note_id):
    note = get_object_or_404(_accessible_notes_queryset(request.user), id=note_id)
    decision_text = (request.POST.get('decision_text') or '').strip()
    if not decision_text:
        messages.error(request, 'Texte de décision requis.')
        return redirect(f"{reverse('notes:workspace')}?note_id={note.id}")
    responsible_id = (request.POST.get('responsible_id') or '').strip()
    user_model = Note._meta.get_field('created_by').remote_field.model
    responsible = user_model.objects.filter(id=responsible_id).first() if responsible_id else None
    NoteDecision.objects.create(
        note=note,
        decision_text=decision_text,
        context=(request.POST.get('context') or '').strip(),
        justification=(request.POST.get('justification') or '').strip(),
        date_decided=(request.POST.get('decision_date') or None),
        status=(request.POST.get('status') or 'draft').strip(),
        responsible=responsible,
        entity_type=(request.POST.get('entity_type') or '').strip(),
        entity_id=(request.POST.get('entity_id') or '').strip(),
    )
    messages.success(request, 'Décision ajoutée.')
    return redirect(f"{reverse('notes:workspace')}?note_id={note.id}")


@login_required
@require_POST
def create_from_template(request, template_id):
    template = get_object_or_404(_accessible_notes_queryset(request.user), id=template_id, is_template=True)
    note = Note.objects.create(
        parent=template.parent,
        title=f"{template.title} copie",
        note_type=template.note_type,
        status='draft',
        content_json=template.content_json,
        content_text=template.content_text,
        visibility='private',
        created_by=request.user,
        updated_by=request.user,
    )
    note.tags.set(template.tags.all())
    for link in template.links.all():
        NoteLink.objects.create(
            note=note,
            entity_type=link.entity_type,
            entity_id=link.entity_id,
            label=link.label,
            content_type=link.content_type,
            object_id=link.object_id,
        )
    _sync_blocks_support_objects(note, request.user)
    messages.success(request, 'Note créée depuis le modèle.')
    return redirect(f"{reverse('notes:workspace')}?note_id={note.id}")
