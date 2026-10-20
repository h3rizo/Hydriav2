"""
Vue pour la vérification des scans - Page récapitulative par mois/fichier
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Case, When, IntegerField
from django.core.paginator import Paginator
from collections import defaultdict
from .models import BaseDiameX, ScanVerificationCache
from apps.employees.models import EmployeBaseDiameX
from apps.organization.models import Base
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _get_scoped_diamex_queryset(user):
    qs = BaseDiameX.objects.all()
    if getattr(user, 'is_superuser', False):
        return qs

    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return qs.none()

    allowed_progs = list(
        Base.objects.filter(organisation_id=organisation_id)
        .exclude(prog_diamex__isnull=True)
        .exclude(prog_diamex='')
        .values_list('prog_diamex', flat=True)
        .distinct()
    )
    if not allowed_progs:
        return qs.none()
    return qs.filter(prog__in=allowed_progs)


def _get_scoped_bases_queryset(user):
    qs = EmployeBaseDiameX.objects.select_related('employe')
    if getattr(user, 'is_superuser', False):
        return qs

    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return qs.none()
    return qs.filter(employe__base__organisation_id=organisation_id)


@login_required
def verification_scans_recap(request):
    """
    Page récapitulative de vérification des scans par mois/fichier.
    N'affiche que les opérations qui ont besoin de scan.
    """

    # Récupérer uniquement les entrées qui ont besoin de scan
    # Exclure:
    # - 00BOOK (transferts internes)
    # - 00PERS (comptes de tiers)
    # - 00FND1 SANS "EDF" dans description/info (transferts inter-fichiers)
    entries_all = _get_scoped_diamex_queryset(request.user).exclude(
        Q(compte_code__icontains='00BOOK') |
        Q(compte_code__icontains='00PERS') |
        (Q(compte_code__icontains='00FND1') & ~Q(description__icontains='EDF') & ~Q(info__icontains='EDF'))
    )

    # Récupérer la liste des fichiers pour le filtre (sans doublons)
    fichiers_list = sorted(list(set(
        entries_all.exclude(
            Q(fichier_source__isnull=True) | Q(fichier_source='')
        ).values_list('fichier_source', flat=True)
    )))

    # Récupérer les filtres
    filter_mois = request.GET.get('mois', '')
    filter_fichier = request.GET.get('fichier', '')

    # Appliquer les filtres
    entries_base = entries_all
    if filter_mois:
        # Format: YYYY-MM
        year, month = filter_mois.split('-')
        entries_base = entries_base.filter(
            date_m__year=int(year),
            date_m__month=int(month)
        )

    if filter_fichier:
        entries_base = entries_base.filter(fichier_source=filter_fichier)

    # Statistiques globales (après filtres)
    total_entries = entries_base.count()

    # Récupérer le cache de vérification
    cache = ScanVerificationCache.objects.first()

    scans_valides_ids = set(cache.scans_valides_ids) if cache and cache.scans_valides_ids else set()
    liens_morts_ids = set(cache.liens_morts_ids) if cache and cache.liens_morts_ids else set()

    # Compter par statut de scan en utilisant le cache
    scans_valides = entries_base.filter(id__in=scans_valides_ids).count() if scans_valides_ids else 0
    liens_morts = entries_base.filter(id__in=liens_morts_ids).count() if liens_morts_ids else 0
    sans_scan = entries_base.filter(
        Q(scan__isnull=True) | Q(scan='')
    ).count()

    # Date de dernière vérification depuis le cache
    date_derniere_verif = cache.date_verification if cache else None

    # Groupement par mois et fichier avec agrégation SQL
    # Utiliser Case/When pour compter les statuts basés sur les IDs du cache
    recap_data = entries_base.values(
        'date_m',
        'fichier_source'
    ).annotate(
        total=Count('id'),
        scans_valides=Count(
            Case(
                When(id__in=scans_valides_ids, then=1),
                output_field=IntegerField()
            )
        ) if scans_valides_ids else Count('id', filter=Q(id__in=[])),
        liens_morts=Count(
            Case(
                When(id__in=liens_morts_ids, then=1),
                output_field=IntegerField()
            )
        ) if liens_morts_ids else Count('id', filter=Q(id__in=[])),
        sans_scan=Count('id', filter=Q(scan__isnull=True) | Q(scan=''))
    ).order_by('-date_m', 'fichier_source')

    # Organiser les données par fichier et mois
    recap_par_fichier = defaultdict(lambda: {
        'mois': {},
        'total': 0,
        'scans_valides': 0,
        'liens_morts': 0,
        'sans_scan': 0
    })

    for entry in recap_data:
        mois_key = entry['date_m'].strftime('%Y-%m') if entry['date_m'] else 'Sans date'
        fichier = entry['fichier_source'] or 'Sans fichier'

        # Ajouter au mois spécifique pour ce fichier
        if mois_key not in recap_par_fichier[fichier]['mois']:
            recap_par_fichier[fichier]['mois'][mois_key] = {
                'total': 0,
                'scans_valides': 0,
                'liens_morts': 0,
                'sans_scan': 0,
                'taux_valides': 0
            }

        total = entry['total']
        valides = entry['scans_valides']

        recap_par_fichier[fichier]['mois'][mois_key]['total'] = total
        recap_par_fichier[fichier]['mois'][mois_key]['scans_valides'] = valides
        recap_par_fichier[fichier]['mois'][mois_key]['liens_morts'] = entry['liens_morts']
        recap_par_fichier[fichier]['mois'][mois_key]['sans_scan'] = entry['sans_scan']
        recap_par_fichier[fichier]['mois'][mois_key]['taux_valides'] = int((valides / total * 100) if total > 0 else 0)

        # Ajouter aux totaux du fichier
        recap_par_fichier[fichier]['total'] += total
        recap_par_fichier[fichier]['scans_valides'] += valides
        recap_par_fichier[fichier]['liens_morts'] += entry['liens_morts']
        recap_par_fichier[fichier]['sans_scan'] += entry['sans_scan']

    # Convertir en liste triée par fichier
    recap_by_fichier = []
    for fichier, data in sorted(recap_par_fichier.items()):
        # Convertir les mois en liste triée
        mois_details = []
        for mois_key, mois_stats in sorted(data['mois'].items(), reverse=True):
            mois_details.append({
                'mois': mois_key,
                'total': mois_stats['total'],
                'scans_valides': mois_stats['scans_valides'],
                'liens_morts': mois_stats['liens_morts'],
                'sans_scan': mois_stats['sans_scan'],
                'taux_valides': mois_stats['taux_valides']
            })

        recap_by_fichier.append({
            'fichier': fichier,
            'mois_count': len(mois_details),
            'total': data['total'],
            'scans_valides': data['scans_valides'],
            'liens_morts': data['liens_morts'],
            'sans_scan': data['sans_scan'],
            'mois_list': mois_details
        })

    # Statistiques en pourcentage
    taux_scans_valides = int((scans_valides / total_entries * 100) if total_entries > 0 else 0)
    taux_liens_morts = int((liens_morts / total_entries * 100) if total_entries > 0 else 0)
    taux_sans_scan = int((sans_scan / total_entries * 100) if total_entries > 0 else 0)

    context = {
        'total_entries': total_entries,
        'scans_valides': scans_valides,
        'liens_morts': liens_morts,
        'sans_scan': sans_scan,
        'taux_scans_valides': taux_scans_valides,
        'taux_liens_morts': taux_liens_morts,
        'taux_sans_scan': taux_sans_scan,
        'date_derniere_verif': date_derniere_verif,
        'recap_by_fichier': recap_by_fichier,
        'fichiers_list': fichiers_list,
    }

    return render(request, 'accounting/verification_scans_recap.html', context)


@login_required
def api_detail_scans(request):
    """
    API pour récupérer le détail des scans pour un mois/fichier spécifique.
    """
    mois = request.GET.get('mois')  # Format: YYYY-MM
    fichier = request.GET.get('fichier')
    statut = request.GET.get('statut', 'all')  # all, valides, liens_morts, sans_scan

    if not mois or not fichier:
        return JsonResponse({
            'success': False,
            'error': 'Paramètres mois et fichier requis'
        }, status=400)

    # Filtrer les entrées - Exclure celles qui n'ont pas besoin de scan
    # - 00BOOK (transferts internes)
    # - 00PERS (comptes de tiers)
    # - 00FND1 SANS "EDF" dans description/info (transferts inter-fichiers)
    entries = _get_scoped_diamex_queryset(request.user).exclude(
        Q(compte_code__icontains='00BOOK') |
        Q(compte_code__icontains='00PERS') |
        (Q(compte_code__icontains='00FND1') & ~Q(description__icontains='EDF') & ~Q(info__icontains='EDF'))
    )

    # Filtre par mois
    if mois != 'Sans date':
        year, month = mois.split('-')
        entries = entries.filter(
            date_m__year=int(year),
            date_m__month=int(month)
        )
    else:
        entries = entries.filter(date_m__isnull=True)

    # Filtre par fichier
    if fichier != 'Sans fichier':
        entries = entries.filter(fichier_source=fichier)
    else:
        entries = entries.filter(
            Q(fichier_source__isnull=True) | Q(fichier_source='')
        )

    # Récupérer le cache de vérification
    cache = ScanVerificationCache.objects.first()
    scans_valides_ids = set(cache.scans_valides_ids) if cache and cache.scans_valides_ids else set()
    liens_morts_ids = set(cache.liens_morts_ids) if cache and cache.liens_morts_ids else set()

    # Filtre par statut
    if statut == 'valides':
        entries = entries.filter(id__in=scans_valides_ids)
    elif statut == 'liens_morts':
        entries = entries.filter(id__in=liens_morts_ids)
    elif statut == 'sans_scan':
        entries = entries.filter(Q(scan__isnull=True) | Q(scan=''))

    # Pagination
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 50))

    paginator = Paginator(entries.order_by('-date_rec'), per_page)
    page_obj = paginator.get_page(page)

    # Précharger les bases DiameX pour reconstruire les chemins scans
    bases_by_employe_file = {}
    global_base_by_file = {}
    for base in _get_scoped_bases_queryset(request.user):
        bases_by_employe_file[(str(base.employe_id), base.base_diamex)] = base.chemin_base_diamex or ''
        if base.base_diamex not in global_base_by_file:
            global_base_by_file[base.base_diamex] = base.chemin_base_diamex or ''

    # Construire les données avec détection du statut scan
    entries_data = []
    for entry in page_obj:
        # Déterminer le statut de scan : la copie serveur (VPS) prime, puis le cache
        from .scan_resolution import copie_serveur_existe
        if entry.id in scans_valides_ids or copie_serveur_existe(entry):
            scan_info = {
                'statut': 'valide',
                'label': 'Scan valide',
                'badge_class': 'badge-success'
            }
        elif entry.id in liens_morts_ids:
            scan_info = {
                'statut': 'lien_mort',
                'label': 'Lien mort',
                'badge_class': 'badge-warning'
            }
        elif entry.scan:
            scan_info = {
                'statut': 'non_verifie',
                'label': 'Non vérifié',
                'badge_class': 'badge-info'
            }
        else:
            scan_info = {
                'statut': 'sans_scan',
                'label': 'Sans scan',
                'badge_class': 'badge-error'
            }

        # Construire le chemin absolu du scan si disponible
        scan_absolu = None
        if entry.scan:
            scan_relatif = entry.scan.strip('#')
            if scan_relatif.startswith('.'):
                scan_relatif = scan_relatif[1:]

            # Si déjà absolu (C:\..., \\serveur\... ou /...)
            is_abs = (
                (len(scan_relatif) > 2 and scan_relatif[1] == ':' and scan_relatif[2] in ('\\', '/')) or
                scan_relatif.startswith('\\\\') or
                scan_relatif.startswith('/')
            )

            if is_abs:
                scan_absolu = scan_relatif
            else:
                chemin_base = ''

                # Priorité 1: base de l'employé qui a importé l'entrée
                if entry.imported_by_id and entry.fichier_source:
                    chemin_base = bases_by_employe_file.get((str(entry.imported_by_id), entry.fichier_source), '')

                # Priorité 2: fallback global sur le fichier_source si unique
                if not chemin_base and entry.fichier_source:
                    chemin_base = global_base_by_file.get(entry.fichier_source, '')

                if chemin_base:
                    scan_clean = scan_relatif.lstrip('\\/')
                    scan_absolu = os.path.normpath(os.path.join(chemin_base, scan_clean))
                else:
                    scan_absolu = scan_relatif

        entries_data.append({
            'id': entry.id,
            'id_access': entry.id_access,
            'date_rec': entry.date_rec.strftime('%d/%m/%Y') if entry.date_rec else '-',
            'rec': entry.rec or '-',
            'journal_code': entry.journal_code or '-',
            'description': entry.description or '-',
            'compte_code': entry.compte_code or '-',
            'montant_in': float(entry.montant_in) if entry.montant_in else 0,
            'montant_out': float(entry.montant_out) if entry.montant_out else 0,
            'scan_absolu': scan_absolu,
            'scan_info': scan_info,
            'pers': entry.pers or '-',
            'detail': entry.detail or '-',
            'info': entry.info or '-',
        })

    return JsonResponse({
        'success': True,
        'entries': entries_data,
        'pagination': {
            'current_page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_entries': paginator.count,
            'has_previous': page_obj.has_previous(),
            'has_next': page_obj.has_next(),
        }
    })
