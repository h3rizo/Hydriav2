from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.models import User
from django.views.decorators.http import require_http_methods
from django.db import transaction, DatabaseError
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth import update_session_auth_hash
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.utils import timezone
from .models import PasswordResetCode, StorageSnapshot
import json
import random
import string
import io
import os
import shutil
import tempfile
import subprocess
from django.core.management import call_command
from django.conf import settings
from apps.employees.permissions import is_visiteur
from apps.employees.decorators import admin_required
from .visiteur import ensure_visiteur_profile, remove_visiteur_group
import logging


logger = logging.getLogger(__name__)


def _exception_root_message(exc):
    """Retourne la cause SQL initiale lorsqu'une erreur de transaction la masque."""
    root = exc
    visited = set()
    while id(root) not in visited:
        visited.add(id(root))
        next_error = getattr(root, '__cause__', None) or getattr(root, '__context__', None)
        if next_error is None:
            break
        root = next_error

    if root is exc or not str(root):
        return str(exc)
    return f"{exc} Cause initiale: {root}"

@login_required
def users_management(request):
    from apps.employees.models import Employe
    from apps.billing.models import PointEau
    from apps.recrutement.models import Candidat

    employes = Employe.objects.filter(date_debauchage__isnull=True).order_by('surnom')
    points_eau = PointEau.objects.select_related('ouvrage', 'type_point_eau').order_by('nomabonne')
    candidats = Candidat.objects.filter(user__isnull=True).select_related('poste_souhaite').order_by('-date_candidature')

    return render(request, 'system/users_management.html', {
        'employes': employes,
        'points_eau': points_eau,
        'candidats': candidats
    })

@login_required
def system_parameters(request):
    return render(request, 'system/system_parameters.html')


