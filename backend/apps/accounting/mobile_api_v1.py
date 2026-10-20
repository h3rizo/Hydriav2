"""
API mobile — module Comptabilité (app Android `HydriaCompta`).

Montée sous /api/mobile/v1/compta/. Réutilise le jeton `scope='mobile'` émis
par /mobile/api/login/ (même décorateur que les endpoints terrain).

V1 — décisions arrêtées :
- Périmètre : l'ORGANISATION de l'employé connecté (via employe.base.organisation).
- Grand livre répliqué : exercice courant + N-1.
- Capacités : lecture + saisie caisse / écritures.

Restes (cf. doc de fondation §7) : champs de révision serveur pour un vrai
delta `changes`, idempotence forte des mutations, caisses / barèmes / soldes.
"""
import functools
import json
import logging
import traceback
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core.auth_tokens import token_or_session_required
from apps.core.models import WidgetAuthToken

from apps.accounting.models import BaseDiameX, SaisieComptable
from apps.billing.models import Fournisseur
from apps.organization.models import Compte, Journal

logger = logging.getLogger(__name__)
mobile_required = token_or_session_required(scope=WidgetAuthToken.SCOPE_MOBILE)

# Garde-fous de taille du payload bootstrap.
GRAND_LIVRE_MAX_ROWS = 8000
TIERS_MAX_ROWS = 6000


def _json_errors(view):
    """Toute exception -> JSON 500 (jamais de page HTML) + trace dans les logs."""
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("compta mobile %s a échoué", view.__name__)
            return JsonResponse(
                {'code': 'SERVER_ERROR', 'message': str(exc),
                 'where': view.__name__,
                 'trace': traceback.format_exc().splitlines()[-6:]},
                status=500,
            )
    return wrapper


def _employe(request):
    return getattr(request.user, 'employe', None)


def _organisation(request):
    employe = _employe(request)
    base = getattr(employe, 'base', None) if employe else None
    return getattr(base, 'organisation', None), base


def _money(value):
    """Float DiameX -> chaîne décimale à 2 décimales (jamais de float côté client)."""
    return f"{(value or 0):.2f}"


def _capabilities():
    codes = {
        'ecriture.read': True, 'ecriture.create': True,
        'caisse.read': True, 'caisse.create': True,
        'tiers.read': True, 'tiers.create': True,
        'facture.read': True, 'facture.create': False,  # V2
        'paie.simulate': True,
    }
    return [{'code': c, 'allowed': v} for c, v in codes.items()]


# --------------------------------------------------------------------------- #
#  bootstrap
# --------------------------------------------------------------------------- #

