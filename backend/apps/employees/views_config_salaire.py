"""
Vues pour la gestion des configurations de salaires (ConfigSalaire et ConfigTrancheIRSA)
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
import json

from .models import ConfigSalaire, ConfigTrancheIRSA, GrilleSalaire, Contrat, Employe, Poste


def _build_irsa_breakdown(base_imposable, deduction_impots=Decimal('0'), minimum_irsa=None):
    base_imposable = Decimal(str(base_imposable or 0))
    deduction_impots = Decimal(str(deduction_impots or 0))
    if minimum_irsa is None:
        minimum_irsa = ConfigSalaire.get_config().minimum_irsa
    else:
        minimum_irsa = Decimal(str(minimum_irsa))

    tranches = ConfigTrancheIRSA.objects.all().order_by('ordre', 'tranche_superieure')
    detail_tranches = []
    montant_restant = base_imposable
    tranche_precedente = Decimal('0')
    irsa_par_tranches = Decimal('0')

    for tranche in tranches:
        if montant_restant <= 0:
            break

        montant_tranche = tranche.tranche_superieure - tranche_precedente
        montant_taxable = min(montant_restant, montant_tranche)
        irsa_tranche = montant_taxable * (tranche.pourcentage / Decimal('100'))
        irsa_par_tranches += irsa_tranche

        detail_tranches.append({
            'ordre': tranche.ordre,
            'tranche_inf': float(tranche_precedente),
            'tranche_sup': float(tranche.tranche_superieure),
            'pourcentage': float(tranche.pourcentage),
            'montant_taxable': float(montant_taxable),
            'irsa_tranche': float(irsa_tranche),
        })

        montant_restant -= montant_taxable
        tranche_precedente = tranche.tranche_superieure

    irsa_apres_deduction = irsa_par_tranches - deduction_impots
    if irsa_apres_deduction < 0:
        irsa_apres_deduction = Decimal('0')

    irsa_final = Decimal('0')
    minimum_applique = False
    if base_imposable > 0:
        irsa_final = max(irsa_apres_deduction, minimum_irsa)
        minimum_applique = irsa_apres_deduction < minimum_irsa

    return {
        'base_imposable': float(base_imposable),
        'irsa_par_tranches': float(irsa_par_tranches),
        'deduction_impots': float(deduction_impots),
        'irsa_apres_deduction': float(irsa_apres_deduction),
        'minimum_irsa': float(minimum_irsa),
        'minimum_applique': minimum_applique,
        'irsa_final': float(irsa_final),
        'detail_tranches': detail_tranches,
    }


def _build_simulation_grille(mode_simulation, salaire_net_cible, personnes_charge,
                             nb_jours_presence, nb_jours_feries_gardien,
                             a_travaille_1er_mai, nb_heures_remplacement_gardien,
                             nb_heures_nuit_gardien=Decimal('0'),
                             nb_heures_dimanche_gardien=Decimal('0'),
                             nb_heures_feries_gardien=Decimal('0'),
                             nb_heures_chomes_payes=Decimal('0'),
                             nb_heures_1er_mai_gardien=Decimal('0'),
                             nb_heures_remplacement_ordinaire_gardien=Decimal('0')):
    poste_nom = 'Gardien' if mode_simulation == 'gardien' else 'Simulation'
    poste = Poste(nom_poste=poste_nom)
    employe = Employe(
        nom='Simulation',
        prenom='Simulation',
        poste=poste,
        personnes_charge=personnes_charge,
    )
    contrat = Contrat(
        employe=employe,
        poste=poste,
        debut_contrat=date.today(),
        type_contrat='journalier' if mode_simulation == 'journalier' else 'temps_plein',
        salaire_brut_base=Decimal('0'),
    )
    return GrilleSalaire(
        contrat=contrat,
        date_salaire=date.today(),
        personnes_charge=personnes_charge,
        salaire_net_cible=Decimal(str(salaire_net_cible or 0)),
        salaire_brut_base=Decimal('0'),
        nb_jours_presence=nb_jours_presence,
        est_prorata=(mode_simulation == 'prorata'),
        nb_jours_feries_gardien=nb_jours_feries_gardien,
        a_travaille_1er_mai=a_travaille_1er_mai,
        nb_heures_remplacement_gardien=Decimal(str(nb_heures_remplacement_gardien)),
        nb_heures_remplacement_ordinaire_gardien=Decimal(str(nb_heures_remplacement_ordinaire_gardien)),
        nb_heures_nuit_gardien=Decimal(str(nb_heures_nuit_gardien)),
        nb_heures_dimanche_gardien=Decimal(str(nb_heures_dimanche_gardien)),
        nb_heures_feries_gardien=Decimal(str(nb_heures_feries_gardien)),
        nb_heures_chomes_payes=Decimal(str(nb_heures_chomes_payes)),
        nb_heures_1er_mai_gardien=Decimal(str(nb_heures_1er_mai_gardien)),
    )


def _round_to_100(value):
    value = Decimal(str(value or 0))
    return (value / Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * Decimal('100')


def _compute_simulation_snapshot(grille):
    grille.calculer_tous_les_champs()
    salaire_net_exact = (
        grille.salaire_brut_total
        - grille.charge_cnaps_employe
        - grille.mutuelle_sante
        - grille.irsa
    )
    return {
        'salaire_net_exact': salaire_net_exact,
        'salaire_net_arrondi': _round_to_100(salaire_net_exact),
    }


def _solve_gross_from_net_exact(grille, salaire_net_cible, max_iterations=100, tolerance=Decimal('0.01')):
    salaire_net_cible = Decimal(str(salaire_net_cible or 0))
    if salaire_net_cible <= 0:
        return Decimal('0')

    salaire_brut_min = Decimal('0')
    salaire_brut_max = max(salaire_net_cible, Decimal('1'))
    salaire_brut_test = salaire_brut_max

    for _ in range(max_iterations):
        grille.salaire_brut_base = salaire_brut_max
        snapshot = _compute_simulation_snapshot(grille)
        if snapshot['salaire_net_exact'] >= salaire_net_cible:
            break
        salaire_brut_max *= Decimal('2')

    for _ in range(max_iterations):
        salaire_brut_test = (salaire_brut_min + salaire_brut_max) / Decimal('2')
        grille.salaire_brut_base = salaire_brut_test
        snapshot = _compute_simulation_snapshot(grille)
        ecart = abs(snapshot['salaire_net_exact'] - salaire_net_cible)

        if ecart <= tolerance:
            return salaire_brut_test

        if snapshot['salaire_net_exact'] < salaire_net_cible:
            salaire_brut_min = salaire_brut_test
        else:
            salaire_brut_max = salaire_brut_test

    return salaire_brut_test


def _pick_best_integer_gross(grille, salaire_brut_estime, salaire_net_cible):
    salaire_brut_estime = Decimal(str(salaire_brut_estime or 0))
    salaire_net_cible = Decimal(str(salaire_net_cible or 0))
    brut_arrondi = salaire_brut_estime.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    candidats = [
        max(Decimal('0'), brut_arrondi - Decimal('1')),
        max(Decimal('0'), brut_arrondi),
        max(Decimal('0'), brut_arrondi + Decimal('1')),
    ]

    meilleur_brut = candidats[0]
    meilleur_ecart = None
    for candidat in candidats:
        grille.salaire_brut_base = candidat
        snapshot = _compute_simulation_snapshot(grille)
        ecart = abs(snapshot['salaire_net_exact'] - salaire_net_cible)
        if (
            meilleur_ecart is None
            or ecart < meilleur_ecart
            or (ecart == meilleur_ecart and candidat < meilleur_brut)
        ):
            meilleur_brut = candidat
            meilleur_ecart = ecart

    return meilleur_brut


# ==================== ConfigSalaire (Singleton) ====================

def config_salaire_view(request):
    """
    Page de gestion de la configuration des salaires (singleton)
    Affiche le formulaire pour modifier le salaire minimum et la déduction IRSA
    """
    config = ConfigSalaire.get_config()

    context = {
        'config': config,
        'page_title': 'Configuration Salaires',
    }

    return render(request, 'employees/config_salaire.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def api_update_config_salaire(request):
    """
    API pour mettre à jour la configuration des salaires
    """
    try:
        data = json.loads(request.body)

        salaire_minimum = data.get('salaire_minimum')
        deduction_irsa = data.get('deduction_irsa')
        minimum_irsa = data.get('minimum_irsa')
        indemnite_hors_zone = data.get('indemnite_hors_zone')
        indemnite_terrain = data.get('indemnite_terrain')
        indemnite_herizo = data.get('indemnite_herizo')

        # Validation
        if salaire_minimum is None:
            return JsonResponse({
                'success': False,
                'error': 'Le salaire minimum est obligatoire'
            }, status=400)

        if deduction_irsa is None:
            return JsonResponse({
                'success': False,
                'error': 'La déduction IRSA est obligatoire'
            }, status=400)

        if minimum_irsa is None:
            return JsonResponse({
                'success': False,
                'error': 'Le minimum IRSA est obligatoire'
            }, status=400)

        if indemnite_hors_zone is None:
            return JsonResponse({
                'success': False,
                'error': "L'indemnite hors zone est obligatoire"
            }, status=400)

        if indemnite_terrain is None:
            return JsonResponse({
                'success': False,
                'error': "L'indemnite terrain est obligatoire"
            }, status=400)

        if indemnite_herizo is None:
            return JsonResponse({
                'success': False,
                'error': "L'indemnite Herizo est obligatoire"
            }, status=400)

        # Convertir en Decimal
        salaire_minimum = Decimal(str(salaire_minimum))
        deduction_irsa = Decimal(str(deduction_irsa))
        minimum_irsa = Decimal(str(minimum_irsa))
        indemnite_hors_zone = Decimal(str(indemnite_hors_zone))
        indemnite_terrain = Decimal(str(indemnite_terrain))
        indemnite_herizo = Decimal(str(indemnite_herizo))

        # Validation des montants positifs
        if salaire_minimum < 0:
            return JsonResponse({
                'success': False,
                'error': 'Le salaire minimum doit être positif'
            }, status=400)

        if deduction_irsa < 0:
            return JsonResponse({
                'success': False,
                'error': 'La déduction IRSA doit être positive'
            }, status=400)

        if minimum_irsa < 0:
            return JsonResponse({
                'success': False,
                'error': 'Le minimum IRSA doit être positif'
            }, status=400)

        if indemnite_hors_zone < 0:
            return JsonResponse({
                'success': False,
                'error': "L'indemnite hors zone doit etre positive"
            }, status=400)

        if indemnite_terrain < 0:
            return JsonResponse({
                'success': False,
                'error': "L'indemnite terrain doit etre positive"
            }, status=400)

        if indemnite_herizo < 0:
            return JsonResponse({
                'success': False,
                'error': "L'indemnite Herizo doit etre positive"
            }, status=400)


        # Mettre à jour ou créer la config
        config = ConfigSalaire.get_config()
        config.salaire_minimum = salaire_minimum
        config.deduction_irsa = deduction_irsa
        config.minimum_irsa = minimum_irsa
        config.indemnite_hors_zone = indemnite_hors_zone
        config.indemnite_terrain = indemnite_terrain
        config.indemnite_herizo = indemnite_herizo
        config.save()

        return JsonResponse({
            'success': True,
            'message': 'Configuration des salaires mise à jour avec succès',
            'config': {
                'salaire_minimum': float(config.salaire_minimum),
                'deduction_irsa': float(config.deduction_irsa),
                'minimum_irsa': float(config.minimum_irsa),
                'indemnite_hors_zone': float(config.indemnite_hors_zone),
                'indemnite_terrain': float(config.indemnite_terrain),
                'indemnite_herizo': float(config.indemnite_herizo),
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ==================== ConfigTrancheIRSA ====================

def config_tranches_irsa_view(request):
    """
    Page de gestion des tranches IRSA
    Affiche la liste des tranches et permet d'ajouter/modifier/supprimer
    """
    tranches = ConfigTrancheIRSA.objects.all().order_by('ordre', 'tranche_superieure')
    config = ConfigSalaire.get_config()

    context = {
        'tranches': tranches,
        'config': config,
        'page_title': 'Configuration Tranches IRSA',
    }

    return render(request, 'employees/config_tranches_irsa.html', context)


@csrf_exempt
@require_http_methods(["GET"])
def api_list_tranches_irsa(request):
    """
    API pour lister toutes les tranches IRSA
    """
    try:
        tranches = ConfigTrancheIRSA.objects.all().order_by('ordre', 'tranche_superieure')

        tranches_data = [{
            'id': str(tranche.id),
            'tranche_superieure': float(tranche.tranche_superieure),
            'pourcentage': float(tranche.pourcentage),
            'ordre': tranche.ordre,
        } for tranche in tranches]

        return JsonResponse({
            'success': True,
            'tranches': tranches_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_create_tranche_irsa(request):
    """
    API pour créer une nouvelle tranche IRSA
    """
    try:
        data = json.loads(request.body)

        tranche_superieure = data.get('tranche_superieure')
        pourcentage = data.get('pourcentage')
        ordre = data.get('ordre')

        # Validation
        if tranche_superieure is None:
            return JsonResponse({
                'success': False,
                'error': 'La tranche supérieure est obligatoire'
            }, status=400)

        if pourcentage is None:
            return JsonResponse({
                'success': False,
                'error': 'Le pourcentage est obligatoire'
            }, status=400)

        if ordre is None:
            return JsonResponse({
                'success': False,
                'error': 'L\'ordre est obligatoire'
            }, status=400)

        # Convertir en types appropriés
        tranche_superieure = Decimal(str(tranche_superieure))
        pourcentage = Decimal(str(pourcentage))
        ordre = int(ordre)

        # Validation des valeurs
        if tranche_superieure <= 0:
            return JsonResponse({
                'success': False,
                'error': 'La tranche supérieure doit être strictement positive'
            }, status=400)

        if pourcentage < 0 or pourcentage > 100:
            return JsonResponse({
                'success': False,
                'error': 'Le pourcentage doit être entre 0 et 100'
            }, status=400)

        if ordre < 1:
            return JsonResponse({
                'success': False,
                'error': 'L\'ordre doit être supérieur ou égal à 1'
            }, status=400)

        # Créer la tranche
        tranche = ConfigTrancheIRSA.objects.create(
            tranche_superieure=tranche_superieure,
            pourcentage=pourcentage,
            ordre=ordre
        )

        return JsonResponse({
            'success': True,
            'message': 'Tranche IRSA créée avec succès',
            'tranche': {
                'id': str(tranche.id),
                'tranche_superieure': float(tranche.tranche_superieure),
                'pourcentage': float(tranche.pourcentage),
                'ordre': tranche.ordre,
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_update_tranche_irsa(request, tranche_id):
    """
    API pour mettre à jour une tranche IRSA existante
    """
    try:
        tranche = get_object_or_404(ConfigTrancheIRSA, id=tranche_id)
        data = json.loads(request.body)

        tranche_superieure = data.get('tranche_superieure')
        pourcentage = data.get('pourcentage')
        ordre = data.get('ordre')

        # Validation
        if tranche_superieure is None:
            return JsonResponse({
                'success': False,
                'error': 'La tranche supérieure est obligatoire'
            }, status=400)

        if pourcentage is None:
            return JsonResponse({
                'success': False,
                'error': 'Le pourcentage est obligatoire'
            }, status=400)

        if ordre is None:
            return JsonResponse({
                'success': False,
                'error': 'L\'ordre est obligatoire'
            }, status=400)

        # Convertir en types appropriés
        tranche_superieure = Decimal(str(tranche_superieure))
        pourcentage = Decimal(str(pourcentage))
        ordre = int(ordre)

        # Validation des valeurs
        if tranche_superieure <= 0:
            return JsonResponse({
                'success': False,
                'error': 'La tranche supérieure doit être strictement positive'
            }, status=400)

        if pourcentage < 0 or pourcentage > 100:
            return JsonResponse({
                'success': False,
                'error': 'Le pourcentage doit être entre 0 et 100'
            }, status=400)

        if ordre < 1:
            return JsonResponse({
                'success': False,
                'error': 'L\'ordre doit être supérieur ou égal à 1'
            }, status=400)

        # Mettre à jour
        tranche.tranche_superieure = tranche_superieure
        tranche.pourcentage = pourcentage
        tranche.ordre = ordre
        tranche.save()

        return JsonResponse({
            'success': True,
            'message': 'Tranche IRSA mise à jour avec succès',
            'tranche': {
                'id': str(tranche.id),
                'tranche_superieure': float(tranche.tranche_superieure),
                'pourcentage': float(tranche.pourcentage),
                'ordre': tranche.ordre,
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_delete_tranche_irsa(request, tranche_id):
    """
    API pour supprimer une tranche IRSA
    """
    try:
        tranche = get_object_or_404(ConfigTrancheIRSA, id=tranche_id)
        tranche.delete()

        return JsonResponse({
            'success': True,
            'message': 'Tranche IRSA supprimée avec succès'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_calculer_irsa_test(request):
    """
    API pour tester le calcul de l'IRSA pour une base imposable donnée
    """
    try:
        data = json.loads(request.body)
        base_imposable = data.get('base_imposable')

        enfants_charge = data.get('enfants_charge', 0)

        if base_imposable is None:
            return JsonResponse({
                'success': False,
                'error': 'La base imposable est obligatoire'
            }, status=400)

        base_imposable = Decimal(str(base_imposable))
        enfants_charge = int(enfants_charge) if enfants_charge else 0

        if base_imposable < 0:
            return JsonResponse({
                'success': False,
                'error': 'La base imposable doit être positive'
            }, status=400)

        if enfants_charge < 0:
            return JsonResponse({
                'success': False,
                'error': 'Le nombre d\'enfants doit être positif'
            }, status=400)

        # Récupérer la configuration pour déduction IRSA et minimum IRSA
        config_salaire = ConfigSalaire.get_config()
        deduction_irsa_unitaire = config_salaire.deduction_irsa
        minimum_irsa = config_salaire.minimum_irsa

        # Calculer la déduction pour enfants
        deduction_enfants = deduction_irsa_unitaire * Decimal(str(enfants_charge))
        breakdown = _build_irsa_breakdown(
            base_imposable=base_imposable,
            deduction_impots=deduction_enfants,
            minimum_irsa=minimum_irsa,
        )

        return JsonResponse({
            'success': True,
            'base_imposable': float(base_imposable),
            'enfants_charge': enfants_charge,
            'deduction_irsa_unitaire': float(deduction_irsa_unitaire),
            'deduction_enfants': float(deduction_enfants),
            'irsa_par_tranches': breakdown['irsa_par_tranches'],
            'irsa_apres_deduction': breakdown['irsa_apres_deduction'],
            'minimum_irsa': breakdown['minimum_irsa'],
            'irsa_final': breakdown['irsa_final'],
            'minimum_applique': breakdown['minimum_applique'],
            'detail_tranches': breakdown['detail_tranches']
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_simuler_salaire_depuis_net(request):
    """
    API de simulation complète salaire net cible -> brut + retenues.
    Réutilise le moteur réel de GrilleSalaire sans enregistrer de données.
    """
    try:
        data = json.loads(request.body)
        simulation_basis = (data.get('simulation_basis') or 'net').strip().lower()
        salaire_net_cible = data.get('salaire_net_cible')
        salaire_brut_cible = data.get('salaire_brut_cible')
        personnes_charge = int(data.get('personnes_charge', 0) or 0)
        mode_simulation = (data.get('mode_simulation') or 'standard').strip().lower()
        nb_jours_presence = int(data.get('nb_jours_presence', 0) or 0)
        nb_jours_feries_gardien = int(data.get('nb_jours_feries_gardien', 0) or 0)
        a_travaille_1er_mai = bool(data.get('a_travaille_1er_mai'))
        nb_heures_remplacement_gardien = Decimal(str(data.get('nb_heures_remplacement_gardien', 0) or 0))
        nb_heures_remplacement_ordinaire_gardien = Decimal(str(data.get('nb_heures_remplacement_ordinaire_gardien', 0) or 0))
        nb_heures_nuit_gardien = Decimal(str(data.get(
            'nb_heures_nuit_gardien',
            56 if mode_simulation == 'gardien' else 0,
        ) or 0))
        nb_heures_dimanche_gardien = Decimal(str(data.get(
            'nb_heures_dimanche_gardien',
            0,
        ) or 0))
        nb_heures_feries_gardien = Decimal(str(data.get('nb_heures_feries_gardien', 0) or 0))
        nb_heures_chomes_payes = Decimal(str(data.get('nb_heures_chomes_payes', 0) or 0))
        nb_heures_1er_mai_gardien = Decimal(str(data.get('nb_heures_1er_mai_gardien', 0) or 0))

        if simulation_basis not in {'net', 'brut'}:
            return JsonResponse({
                'success': False,
                'error': 'Base de simulation invalide'
            }, status=400)

        if simulation_basis == 'net':
            if salaire_net_cible is None:
                return JsonResponse({
                    'success': False,
                    'error': 'Le salaire net cible est obligatoire'
                }, status=400)
            salaire_net_cible = Decimal(str(salaire_net_cible))
            if salaire_net_cible <= 0:
                return JsonResponse({
                    'success': False,
                    'error': 'Le salaire net cible doit être strictement positif'
                }, status=400)
            salaire_brut_cible = None
        else:
            if salaire_brut_cible is None:
                return JsonResponse({
                    'success': False,
                    'error': 'Le salaire brut cible est obligatoire'
                }, status=400)
            salaire_brut_cible = Decimal(str(salaire_brut_cible))
            if salaire_brut_cible <= 0:
                return JsonResponse({
                    'success': False,
                    'error': 'Le salaire brut cible doit être strictement positif'
                }, status=400)
            salaire_net_cible = Decimal('0')

        if personnes_charge < 0:
            return JsonResponse({
                'success': False,
                'error': 'Le nombre de personnes à charge doit être positif'
            }, status=400)

        modes_valides = {'standard', 'prorata', 'journalier', 'gardien'}
        if mode_simulation not in modes_valides:
            return JsonResponse({
                'success': False,
                'error': 'Mode de simulation invalide'
            }, status=400)

        if nb_heures_remplacement_ordinaire_gardien > nb_heures_remplacement_gardien:
            return JsonResponse({
                'success': False,
                'error': 'Les heures de remplacement un jour ordinaire ne peuvent pas dépasser le total des heures de remplacement'
            }, status=400)

        guardian_hours = (
            nb_heures_remplacement_gardien,
            nb_heures_remplacement_ordinaire_gardien,
            nb_heures_nuit_gardien,
            nb_heures_dimanche_gardien,
            nb_heures_feries_gardien,
            nb_heures_chomes_payes,
            nb_heures_1er_mai_gardien,
        )
        if nb_jours_presence < 0 or nb_jours_feries_gardien < 0 or any(value < 0 for value in guardian_hours):
            return JsonResponse({
                'success': False,
                'error': 'Les quantités de jours ou heures doivent être positives'
            }, status=400)

        if mode_simulation in {'prorata', 'journalier'} and nb_jours_presence <= 0:
            return JsonResponse({
                'success': False,
                'error': 'Le nombre de jours de présence est obligatoire pour ce mode'
            }, status=400)

        grille = _build_simulation_grille(
            mode_simulation=mode_simulation,
            salaire_net_cible=salaire_net_cible,
            personnes_charge=personnes_charge,
            nb_jours_presence=nb_jours_presence,
            nb_jours_feries_gardien=nb_jours_feries_gardien,
            a_travaille_1er_mai=a_travaille_1er_mai,
            nb_heures_remplacement_gardien=nb_heures_remplacement_gardien,
            nb_heures_remplacement_ordinaire_gardien=nb_heures_remplacement_ordinaire_gardien,
            nb_heures_nuit_gardien=nb_heures_nuit_gardien,
            nb_heures_dimanche_gardien=nb_heures_dimanche_gardien,
            nb_heures_feries_gardien=nb_heures_feries_gardien,
            nb_heures_chomes_payes=nb_heures_chomes_payes,
            nb_heures_1er_mai_gardien=nb_heures_1er_mai_gardien,
        )

        if simulation_basis == 'net':
            salaire_brut = _solve_gross_from_net_exact(grille, salaire_net_cible)
            salaire_brut = _pick_best_integer_gross(grille, salaire_brut, salaire_net_cible)
            grille.salaire_brut_base = salaire_brut
        else:
            grille.salaire_brut_base = salaire_brut_cible
        snapshot = _compute_simulation_snapshot(grille)

        config = ConfigSalaire.get_config()
        plafond_cnaps = Decimal('8') * config.salaire_minimum
        base_cnaps = min(grille.salaire_brut_total, plafond_cnaps)
        irsa_detail = _build_irsa_breakdown(
            base_imposable=grille.base_imposable,
            deduction_impots=grille.deduction_impots,
            minimum_irsa=config.minimum_irsa,
        )

        return JsonResponse({
            'success': True,
            'simulation_basis': simulation_basis,
            'mode_simulation': mode_simulation,
            'salaire_net_cible': float(salaire_net_cible),
            'salaire_brut_cible': float(salaire_brut_cible) if salaire_brut_cible is not None else None,
            'salaire_brut_base': float(grille.salaire_brut_base),
            'salaire_brut_total': float(grille.salaire_brut_total),
            'base_cnaps': float(base_cnaps),
            'charge_cnaps_employe': float(grille.charge_cnaps_employe),
            'mutuelle_sante': float(grille.mutuelle_sante),
            'base_imposable': float(grille.base_imposable),
            'deduction_impots': float(grille.deduction_impots),
            'irsa': float(grille.irsa),
            'salaire_net': float(snapshot['salaire_net_arrondi']),
            'salaire_net_exact': float(snapshot['salaire_net_exact']),
            'salaire_net_arrondi': float(snapshot['salaire_net_arrondi']),
            'ecart_net': float(abs(snapshot['salaire_net_exact'] - salaire_net_cible)) if simulation_basis == 'net' else 0.0,
            'majoration_nuit_gardien': float(grille.majoration_nuit_gardien),
            'majoration_dimanche_gardien': float(grille.majoration_dimanche_gardien),
            'montant_jours_feries_gardien': float(grille.montant_jours_feries_gardien),
            'montant_jours_chomes_payes': float(grille.montant_jours_chomes_payes),
            'montant_majoration_1er_mai': float(grille.montant_majoration_1er_mai),
            'montant_remplacement_gardien': float(grille.montant_remplacement_gardien),
            'nb_heures_nuit_gardien': float(grille.nb_heures_nuit_gardien),
            'nb_heures_dimanche_gardien': float(grille.nb_heures_dimanche_gardien),
            'nb_heures_feries_gardien': float(grille.nb_heures_feries_gardien),
            'nb_heures_chomes_payes': float(grille.nb_heures_chomes_payes),
            'nb_heures_1er_mai_gardien': float(grille.nb_heures_1er_mai_gardien),
            'nb_heures_remplacement_gardien': float(grille.nb_heures_remplacement_gardien),
            'nb_heures_remplacement_ordinaire_gardien': float(grille.nb_heures_remplacement_ordinaire_gardien),
            'hypotheses': {
                'salaire_minimum': float(config.salaire_minimum),
                'deduction_irsa_unitaire': float(config.deduction_irsa),
                'minimum_irsa': float(config.minimum_irsa),
                'mutuelle_identique_cnaps': True,
            },
            'irsa_detail': irsa_detail,
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