@login_required
@require_http_methods(["GET"])
def download_data_backup(request):
    """Télécharge une sauvegarde JSON de la base de données."""
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({
            'success': False,
            'error': 'Accès réservé aux administrateurs.'
        }, status=403)

    try:
        output = io.StringIO()
        call_command(
            'dumpdata',
            '--natural-foreign',
            '--natural-primary',
            '--indent', '2',
            '--exclude', 'contenttypes',
            '--exclude', 'auth.permission',
            '--exclude', 'admin.logentry',
            '--exclude', 'sessions.session',
            stdout=output
        )

        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        filename = f'hydria_backup_{timestamp}.json'

        response = HttpResponse(output.getvalue(), content_type='application/json; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def download_postgres_backup(request):
    """Télécharge une sauvegarde PostgreSQL native (.sql) via pg_dump."""
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({
            'success': False,
            'error': 'Accès réservé aux administrateurs.'
        }, status=403)

    try:
        db = settings.DATABASES.get('default', {})
        engine = db.get('ENGINE', '')
        if 'postgresql' not in engine:
            return JsonResponse({
                'success': False,
                'error': 'La base active n’est pas PostgreSQL.'
            }, status=400)

        db_name = db.get('NAME')
        db_user = db.get('USER')
        db_password = db.get('PASSWORD') or ''
        db_host = db.get('HOST') or 'localhost'
        db_port = str(db.get('PORT') or '5432')

        if not db_name or not db_user:
            return JsonResponse({
                'success': False,
                'error': 'Configuration PostgreSQL incomplète (NAME/USER).'
            }, status=500)

        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        filename = f'hydria_postgres_backup_{timestamp}.sql'

        with tempfile.NamedTemporaryFile(delete=False, suffix='.sql') as tmp_file:
            tmp_path = tmp_file.name

        env = os.environ.copy()
        env['PGPASSWORD'] = db_password

        cmd = [
            'pg_dump',
            '-h', db_host,
            '-p', db_port,
            '-U', db_user,
            '--no-owner',
            '--no-privileges',
            db_name,
        ]

        try:
            with open(tmp_path, 'wb') as out_file:
                result = subprocess.run(
                    cmd,
                    stdout=out_file,
                    stderr=subprocess.PIPE,
                    env=env,
                    check=False
                )
        except FileNotFoundError:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return JsonResponse({
                'success': False,
                'error': 'pg_dump introuvable sur le serveur.'
            }, status=500)

        if result.returncode != 0:
            stderr_msg = (result.stderr or b'').decode('utf-8', errors='ignore').strip() or 'Erreur pg_dump'
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return JsonResponse({
                'success': False,
                'error': stderr_msg
            }, status=500)

        with open(tmp_path, 'rb') as dump_file:
            dump_bytes = dump_file.read()
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

        response = HttpResponse(dump_bytes, content_type='application/sql; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def logs_monitoring(request):
    return render(request, 'system/logs_monitoring.html')


def _format_bytes(num_bytes):
    value = float(num_bytes or 0)
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024.0
        unit_index += 1
    if unit_index == 0:
        return f"{int(value)} {units[unit_index]}"
    return f"{value:.1f} {units[unit_index]}"


def _safe_dir_size(path):
    total = 0
    if not path or not os.path.exists(path):
        return 0
    try:
        for root, _, files in os.walk(path):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                try:
                    if not os.path.islink(file_path):
                        total += os.path.getsize(file_path)
                except OSError:
                    continue
    except OSError:
        return 0
    return total


def _collect_file_type_sizes(paths):
    stats = {}
    for path in paths:
        if not path or not os.path.exists(path):
            continue
        try:
            for root, _, files in os.walk(path):
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    try:
                        if os.path.islink(file_path):
                            continue
                        size = os.path.getsize(file_path)
                    except OSError:
                        continue
                    ext = os.path.splitext(file_name)[1].lower() or '[sans extension]'
                    stats[ext] = stats.get(ext, 0) + size
        except OSError:
            continue
    ranked = sorted(stats.items(), key=lambda item: item[1], reverse=True)
    return [
        {
            'extension': extension,
            'size_bytes': size_bytes,
            'size_display': _format_bytes(size_bytes),
        }
        for extension, size_bytes in ranked[:12]
    ]


@login_required
def storage_monitoring(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({
            'success': False,
            'error': 'Acces reserve aux administrateurs.'
        }, status=403)
    try:
        disk_root = getattr(settings, 'BASE_DIR', os.getcwd())
        if os.name != 'nt':
            disk_root = '/'

        total_bytes, used_bytes, free_bytes = shutil.disk_usage(disk_root)
        used_percent = round((used_bytes / total_bytes) * 100, 1) if total_bytes else 0
        free_percent = round((free_bytes / total_bytes) * 100, 1) if total_bytes else 0
        used_percent_int = min(100, round(used_percent)) if total_bytes else 0
        free_percent_int = min(100, round(free_percent)) if total_bytes else 0

        project_root = os.path.dirname(settings.BASE_DIR)
        monitored_dirs = [
            ('Projet backend', settings.BASE_DIR),
            ('Media', getattr(settings, 'MEDIA_ROOT', '')),
            ('Staticfiles', os.path.join(settings.BASE_DIR, 'staticfiles')),
            ('Logs', os.path.join(project_root, 'logs')),
            ('Package import', os.path.join(settings.BASE_DIR)),
        ]

        folder_stats = []
        for label, path in monitored_dirs:
            size_bytes = _safe_dir_size(path)
            folder_stats.append({
                'label': label,
                'path': path,
                'exists': bool(path and os.path.exists(path)),
                'size_bytes': size_bytes,
                'size_display': _format_bytes(size_bytes),
                'percent_of_disk': round((size_bytes / total_bytes) * 100, 2) if total_bytes else 0,
                'percent_of_disk_int': min(100, round((size_bytes / total_bytes) * 100)) if total_bytes else 0,
            })

        folder_stats.sort(key=lambda item: item['size_bytes'], reverse=True)
        file_type_stats = _collect_file_type_sizes([item['path'] for item in folder_stats if item['exists']])
        for item in file_type_stats:
            item['percent_of_disk'] = round((item['size_bytes'] / total_bytes) * 100, 2) if total_bytes else 0
            item['percent_of_disk_int'] = min(100, round((item['size_bytes'] / total_bytes) * 100)) if total_bytes else 0

        latest_snapshot = None
        history_snapshots = []
        snapshot_error = ''
        try:
            latest_snapshot = StorageSnapshot.objects.filter(root_path=disk_root).order_by('-created_at').first()
            should_create_snapshot = (
                latest_snapshot is None or
                (timezone.now() - latest_snapshot.created_at).total_seconds() >= 21600
            )
            if should_create_snapshot:
                latest_snapshot = StorageSnapshot.objects.create(
                    root_path=disk_root,
                    total_bytes=total_bytes,
                    used_bytes=used_bytes,
                    free_bytes=free_bytes,
                    used_percent=used_percent,
                )

            history_snapshots = list(
                StorageSnapshot.objects.filter(root_path=disk_root).order_by('-created_at')[:14]
            )
            history_snapshots.reverse()
        except DatabaseError:
            snapshot_error = 'Historique de stockage indisponible tant que les migrations system ne sont pas appliquees.'

        alert_level = 'success'
        alert_label = 'Stockage confortable'
        if used_percent >= 90:
            alert_level = 'error'
            alert_label = 'Alerte critique'
        elif used_percent >= 80:
            alert_level = 'warning'
            alert_label = 'Surveillance recommandee'

        context = {
            'disk_root': disk_root,
            'disk_total_bytes': total_bytes,
            'disk_used_bytes': used_bytes,
            'disk_free_bytes': free_bytes,
            'disk_total_display': _format_bytes(total_bytes),
            'disk_used_display': _format_bytes(used_bytes),
            'disk_free_display': _format_bytes(free_bytes),
            'disk_used_percent': used_percent,
            'disk_used_percent_int': used_percent_int,
            'disk_free_percent': free_percent,
            'disk_free_percent_int': free_percent_int,
            'vps_capacity_reference_gb': round(total_bytes / (1024 ** 3)) if total_bytes else 0,
            'folder_stats': folder_stats,
            'file_type_stats': file_type_stats,
            'history_snapshots': history_snapshots,
            'latest_snapshot': latest_snapshot,
            'snapshot_error': snapshot_error,
            'alert_level': alert_level,
            'alert_label': alert_label,
            'project_root': project_root,
        }
        return render(request, 'system/storage_monitoring.html', context)
    except Exception as exc:
        return HttpResponse(
            f"Erreur stockage: {type(exc).__name__}: {exc}",
            status=500,
            content_type='text/plain; charset=utf-8',
        )

@login_required
def api_users_list(request):
    from apps.employees.models import ClientUser
    from django.contrib.humanize.templatetags.humanize import naturaltime
    from django.db.models import Q, OuterRef, Subquery, DateTimeField, Value, CharField
    from django.db.models.functions import Coalesce
    from .models import UserPresence, ActivityLog
    from urllib.parse import urlsplit

    search = request.GET.get('search', '')
    user_type = request.GET.get('type', 'all')  # 'all', 'employe', 'client', 'candidat', 'admin', 'visiteur'
    is_active_filter = request.GET.get('is_active', '')
    is_staff_filter = request.GET.get('is_staff', '')
    page = int(request.GET.get('page', 1))
    per_page = 20

    latest_presence_base_qs = UserPresence.objects.filter(
        user_id=OuterRef('pk')
    ).order_by('-last_seen')
    latest_presence_seen_subquery = latest_presence_base_qs.values('last_seen')[:1]
    latest_presence_path_subquery = latest_presence_base_qs.values('path')[:1]

    very_old_date = timezone.now() - timezone.timedelta(days=36500)

    users_qs = User.objects.all().select_related(
        'employe',
        'client',
        'candidat',
        'candidat__poste_souhaite'
    ).prefetch_related(
        'groups'
    ).annotate(
        latest_presence=Subquery(latest_presence_seen_subquery, output_field=DateTimeField()),
        latest_presence_path=Subquery(latest_presence_path_subquery, output_field=CharField()),
        last_activity=Coalesce(
            Subquery(latest_presence_seen_subquery, output_field=DateTimeField()),
            'last_login',
            Value(very_old_date, output_field=DateTimeField())
        )
    ).order_by('-last_activity', 'username')

    # Filtres de base
    if search:
        users_qs = users_qs.filter(
            Q(username__icontains=search) |
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        )
    
    if is_active_filter == 'true':
        users_qs = users_qs.filter(is_active=True)
    elif is_active_filter == 'false':
        users_qs = users_qs.filter(is_active=False)
        
    if is_staff_filter == 'true':
        users_qs = users_qs.filter(is_staff=True)
    elif is_staff_filter == 'false':
        users_qs = users_qs.filter(is_staff=False)

    # Statistiques globales (avant filtrage par type pour avoir les totaux réels)
    stats = {
        'total': User.objects.count(),
        'active': User.objects.filter(is_active=True).count(),
        'staff': User.objects.filter(is_staff=True).count(),
        'employes': User.objects.filter(employe__isnull=False).count(),
        'clients': User.objects.filter(client__isnull=False).count(),
        'candidats': User.objects.filter(candidat__isnull=False).count(),
        'visiteurs': User.objects.filter(groups__name='Visiteur').distinct().count(),
        'admins': User.objects.filter(
            employe__isnull=True,
            client__isnull=True,
            candidat__isnull=True
        ).exclude(groups__name='Visiteur').distinct().count()
    }

    # Filtrage par type (appliqué sur le QuerySet final)
    if user_type == 'employe':
        users_qs = users_qs.filter(employe__isnull=False)
    elif user_type == 'client':
        users_qs = users_qs.filter(client__isnull=False)
    elif user_type == 'candidat':
        users_qs = users_qs.filter(candidat__isnull=False)
    elif user_type == 'visiteur':
        users_qs = users_qs.filter(groups__name='Visiteur').distinct()
    elif user_type == 'admin':
        users_qs = users_qs.filter(
            employe__isnull=True,
            client__isnull=True,
            candidat__isnull=True
        ).exclude(groups__name='Visiteur').distinct()

    total_filtered = users_qs.count()
    start = (page - 1) * per_page
    end = start + per_page
    users = users_qs[start:end]
    online_threshold = timezone.now() - timezone.timedelta(seconds=65)
    user_ids = [u.id for u in users]
    month_start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    active_presences_by_user = {}
    if user_ids:
        active_presences = UserPresence.objects.filter(
            user_id__in=user_ids,
            last_seen__gte=online_threshold
        ).order_by('user_id', '-last_seen')

        for presence in active_presences:
            current = active_presences_by_user.setdefault(presence.user_id, [])
            # Eviter les doublons de path pour un même utilisateur
            if any(item['path'] == presence.path for item in current):
                continue
            current.append({
                'path': presence.path,
                'last_seen': presence.last_seen
            })

    monthly_connection_seconds = {user_id: 0 for user_id in user_ids}
    if user_ids:
        month_logs = list(
            ActivityLog.objects.filter(
                user_id__in=user_ids,
                log_type__in=['login', 'logout'],
                created_at__gte=month_start
            ).order_by('user_id', 'created_at')
        )

        user_lookup = {u.id: u for u in users}
        open_sessions = {}

        for log in month_logs:
            if log.log_type == 'login':
                open_sessions[log.user_id] = log.created_at
                continue

            login_at = open_sessions.pop(log.user_id, None)
            if login_at and log.created_at > login_at:
                monthly_connection_seconds[log.user_id] += int((log.created_at - login_at).total_seconds())

        now_dt = timezone.now()
        for user_id, login_at in open_sessions.items():
            if not login_at:
                continue
            fallback_end = now_dt
            presence_items = active_presences_by_user.get(user_id, [])
            if presence_items:
                latest_seen = max((item['last_seen'] for item in presence_items if item.get('last_seen')), default=None)
                if latest_seen and latest_seen > login_at:
                    fallback_end = latest_seen
            else:
                user_obj = user_lookup.get(user_id)
                latest_presence = getattr(user_obj, 'latest_presence', None) if user_obj else None
                if latest_presence and latest_presence > login_at:
                    fallback_end = latest_presence

            if fallback_end > login_at:
                monthly_connection_seconds[user_id] += int((fallback_end - login_at).total_seconds())

    def _format_duration(total_seconds):
        total_seconds = max(int(total_seconds or 0), 0)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours} h {minutes:02d}"

    def _humanize_path(raw_path):
        if not raw_path:
            return 'Page inconnue'
        split = urlsplit(raw_path)
        path_only = split.path or '/'
        if path_only == '/':
            base = 'Accueil'
        else:
            segments = [seg for seg in path_only.split('/') if seg]
            if not segments:
                base = 'Accueil'
            elif len(segments) == 1:
                base = segments[0].replace('-', ' ').replace('_', ' ').title()
            else:
                parent = segments[-2].replace('-', ' ').replace('_', ' ').title()
                current = segments[-1].replace('-', ' ').replace('_', ' ').title()
                base = f'{parent} / {current}'
        if split.query:
            return f'{base} (filtré)'
        return base

    data = []
    for u in users:
        employe_info = None
        client_info = None
        candidat_info = None
        type_user = 'admin'
        visitor_info = None

        if is_visiteur(u):
            type_user = 'visiteur'
            visitor_info = {
                'email': u.email or u.username,
            }
            if hasattr(u, 'employe') and u.employe:
                employe_info = {
                    'id': str(u.employe.id),
                    'surnom': u.employe.surnom,
                    'nom': u.employe.nom_employe,
                    'prenom': u.employe.prenom
                }
        elif hasattr(u, 'employe') and u.employe:
            type_user = 'employe'
            employe_info = {
                'id': str(u.employe.id),
                'surnom': u.employe.surnom,
                'nom': u.employe.nom_employe,
                'prenom': u.employe.prenom
            }
        elif hasattr(u, 'client') and u.client:
            type_user = 'client'
            client_info = {
                'id': str(u.client.id),
                'nom_complet': u.client.nom_complet,
                'point_eau_nom': u.client.point_eau.nomabonne if u.client.point_eau else None,
                'ouvrage_nom': u.client.ouvrage.nom_ouvrage if u.client.ouvrage else None,
                'telephone': u.client.telephone
            }
        elif hasattr(u, 'candidat') and u.candidat:
            type_user = 'candidat'
            candidat_info = {
                'id': str(u.candidat.id),
                'nom_complet': u.candidat.nom_complet,
                'email': u.candidat.email,
                'poste': u.candidat.poste_souhaite.nom_poste if u.candidat.poste_souhaite else None,
                'statut': u.candidat.statut
            }

        last_seen = getattr(u, 'latest_presence', None)
        is_online = bool(last_seen and last_seen >= online_threshold)
        active_pages = active_presences_by_user.get(u.id, [])

        current_page_path = active_pages[0]['path'] if active_pages else getattr(u, 'latest_presence_path', None)
        current_page_label = _humanize_path(current_page_path) if current_page_path else None

        data.append({
            'id': u.id,
            'username': u.username,
            'email': u.email or '',
            'first_name': u.first_name,
            'last_name': u.last_name,
            'is_staff': u.is_staff,
            'is_superuser': u.is_superuser,
            'is_active': u.is_active,
            'last_login': naturaltime(u.last_login) if u.last_login else None,
            'last_login_raw': u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else None,
            'last_login_iso': u.last_login.isoformat() if u.last_login else None,
            'is_online': is_online,
            'last_seen': naturaltime(last_seen) if last_seen else None,
            'last_seen_raw': last_seen.strftime('%Y-%m-%d %H:%M:%S') if last_seen else None,
            'last_seen_iso': last_seen.isoformat() if last_seen else None,
            'connection_hours_month': _format_duration(monthly_connection_seconds.get(u.id, 0)),
            'connection_seconds_month': monthly_connection_seconds.get(u.id, 0),
            'current_page': current_page_path,
            'current_page_label': current_page_label,
            'active_pages': [
                {
                    'path': p['path'],
                    'label': _humanize_path(p['path']),
                    'last_seen_iso': p['last_seen'].isoformat() if p.get('last_seen') else None,
                    'last_seen_raw': p['last_seen'].strftime('%Y-%m-%d %H:%M:%S') if p.get('last_seen') else None,
                }
                for p in active_pages
            ],
            'type': type_user,
            'employe': employe_info,
            'client': client_info,
            'candidat': candidat_info,
            'visitor': visitor_info
        })

    return JsonResponse({
        'users': data,
        'stats': stats,
        'pagination': {
            'total_count': total_filtered,
            'page': page,
            'per_page': per_page,
            'total_pages': (total_filtered + per_page - 1) // per_page
        }
    })

@login_required
def api_logs_list(request):
    from .models import ActivityLog
    logs = ActivityLog.objects.all()[:50]
    data = [{'id': str(l.id), 'action': l.action} for l in logs]
    return JsonResponse({'logs': data, 'pagination': {'total_count': len(data)}})

@login_required
def api_logs_stats(request):
    return JsonResponse({'total_logs': 0})

@login_required
def api_parameters_list(request):
    return JsonResponse({'parameters': []})

@login_required
@require_http_methods(["POST"])
def api_user_create(request):
    try:
        data = json.loads(request.body)

        # Validation
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        user_type = data.get('user_type', 'admin')

        if user_type == 'visiteur':
            email = email.lower()
            if not email:
                return JsonResponse({'success': False, 'error': "Email requis pour un visiteur"}, status=400)
            if not username:
                username = email

        if not username:
            return JsonResponse({'success': False, 'error': 'Nom d\'utilisateur requis'}, status=400)

        if User.objects.filter(username=username).exists():
            return JsonResponse({'success': False, 'error': 'Nom d\'utilisateur deja utilise'}, status=400)

        if email:
            try:
                validate_email(email)
            except ValidationError:
                return JsonResponse({'success': False, 'error': 'Email invalide'}, status=400)

        if email and User.objects.filter(email=email).exists():
            return JsonResponse({'success': False, 'error': 'Email deja utilise'}, status=400)

        # Creer l'utilisateur
        with transaction.atomic():
            generated_password = ''.join(random.choices(string.ascii_letters + string.digits, k=20))
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', ''),
                password=password if password else (generated_password if user_type == 'visiteur' else username)
            )

            user.is_staff = False if user_type == 'visiteur' else data.get('is_staff', False)
            user.is_superuser = False if user_type == 'visiteur' else data.get('is_superuser', False)
            user.is_active = data.get('is_active', True)
            user.save()

            # Lier selon le type d'utilisateur
            if user_type == 'employe':
                employe_id = data.get('employe_id')
                if employe_id:
                    from apps.employees.models import Employe
                    try:
                        employe = Employe.objects.get(id=employe_id)
                        employe.user = user
                        employe.save()
                    except Employe.DoesNotExist:
                        pass

            elif user_type == 'client':
                from apps.employees.models import ClientUser
                from apps.billing.models import PointEau

                point_eau_id = data.get('point_eau_id')
                if not point_eau_id:
                    return JsonResponse({'success': False, 'error': 'Point d\'eau requis pour un client'}, status=400)

                try:
                    point_eau = PointEau.objects.get(id=point_eau_id)

                    # Creer le ClientUser
                    ClientUser.objects.create(
                        user=user,
                        nom=data.get('last_name', ''),
                        prenom=data.get('first_name', ''),
                        telephone=data.get('telephone', ''),
                        email=email,
                        point_eau=point_eau
                    )

                except PointEau.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable'}, status=400)
            elif user_type == 'candidat':
                from apps.recrutement.models import Candidat

                candidat_id = data.get('candidat_id')
                if not candidat_id:
                    return JsonResponse({'success': False, 'error': 'Candidat requis'}, status=400)

                try:
                    candidat = Candidat.objects.get(id=candidat_id)
                except Candidat.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'Candidat introuvable'}, status=400)

                if candidat.user and candidat.user_id != user.id:
                    return JsonResponse({'success': False, 'error': 'Ce candidat est deja lie a un autre utilisateur'}, status=400)

                candidat.user = user
                candidat.save(update_fields=['user'])
            elif user_type == 'visiteur':
                ensure_visiteur_profile(user, email=email or username)

        return JsonResponse({'success': True, 'message': 'Utilisateur cree avec succes'})

    except Exception as e:
        logger.exception(
            "Erreur lors de la creation de l'utilisateur %r (type=%r)",
            locals().get('username', ''),
            locals().get('user_type', ''),
        )
        return JsonResponse(
            {'success': False, 'error': _exception_root_message(e)},
            status=500,
        )