@require_GET
@mobile_required
@_json_errors
def bootstrap(request):
    organisation, base = _organisation(request)
    if organisation is None:
        return JsonResponse(
            {'code': 'NO_ORG', 'message': "Aucune organisation rattachée à cet utilisateur."},
            status=403,
        )

    annee = date.today().year
    exercices = [
        {
            'id': str(an), 'libelle': str(an),
            'debut': f'{an}-01-01', 'fin': f'{an}-12-31',
            'cloture': an < annee, 'revision': an,
        }
        for an in (annee - 1, annee)
    ]

    comptes = [
        {
            'id': str(c.id),
            'numero': (c.compte or '').strip(),
            'nom': c.nom_compte,
            'type': _type_compte(c.compte),
            'fournisseur_obligatoire': c.fournisseur_obligatoire,
            'employe_obligatoire': c.employe_obligatoire,
            'necessite_ouvrage': c.necessite_ouvrage,
            'charte_verification': c.charte_verification or None,
            'revision': 1,
        }
        for c in Compte.objects.filter(organisation=organisation).exclude(compte__isnull=True).exclude(compte='')
    ]

    journaux_qs = Journal.objects.filter(base__organisation=organisation)
    journaux = [
        {
            'id': str(j.id),
            'code': (j.code or '').strip(),
            'nom': j.nom_journal,
            'compte_contrepartie': j.compte or None,
            'base_id': str(j.base_id),
            'revision': 1,
        }
        for j in journaux_qs
    ]
    org_journal_codes = [j['code'] for j in journaux if j['code']]

    # V1 : tous les fournisseurs actifs de l'instance (le modèle Fournisseur
    # n'est pas cloisonné par organisation). §7 : restreindre aux tiers
    # effectivement mouvementés dans le grand livre de l'organisation une fois
    # les révisions serveur en place.
    tiers_rows = list(
        Fournisseur.objects.filter(actif=True).order_by('nom_fournisseur')
        .values('id', 'code_tiers', 'nom_fournisseur', 'numero_nif', 'numero_stat',
                'cin', 'telephone', 'email', 'adresse')
        [:TIERS_MAX_ROWS]
    )
    tiers = [
        {
            'id': str(f['id']),
            'type': 'FOURNISSEUR',
            'code_tiers': f['code_tiers'] or None,
            'nom': f['nom_fournisseur'],
            'nif': f['numero_nif'] or None,
            'stat': f['numero_stat'] or None,
            'cin': f['cin'] or None,
            'telephone': f['telephone'] or None,
            'email': f['email'] or None,
            'adresse': f['adresse'] or None,
            'actif': True,
            'solde': '0.00',
            'revision': 1,
        }
        for f in tiers_rows
    ]

    date_floor = date(annee - 1, 1, 1)
    gl_rows = list(
        BaseDiameX.objects
        .filter(date_m__gte=date_floor)
        .filter(Q(journal__base__organisation=organisation)
                | Q(journal__isnull=True, journal_code__in=org_journal_codes))
        .exclude(compte_code__isnull=True).exclude(compte_code='')
        .order_by('-date_m', '-rec')
        .values('id', 'date_m', 'date_rec', 'rec', 'description', 'journal_code',
                'compte_code', 'montant_in', 'montant_out', 'pers', 'activ', 'fin', 'scan')
        [:GRAND_LIVRE_MAX_ROWS]
    )
    grand_livre = [
        {
            'id': str(e['id']),
            'exercice_id': str(e['date_m'].year) if e['date_m'] else None,
            'journal_code': (e['journal_code'] or '').strip() or None,
            'date_mouvement': e['date_m'].isoformat() if e['date_m'] else None,
            'date_piece': e['date_rec'].isoformat() if e['date_rec'] else None,
            'rec': e['rec'],
            'description': e['description'] or '',
            'compte_numero': (e['compte_code'] or '').strip(),
            'debit': _money(e['montant_out']),
            'credit': _money(e['montant_in']),
            'tiers_ref': (e['pers'] or '').strip() or None,
            'activ': (e['activ'] or '').strip() or None,
            'financement': (e['fin'] or '').strip() or None,
            'piece_scan_url': e['scan'] or None,
            'lettrage_code': None,
            'revision': 1,
        }
        for e in gl_rows
        if e['date_m']
    ]

    now = timezone.now().isoformat()
    return JsonResponse({
        'cursor': now,
        'server_time': now,
        'payload': {
            'user': {
                'id': str(request.user.pk),
                'username': request.user.get_username(),
                'display_name': _display_name(request),
                'employe_id': str(_employe(request).id) if _employe(request) else None,
                'base_id': str(base.id) if base else None,
                'organisation_id': str(organisation.id),
                'organisation_nom': organisation.nom_organisation,
            },
            'capabilities': _capabilities(),
            'device': {'invoice_range': None},  # allocation à implémenter (V2)
            'exercices': exercices,
            'comptes': comptes,
            'journaux': journaux,
            'tiers': tiers,
            'tiers_tronque': len(tiers) >= TIERS_MAX_ROWS,
            'caisses': [],
            'grand_livre': grand_livre,
            'grand_livre_tronque': len(grand_livre) >= GRAND_LIVRE_MAX_ROWS,
            'soldes_reels': [],
            'baremes': {},
            'employes_paie': [],
        },
    })


def _type_compte(numero):
    first = (numero or '').strip()[:1]
    return {
        '1': 'PASSIF', '2': 'ACTIF', '3': 'ACTIF', '4': 'INDETERMINE',
        '5': 'ACTIF', '6': 'CHARGE', '7': 'PRODUIT',
    }.get(first, 'INDETERMINE')


