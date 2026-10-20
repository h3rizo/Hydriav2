"""
Recoupement des paiements forfaitaires avec la comptabilite DiameX

3 types de recoupement :
1. Normal : PaiementForfaitaire (numeroDiameX, baseDiameX) -> BaseDiameX (id_access, prog)
2. Inverse : BaseDiameX (compte 748411) -> PaiementForfaitaire
3. Par extraction : BaseDiameX (compte 748411) -> Extraction ouvrage -> PaiementForfaitaire (via ouvrage)
"""

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render

from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
from apps.accounting.models import BaseDiameX
from apps.billing.models import PaiementForfaitaire, PointEau
from apps.employees.models import EmployeBaseDiameX
from apps.organization.models import Base, Ouvrage
from apps.organization.scoping import get_user_accessible_gestionnaire_ids


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _get_user_gestionnaire_ids(user):
    return get_user_accessible_gestionnaire_ids(user)


def _get_allowed_progs(user):
    if getattr(user, 'is_superuser', False):
        return None
    gestionnaire_ids = _get_user_gestionnaire_ids(user)
    if gestionnaire_ids is None:
        return None
    if not gestionnaire_ids:
        return []
    return list(
        Base.objects.filter(organisation_id__in=gestionnaire_ids)
        .exclude(prog_diamex__isnull=True)
        .exclude(prog_diamex='')
        .values_list('prog_diamex', flat=True)
        .distinct()
    )