@login_required
@require_http_methods(["POST"])
def api_user_update(request, user_id):
    try:
        user = User.objects.get(id=user_id)
        data = json.loads(request.body)
        target_user_type = data.get('user_type')

        # Mise a jour des champs
        if 'username' in data:
            username = data['username'].strip()
            if target_user_type == 'visiteur' and not username:
                username = (data.get('email') or '').strip().lower()

            if not username:
                return JsonResponse({'success': False, 'error': 'Nom d\'utilisateur requis'}, status=400)

            if username != user.username and User.objects.filter(username=username).exists():
                return JsonResponse({'success': False, 'error': 'Nom d\'utilisateur deja utilise'}, status=400)
            user.username = username

        if 'email' in data:
            email = data['email'].strip()
            if target_user_type == 'visiteur':
                email = email.lower()
                if not email:
                    return JsonResponse({'success': False, 'error': 'Email requis pour un visiteur'}, status=400)
            if email:
                try:
                    validate_email(email)
                except ValidationError:
                    return JsonResponse({'success': False, 'error': 'Email invalide'}, status=400)
            if email != user.email and User.objects.filter(email=email).exists():
                return JsonResponse({'success': False, 'error': 'Email deja utilise'}, status=400)
            user.email = email

        if 'first_name' in data:
            user.first_name = data['first_name']

        if 'last_name' in data:
            user.last_name = data['last_name']

        if target_user_type == 'visiteur':
            user.is_staff = False
            user.is_superuser = False
        else:
            if 'is_staff' in data:
                user.is_staff = data['is_staff']

            if 'is_superuser' in data:
                user.is_superuser = data['is_superuser']

        if 'is_active' in data:
            user.is_active = data['is_active']

        # Changer le mot de passe si fourni
        if data.get('password'):
            user.set_password(data['password'])

        user.save()

        if target_user_type == 'visiteur':
            if not (user.email or data.get('email')):
                return JsonResponse({'success': False, 'error': 'Email requis pour un visiteur'}, status=400)
            ensure_visiteur_profile(user, email=user.email or data.get('email'))
        elif target_user_type in ('admin', 'employe', 'client', 'candidat'):
            remove_visiteur_group(user)

        # Si on change vers un type non-employe, detacher l'employe courant.
        # Cela evite de garder une ancienne liaison "visiteur" qui fausse le type.
        if target_user_type in ('admin', 'client', 'candidat'):
            if hasattr(user, 'employe') and user.employe:
                old_employe = user.employe
                old_employe.user = None
                old_employe.save(update_fields=['user'])

        # Mettre a jour la liaison employe
        if 'employe_id' in data:
            from apps.employees.models import Employe

            # Supprimer l'ancienne liaison
            if hasattr(user, 'employe'):
                old_employe = user.employe
                old_employe.user = None
                old_employe.save()

            # Creer la nouvelle liaison
            if data['employe_id']:
                try:
                    employe = Employe.objects.get(id=data['employe_id'])
                    employe.user = user
                    employe.save()
                except Employe.DoesNotExist:
                    pass

        if 'candidat_id' in data:
            from apps.recrutement.models import Candidat

            # Supprimer l'ancienne liaison candidat
            if hasattr(user, 'candidat') and user.candidat:
                old_candidat = user.candidat
                old_candidat.user = None
                old_candidat.save(update_fields=['user'])

            if data['candidat_id']:
                try:
                    candidat = Candidat.objects.get(id=data['candidat_id'])
                except Candidat.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'Candidat introuvable'}, status=400)

                if candidat.user and candidat.user_id != user.id:
                    return JsonResponse({'success': False, 'error': 'Ce candidat est deja lie a un autre utilisateur'}, status=400)

                candidat.user = user
                candidat.save(update_fields=['user'])

        return JsonResponse({'success': True, 'message': 'Utilisateur mis a jour avec succes'})

    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Utilisateur non trouve'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