def _display_name(request):
    employe = _employe(request)
    if employe is not None:
        return getattr(employe, 'nom_affichage', None) or request.user.get_username()
    return request.user.get_full_name() or request.user.get_username()


# --------------------------------------------------------------------------- #
#  changes  (delta — indisponible tant que les révisions serveur n'existent pas)
# --------------------------------------------------------------------------- #

@require_GET
@mobile_required
def changes(request):
    now = timezone.now().isoformat()
    return JsonResponse({
        'cursor': now,
        'has_more': False,
        'full_refresh_required': True,
        'reason': 'SERVER_REVISIONS_UNAVAILABLE',
        'changes': {},
    })


# --------------------------------------------------------------------------- #
#  soldes  (caisses / banques / financements — même logique que compta.hydria.mg/accueil/)
# --------------------------------------------------------------------------- #

@require_GET
@mobile_required
@_json_errors
def soldes(request):
    from collections import defaultdict
    from apps.accounting import views as av

    entries = av._get_diamex_scope_by_prog(request.user)
    entries = av._exclude_sensitive_diamex_lines_for_non_privileged(entries, request.user)
    entries = entries.filter(Q(montant_in__gt=0) | Q(montant_out__gt=0))

    mois = (request.GET.get('mois') or '').strip()  # 'YYYY-MM' optionnel
    if mois:
        try:
            an, mo = (int(x) for x in mois.split('-', 1))
            import calendar as _cal
            entries = entries.filter(date_m__lte=date(an, mo, _cal.monthrange(an, mo)[1]))
        except (TypeError, ValueError):
            mois = ''

    rows = entries.values('montant_in', 'montant_out', 'fin', 'compte_code', 'journal_code')

    fin_map = defaultdict(lambda: {
        'label': '', 'solde': Decimal('0'), 'edf': Decimal('0'),
        'recettes': Decimal('0'), 'depenses': Decimal('0'), 'count': 0,
    })
    jrn_map = defaultdict(lambda: {
        'label': '', 'solde': Decimal('0'),
        'recettes': Decimal('0'), 'depenses': Decimal('0'), 'count': 0,
    })
    edf_prefixes = ('00FND1', '00FND2', '00FND3', '00FND4')

    for e in rows.iterator(chunk_size=2000):
        mi = Decimal(str(e['montant_in'] or 0))
        mo = Decimal(str(e['montant_out'] or 0))
        s = mi - mo
        cc = (e['compte_code'] or '').strip().upper()
        jc = (e['journal_code'] or '').strip().upper()

        if not (cc.startswith('00PERS') or cc.startswith('00BOOK')):
            fin_label = av._clean_fin_label(e['fin']) or 'Sans financement'
            key = av._normalize_fin_bucket(fin_label) or av._normalize_text(fin_label)
            b = fin_map[key]
            if not b['label'] or len(fin_label) < len(b['label']):
                b['label'] = fin_label
            if cc.startswith(edf_prefixes) or jc.startswith(edf_prefixes):
                b['edf'] += s
            else:
                b['recettes'] += mi
                b['depenses'] += mo
            b['solde'] += s
            b['count'] += 1

        jl = (e['journal_code'] or 'Sans journal').strip() or 'Sans journal'
        if jl not in ('00PERS', '00SPLITBOOK-MGA'):
            jm = jrn_map[av._normalize_text(jl)]
            jm['label'] = jl
            jm['recettes'] += mi
            jm['depenses'] += mo
            jm['solde'] += s
            jm['count'] += 1

    def to_json(bucket):
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in bucket.items()}

    journaux = [
        to_json(it) for it in sorted(jrn_map.values(), key=lambda x: x['label'].lower())
        if abs(it['solde']) > Decimal('0.01')
    ]
    caisses = [j for j in journaux if j['label'].upper().startswith('C')]
    banques = [j for j in journaux if j['label'].upper().startswith('B')]
    autres = [j for j in journaux if not j['label'].upper().startswith(('C', 'B'))]
    financements = [to_json(it) for it in sorted(fin_map.values(), key=lambda x: x['label'].lower())]

    def total(items):
        return str(sum((Decimal(x['solde']) for x in items), Decimal('0')))

    return JsonResponse({
        'generated_at': timezone.now().isoformat(),
        'mois': mois or None,
        'caisses': caisses,
        'banques': banques,
        'autres_journaux': autres,
        'financements': financements,
        'totaux': {
            'caisses': total(caisses),
            'banques': total(banques),
            'financements': total(financements),
        },
    })