def _scope_diamex_queryset(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    allowed_progs = _get_allowed_progs(user)
    if not allowed_progs:
        return queryset.none()
    return queryset.filter(prog__in=allowed_progs)


def _scope_paiements_queryset(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    gestionnaire_ids = _get_user_gestionnaire_ids(user)
    if not gestionnaire_ids:
        return queryset.none()
    return queryset.filter(
        point_eau__ouvrage__modalites_gestion__gestionnaire_id__in=gestionnaire_ids,
        point_eau__ouvrage__modalites_gestion__date_fin__isnull=True,
    ).distinct()


def _scope_ouvrages_queryset(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    gestionnaire_ids = _get_user_gestionnaire_ids(user)
    if not gestionnaire_ids:
        return queryset.none()
    return queryset.filter(
        modalites_gestion__gestionnaire_id__in=gestionnaire_ids,
        modalites_gestion__date_fin__isnull=True,
    ).distinct()


@login_required
def recoupement_paiements_forfaitaires(request):
    filter_status = request.GET.get('status', '')
    filter_base = request.GET.get('base', '')
    filter_mois = request.GET.get('mois', '')
    filter_ouvrage = request.GET.get('ouvrage', '')

    filter_prog_inverse = request.GET.get('prog_inverse', '')
    filter_mois_inverse = request.GET.get('mois_inverse', '')
    filter_status_inverse = request.GET.get('status_inverse', '')

    filter_ouvrage_extraction = request.GET.get('ouvrage_extraction', '')
    filter_mois_extraction = request.GET.get('mois_extraction', '')
    filter_prog_extraction = request.GET.get('prog_extraction', '')
    filter_status_extraction = request.GET.get('status_extraction', '')

    gestionnaire_ids = _get_user_gestionnaire_ids(request.user)
    organisation_ids = set(gestionnaire_ids or [])
    diamex_scope_qs = _scope_diamex_queryset(BaseDiameX.objects.all(), request.user)
    paiements_scope_qs = _scope_paiements_queryset(PaiementForfaitaire.objects.all(), request.user)

    # SECTION 1: RECOUPEMENT NORMAL
    paiements = paiements_scope_qs.filter(
        numeroDiameX__isnull=False,
        baseDiameX__isnull=False,
    ).exclude(numeroDiameX='').exclude(baseDiameX='').select_related(
        'point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle',
        'point_eau__parcelle__village',
        'point_eau__parcelle__village__fokontany',
        'point_eau__parcelle__village__fokontany__commune',
    )

    if filter_base:
        paiements = paiements.filter(baseDiameX=filter_base)

    if filter_mois:
        try:
            year, month = filter_mois.split('-')
            paiements = paiements.filter(date_facture__year=int(year), date_facture__month=int(month))
        except (ValueError, AttributeError):
            pass

    if filter_ouvrage:
        paiements = paiements.filter(point_eau__ouvrage__nom_ouvrage__icontains=filter_ouvrage)

    recoupements_normaux = {}
    for paiement in paiements:
        key = (paiement.numeroDiameX, paiement.baseDiameX)
        if key not in recoupements_normaux:
            commune = None
            if paiement.point_eau and paiement.point_eau.parcelle:
                parcelle = paiement.point_eau.parcelle
                if parcelle.village and parcelle.village.fokontany:
                    commune = parcelle.village.fokontany.commune

            recoupements_normaux[key] = {
                'numero_diamex': paiement.numeroDiameX,
                'base_diamex': paiement.baseDiameX,
                'paiements': [],
                'total_paiements': Decimal('0'),
                'comptabilite_in': None,
                'comptabilite_out': None,
                'comptabilite_entry': None,
                'ecart': None,
                'status': 'unknown',
                'point_eau': None,
                'ouvrage': None,
                'commune': commune,
                'date_facture': None,
                'nb_paiements': 0,
                'scan': None,
            }

        rec = recoupements_normaux[key]
        rec['paiements'].append(paiement)
        rec['total_paiements'] += Decimal(str(paiement.montant)) if paiement.montant else Decimal('0')
        rec['nb_paiements'] += 1

        if rec['point_eau'] is None:
            rec['point_eau'] = paiement.point_eau
            rec['ouvrage'] = paiement.point_eau.ouvrage if paiement.point_eau else None
            rec['date_facture'] = paiement.date_facture

    for key, data in recoupements_normaux.items():
        numero, base = key
        try:
            numero_int = int(str(numero).strip())
        except (TypeError, ValueError):
            numero_int = None

        diamex_entry = None
        if numero_int is not None and base:
            diamex_entry = diamex_scope_qs.filter(id_access=numero_int, prog=base).first()

        if diamex_entry:
            data['comptabilite_entry'] = diamex_entry
            data['comptabilite_in'] = diamex_entry.montant_in
            data['comptabilite_out'] = diamex_entry.montant_out

            if diamex_entry.scan and diamex_entry.fichier_source:
                base_qs = EmployeBaseDiameX.objects.filter(base_diamex=diamex_entry.fichier_source)
                if organisation_ids and not request.user.is_superuser:
                    base_qs = base_qs.filter(employe__base__organisation_id__in=organisation_ids)
                employe_base = base_qs.first()
                if employe_base and employe_base.chemin_base_diamex:
                    scan_relatif = diamex_entry.scan
                    if scan_relatif.startswith('./') or scan_relatif.startswith('.\\'):
                        scan_relatif = scan_relatif[2:]
                    elif scan_relatif.startswith('.'):
                        scan_relatif = scan_relatif[1:]
                    chemin_base = employe_base.chemin_base_diamex
                    if not scan_relatif.startswith(chemin_base):
                        import os
                        if not chemin_base.endswith(os.sep):
                            data['scan'] = chemin_base + os.sep + scan_relatif
                        else:
                            data['scan'] = chemin_base + scan_relatif
                    else:
                        data['scan'] = scan_relatif
                else:
                    data['scan'] = diamex_entry.scan

            data['ecart'] = data['total_paiements'] - Decimal(str(data['comptabilite_in']))
            if abs(data['ecart']) < Decimal('0.01'):
                data['status'] = 'ok'
            elif abs(data['ecart']) < Decimal('100'):
                data['status'] = 'warning'
            else:
                data['status'] = 'error'
        else:
            data['status'] = 'missing'
            data['ecart'] = data['total_paiements']

    recoupements_normaux_list = sorted(
        recoupements_normaux.values(),
        key=lambda x: abs(x['ecart']) if x['ecart'] is not None else 0,
        reverse=True,
    )
    if filter_status:
        recoupements_normaux_list = [r for r in recoupements_normaux_list if r['status'] == filter_status]

    recoupements_par_base = {}
    for rec in recoupements_normaux_list:
        base = rec['base_diamex']
        if base not in recoupements_par_base:
            recoupements_par_base[base] = {}
        ouvrage_nom = rec['ouvrage'].nom_ouvrage if rec['ouvrage'] else 'Sans ouvrage'
        if ouvrage_nom not in recoupements_par_base[base]:
            recoupements_par_base[base][ouvrage_nom] = {
                'records': [],
                'somme_a_collecter': Decimal('0'),
                'nb_points_eau': 0,
                'total_compta_in': Decimal('0'),
            }
        recoupements_par_base[base][ouvrage_nom]['records'].append(rec)
        if rec.get('montant_in'):
            recoupements_par_base[base][ouvrage_nom]['total_compta_in'] += Decimal(str(rec['montant_in']))

    for base in recoupements_par_base:
        for ouvrage_nom in recoupements_par_base[base]:
            if ouvrage_nom == 'Sans ouvrage':
                continue
            ouvrage_qs = _scope_ouvrages_queryset(Ouvrage.objects.filter(nom_ouvrage=ouvrage_nom), request.user)
            ouvrage_obj = ouvrage_qs.first()
            if not ouvrage_obj:
                continue
            points_eau_ids = paiements_scope_qs.filter(
                point_eau__ouvrage=ouvrage_obj,
                point_eau__tarifforfaitaire__isnull=False,
            ).values_list('point_eau_id', flat=True).distinct()
            points_eau = PointEau.objects.filter(id__in=points_eau_ids)
            nb_pe = points_eau.count()
            somme = sum((pe.tarifforfaitaire * 4) for pe in points_eau)
            recoupements_par_base[base][ouvrage_nom]['somme_a_collecter'] = Decimal(str(somme))
            recoupements_par_base[base][ouvrage_nom]['nb_points_eau'] = nb_pe
            recoupements_par_base[base][ouvrage_nom]['ecart'] = (
                recoupements_par_base[base][ouvrage_nom]['total_compta_in'] - Decimal(str(somme))
            )

    stats_normales = {
        'total': len(recoupements_normaux_list) if not filter_status else sum(1 for _ in recoupements_normaux.values()),
        'ok': sum(1 for r in recoupements_normaux.values() if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements_normaux.values() if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements_normaux.values() if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements_normaux.values() if r['status'] == 'missing'),
    }

    # SECTION 2: RECOUPEMENT INVERSE
    diamex_forfaitaires = diamex_scope_qs.filter(compte_code='748411').order_by('-date_m')
    if filter_prog_inverse:
        diamex_forfaitaires = diamex_forfaitaires.filter(prog=filter_prog_inverse)
    if filter_mois_inverse:
        try:
            year, month = filter_mois_inverse.split('-')
            diamex_forfaitaires = diamex_forfaitaires.filter(date_m__year=int(year), date_m__month=int(month))
        except (ValueError, AttributeError):
            pass

    recoupements_inverses = []
    for entry in diamex_forfaitaires:
        paiements_lies = paiements_scope_qs.filter(numeroDiameX=entry.id_access, baseDiameX=entry.prog).select_related('point_eau', 'point_eau__ouvrage')
        total_paiements = sum(Decimal(str(p.montant)) for p in paiements_lies if p.montant)

        extraction = extraire_ouvrage_et_mois_generique(entry.description, entry.compte_code)
        ouvrage_nom = extraction.get('ouvrage_nom', '')
        ouvrage_obj = extraction.get('ouvrage_obj')

        chemin_base = ''
        if entry.fichier_source:
            base_qs = EmployeBaseDiameX.objects.filter(base_diamex=entry.fichier_source)
            if organisation_ids and not request.user.is_superuser:
                base_qs = base_qs.filter(employe__base__organisation_id__in=organisation_ids)
            employe_base = base_qs.first()
            if employe_base:
                chemin_base = employe_base.chemin_base_diamex or ''

        scan_path = ''
        if entry.scan:
            scan_clean = entry.scan
            if scan_clean.startswith('./') or scan_clean.startswith('.\\'):
                scan_clean = scan_clean[2:]
            elif scan_clean.startswith('.'):
                scan_clean = scan_clean[1:]
            if chemin_base:
                import os
                if not chemin_base.endswith(os.sep):
                    scan_path = chemin_base + os.sep + scan_clean
                else:
                    scan_path = chemin_base + scan_clean
            else:
                scan_path = entry.scan

        if paiements_lies.exists():
            ecart = total_paiements - Decimal(str(entry.montant_in))
            if abs(ecart) < Decimal('0.01'):
                status = 'ok'
            elif abs(ecart) < Decimal('100'):
                status = 'warning'
            else:
                status = 'error'
        else:
            status = 'missing'
            ecart = Decimal('0') - Decimal(str(entry.montant_in))

        if filter_status_inverse and status != filter_status_inverse:
            continue

        recoupements_inverses.append({
            'id_access': entry.id_access,
            'prog': entry.prog,
            'description': entry.description,
            'montant_in': entry.montant_in,
            'date_m': entry.date_m,
            'paiements_lies': list(paiements_lies),
            'total_paiements': total_paiements,
            'ecart': ecart,
            'status': status,
            'scan': entry.scan,
            'scan_path': scan_path,
            'ouvrage_nom': ouvrage_nom,
            'ouvrage_obj': ouvrage_obj,
        })

    recoupements_inverses_par_prog = {}
    for rec in recoupements_inverses:
        prog = rec['prog']
        ouvrage_nom = rec['ouvrage_nom'] or 'Sans ouvrage'
        if prog not in recoupements_inverses_par_prog:
            recoupements_inverses_par_prog[prog] = {}
        if ouvrage_nom not in recoupements_inverses_par_prog[prog]:
            recoupements_inverses_par_prog[prog][ouvrage_nom] = {
                'records': [],
                'somme_a_collecter': Decimal('0'),
                'nb_points_eau': 0,
                'total_compta_in': Decimal('0'),
            }
        recoupements_inverses_par_prog[prog][ouvrage_nom]['records'].append(rec)
        if rec.get('montant_in'):
            recoupements_inverses_par_prog[prog][ouvrage_nom]['total_compta_in'] += Decimal(str(rec['montant_in']))

    for prog in recoupements_inverses_par_prog:
        for ouvrage_nom in recoupements_inverses_par_prog[prog]:
            if ouvrage_nom == 'Sans ouvrage':
                continue
            ouvrage_qs = _scope_ouvrages_queryset(Ouvrage.objects.filter(nom_ouvrage=ouvrage_nom), request.user)
            ouvrage_obj = ouvrage_qs.first()
            if not ouvrage_obj:
                continue
            points_eau_ids = paiements_scope_qs.filter(
                point_eau__ouvrage=ouvrage_obj,
                point_eau__tarifforfaitaire__isnull=False,
            ).values_list('point_eau_id', flat=True).distinct()
            points_eau = PointEau.objects.filter(id__in=points_eau_ids)
            nb_pe = points_eau.count()
            somme = sum((pe.tarifforfaitaire * 4) for pe in points_eau)
            recoupements_inverses_par_prog[prog][ouvrage_nom]['somme_a_collecter'] = Decimal(str(somme))
            recoupements_inverses_par_prog[prog][ouvrage_nom]['nb_points_eau'] = nb_pe
            recoupements_inverses_par_prog[prog][ouvrage_nom]['ecart'] = (
                recoupements_inverses_par_prog[prog][ouvrage_nom]['total_compta_in'] - Decimal(str(somme))
            )

    stats_inverses = {
        'total': len(recoupements_inverses),
        'ok': sum(1 for r in recoupements_inverses if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements_inverses if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements_inverses if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements_inverses if r['status'] == 'missing'),
    }

    # SECTION 3: RECOUPEMENT PAR EXTRACTION
    diamex_extraction = diamex_scope_qs.filter(compte_code='748411').order_by('-date_m')
    if filter_mois_extraction:
        try:
            year, month = filter_mois_extraction.split('-')
            diamex_extraction = diamex_extraction.filter(date_m__year=int(year), date_m__month=int(month))
        except (ValueError, AttributeError):
            pass
    if filter_prog_extraction:
        diamex_extraction = diamex_extraction.filter(prog=filter_prog_extraction)

    regroupements_par_ouvrage_mois = {}
    recoupements_extraction = []

    for entry in diamex_extraction:
        extraction = extraire_ouvrage_et_mois_generique(entry.description, entry.compte_code)
        ouvrage_obj = extraction.get('ouvrage_obj')
        ouvrage_nom = extraction.get('ouvrage_nom')

        if filter_ouvrage_extraction and ouvrage_nom and filter_ouvrage_extraction.lower() not in ouvrage_nom.lower():
            continue

        if ouvrage_obj and entry.date_m:
            key = (ouvrage_obj.id, entry.date_m.year, entry.date_m.month)
        else:
            key = (None, entry.date_m.year if entry.date_m else None, entry.date_m.month if entry.date_m else None)

        if key not in regroupements_par_ouvrage_mois:
            regroupements_par_ouvrage_mois[key] = {
                'ouvrage_obj': ouvrage_obj,
                'ouvrage_nom': ouvrage_nom,
                'annee': entry.date_m.year if entry.date_m else None,
                'mois': entry.date_m.month if entry.date_m else None,
                'prog': entry.prog,
                'diamex_entries': [],
                'paiements_forfaitaires': set(),
                'total_diamex': Decimal('0'),
                'total_paiements': Decimal('0'),
            }

        regroupements_par_ouvrage_mois[key]['diamex_entries'].append(entry)
        regroupements_par_ouvrage_mois[key]['total_diamex'] += Decimal(str(entry.montant_in))

    for key, groupe in regroupements_par_ouvrage_mois.items():
        ouvrage_obj = groupe['ouvrage_obj']
        annee = groupe['annee']
        mois = groupe['mois']
        if ouvrage_obj and annee and mois:
            paiements_lies = paiements_scope_qs.filter(
                point_eau__ouvrage=ouvrage_obj,
                date_facture__year=annee,
                date_facture__month=mois,
            ).select_related('point_eau', 'point_eau__ouvrage')
            for p in paiements_lies:
                groupe['paiements_forfaitaires'].add(p.id)
                if p.montant:
                    groupe['total_paiements'] += Decimal(str(p.montant))

    for key, groupe in regroupements_par_ouvrage_mois.items():
        ecart = groupe['total_paiements'] - groupe['total_diamex']
        nb_paiements = len(groupe['paiements_forfaitaires'])

        if nb_paiements > 0:
            if abs(ecart) < Decimal('0.01'):
                status = 'ok'
            elif abs(ecart) < Decimal('100'):
                status = 'warning'
            else:
                status = 'error'
        else:
            status = 'missing' if groupe['ouvrage_obj'] else 'error'

        if filter_status_extraction and status != filter_status_extraction:
            continue

        recoupements_extraction.append({
            'ouvrage_nom': groupe['ouvrage_nom'],
            'ouvrage_obj': groupe['ouvrage_obj'],
            'annee': groupe['annee'],
            'mois': groupe['mois'],
            'prog': groupe['prog'],
            'nb_entries_diamex': len(groupe['diamex_entries']),
            'total_diamex': groupe['total_diamex'],
            'nb_paiements': nb_paiements,
            'total_paiements': groupe['total_paiements'],
            'ecart': ecart,
            'status': status,
            'diamex_entries': groupe['diamex_entries'],
            'paiements_ids': list(groupe['paiements_forfaitaires']),
        })

    recoupements_extraction_par_prog = {}
    for rec in recoupements_extraction:
        prog = rec['prog']
        if prog not in recoupements_extraction_par_prog:
            recoupements_extraction_par_prog[prog] = {}
        ouvrage_nom = rec['ouvrage_nom'] if rec['ouvrage_nom'] else 'Non extrait'
        if ouvrage_nom not in recoupements_extraction_par_prog[prog]:
            recoupements_extraction_par_prog[prog][ouvrage_nom] = []
        recoupements_extraction_par_prog[prog][ouvrage_nom].append(rec)

    stats_extraction = {
        'total': len(recoupements_extraction),
        'ok': sum(1 for r in recoupements_extraction if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements_extraction if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements_extraction if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements_extraction if r['status'] == 'missing'),
    }

    bases_list = sorted(set(
        p.baseDiameX
        for p in paiements_scope_qs.filter(baseDiameX__isnull=False).exclude(baseDiameX='')
        if p.baseDiameX
    ))

    ouvrages_list = sorted(set(
        p.point_eau.ouvrage.nom_ouvrage
        for p in paiements_scope_qs.filter(point_eau__isnull=False, point_eau__ouvrage__isnull=False).select_related('point_eau__ouvrage')
        if p.point_eau and p.point_eau.ouvrage
    ))

    progs_list_inverse = sorted(set(
        entry.prog
        for entry in diamex_scope_qs.filter(compte_code='748411', prog__isnull=False)
        if entry.prog
    ))
    progs_list_extraction = progs_list_inverse

    paginator = Paginator(recoupements_normaux_list, 50)
    page_number = request.GET.get('page', 1)
    try:
        page_number = int(page_number)
        if page_number < 1:
            page_number = 1
    except (ValueError, TypeError):
        page_number = 1
    page_obj = paginator.get_page(page_number)

    return render(request, 'accounting/recoupement_forfaitaires.html', {
        'page_obj': page_obj,
        'recoupements_normaux': page_obj,
        'recoupements_par_base': recoupements_par_base,
        'stats_normales': stats_normales,
        'recoupements_inverses': recoupements_inverses,
        'recoupements_inverses_par_prog': recoupements_inverses_par_prog,
        'stats_inverses': stats_inverses,
        'recoupements_extraction': recoupements_extraction,
        'recoupements_extraction_par_prog': recoupements_extraction_par_prog,
        'stats_extraction': stats_extraction,
        'bases_list': bases_list,
        'ouvrages_list': ouvrages_list,
        'progs_list_inverse': progs_list_inverse,
        'progs_list_extraction': progs_list_extraction,
        'filter_status': filter_status,
        'filter_base': filter_base,
        'filter_mois': filter_mois,
        'filter_ouvrage': filter_ouvrage,
        'filter_prog_inverse': filter_prog_inverse,
        'filter_mois_inverse': filter_mois_inverse,
        'filter_status_inverse': filter_status_inverse,
        'filter_ouvrage_extraction': filter_ouvrage_extraction,
        'filter_mois_extraction': filter_mois_extraction,
        'filter_prog_extraction': filter_prog_extraction,
        'filter_status_extraction': filter_status_extraction,
    })