@login_required
@require_http_methods(["POST"])
def api_user_delete(request, user_id):
    try:
        user = User.objects.get(id=user_id)

        # Empêcher la suppression de son propre compte
        if user.id == request.user.id:
            return JsonResponse({'success': False, 'error': 'Vous ne pouvez pas supprimer votre propre compte'}, status=400)

        username = user.username
        user.delete()

        return JsonResponse({'success': True, 'message': f'Utilisateur {username} supprimé avec succès'})

    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Utilisateur non trouvé'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def api_parameter_update(request, param_id):
    return JsonResponse({'success': True})

def password_reset_request(request):
    """Demande de réinitialisation de mot de passe"""
    if request.method == 'POST':
        email = request.POST.get('email')
        if not email:
            messages.error(request, "Veuillez saisir votre adresse email.")
            return render(request, 'registration/password_reset_request.html')

        # Trouver l'utilisateur par email
        user = User.objects.filter(email=email).first()
        if user:
            # Générer un code à 6 chiffres
            code = ''.join(random.choices(string.digits, k=6))
            
            # Sauvegarder le code
            PasswordResetCode.objects.create(email=email, code=code)
            
            # Envoyer l'email
            subject = "Code de réinitialisation de mot de passe - Hydria"
            message = f"Bonjour,\n\nVotre code de réinitialisation de mot de passe est : {code}\n\nCe code vous permettra de définir un nouveau mot de passe pour votre compte Hydria.\n\nCordialement,\nL'Herizo"
            
            try:
                send_mail(subject, message, None, [email], fail_silently=False)
                # Stocker l'email en session pour l'étape suivante
                request.session['reset_email'] = email
                return render(request, 'registration/password_reset_verify.html', {'email': email})
            except Exception as e:
                messages.error(request, f"Erreur lors de l'envoi de l'email : {str(e)}")
        else:
            # Pour la sécurité, on ne dit pas si l'email existe ou pas
            messages.info(request, "Si un compte correspond à cet email, un code de réinitialisation a été envoyé.")
            # Mais on redirige quand même pour qu'il puisse essayer le code s'il l'a reçu
            request.session['reset_email'] = email
            return render(request, 'registration/password_reset_verify.html', {'email': email})

    return render(request, 'registration/password_reset_request.html')