# --------------------------------------------------------------------------- #
#  vérification des scans (lecture seule — reprend
#  apps/accounting/views_verification_scans.py, sans relancer la vérification
#  filesystem : celle-ci reste une action web/desktop, exécutée sur une machine
#  ayant accès au lecteur réseau des scans. Le mobile consulte le cache déjà
#  calculé (ScanVerificationCache).
# --------------------------------------------------------------------------- #

# Comptes qui n'ont jamais besoin de scan : transferts internes (00BOOK),
# comptes de tiers (00PERS), et 00FND1 hors mention EDF (transferts inter-
# fichiers). Même filtre que la page web.
def _entries_necessitant_scan(request):
    from apps.accounting import views as av

    entries = av._get_diamex_scope_by_prog(request.user)
    entries = av._exclude_sensitive_diamex_lines_for_non_privileged(entries, request.user)
    return entries.exclude(
        Q(compte_code__icontains='00BOOK')
        | Q(compte_code__icontains='00PERS')
        | (Q(compte_code__icontains='00FND1')
           & ~Q(description__icontains='EDF') & ~Q(info__icontains='EDF'))
    )


@require_GET
@mobile_required
@_json_errors
def verification_scans_recap(request):
    from collections import defaultdict
    from .models import ScanVerificationCache

    entries = _entries_necessitant_scan(request)
    total_entries = entries.count()

    cache = ScanVerificationCache.objects.first()
    scans_valides_ids = set(cache.scans_valides_ids) if cache and cache.scans_valides_ids else set()
    liens_morts_ids = set(cache.liens_morts_ids) if cache and cache.liens_morts_ids else set()

    def taux(part, total):
        return int((part / total * 100)) if total > 0 else 0

    scans_valides = entries.filter(id__in=scans_valides_ids).count() if scans_valides_ids else 0
    liens_morts = entries.filter(id__in=liens_morts_ids).count() if liens_morts_ids else 0
    sans_scan = entries.filter(Q(scan__isnull=True) | Q(scan='')).count()

    rows = entries.values('date_m', 'fichier_source', 'id')
    par_fichier = defaultdict(lambda: defaultdict(lambda: {
        'total': 0, 'scans_valides': 0, 'liens_morts': 0, 'sans_scan': 0,
    }))
    par_fichier_totaux = defaultdict(lambda: {
        'total': 0, 'scans_valides': 0, 'liens_morts': 0, 'sans_scan': 0,
    })

    # Comptage en Python (mêmes petites lignes que la page web, agrégées ici
    # sans SQL Case/When pour rester simple à maintenir en commun avec le detail).
    for row in rows.iterator(chunk_size=3000):
        fichier = row['fichier_source'] or 'Sans fichier'
        mois_key = row['date_m'].strftime('%Y-%m') if row['date_m'] else 'Sans date'
        bucket = par_fichier[fichier][mois_key]
        bucket['total'] += 1
        totaux = par_fichier_totaux[fichier]
        totaux['total'] += 1
        rid = row['id']
        if rid in scans_valides_ids:
            bucket['scans_valides'] += 1
            totaux['scans_valides'] += 1
        elif rid in liens_morts_ids:
            bucket['liens_morts'] += 1
            totaux['liens_morts'] += 1

    # sans_scan compté séparément (scan vide/null), pas d'aller-retour DB par ligne.
    sans_scan_rows = entries.filter(Q(scan__isnull=True) | Q(scan='')).values('date_m', 'fichier_source')
    for row in sans_scan_rows.iterator(chunk_size=3000):
        fichier = row['fichier_source'] or 'Sans fichier'
        mois_key = row['date_m'].strftime('%Y-%m') if row['date_m'] else 'Sans date'
        par_fichier[fichier][mois_key]['sans_scan'] += 1
        par_fichier_totaux[fichier]['sans_scan'] += 1

    fichiers_json = []
    for fichier in sorted(par_fichier.keys()):
        mois_list = []
        for mois_key, stats in sorted(par_fichier[fichier].items(), reverse=True):
            mois_list.append({
                'mois': mois_key,
                'total': stats['total'],
                'scans_valides': stats['scans_valides'],
                'liens_morts': stats['liens_morts'],
                'sans_scan': stats['sans_scan'],
                'taux_valides': taux(stats['scans_valides'], stats['total']),
            })
        totaux = par_fichier_totaux[fichier]
        fichiers_json.append({
            'fichier': fichier,
            'total': totaux['total'],
            'scans_valides': totaux['scans_valides'],
            'liens_morts': totaux['liens_morts'],
            'sans_scan': totaux['sans_scan'],
            'mois': mois_list,
        })

    return JsonResponse({
        'generated_at': timezone.now().isoformat(),
        'date_derniere_verif': cache.date_verification.isoformat() if cache and cache.date_verification else None,
        'total_entries': total_entries,
        'scans_valides': scans_valides,
        'liens_morts': liens_morts,
        'sans_scan': sans_scan,
        'taux_scans_valides': taux(scans_valides, total_entries),
        'taux_liens_morts': taux(liens_morts, total_entries),
        'taux_sans_scan': taux(sans_scan, total_entries),
        'fichiers': fichiers_json,
    })


