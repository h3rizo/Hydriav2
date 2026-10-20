"""
Vues pour le recoupement des salaires avec la comptabilité DiameX
"""
from decimal import Decimal
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from apps.employees.models import Salaire
from apps.organization.models import Base
from .models import BaseDiameX


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _get_allowed_progs(user):
    if getattr(user, 'is_superuser', False):
        return None
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return []
    return list(
        Base.objects.filter(organisation_id=organisation_id)
        .exclude(prog_diamex__isnull=True)
        .exclude(prog_diamex='')
        .values_list('prog_diamex', flat=True)
        .distinct()
    )


@login_required
def recoupement_salaires(request):
    """
    Recoupement entre Salaires et BaseDiameX pour les 5 types de charges salariales:
    1. Salaire : numeroDiameXSalaire + BaseDiameXSalaire
    2. IRSA : numeroDiameXIRSA + BaseDiameXIRSA
    3. CNaPS : numeroDiameXCnaPS + BaseDiameXCnaPS
    4. FMFP : numeroDiameXFMFP + BaseDiameXFMFP
    5. Santé : numeroDiameXSante + BaseDiameXSante

    Clé: (numeroDiameXXXX, BaseDiameXXXX) <-> (ID, Prog) dans BaseDiameX
    """
    # Filtres depuis GET
    filter_status = request.GET.get('status', '')
    filter_type = request.GET.get('type', '')  # salaire, irsa, cnaps, fmfp, sante
    filter_base = request.GET.get('base', '')
    filter_mois = request.GET.get('mois', '')
    filter_employe = request.GET.get('employe', '')

    # Récupérer tous les salaires avec au moins un numéro DiameX renseigné
    salaires = Salaire.objects.filter(
        Q(numero_diamex_salaire__isnull=False) |
        Q(numero_diamex_irsa__isnull=False) |
        Q(numero_diamex_cnaps__isnull=False) |
        Q(numero_diamex_fmfp__isnull=False) |
        Q(numero_diamex_mutuelle_sante__isnull=False)
    ).select_related(
        'grille_salaire__contrat__employe__poste',
        'grille_salaire__contrat__employe__base'
    )
    organisation_id = _get_user_organisation_id(request.user)
    if organisation_id and not getattr(request.user, 'is_superuser', False):
        salaires = salaires.filter(grille_salaire__contrat__employe__base__organisation_id=organisation_id)

    diamex_qs = BaseDiameX.objects.all()
    allowed_progs = _get_allowed_progs(request.user)
    if allowed_progs is not None:
        diamex_qs = diamex_qs.filter(prog__in=allowed_progs)

    # Appliquer filtre base DiameX
    if filter_base:
        salaires = salaires.filter(
            Q(base_diamex_salaire=filter_base) |
            Q(base_diamex_irsa=filter_base) |
            Q(base_diamex_cnaps=filter_base) |
            Q(base_diamex_fmfp=filter_base) |
            Q(base_diamex_mutuelle_sante=filter_base)
        )

    # Appliquer filtre mois/année
    if filter_mois:
        try:
            year, month = filter_mois.split('-')
            salaires = salaires.filter(
                date_paiement__year=int(year),
                date_paiement__month=int(month)
            )
        except (ValueError, AttributeError):
            pass

    # Appliquer filtre employé
    if filter_employe:
        salaires = salaires.filter(
            Q(grille_salaire__contrat__employe__nom__icontains=filter_employe) |
            Q(grille_salaire__contrat__employe__prenom__icontains=filter_employe) |
            Q(grille_salaire__contrat__employe__surnom__icontains=filter_employe)
        )

    # Créer les recoupements pour les 5 types
    recoupements_list = []

    for salaire in salaires:
        employe = salaire.grille_salaire.contrat.employe if salaire.grille_salaire and salaire.grille_salaire.contrat else None

        # 5 types de charges à vérifier
        types_charges = [
            {
                'type': 'salaire',
                'label': 'Salaire net',
                'numero': salaire.numero_diamex_salaire,
                'base': salaire.base_diamex_salaire,
                'montant_attendu': salaire.salaire_net_paye or Decimal('0'),
                'icon': 'fa-money-bill-wave',
                'color': 'primary'
            },
            {
                'type': 'irsa',
                'label': 'IRSA',
                'numero': salaire.numero_diamex_irsa,
                'base': salaire.base_diamex_irsa,
                'montant_attendu': salaire.irsa_paye or Decimal('0'),
                'icon': 'fa-percent',
                'color': 'warning'
            },
            {
                'type': 'cnaps',
                'label': 'CNaPS',
                'numero': salaire.numero_diamex_cnaps,
                'base': salaire.base_diamex_cnaps,
                'montant_attendu': salaire.cnaps_paye or Decimal('0'),
                'icon': 'fa-shield-alt',
                'color': 'info'
            },
            {
                'type': 'fmfp',
                'label': 'FMFP',
                'numero': salaire.numero_diamex_fmfp,
                'base': salaire.base_diamex_fmfp,
                'montant_attendu': salaire.fmfp_paye or Decimal('0'),
                'icon': 'fa-landmark',
                'color': 'accent'
            },
            {
                'type': 'sante',
                'label': 'Mutuelle Santé',
                'numero': salaire.numero_diamex_mutuelle_sante,
                'base': salaire.base_diamex_mutuelle_sante,
                'montant_attendu': salaire.mutuelle_sante_paye or Decimal('0'),
                'icon': 'fa-heartbeat',
                'color': 'success'
            }
        ]

        for charge in types_charges:
            # Ignorer si numéro DiameX non renseigné
            if not charge['numero'] or not charge['base']:
                continue

            # Filtrer par type si demandé
            if filter_type and charge['type'] != filter_type:
                continue

            # Chercher l'entrée comptabilité correspondante
            compta_entry = None
            try:
                compta_entry = diamex_qs.get(
                    id_access=charge['numero'],
                    prog=charge['base']
                )
            except BaseDiameX.DoesNotExist:
                pass

            # Calculer montants et écarts
            if compta_entry:
                montant_compta_out = Decimal(str(compta_entry.montant_out)) if compta_entry.montant_out else Decimal('0')
                montant_compta_in = Decimal(str(compta_entry.montant_in)) if compta_entry.montant_in else Decimal('0')
                ecart = abs(charge['montant_attendu'] - montant_compta_out)

                # Déterminer le statut
                if ecart == 0:
                    status = 'ok'
                elif ecart <= Decimal('100'):  # Tolérance 100 Ar pour arrondis
                    status = 'warning'
                else:
                    status = 'error'
            else:
                montant_compta_out = None
                montant_compta_in = None
                ecart = charge['montant_attendu']
                status = 'missing'

            # Filtrer par status si demandé
            if filter_status and status != filter_status:
                continue

            recoupements_list.append({
                'salaire_id': salaire.id,
                'employe': employe,
                'date_paiement': salaire.date_paiement,
                'type_charge': charge['type'],
                'label_charge': charge['label'],
                'icon': charge['icon'],
                'color': charge['color'],
                'numero_diamex': charge['numero'],
                'base_diamex': charge['base'],
                'montant_attendu': charge['montant_attendu'],
                'montant_compta_out': montant_compta_out,
                'montant_compta_in': montant_compta_in,
                'ecart': ecart,
                'status': status,
                'comptabilite_entry': compta_entry
            })

    # Grouper par employé puis par type de charge
    recoupements_par_employe = {}
    for rec in recoupements_list:
        employe_nom = rec['employe'].nom_complet if rec['employe'] else 'Inconnu'
        employe_id = rec['employe'].id if rec['employe'] else None

        if employe_id not in recoupements_par_employe:
            recoupements_par_employe[employe_id] = {
                'employe_nom': employe_nom,
                'employe': rec['employe'],
                'types': {}
            }

        type_charge = rec['type_charge']
        if type_charge not in recoupements_par_employe[employe_id]['types']:
            recoupements_par_employe[employe_id]['types'][type_charge] = []

        recoupements_par_employe[employe_id]['types'][type_charge].append(rec)

    # Calculer statistiques globales
    stats = {
        'total': len(recoupements_list),
        'ok': len([r for r in recoupements_list if r['status'] == 'ok']),
        'warning': len([r for r in recoupements_list if r['status'] == 'warning']),
        'error': len([r for r in recoupements_list if r['status'] == 'error']),
        'missing': len([r for r in recoupements_list if r['status'] == 'missing'])
    }

    # Listes pour les filtres
    bases_list = set()
    employes_map = {}

    salaires_filtres_listes = Salaire.objects.all().select_related(
        'grille_salaire__contrat__employe__base',
        'grille_salaire__contrat__employe__poste',
    )
    if organisation_id and not getattr(request.user, 'is_superuser', False):
        salaires_filtres_listes = salaires_filtres_listes.filter(
            grille_salaire__contrat__employe__base__organisation_id=organisation_id
        )

    for salaire in salaires_filtres_listes:
        if salaire.base_diamex_salaire:
            bases_list.add(salaire.base_diamex_salaire)
        if salaire.base_diamex_irsa:
            bases_list.add(salaire.base_diamex_irsa)
        if salaire.base_diamex_cnaps:
            bases_list.add(salaire.base_diamex_cnaps)
        if salaire.base_diamex_fmfp:
            bases_list.add(salaire.base_diamex_fmfp)
        if salaire.base_diamex_mutuelle_sante:
            bases_list.add(salaire.base_diamex_mutuelle_sante)

        if salaire.grille_salaire and salaire.grille_salaire.contrat:
            employe = salaire.grille_salaire.contrat.employe
            if employe:
                filter_value = employe.nom_complet
                employes_map.setdefault(filter_value, {
                    'id': filter_value,
                    'display_name': filter_value,
                    'base_name': employe.base.nom_base if employe.base else 'Sans base',
                    'poste_name': employe.poste.nom_poste if employe.poste else 'Sans poste',
                })

    context = {
        'recoupements_par_employe': recoupements_par_employe,
        'stats': stats,
        'bases_list': sorted(bases_list),
        'employes_list': list(employes_map.values())
    }

    return render(request, 'accounting/recoupement_salaires.html', context)