def password_reset_verify(request):
    """Vérification du code et réinitialisation du mot de passe"""
    email = request.session.get('reset_email')
    
    if request.method == 'POST':
        code = request.POST.get('code')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        
        if not email:
            messages.error(request, "Session expirée. Veuillez recommencer la demande.")
            return render(request, 'registration/password_reset_request.html')
            
        # Vérifier le code
        reset_code = PasswordResetCode.objects.filter(
            email=email, 
            code=code, 
            is_used=False,
            created_at__gte=timezone.now() - timezone.timedelta(hours=2)
        ).first()
        
        if reset_code:
            if password == confirm_password:
                if len(password) < 8:
                    messages.error(request, "Le mot de passe doit contenir au moins 8 caractères.")
                else:
                    user = User.objects.filter(email=email).first()
                    if user:
                        user.set_password(password)
                        user.save()
                        reset_code.is_used = True
                        reset_code.save()
                        messages.success(request, "Votre mot de passe a été réinitialisé avec succès. Vous pouvez maintenant vous connecter.")
                        return render(request, 'registration/login.html')
            else:
                messages.error(request, "Les mots de passe ne correspondent pas.")
        else:
            messages.error(request, "Code invalide ou expiré.")

    return render(request, 'registration/password_reset_verify.html', {'email': email})