@require_GET
@mobile_required
@_json_errors
def verification_scans_detail(request):
    from apps.employees.models import EmployeBaseDiameX
    from .models import ScanVerificationCache
    import os

    mois = (request.GET.get('mois') or '').strip()
    fichier = (request.GET.get('fichier') or '').strip()
    statut = (request.GET.get('statut') or 'all').strip()
    if not mois or not fichier:
        return JsonResponse({'success': False, 'error': 'Paramètres mois et fichier requis'}, status=400)

    entries = _entries_necessitant_scan(request)
    if mois != 'Sans date':
        try:
            annee, mo = (int(x) for x in mois.split('-', 1))
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Paramètre mois invalide'}, status=400)
        entries = entries.filter(date_m__year=annee, date_m__month=mo)
    else:
        entries = entries.filter(date_m__isnull=True)

    if fichier != 'Sans fichier':
        entries = entries.filter(fichier_source=fichier)
    else:
        entries = entries.filter(Q(fichier_source__isnull=True) | Q(fichier_source=''))

    cache = ScanVerificationCache.objects.first()
    scans_valides_ids = set(cache.scans_valides_ids) if cache and cache.scans_valides_ids else set()
    liens_morts_ids = set(cache.liens_morts_ids) if cache and cache.liens_morts_ids else set()

    if statut == 'valides':
        entries = entries.filter(id__in=scans_valides_ids)
    elif statut == 'liens_morts':
        entries = entries.filter(id__in=liens_morts_ids)
    elif statut == 'sans_scan':
        entries = entries.filter(Q(scan__isnull=True) | Q(scan=''))

    page = max(1, int(request.GET.get('page', 1) or 1))
    per_page = min(100, max(1, int(request.GET.get('per_page', 50) or 50)))

    from django.core.paginator import Paginator
    paginator = Paginator(entries.order_by('-date_rec'), per_page)
    page_obj = paginator.get_page(page)

    organisation, _base = _organisation(request)
    bases_qs = EmployeBaseDiameX.objects.select_related('employe')
    if organisation is not None:
        bases_qs = bases_qs.filter(employe__base__organisation=organisation)
    bases_by_employe_file = {}
    global_base_by_file = {}
    for b in bases_qs:
        bases_by_employe_file[(str(b.employe_id), b.base_diamex)] = b.chemin_base_diamex or ''
        global_base_by_file.setdefault(b.base_diamex, b.chemin_base_diamex or '')

    entries_data = []
    for entry in page_obj:
        if entry.id in scans_valides_ids:
            scan_statut, scan_label = 'valide', 'Scan valide'
        elif entry.id in liens_morts_ids:
            scan_statut, scan_label = 'lien_mort', 'Lien mort'
        elif entry.scan:
            scan_statut, scan_label = 'non_verifie', 'Non vérifié'
        else:
            scan_statut, scan_label = 'sans_scan', 'Sans scan'

        scan_absolu = None
        if entry.scan:
            scan_relatif = entry.scan.strip('#')
            if scan_relatif.startswith('.'):
                scan_relatif = scan_relatif[1:]
            is_abs = (
                (len(scan_relatif) > 2 and scan_relatif[1] == ':' and scan_relatif[2] in ('\\', '/'))
                or scan_relatif.startswith('\\\\')
                or scan_relatif.startswith('/')
            )
            if is_abs:
                scan_absolu = scan_relatif
            else:
                chemin_base = ''
                if entry.imported_by_id and entry.fichier_source:
                    chemin_base = bases_by_employe_file.get((str(entry.imported_by_id), entry.fichier_source), '')
                if not chemin_base and entry.fichier_source:
                    chemin_base = global_base_by_file.get(entry.fichier_source, '')
                if chemin_base:
                    scan_absolu = os.path.normpath(os.path.join(chemin_base, scan_relatif.lstrip('\\/')))
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
            'montant_in': _money(entry.montant_in),
            'montant_out': _money(entry.montant_out),
            'scan_absolu': scan_absolu,
            'scan_statut': scan_statut,
            'scan_label': scan_label,
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
        },
    })


