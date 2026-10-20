"""
Vues pour la reconstitution automatique des champs DiameX manquants
dans la table Salaires en utilisant les données de BaseDiameX
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from decimal import Decimal
import json
import re

from apps.employees.models import Salaire, Employe
from .models import BaseDiameX


def reconstitution_diamex_salaires(request):
    """
    Page de reconstitution des champs DiameX manquants dans les salaires
    avec statistiques, filtres et regroupements
    """
    from apps.organization.models import Base
    from apps.employees.models import Poste
    from django.db.models import Count
    from datetime import datetime

    # Récupérer les filtres
    filter_mois = request.GET.get('mois', '')  # Format: YYYY-MM
    filter_zone = request.GET.get('zone', '')
    filter_poste = request.GET.get('poste', '')

    # Récupérer l'option de regroupement
    grouper_par = request.GET.get('grouper_par', '')

    # Base queryset - tous les salaires avec date de paiement
    base_qs = Salaire.objects.filter(
        date_paiement__isnull=False
    ).select_related(
        'grille_salaire__contrat__employe',
        'grille_salaire__contrat__employe__poste',
        'grille_salaire__contrat__employe__base'
    )

    # Appliquer les filtres
    if filter_mois:
        try:
            year, month = filter_mois.split('-')
            base_qs = base_qs.filter(
                date_paiement__year=int(year),
                date_paiement__month=int(month)
            )
        except:
            pass

    if filter_zone:
        base_qs = base_qs.filter(
            grille_salaire__contrat__employe__base_id=filter_zone
        )

    if filter_poste:
        base_qs = base_qs.filter(
            grille_salaire__contrat__employe__poste_id=filter_poste
        )

    # Calculer les statistiques globales
    total_salaires = base_qs.count()
    total_cases = total_salaires * 5  # 5 champs DiameX par salaire

    # Compter les cases vides pour chaque champ
    cases_vides_salaire = base_qs.filter(
        Q(numero_diamex_salaire__isnull=True) | Q(numero_diamex_salaire='')
    ).count()
    cases_vides_irsa = base_qs.filter(
        Q(numero_diamex_irsa__isnull=True) | Q(numero_diamex_irsa='')
    ).count()
    cases_vides_cnaps = base_qs.filter(
        Q(numero_diamex_cnaps__isnull=True) | Q(numero_diamex_cnaps='')
    ).count()
    cases_vides_fmfp = base_qs.filter(
        Q(numero_diamex_fmfp__isnull=True) | Q(numero_diamex_fmfp='')
    ).count()
    cases_vides_mutuelle = base_qs.filter(
        Q(numero_diamex_mutuelle_sante__isnull=True) | Q(numero_diamex_mutuelle_sante='')
    ).count()

    total_cases_vides = cases_vides_salaire + cases_vides_irsa + cases_vides_cnaps + cases_vides_fmfp + cases_vides_mutuelle
    total_cases_remplies = total_cases - total_cases_vides
    taux_remplissage = int((total_cases_remplies / total_cases * 100)) if total_cases > 0 else 0

    # Statistiques par champ
    stats_par_champ = [
        {'nom': 'Salaire', 'total': total_salaires, 'vides': cases_vides_salaire,
         'remplis': total_salaires - cases_vides_salaire,
         'taux': int(((total_salaires - cases_vides_salaire) / total_salaires * 100)) if total_salaires > 0 else 0},
        {'nom': 'IRSA', 'total': total_salaires, 'vides': cases_vides_irsa,
         'remplis': total_salaires - cases_vides_irsa,
         'taux': int(((total_salaires - cases_vides_irsa) / total_salaires * 100)) if total_salaires > 0 else 0},
        {'nom': 'CNaPS', 'total': total_salaires, 'vides': cases_vides_cnaps,
         'remplis': total_salaires - cases_vides_cnaps,
         'taux': int(((total_salaires - cases_vides_cnaps) / total_salaires * 100)) if total_salaires > 0 else 0},
        {'nom': 'FMFP', 'total': total_salaires, 'vides': cases_vides_fmfp,
         'remplis': total_salaires - cases_vides_fmfp,
         'taux': int(((total_salaires - cases_vides_fmfp) / total_salaires * 100)) if total_salaires > 0 else 0},
        {'nom': 'Mutuelle', 'total': total_salaires, 'vides': cases_vides_mutuelle,
         'remplis': total_salaires - cases_vides_mutuelle,
         'taux': int(((total_salaires - cases_vides_mutuelle) / total_salaires * 100)) if total_salaires > 0 else 0},
    ]

    # Regroupement par Zone (Base)
    stats_par_zone = []
    zones = Base.objects.all().order_by('nom_base')
    for zone in zones:
        zone_qs = base_qs.filter(grille_salaire__contrat__employe__base=zone)
        zone_total = zone_qs.count()
        if zone_total > 0:
            zone_cases = zone_total * 5
            zone_vides = (
                zone_qs.filter(Q(numero_diamex_salaire__isnull=True) | Q(numero_diamex_salaire='')).count() +
                zone_qs.filter(Q(numero_diamex_irsa__isnull=True) | Q(numero_diamex_irsa='')).count() +
                zone_qs.filter(Q(numero_diamex_cnaps__isnull=True) | Q(numero_diamex_cnaps='')).count() +
                zone_qs.filter(Q(numero_diamex_fmfp__isnull=True) | Q(numero_diamex_fmfp='')).count() +
                zone_qs.filter(Q(numero_diamex_mutuelle_sante__isnull=True) | Q(numero_diamex_mutuelle_sante='')).count()
            )
            stats_par_zone.append({
                'id': str(zone.id),
                'nom': zone.nom_base,
                'total_salaires': zone_total,
                'total_cases': zone_cases,
                'cases_vides': zone_vides,
                'cases_remplies': zone_cases - zone_vides,
                'taux': int(((zone_cases - zone_vides) / zone_cases * 100)) if zone_cases > 0 else 0
            })

    # Regroupement par Poste
    stats_par_poste = []
    postes = Poste.objects.all().order_by('ordre_affichage', 'nom_poste')
    for poste in postes:
        poste_qs = base_qs.filter(grille_salaire__contrat__employe__poste=poste)
        poste_total = poste_qs.count()
        if poste_total > 0:
            poste_cases = poste_total * 5
            poste_vides = (
                poste_qs.filter(Q(numero_diamex_salaire__isnull=True) | Q(numero_diamex_salaire='')).count() +
                poste_qs.filter(Q(numero_diamex_irsa__isnull=True) | Q(numero_diamex_irsa='')).count() +
                poste_qs.filter(Q(numero_diamex_cnaps__isnull=True) | Q(numero_diamex_cnaps='')).count() +
                poste_qs.filter(Q(numero_diamex_fmfp__isnull=True) | Q(numero_diamex_fmfp='')).count() +
                poste_qs.filter(Q(numero_diamex_mutuelle_sante__isnull=True) | Q(numero_diamex_mutuelle_sante='')).count()
            )
            stats_par_poste.append({
                'id': str(poste.id),
                'nom': poste.nom_poste,
                'total_salaires': poste_total,
                'total_cases': poste_cases,
                'cases_vides': poste_vides,
                'cases_remplies': poste_cases - poste_vides,
                'taux': int(((poste_cases - poste_vides) / poste_cases * 100)) if poste_cases > 0 else 0
            })

    # Liste des salaires incomplets (filtrés)
    salaires_incomplets_qs = base_qs.filter(
        Q(numero_diamex_salaire__isnull=True) | Q(numero_diamex_salaire='') |
        Q(numero_diamex_irsa__isnull=True) | Q(numero_diamex_irsa='') |
        Q(numero_diamex_cnaps__isnull=True) | Q(numero_diamex_cnaps='') |
        Q(numero_diamex_fmfp__isnull=True) | Q(numero_diamex_fmfp='') |
        Q(numero_diamex_mutuelle_sante__isnull=True) | Q(numero_diamex_mutuelle_sante='')
    ).order_by('-date_paiement')[:100]

    # Enrichir chaque salaire avec le statut de correspondance pour les champs manquants
    salaires_incomplets = []
    for salaire in salaires_incomplets_qs:
        employe = salaire.grille_salaire.contrat.employe
        date_paiement = salaire.date_paiement

        # Préparer les statuts de correspondance
        statuts = {}

        if date_paiement:
            annee = date_paiement.year
            mois = date_paiement.month

            # Vérifier chaque champ manquant
            if not salaire.numero_diamex_salaire:
                resultat = rechercher_diamex_salaire(employe, annee, mois, 'Salaire')
                statuts['salaire'] = 'trouve' if resultat else 'non_trouve'
            else:
                statuts['salaire'] = 'rempli'

            if not salaire.numero_diamex_irsa:
                resultat = rechercher_diamex_salaire(employe, annee, mois, 'IRSA')
                statuts['irsa'] = 'trouve' if resultat else 'non_trouve'
            else:
                statuts['irsa'] = 'rempli'

            if not salaire.numero_diamex_cnaps:
                resultat = rechercher_diamex_salaire(employe, annee, mois, 'CNaPS')
                statuts['cnaps'] = 'trouve' if resultat else 'non_trouve'
            else:
                statuts['cnaps'] = 'rempli'

            if not salaire.numero_diamex_fmfp:
                resultat = rechercher_diamex_salaire(employe, annee, mois, 'FMFP')
                statuts['fmfp'] = 'trouve' if resultat else 'non_trouve'
            else:
                statuts['fmfp'] = 'rempli'

            if not salaire.numero_diamex_mutuelle_sante:
                resultat = rechercher_diamex_mutuelle(employe, annee, mois)
                statuts['mutuelle'] = 'trouve' if resultat else 'non_trouve'
            else:
                statuts['mutuelle'] = 'rempli'
        else:
            # Pas de date de paiement - impossible de chercher
            statuts = {
                'salaire': 'non_trouve' if not salaire.numero_diamex_salaire else 'rempli',
                'irsa': 'non_trouve' if not salaire.numero_diamex_irsa else 'rempli',
                'cnaps': 'non_trouve' if not salaire.numero_diamex_cnaps else 'rempli',
                'fmfp': 'non_trouve' if not salaire.numero_diamex_fmfp else 'rempli',
                'mutuelle': 'non_trouve' if not salaire.numero_diamex_mutuelle_sante else 'rempli',
            }

        # Ajouter les statuts comme attribut du salaire
        salaire.statuts_correspondance = statuts
        salaires_incomplets.append(salaire)

    # Listes pour les filtres
    zones_list = Base.objects.all().order_by('nom_base')
    postes_list = Poste.objects.all().order_by('ordre_affichage', 'nom_poste')

    # Générer la liste des mois disponibles
    mois_disponibles = Salaire.objects.filter(
        date_paiement__isnull=False
    ).dates('date_paiement', 'month', order='DESC')[:24]

    context = {
        'salaires_incomplets': salaires_incomplets,
        'total': len(salaires_incomplets),
        # Statistiques globales
        'total_salaires': total_salaires,
        'total_cases': total_cases,
        'total_cases_vides': total_cases_vides,
        'total_cases_remplies': total_cases_remplies,
        'taux_remplissage': taux_remplissage,
        # Statistiques par champ
        'stats_par_champ': stats_par_champ,
        # Regroupements
        'stats_par_zone': stats_par_zone,
        'stats_par_poste': stats_par_poste,
        # Filtres
        'zones_list': zones_list,
        'postes_list': postes_list,
        'mois_disponibles': mois_disponibles,
        'filter_mois': filter_mois,
        'filter_zone': filter_zone,
        'filter_poste': filter_poste,
        'grouper_par': grouper_par,
    }

    return render(request, 'accounting/reconstitution_diamex_salaires.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def api_rechercher_correspondances(request):
    """
    API pour rechercher les correspondances dans BaseDiameX
    pour un salaire donné
    """
    try:
        data = json.loads(request.body)
        salaire_id = data.get('salaire_id')

        if not salaire_id:
            return JsonResponse({
                'success': False,
                'error': 'ID salaire manquant'
            }, status=400)

        # Récupérer le salaire
        salaire = Salaire.objects.select_related(
            'grille_salaire__contrat__employe'
        ).get(id=salaire_id)

        employe = salaire.grille_salaire.contrat.employe
        date_paiement = salaire.date_paiement

        if not date_paiement:
            return JsonResponse({
                'success': False,
                'error': 'Date de paiement manquante'
            })

        # Extraire année et mois
        annee = date_paiement.year
        mois = date_paiement.month

        # Préparer les résultats avec statut pour chaque champ
        correspondances = {}

        # 1. RECHERCHE SALAIRE
        if salaire.numero_diamex_salaire:
            correspondances['salaire'] = {
                'statut': 'deja_rempli',
                'numero_existant': salaire.numero_diamex_salaire,
                'base_existante': salaire.base_diamex_salaire or ''
            }
        else:
            resultat = rechercher_diamex_salaire(employe, annee, mois, 'Salaire')
            correspondances['salaire'] = {
                'statut': 'trouve' if resultat else 'non_trouve',
                'data': resultat
            }

        # 2. RECHERCHE IRSA
        if salaire.numero_diamex_irsa:
            correspondances['irsa'] = {
                'statut': 'deja_rempli',
                'numero_existant': salaire.numero_diamex_irsa,
                'base_existante': salaire.base_diamex_irsa or ''
            }
        else:
            resultat = rechercher_diamex_salaire(employe, annee, mois, 'IRSA')
            correspondances['irsa'] = {
                'statut': 'trouve' if resultat else 'non_trouve',
                'data': resultat
            }

        # 3. RECHERCHE CNaPS
        if salaire.numero_diamex_cnaps:
            correspondances['cnaps'] = {
                'statut': 'deja_rempli',
                'numero_existant': salaire.numero_diamex_cnaps,
                'base_existante': salaire.base_diamex_cnaps or ''
            }
        else:
            resultat = rechercher_diamex_salaire(employe, annee, mois, 'CNaPS')
            correspondances['cnaps'] = {
                'statut': 'trouve' if resultat else 'non_trouve',
                'data': resultat
            }

        # 4. RECHERCHE FMFP
        if salaire.numero_diamex_fmfp:
            correspondances['fmfp'] = {
                'statut': 'deja_rempli',
                'numero_existant': salaire.numero_diamex_fmfp,
                'base_existante': salaire.base_diamex_fmfp or ''
            }
        else:
            resultat = rechercher_diamex_salaire(employe, annee, mois, 'FMFP')
            correspondances['fmfp'] = {
                'statut': 'trouve' if resultat else 'non_trouve',
                'data': resultat
            }

        # 5. RECHERCHE MUTUELLE SANTÉ (OSIEF ou AMIT)
        if salaire.numero_diamex_mutuelle_sante:
            correspondances['mutuelle_sante'] = {
                'statut': 'deja_rempli',
                'numero_existant': salaire.numero_diamex_mutuelle_sante,
                'base_existante': salaire.base_diamex_mutuelle_sante or ''
            }
        else:
            resultat = rechercher_diamex_mutuelle(employe, annee, mois)
            correspondances['mutuelle_sante'] = {
                'statut': 'trouve' if resultat else 'non_trouve',
                'data': resultat
            }

        return JsonResponse({
            'success': True,
            'correspondances': correspondances,
            'employe': {
                'surnom': employe.surnom or employe.prenom,
                'nom_complet': f"{employe.prenom} {employe.nom}"
            },
            'date': f"{annee}-{mois:02d}"
        })

    except Salaire.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Salaire non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def get_trimestre_from_mois(mois):
    """
    Retourne le numéro du trimestre et les mois correspondants

    Args:
        mois: Numéro du mois (1-12)

    Returns:
        tuple (numero_trimestre, liste_mois)
        Ex: mois=7 -> (3, [7, 8, 9]) pour "3e trimestre"
    """
    if mois in [1, 2, 3]:
        return (1, [1, 2, 3])
    elif mois in [4, 5, 6]:
        return (2, [4, 5, 6])
    elif mois in [7, 8, 9]:
        return (3, [7, 8, 9])
    else:  # 10, 11, 12
        return (4, [10, 11, 12])


def get_trimestre_label(num_trimestre):
    """
    Retourne le label du trimestre tel qu'utilisé dans DiameX
    Ex: 1 -> "1er trimestre", 2 -> "2e trimestre"
    """
    if num_trimestre == 1:
        return "1er trimestre"
    else:
        return f"{num_trimestre}e trimestre"


def rechercher_diamex_salaire(employe, annee, mois, type_charge):
    """
    Recherche une correspondance dans BaseDiameX pour un type de charge donné

    Args:
        employe: Instance Employe
        annee: Année (int)
        mois: Mois (int)
        type_charge: 'Salaire', 'IRSA', 'CNaPS', 'FMFP'

    Returns:
        dict avec {id, prog, description, detail, montant} ou None
    """
    from django.db.models import Q

    surnom = employe.surnom or employe.prenom

    # Pour CNAPS et IRSA: recherche trimestrielle uniquement
    # Pour Salaire et FMFP: recherche mensuelle
    if type_charge in ['CNaPS', 'IRSA']:
        # Recherche TRIMESTRIELLE
        num_trimestre, mois_du_trimestre = get_trimestre_from_mois(mois)
        trimestre_label = get_trimestre_label(num_trimestre)

        # Pattern: "CNaPS_2025 2e trimestre" ou "IRSA_2025 1er trimestre"
        description_pattern = f"{type_charge}_{annee} {trimestre_label}"

        resultats = BaseDiameX.objects.filter(
            description__icontains=description_pattern,
            detail__icontains=surnom
        ).values('id_access', 'prog', 'description', 'detail', 'montant_out', 'montant_in')

        if resultats.exists():
            resultat = resultats.first()
            return {
                'id': resultat['id_access'],
                'prog': resultat['prog'],
                'description': resultat['description'],
                'detail': resultat['detail'],
                'montant_out': float(resultat['montant_out']) if resultat['montant_out'] else 0,
                'montant_in': float(resultat['montant_in']) if resultat['montant_in'] else 0,
                'type_recherche': 'trimestre',
                'trimestre': num_trimestre,
                'mois_concernes': mois_du_trimestre
            }

        return None

    else:
        # Recherche MENSUELLE (Salaire, FMFP)
        # Pattern pour la description
        # Format dans BaseDiameX: "_AM NOM Prenom_Salaire_2025 10" (sans zero devant pour mois < 10)
        description_pattern_sans_zero = f"{type_charge}_{annee} {mois}"
        description_pattern_avec_zero = f"{type_charge}_{annee} {mois:02d}"

        resultats = BaseDiameX.objects.filter(
            Q(description__icontains=description_pattern_sans_zero) |
            Q(description__icontains=description_pattern_avec_zero),
            detail__icontains=surnom
        ).values('id_access', 'prog', 'description', 'detail', 'montant_out', 'montant_in')

        if resultats.exists():
            resultat = resultats.first()
            return {
                'id': resultat['id_access'],
                'prog': resultat['prog'],
                'description': resultat['description'],
                'detail': resultat['detail'],
                'montant_out': float(resultat['montant_out']) if resultat['montant_out'] else 0,
                'montant_in': float(resultat['montant_in']) if resultat['montant_in'] else 0,
                'type_recherche': 'mois'
            }

        return None


def rechercher_diamex_mutuelle(employe, annee, mois):
    """
    Recherche une correspondance pour la mutuelle santé (OSIEF ou AMIT)

    La mutuelle peut être payée:
    - MENSUELLEMENT: "OSIEF_2025 7" ou "AMIT_2025 07"
    - TRIMESTRIELLEMENT: "OSIEF_2025 3e trimestre" ou "AMIT_2025 1er trimestre"

    On cherche d'abord le pattern mensuel, puis le pattern trimestriel

    Returns:
        dict avec {id, prog, description, detail, montant, type_recherche} ou None
    """
    from django.db.models import Q

    surnom = employe.surnom or employe.prenom

    # Types de mutuelle à chercher
    types_mutuelle = ['OSIEFSoVa', 'AMIT']

    for type_mut in types_mutuelle:
        # 1. D'ABORD chercher le pattern MENSUEL
        date_pattern_sans_zero = f"{annee} {mois}"
        date_pattern_avec_zero = f"{annee} {mois:02d}"

        resultats_mensuel = BaseDiameX.objects.filter(
            Q(description__icontains=type_mut) & (
                Q(description__icontains=date_pattern_sans_zero) |
                Q(description__icontains=date_pattern_avec_zero)
            ),
            detail__icontains=surnom
        ).exclude(
            # Exclure les patterns trimestriels
            description__icontains='trimestre'
        ).values('id_access', 'prog', 'description', 'detail', 'montant_out', 'montant_in')

        if resultats_mensuel.exists():
            resultat = resultats_mensuel.first()
            return {
                'id': resultat['id_access'],
                'prog': resultat['prog'],
                'description': resultat['description'],
                'detail': resultat['detail'],
                'montant_out': float(resultat['montant_out']) if resultat['montant_out'] else 0,
                'montant_in': float(resultat['montant_in']) if resultat['montant_in'] else 0,
                'type_mutuelle': type_mut,
                'type_recherche': 'mois'
            }

        # 2. ENSUITE chercher le pattern TRIMESTRIEL
        num_trimestre, mois_du_trimestre = get_trimestre_from_mois(mois)
        trimestre_label = get_trimestre_label(num_trimestre)
        trimestre_pattern = f"{annee} {trimestre_label}"

        resultats_trimestre = BaseDiameX.objects.filter(
            Q(description__icontains=type_mut) &
            Q(description__icontains=trimestre_pattern),
            detail__icontains=surnom
        ).values('id_access', 'prog', 'description', 'detail', 'montant_out', 'montant_in')

        if resultats_trimestre.exists():
            resultat = resultats_trimestre.first()
            return {
                'id': resultat['id_access'],
                'prog': resultat['prog'],
                'description': resultat['description'],
                'detail': resultat['detail'],
                'montant_out': float(resultat['montant_out']) if resultat['montant_out'] else 0,
                'montant_in': float(resultat['montant_in']) if resultat['montant_in'] else 0,
                'type_mutuelle': type_mut,
                'type_recherche': 'trimestre',
                'trimestre': num_trimestre,
                'mois_concernes': mois_du_trimestre
            }

    return None


@csrf_exempt
@require_http_methods(["POST"])
def api_appliquer_correspondances(request):
    """
    API pour appliquer les correspondances trouvées
    et remplir les champs DiameX dans Salaire
    """
    try:
        data = json.loads(request.body)
        salaire_id = data.get('salaire_id')
        correspondances = data.get('correspondances', {})

        if not salaire_id:
            return JsonResponse({
                'success': False,
                'error': 'ID salaire manquant'
            }, status=400)

        # Récupérer le salaire
        salaire = Salaire.objects.get(id=salaire_id)

        nb_champs_remplis = 0

        # Appliquer chaque correspondance si elle existe et a été trouvée
        # Nouveau format: {statut: 'trouve', data: {id, prog, ...}}
        if correspondances.get('salaire') and correspondances['salaire'].get('statut') == 'trouve':
            corr = correspondances['salaire']['data']
            salaire.numero_diamex_salaire = corr['id']
            salaire.base_diamex_salaire = corr['prog']
            nb_champs_remplis += 1

        if correspondances.get('irsa') and correspondances['irsa'].get('statut') == 'trouve':
            corr = correspondances['irsa']['data']
            salaire.numero_diamex_irsa = corr['id']
            salaire.base_diamex_irsa = corr['prog']
            nb_champs_remplis += 1

        if correspondances.get('cnaps') and correspondances['cnaps'].get('statut') == 'trouve':
            corr = correspondances['cnaps']['data']
            salaire.numero_diamex_cnaps = corr['id']
            salaire.base_diamex_cnaps = corr['prog']
            nb_champs_remplis += 1

        if correspondances.get('fmfp') and correspondances['fmfp'].get('statut') == 'trouve':
            corr = correspondances['fmfp']['data']
            salaire.numero_diamex_fmfp = corr['id']
            salaire.base_diamex_fmfp = corr['prog']
            nb_champs_remplis += 1

        if correspondances.get('mutuelle_sante') and correspondances['mutuelle_sante'].get('statut') == 'trouve':
            corr = correspondances['mutuelle_sante']['data']
            salaire.numero_diamex_mutuelle_sante = corr['id']
            salaire.base_diamex_mutuelle_sante = corr['prog']
            nb_champs_remplis += 1

        if nb_champs_remplis > 0:
            salaire.save()

        return JsonResponse({
            'success': True,
            'message': f'{nb_champs_remplis} champ(s) rempli(s) avec succès',
            'nb_champs_remplis': nb_champs_remplis
        })

    except Salaire.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Salaire non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_reconstitution_batch(request):
    """
    API pour reconstituer automatiquement plusieurs salaires en batch
    """
    try:
        # Récupérer tous les salaires avec champs manquants (limité)
        salaires_incomplets = Salaire.objects.filter(
            Q(numero_diamex_salaire__isnull=True) | Q(numero_diamex_salaire='') |
            Q(numero_diamex_irsa__isnull=True) | Q(numero_diamex_irsa='') |
            Q(numero_diamex_cnaps__isnull=True) | Q(numero_diamex_cnaps='') |
            Q(numero_diamex_fmfp__isnull=True) | Q(numero_diamex_fmfp='') |
            Q(numero_diamex_mutuelle_sante__isnull=True) | Q(numero_diamex_mutuelle_sante='')
        ).select_related(
            'grille_salaire__contrat__employe'
        )[:50]  # Limiter à 50 pour éviter timeout

        nb_salaires_traites = 0
        nb_champs_remplis = 0
        erreurs = []

        for salaire in salaires_incomplets:
            try:
                employe = salaire.grille_salaire.contrat.employe
                date_paiement = salaire.date_paiement

                if not date_paiement:
                    continue

                annee = date_paiement.year
                mois = date_paiement.month

                champs_modifies = False

                # Rechercher et appliquer chaque correspondance
                if not salaire.numero_diamex_salaire:
                    corr = rechercher_diamex_salaire(employe, annee, mois, 'Salaire')
                    if corr:
                        salaire.numero_diamex_salaire = corr['id']
                        salaire.base_diamex_salaire = corr['prog']
                        nb_champs_remplis += 1
                        champs_modifies = True

                if not salaire.numero_diamex_irsa:
                    corr = rechercher_diamex_salaire(employe, annee, mois, 'IRSA')
                    if corr:
                        salaire.numero_diamex_irsa = corr['id']
                        salaire.base_diamex_irsa = corr['prog']
                        nb_champs_remplis += 1
                        champs_modifies = True

                if not salaire.numero_diamex_cnaps:
                    corr = rechercher_diamex_salaire(employe, annee, mois, 'CNaPS')
                    if corr:
                        salaire.numero_diamex_cnaps = corr['id']
                        salaire.base_diamex_cnaps = corr['prog']
                        nb_champs_remplis += 1
                        champs_modifies = True

                if not salaire.numero_diamex_fmfp:
                    corr = rechercher_diamex_salaire(employe, annee, mois, 'FMFP')
                    if corr:
                        salaire.numero_diamex_fmfp = corr['id']
                        salaire.base_diamex_fmfp = corr['prog']
                        nb_champs_remplis += 1
                        champs_modifies = True

                if not salaire.numero_diamex_mutuelle_sante:
                    corr = rechercher_diamex_mutuelle(employe, annee, mois)
                    if corr:
                        salaire.numero_diamex_mutuelle_sante = corr['id']
                        salaire.base_diamex_mutuelle_sante = corr['prog']
                        nb_champs_remplis += 1
                        champs_modifies = True

                if champs_modifies:
                    salaire.save()
                    nb_salaires_traites += 1

            except Exception as e:
                erreurs.append(f"Salaire {salaire.id}: {str(e)}")

        return JsonResponse({
            'success': True,
            'message': f'{nb_salaires_traites} salaire(s) traité(s), {nb_champs_remplis} champ(s) rempli(s)',
            'nb_salaires_traites': nb_salaires_traites,
            'nb_champs_remplis': nb_champs_remplis,
            'erreurs': erreurs
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