@login_required
def password_change(request):
    """Changement de mot de passe pour utilisateur connecté"""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Garder l'utilisateur connecté
            messages.success(request, 'Votre mot de passe a été mis à jour avec succès !')
            return render(request, 'registration/password_change.html', {'form': form})
        else:
            messages.error(request, 'Veuillez corriger les erreurs ci-dessous.')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'registration/password_change.html', {'form': form})

@login_required
@require_http_methods(["POST"])
def api_presence_update(request):
    """Met à jour la présence et renvoie les autres utilisateurs sur la même page"""
    try:
        data = json.loads(request.body)
        path = data.get('path', '/')
        
        from .models import UserPresence
        from apps.employees.models import Employe
        
        # 1. Mettre à jour la présence de l'utilisateur actuel
        employe = Employe.objects.filter(user=request.user).first()
        
        UserPresence.objects.update_or_create(
            user=request.user,
            path=path,
            defaults={
                'employe': employe,
                'last_seen': timezone.now()
            }
        )
        
        # 2. Nettoyer les présences obsolètes (> 45 secondes sans ping)
        # On utilise une marge courte car le polling frontend sera typiquement de 15-30s
        expiry = timezone.now() - timezone.timedelta(seconds=45)
        UserPresence.objects.filter(last_seen__lt=expiry).delete()
        
        # 3. Récupérer les autres utilisateurs sur la même page
        presences = UserPresence.objects.filter(path=path).exclude(user=request.user).select_related('user', 'employe')
        
        others = []
        for p in presences:
            others.append({
                'id': p.user.id,
                'username': p.user.username,
                'full_name': f"{p.user.first_name} {p.user.last_name}".strip() or p.user.username,
                'surnom': p.employe.surnom if p.employe else None,
                'last_seen': p.last_seen.isoformat()
            })
            
        return JsonResponse({
            'success': True,
            'active_users': others,
            'count': len(others)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ============================================================
# Preview / envoi manuel : rappel mensuel factures non pointees
# ============================================================

@admin_required
def preview_relances_factures(request):
    """Page de preview : calcule et affiche les emails qui seraient envoyes
    pour le mois cible sans jamais envoyer ni ecrire de trace."""
    from apps.messaging.models import RelanceFacturesNonPointees
    from apps.messaging.monthly_billing_mailer import envoyer_toutes_les_relances

    annee_param = request.GET.get('annee')
    mois_param = request.GET.get('mois')
    annee = int(annee_param) if annee_param else None
    mois = int(mois_param) if mois_param else None

    resultat = envoyer_toutes_les_relances(annee=annee, mois=mois, dry_run=True)

    dernier = (
        RelanceFacturesNonPointees.objects
        .filter(est_test=False)
        .order_by('-annee', '-mois')
        .values('annee', 'mois')
        .first()
    )
    stats_dernier_traitement = None
    if dernier:
        qs = RelanceFacturesNonPointees.objects.filter(
            est_test=False, annee=dernier['annee'], mois=dernier['mois'],
        )
        stats_dernier_traitement = {
            'annee': dernier['annee'],
            'mois': dernier['mois'],
            'total': qs.count(),
            'envoyes': qs.filter(statut='envoye').count(),
            'echecs': qs.filter(statut='echec').count(),
            'email_manquant': qs.filter(statut='email_manquant').count(),
        }

    return render(request, 'system/preview_rappel_factures.html', {
        'resultat': resultat,
        'aucun_email': resultat['nb_responsables'] == 0,
        'stats_dernier_traitement': stats_dernier_traitement,
    })


@admin_required
def preview_relance_detail(request, employe_id):
    """Rendu HTML ou texte d'un email individuel, calcule a la volee (aucun
    envoi, aucune ecriture). type=responsable (defaut) ou type=superieur
    selon le role a previsualiser pour cet employe sur la periode."""
    from django.http import Http404
    from apps.employees.models import Employe
    from apps.messaging.monthly_billing_reminder import (
        calculer_periode_cible,
        construire_regroupement,
        construire_regroupement_hierarchique,
    )
    from apps.messaging.monthly_billing_mailer import rendre_email, rendre_email_superieur

    try:
        annee = int(request.GET.get('annee'))
        mois = int(request.GET.get('mois'))
    except (TypeError, ValueError):
        raise Http404("Parametres annee/mois requis.")

    format_demande = request.GET.get('format', 'html')
    type_destinataire = request.GET.get('type', 'responsable')
    employe = get_object_or_404(Employe, id=employe_id)

    regroupement = construire_regroupement(annee, mois)

    if type_destinataire == 'superieur':
        _, _, date_fin_periode = calculer_periode_cible(annee, mois)
        regroupement_hierarchique = construire_regroupement_hierarchique(regroupement, date_fin_periode)
        entree = regroupement_hierarchique.get(employe.id)
        if not entree:
            raise Http404("Aucun rappel hierarchique pour cet employe sur cette periode.")
        sujet, texte, html, _nb_pe, _nb_fact, _montant = rendre_email_superieur(
            employe, annee, mois, entree, est_test=False,
        )
    else:
        entree = regroupement.get(employe.id)
        if not entree:
            raise Http404("Aucune facture non pointee pour ce responsable sur cette periode.")
        sujet, texte, html, _nb_pe, _nb_fact, _montant = rendre_email(
            employe, annee, mois, entree, est_test=False,
        )

    if format_demande == 'text':
        return HttpResponse(texte, content_type='text/plain; charset=utf-8')
    return HttpResponse(html, content_type='text/html; charset=utf-8')


@admin_required
@require_http_methods(["POST"])
def envoyer_relances_test(request):
    """Declenche un envoi de TEST : tous les emails generes partent vers UNE
    seule adresse fournie par l'admin, bandeau TEST inclus."""
    from apps.messaging.monthly_billing_mailer import envoyer_toutes_les_relances

    email_test = (request.POST.get('email_test') or '').strip()
    if not email_test:
        messages.error(request, "Adresse email de test requise.")
        return redirect('system:preview_relances_factures')
    try:
        validate_email(email_test)
    except ValidationError:
        messages.error(request, "Adresse email de test invalide.")
        return redirect('system:preview_relances_factures')

    annee_param = request.POST.get('annee')
    mois_param = request.POST.get('mois')
    resultat = envoyer_toutes_les_relances(
        annee=int(annee_param) if annee_param else None,
        mois=int(mois_param) if mois_param else None,
        dry_run=False, est_test=True, email_test_override=email_test,
    )
    messages.success(
        request,
        f"Envoi de test effectue : {resultat['nb_envoyes']} email(s) envoye(s) vers {email_test} "
        f"(representant {resultat['nb_responsables']} responsable(s) reel(s))."
    )
    redirect_url = f"{reverse('system:preview_relances_factures')}?annee={resultat['annee']}&mois={resultat['mois']}"
    return redirect(redirect_url)


@admin_required
@require_http_methods(["POST"])
def envoyer_relances_reelles(request):
    """
    Declenchement manuel de l'envoi REEL (pas de test). Reserve a une action
    volontaire de l'administrateur : n'est appelee automatiquement par aucun
    code (ni tache Celery, ni cron), c'est un point d'entree distinct.
    """
    from apps.messaging.monthly_billing_mailer import envoyer_toutes_les_relances

    annee_param = request.POST.get('annee')
    mois_param = request.POST.get('mois')
    resultat = envoyer_toutes_les_relances(
        annee=int(annee_param) if annee_param else None,
        mois=int(mois_param) if mois_param else None,
        dry_run=False, est_test=False,
    )
    messages.success(
        request,
        f"{resultat['nb_envoyes']} email(s) reel(s) envoye(s), {resultat['nb_echecs']} echec(s), "
        f"{resultat['nb_email_manquant']} email(s) manquant(s)."
    )
    redirect_url = f"{reverse('system:preview_relances_factures')}?annee={resultat['annee']}&mois={resultat['mois']}"
    return redirect(redirect_url)


def _regrouper_details_par_base_et_poste(details):
    """
    Transforme la liste plate resultat['details'] en structure imbriquee
    {base_nom: {poste_nom: [details...]}} triee alphabetiquement, pour
    l'affichage groupe de la page preview_situations_attention. Les
    employes sans base/poste renseignes sont regroupes sous des libelles
    explicites plutot que silencieusement omis.
    """
    groupes = {}
    for detail in details:
        employe = detail['employe']
        base_nom = employe.base.nom_base if employe.base else 'Sans base'
        poste_nom = employe.poste.nom_poste if employe.poste else 'Sans poste'
        groupes.setdefault(base_nom, {}).setdefault(poste_nom, []).append(detail)

    return {
        base_nom: dict(sorted(postes.items(), key=lambda item: item[0]))
        for base_nom, postes in sorted(groupes.items(), key=lambda item: item[0])
    }


@admin_required
def preview_situations_attention(request):
    """Page de preview du moteur combine (paiements non pointes +
    reparations echues) : calcule et affiche les emails qui seraient
    envoyes, un par destinataire, regroupe par base puis par poste (chaque
    groupe restant lui-meme trie par ouvrage/criticite via resultat['details']),
    sans jamais envoyer ni ecrire de trace."""
    from apps.messaging.models import RelanceFacturesNonPointees, RelanceReparations
    from apps.messaging.relance_mailer_combine import envoyer_toutes_les_relances_combinees

    annee_param = request.GET.get('annee')
    mois_param = request.GET.get('mois')
    annee = int(annee_param) if annee_param else None
    mois = int(mois_param) if mois_param else None

    resultat = envoyer_toutes_les_relances_combinees(annee=annee, mois=mois, dry_run=True)
    if resultat['details']:
        from apps.employees.models import Employe
        employes_ids = {detail['employe'].id for detail in resultat['details']}
        employes_avec_relations = {
            e.id: e for e in Employe.objects.filter(id__in=employes_ids).select_related('base', 'poste')
        }
        for detail in resultat['details']:
            detail['employe'] = employes_avec_relations[detail['employe'].id]
    details_groupes = _regrouper_details_par_base_et_poste(resultat['details'])

    dernier_paiements = (
        RelanceFacturesNonPointees.objects
        .filter(est_test=False)
        .order_by('-annee', '-mois')
        .values('annee', 'mois')
        .first()
    )
    stats_dernier_traitement = None
    if dernier_paiements:
        qs_paiements = RelanceFacturesNonPointees.objects.filter(
            est_test=False, annee=dernier_paiements['annee'], mois=dernier_paiements['mois'],
        )
        dernier_batch = (
            RelanceReparations.objects
            .filter(est_test=False)
            .order_by('-created_at')
            .values_list('batch_id', flat=True)
            .first()
        )
        qs_reparations = RelanceReparations.objects.filter(est_test=False, batch_id=dernier_batch) if dernier_batch else RelanceReparations.objects.none()
        stats_dernier_traitement = {
            'annee': dernier_paiements['annee'],
            'mois': dernier_paiements['mois'],
            'total': qs_paiements.count() + qs_reparations.count(),
            'envoyes': qs_paiements.filter(statut='envoye').count() + qs_reparations.filter(statut='envoye').count(),
            'echecs': qs_paiements.filter(statut='echec').count() + qs_reparations.filter(statut='echec').count(),
            'email_manquant': qs_paiements.filter(statut='email_manquant').count() + qs_reparations.filter(statut='email_manquant').count(),
        }

    return render(request, 'system/preview_situations_attention.html', {
        'resultat': resultat,
        'details_groupes': details_groupes,
        'aucun_email': resultat['nb_destinataires'] == 0,
        'stats_dernier_traitement': stats_dernier_traitement,
    })


@admin_required
def preview_situation_detail(request, employe_id):
    """Rendu HTML ou texte d'un email combine individuel, calcule a la
    volee (aucun envoi, aucune ecriture)."""
    from django.http import Http404

    from apps.employees.models import Employe
    from apps.messaging.relance_engine import construire_regroupement_combine
    from apps.messaging.relance_mailer_combine import _reverifier_eligibilite, rendre_email_combine

    try:
        annee = int(request.GET.get('annee'))
        mois = int(request.GET.get('mois'))
    except (TypeError, ValueError):
        raise Http404("Parametres annee/mois requis.")

    format_demande = request.GET.get('format', 'html')
    employe = get_object_or_404(Employe, id=employe_id)

    (
        regroupement_combine, annee_cible, mois_cible, date_fin_periode,
        date_reference_reparations, _factures_sans_responsable,
        _reparations_sans_responsable,
    ) = construire_regroupement_combine(annee, mois)

    entree = regroupement_combine.get(employe.id)
    if not entree:
        raise Http404("Aucune situation a relancer pour cet employe sur cette periode.")

    ouvrages_valides = _reverifier_eligibilite(entree, date_fin_periode, date_reference_reparations)
    if not ouvrages_valides:
        raise Http404("Plus aucune situation eligible pour cet employe (deja traitee).")

    sujet, texte, html, _nb_pe, _nb_fact, _nb_rep, _montant = rendre_email_combine(
        employe, entree['type_destinataire'], ouvrages_valides, annee_cible, mois_cible,
        date_fin_periode, est_test=False,
    )

    if format_demande == 'text':
        return HttpResponse(texte, content_type='text/plain; charset=utf-8')
    return HttpResponse(html, content_type='text/html; charset=utf-8')


@admin_required
@require_http_methods(["POST"])
def envoyer_situations_attention_test(request):
    """Declenche un envoi de TEST du moteur combine : tous les emails
    generes partent vers UNE seule adresse fournie par l'admin, bandeau
    TEST inclus."""
    from apps.messaging.relance_mailer_combine import envoyer_toutes_les_relances_combinees

    email_test = (request.POST.get('email_test') or '').strip()
    if not email_test:
        messages.error(request, "Adresse email de test requise.")
        return redirect('system:preview_situations_attention')
    try:
        validate_email(email_test)
    except ValidationError:
        messages.error(request, "Adresse email de test invalide.")
        return redirect('system:preview_situations_attention')

    annee_param = request.POST.get('annee')
    mois_param = request.POST.get('mois')
    resultat = envoyer_toutes_les_relances_combinees(
        annee=int(annee_param) if annee_param else None,
        mois=int(mois_param) if mois_param else None,
        dry_run=False, est_test=True, email_test_override=email_test,
    )
    messages.success(
        request,
        f"Envoi de test effectue : {resultat['nb_envoyes']} email(s) envoye(s) vers {email_test} "
        f"(representant {resultat['nb_destinataires']} destinataire(s) reel(s))."
    )
    redirect_url = f"{reverse('system:preview_situations_attention')}?annee={resultat['annee']}&mois={resultat['mois']}"
    return redirect(redirect_url)


@admin_required
@require_http_methods(["POST"])
def envoyer_situations_attention_reelles(request):
    """
    Declenchement manuel de l'envoi REEL combine (pas de test). Reserve a
    une action volontaire de l'administrateur : n'est appelee
    automatiquement par aucun code (ni tache Celery, ni cron), c'est un
    point d'entree distinct.
    """
    from apps.messaging.relance_mailer_combine import envoyer_toutes_les_relances_combinees

    annee_param = request.POST.get('annee')
    mois_param = request.POST.get('mois')
    resultat = envoyer_toutes_les_relances_combinees(
        annee=int(annee_param) if annee_param else None,
        mois=int(mois_param) if mois_param else None,
        dry_run=False, est_test=False,
    )
    messages.success(
        request,
        f"{resultat['nb_envoyes']} email(s) reel(s) envoye(s), {resultat['nb_echecs']} echec(s), "
        f"{resultat['nb_email_manquant']} email(s) manquant(s)."
    )
    redirect_url = f"{reverse('system:preview_situations_attention')}?annee={resultat['annee']}&mois={resultat['mois']}"
    return redirect(redirect_url)