# --------------------------------------------------------------------------- #
#  mutations  (push de l'outbox)
# --------------------------------------------------------------------------- #

@csrf_exempt
@require_POST
@mobile_required
@_json_errors
def mutations(request):
    organisation, base = _organisation(request)
    if organisation is None:
        return JsonResponse({'code': 'NO_ORG', 'message': "Aucune organisation rattachée."}, status=403)

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'code': 'INVALID_JSON', 'message': 'Corps JSON invalide.'}, status=400)

    results = []
    for item in body.get('mutations', []):
        results.append(_traiter_mutation(request, organisation, base, item))
    return JsonResponse({'results': results})


def _traiter_mutation(request, organisation, base, item):
    local_uuid = item.get('local_uuid')
    op = item.get('type')
    payload = item.get('payload') or {}
    base_out = {'local_uuid': local_uuid}

    # Idempotence faible V1 : jeton mobile stocké dans SaisieComptable.info.
    token = f'mobile:{local_uuid}'
    existante = SaisieComptable.objects.filter(info=token).order_by('created_at').first()
    if existante is not None:
        return {**base_out, 'status': 'accepted', 'server_id': str(existante.id)}

    try:
        if op in ('piece.submit', 'piece.create', 'piece.update'):
            server_id = _creer_piece(request, organisation, base, payload, token)
        elif op == 'caisse.mouvement.create':
            server_id = _creer_mouvement_caisse(request, organisation, base, payload, token)
        elif op == 'tiers.create':
            server_id = _creer_tiers(payload)
        else:
            return {**base_out, 'status': 'rejected', 'errors': f"Type de mutation non supporté (V1) : {op}"}
    except _RejetValidation as exc:
        return {**base_out, 'status': 'rejected', 'errors': str(exc)}

    return {**base_out, 'status': 'accepted', 'server_id': server_id}


class _RejetValidation(Exception):
    pass


def _parse_date(raw):
    try:
        return date.fromisoformat((raw or '').strip()) if raw else date.today()
    except ValueError:
        raise _RejetValidation(f"Date invalide : {raw!r} (attendu AAAA-MM-JJ).")


def _parse_montant(raw):
    try:
        return Decimal(str(raw or 0))
    except (InvalidOperation, ValueError):
        raise _RejetValidation(f"Montant invalide : {raw!r}.")


def _resoudre_journal(organisation, base, payload):
    journal_id = payload.get('journal_id')
    qs = Journal.objects.filter(base__organisation=organisation)
    if journal_id:
        journal = qs.filter(id=journal_id).first()
        if journal:
            return journal
    code = payload.get('journal_code')
    if code:
        journal = qs.filter(code=code).first()
        if journal:
            return journal
    journal = qs.filter(base=base).first() if base else qs.first()
    if journal is None:
        raise _RejetValidation("Aucun journal disponible pour cette organisation.")
    return journal


def _resoudre_base(organisation, base, journal):
    return base or journal.base


def _creer_piece(request, organisation, base, payload, token):
    journal = _resoudre_journal(organisation, base, payload)
    base_obj = _resoudre_base(organisation, base, journal)
    lignes = payload.get('lignes') or []
    if len(lignes) < 2:
        raise _RejetValidation("Une pièce doit comporter au moins deux lignes.")

    date_m = _parse_date(payload.get('date'))
    description = (payload.get('description') or '').strip() or 'Saisie mobile'
    employe = _employe(request)

    total_debit = total_credit = Decimal('0')
    saisies = []
    for idx, ligne in enumerate(lignes, start=1):
        numero = (ligne.get('compte_numero') or '').strip()
        compte = Compte.objects.filter(organisation=organisation, compte=numero).first()
        if compte is None:
            raise _RejetValidation(f"Ligne {idx} : compte {numero!r} inconnu dans l'organisation.")
        debit = _parse_montant(ligne.get('debit'))
        credit = _parse_montant(ligne.get('credit'))
        total_debit += debit
        total_credit += credit
        saisies.append((compte, ligne, debit, credit))

    if abs(total_debit - total_credit) > Decimal('0.01'):
        raise _RejetValidation(
            f"Pièce déséquilibrée : débit {total_debit} ≠ crédit {total_credit}."
        )

    premier_id = None
    for compte, ligne, debit, credit in saisies:
        obj = SaisieComptable.objects.create(
            base=base_obj,
            journal=journal,
            compte=compte,
            compte_code=(compte.compte or ''),
            date_m=date_m,
            description=(ligne.get('libelle') or description)[:255],
            montant_in=credit,
            montant_out=debit,
            activ=(ligne.get('activ') or None),
            fin=(ligne.get('financement') or None),
            fournisseur=(ligne.get('tiers') or None),
            statut='brouillon',
            source_saisie='mobile',
            info=token,
            created_by=employe,
        )
        premier_id = premier_id or str(obj.id)
    return premier_id


def _creer_mouvement_caisse(request, organisation, base, payload, token):
    journal = (
        Journal.objects.filter(base__organisation=organisation, code__icontains='cai').first()
        or _resoudre_journal(organisation, base, payload)
    )
    base_obj = _resoudre_base(organisation, base, journal)
    numero = (payload.get('compte_numero') or '').strip()
    compte = Compte.objects.filter(organisation=organisation, compte=numero).first()
    if compte is None:
        raise _RejetValidation(f"Compte {numero!r} inconnu pour ce mouvement de caisse.")

    montant = _parse_montant(payload.get('montant'))
    entree = (payload.get('sens') or 'ENTREE').upper() == 'ENTREE'
    obj = SaisieComptable.objects.create(
        base=base_obj,
        journal=journal,
        compte=compte,
        compte_code=(compte.compte or ''),
        date_m=_parse_date(payload.get('date')),
        description=(payload.get('motif') or 'Mouvement de caisse')[:255],
        montant_in=montant if entree else Decimal('0'),
        montant_out=Decimal('0') if entree else montant,
        statut='brouillon',
        source_saisie='mobile',
        info=token,
        created_by=_employe(request),
    )
    return str(obj.id)


def _creer_tiers(payload):
    nom = (payload.get('nom') or '').strip()
    if not nom:
        raise _RejetValidation("Nom du tiers requis.")
    fournisseur = Fournisseur.objects.create(
        nom_fournisseur=nom,
        code_tiers=(payload.get('code_tiers') or None),
        numero_nif=(payload.get('nif') or None),
        numero_stat=(payload.get('stat') or None),
        cin=(payload.get('cin') or None),
        telephone=(payload.get('telephone') or None),
        email=(payload.get('email') or None),
        adresse=(payload.get('adresse') or None),
        actif=True,
    )
    return str(fournisseur.id)
