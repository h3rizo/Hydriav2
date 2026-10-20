"""
Vues pour la gestion des grilles de salaire
"""
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db.models import Value
from django.db.models.functions import Coalesce, NullIf
from decimal import Decimal
import json

from datetime import date, datetime

from .models import GrilleSalaire, Contrat, Employe, ConfigSalaire, ConfigTrancheIRSA
from apps.organization.models import Base


def _get_user_organisation(user):
    employe = getattr(user, 'employe', None)
    base = getattr(employe, 'base', None)
    return getattr(base, 'organisation', None)


def _filter_contrats_by_scope(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    organisation = _get_user_organisation(user)
    if not organisation:
        return queryset.none()
    return queryset.filter(employe__base__organisation=organisation)


def _filter_grilles_by_scope(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    organisation = _get_user_organisation(user)
    if not organisation:
        return queryset.none()
    return queryset.filter(contrat__employe__base__organisation=organisation)


def _parse_date(value):
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            try:
                return datetime.fromisoformat(value).date()
            except ValueError:
                return None
    return None


@login_required
def grille_salaire_list(request):
    """
    Page de liste des grilles de salaire avec filtres
    """
    # Filtres
    contrat_id = request.GET.get('contrat')
    employe_id = request.GET.get('employe')
    base_id = request.GET.get('base')
    annee = request.GET.get('annee')
    mois = request.GET.get('mois')

    # Récupérer l'organisation de l'utilisateur connecté
    user_organisation = None
    if hasattr(request.user, 'employe') and request.user.employe:
        if request.user.employe.base:
            user_organisation = request.user.employe.base.organisation

    # Récupérer toutes les grilles
    grilles = GrilleSalaire.objects.select_related(
        'contrat__employe__poste',
        'contrat__employe__base',
        'created_by'
    ).all()

    # Filtrer par organisation de l'utilisateur connecté
    if user_organisation:
        grilles = grilles.filter(contrat__employe__base__organisation=user_organisation)

    # Appliquer les filtres
    if contrat_id:
        grilles = grilles.filter(contrat_id=contrat_id)
    if employe_id:
        grilles = grilles.filter(contrat__employe_id=employe_id)
    if base_id:
        grilles = grilles.filter(contrat__employe__base_id=base_id)
    if annee:
        grilles = grilles.filter(date_salaire__year=annee)
    if mois:
        grilles = grilles.filter(date_salaire__month=mois)

    # Ordonner par date décroissante
    grilles = grilles.order_by('-date_salaire', 'contrat__employe__nom')

    # Listes pour les filtres
    employes = Employe.objects.select_related('poste', 'base').all()
    if user_organisation:
        employes = employes.filter(base__organisation=user_organisation)
    if base_id:
        employes = employes.filter(base_id=base_id)
    employes = employes.annotate(
        nom_affichage_calc=Coalesce(NullIf('surnom', Value('')), 'nom')
    ).order_by('nom_affichage_calc', 'prenom', 'nom')

    if user_organisation:
        bases = Base.objects.filter(organisation=user_organisation).order_by('nom_base')
        contrats = Contrat.objects.filter(
            fin_contrat__isnull=True,
            employe__base__organisation=user_organisation
        ).select_related('employe').order_by('-debut_contrat')
    else:
        bases = Base.objects.all().order_by('nom_base')
        contrats = Contrat.objects.filter(fin_contrat__isnull=True).select_related('employe').order_by('-debut_contrat')

    # Configuration salaire pour affichage
    config = ConfigSalaire.get_config()

    # Formater les montants pour l'affichage (éviter les problèmes de localisation)
    salaire_min_display = f"{int(config.salaire_minimum):,}".replace(',', ' ') if config.salaire_minimum else "0"
    deduction_irsa_display = f"{int(config.deduction_irsa):,}".replace(',', ' ') if config.deduction_irsa else "0"

    context = {
        'grilles': grilles,
        'employes': employes,
        'bases': bases,
        'contrats': contrats,
        'config': config,
        'selected_employe': employe_id,
        'selected_base': base_id,
        'selected_mois': mois,
        'salaire_min_display': salaire_min_display,
        'deduction_irsa_display': deduction_irsa_display,
        'page_title': 'Grilles de Salaire',
    }

    return render(request, 'employees/grille_salaire_list.html', context)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_grille_salaire_create(request):
    """
    API pour créer une grille de salaire
    """
    try:
        data = json.loads(request.body)

        # Champs obligatoires
        contrat_id = data.get('contrat_id')
        date_salaire = _parse_date(data.get('date_salaire'))

        if not contrat_id or not date_salaire:
            return JsonResponse({
                'success': False,
                'error': 'Contrat et date sont obligatoires'
            }, status=400)

        # Récupérer le contrat
        contrat = get_object_or_404(
            _filter_contrats_by_scope(Contrat.objects.all(), request.user),
            id=contrat_id
        )

        # Empêcher les doublons (contrat + date_salaire)
        existing = GrilleSalaire.objects.filter(
            contrat=contrat,
            date_salaire=date_salaire
        ).first()
        if existing:
            return JsonResponse({
                'success': False,
                'error': "Une grille existe déjà pour ce contrat et cette date.",
                'grille_id': str(existing.id)
            }, status=409)

        # Récupérer les personnes à charge depuis l'employé
        personnes_charge = data.get('personnes_charge', contrat.employe.personnes_charge or 0)

        # Créer la grille
        grille = GrilleSalaire(
            contrat=contrat,
            date_salaire=date_salaire,
            personnes_charge=personnes_charge,
            salaire_net_cible=Decimal(str(data.get('salaire_net_cible', 0))) if data.get('salaire_net_cible') else None,
            salaire_brut_base=Decimal(str(data.get('salaire_brut_base', 0))),
            nb_jours_presence=int(data.get('nb_jours_presence', 0)),
            nb_jours_feries_gardien=int(data.get('nb_jours_feries_gardien', 0)),
            a_travaille_1er_mai=bool(data.get('a_travaille_1er_mai')),
            nb_heures_remplacement_gardien=Decimal(str(data.get('nb_heures_remplacement_gardien', 0))),
            created_by=request.user
        )

        # Le save() calculera automatiquement tous les champs
        grille.save()

        # Mettre à jour les personnes à charge dans l'employé si changé
        if personnes_charge != contrat.employe.personnes_charge:
            contrat.employe.personnes_charge = personnes_charge
            contrat.employe.save()

        return JsonResponse({
            'success': True,
            'message': 'Grille de salaire créée avec succès',
            'grille': {
                'id': str(grille.id),
                'date_salaire': grille.date_salaire.strftime('%Y-%m-%d'),
                'employe': grille.employe.surnom or grille.employe.nom,
                'salaire_brut_base': float(grille.salaire_brut_base),
                'salaire_brut_total': float(grille.salaire_brut_total),
                'salaire_net': float(grille.salaire_net),
                'irsa': float(grille.irsa),
                'charge_cnaps_employe': float(grille.charge_cnaps_employe)
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_grille_salaire_update(request, grille_id):
    """
    API pour mettre à jour une grille de salaire
    """
    try:
        data = json.loads(request.body)

        grille = get_object_or_404(
            _filter_grilles_by_scope(GrilleSalaire.objects.all(), request.user),
            id=grille_id
        )

        # Mettre à jour les champs modifiables
        if 'personnes_charge' in data:
            grille.personnes_charge = int(data['personnes_charge'])
            # Mettre à jour aussi l'employé
            grille.contrat.employe.personnes_charge = grille.personnes_charge
            grille.contrat.employe.save()

        if 'salaire_net_cible' in data:
            grille.salaire_net_cible = Decimal(str(data['salaire_net_cible'])) if data['salaire_net_cible'] else None
            grille.salaire_brut_base = 0  # Reset pour recalcul
        elif 'salaire_brut_base' in data:
            grille.salaire_brut_base = Decimal(str(data['salaire_brut_base']))
            grille.salaire_net_cible = None

        if 'nb_jours_presence' in data:
            grille.nb_jours_presence = int(data['nb_jours_presence'])

        if 'nb_jours_feries_gardien' in data:
            grille.nb_jours_feries_gardien = int(data['nb_jours_feries_gardien'])

        if 'a_travaille_1er_mai' in data:
            grille.a_travaille_1er_mai = bool(data['a_travaille_1er_mai'])

        if 'nb_heures_remplacement_gardien' in data:
            grille.nb_heures_remplacement_gardien = Decimal(str(data['nb_heures_remplacement_gardien']))

        # Le save() recalculera automatiquement tous les champs
        grille.save()

        return JsonResponse({
            'success': True,
            'message': 'Grille de salaire mise à jour avec succès',
            'grille': {
                'id': str(grille.id),
                'salaire_brut_base': float(grille.salaire_brut_base),
                'salaire_brut_total': float(grille.salaire_brut_total),
                'salaire_net': float(grille.salaire_net),
                'irsa': float(grille.irsa),
                'charge_cnaps_employe': float(grille.charge_cnaps_employe),
                'mutuelle_sante': float(grille.mutuelle_sante),
                'base_imposable': float(grille.base_imposable),
                'deduction_impots': float(grille.deduction_impots),
                'majoration_nuit_gardien': float(grille.majoration_nuit_gardien),
                'majoration_dimanche_gardien': float(grille.majoration_dimanche_gardien),
                'montant_jours_feries_gardien': float(grille.montant_jours_feries_gardien),
                'montant_majoration_1er_mai': float(grille.montant_majoration_1er_mai),
                'montant_remplacement_gardien': float(grille.montant_remplacement_gardien)
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_grille_salaire_delete(request, grille_id):
    """
    API pour supprimer une grille de salaire
    """
    try:
        grille = get_object_or_404(
            _filter_grilles_by_scope(GrilleSalaire.objects.all(), request.user),
            id=grille_id
        )

        # Vérifier qu'il n'y a pas de salaires payés liés
        if grille.salaires.exists():
            return JsonResponse({
                'success': False,
                'error': 'Impossible de supprimer : des paiements sont liés à cette grille'
            }, status=400)

        grille.delete()

        return JsonResponse({
            'success': True,
            'message': 'Grille de salaire supprimée avec succès'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
@login_required
def api_grille_salaire_detail(request, grille_id):
    """
    API pour récupérer les détails d'une grille de salaire
    """
    try:
        grille = get_object_or_404(
            _filter_grilles_by_scope(
                GrilleSalaire.objects.select_related(
                'contrat__employe__poste',
                'contrat__employe__base'
            ),
                request.user
            ),
            id=grille_id
        )

        employe = grille.contrat.employe
        config = ConfigSalaire.get_config()
        base_imposable_utilisee = Decimal(str(grille.base_imposable or 0))
        deduction_impots = Decimal(str(grille.deduction_impots or 0))

        irsa_tranches = []
        irsa_calcule = Decimal('0')
        if base_imposable_utilisee > 0:
            montant_restant = base_imposable_utilisee
            tranche_precedente = Decimal('0')
            for tranche in ConfigTrancheIRSA.objects.all().order_by('ordre', 'tranche_superieure'):
                if montant_restant <= 0:
                    break
                montant_tranche = tranche.tranche_superieure - tranche_precedente
                montant_taxable = min(montant_restant, montant_tranche)
                irsa_tranche = montant_taxable * (tranche.pourcentage / Decimal('100'))
                irsa_calcule += irsa_tranche
                irsa_tranches.append({
                    'borne_inferieure': float(tranche_precedente),
                    'borne_superieure': float(tranche.tranche_superieure),
                    'pourcentage': float(tranche.pourcentage),
                    'montant_taxable': float(montant_taxable),
                    'irsa_tranche': float(irsa_tranche),
                })
                montant_restant -= montant_taxable
                tranche_precedente = tranche.tranche_superieure

        irsa_apres_deduction = irsa_calcule - deduction_impots
        if irsa_apres_deduction < 0:
            irsa_apres_deduction = Decimal('0')

        irsa_final = Decimal('0')
        minimum_applique = False
        if base_imposable_utilisee > 0:
            irsa_final = max(irsa_apres_deduction, config.minimum_irsa)
            minimum_applique = irsa_apres_deduction < config.minimum_irsa


        return JsonResponse({
            'success': True,
            'grille': {
                'id': str(grille.id),
                'contrat_id': str(grille.contrat.id),
                'date_salaire': grille.date_salaire.strftime('%Y-%m-%d'),
                'date_salaire_display': grille.date_salaire.strftime('%d/%m/%Y'),

                # Employé
                'employe_id': str(employe.id),
                'employe_nom': employe.surnom or employe.nom,
                'employe_complet': f"{employe.prenom} {employe.nom}",
                'poste': employe.poste.nom_poste if employe.poste else '',
                'base': employe.base.nom_base if employe.base else '',
                'est_gardien': grille.est_gardien,
                'est_journalier': grille.est_journalier,

                # Champs saisis
                'personnes_charge': grille.personnes_charge,
                'salaire_net_cible': float(grille.salaire_net_cible) if grille.salaire_net_cible else None,
                'salaire_brut_base': float(grille.salaire_brut_base),
                'nb_jours_presence': grille.nb_jours_presence,
                'nb_dimanches_travailles': grille.nb_dimanches_travailles,
                'nb_jours_feries_gardien': grille.nb_jours_feries_gardien,
                'a_travaille_1er_mai': grille.a_travaille_1er_mai,
                'nb_heures_remplacement_gardien': float(grille.nb_heures_remplacement_gardien),
                'nb_heures_nuit_gardien': float(grille.nb_heures_nuit_gardien),
                'nb_heures_dimanche_gardien': float(grille.nb_heures_dimanche_gardien),
                'nb_heures_feries_gardien': float(grille.nb_heures_feries_gardien),
                'nb_heures_1er_mai_gardien': float(grille.nb_heures_1er_mai_gardien),

                # Majorations gardien
                'majoration_nuit_gardien': float(grille.majoration_nuit_gardien),
                'majoration_dimanche_gardien': float(grille.majoration_dimanche_gardien),
                'montant_jours_feries_gardien': float(grille.montant_jours_feries_gardien),
                'montant_majoration_1er_mai': float(grille.montant_majoration_1er_mai),
                'montant_remplacement_gardien': float(grille.montant_remplacement_gardien),

                # Salaires calculés
                'salaire_brut_total': float(grille.salaire_brut_total),
                'charge_cnaps_employe': float(grille.charge_cnaps_employe),
                'mutuelle_sante': float(grille.mutuelle_sante),
                'base_imposable': float(grille.base_imposable),
                'deduction_impots': float(grille.deduction_impots),
                'irsa': float(grille.irsa),
                'salaire_net': float(grille.salaire_net),
                'irsa_detail': {
                    'base_imposable_utilisee': float(base_imposable_utilisee),
                    'deduction_impots': float(deduction_impots),
                    'irsa_calcule': float(irsa_calcule),
                    'irsa_apres_deduction': float(irsa_apres_deduction),
                    'minimum_irsa': float(config.minimum_irsa),
                    'minimum_applique': minimum_applique,
                    'irsa_final': float(irsa_final),
                    'tranches': irsa_tranches,
                }
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
@login_required
def api_contrats_actifs(request):
    """
    API pour récupérer les contrats actifs avec infos employés
    """
    try:
        employe_id = request.GET.get('employe_id')

        contrats = Contrat.objects.filter(
            fin_contrat__isnull=True
        ).select_related('employe__poste', 'employe__base')
        contrats = _filter_contrats_by_scope(contrats, request.user)

        if employe_id:
            contrats = contrats.filter(employe_id=employe_id)

        contrats = contrats.order_by('employe__nom', 'employe__prenom', '-debut_contrat')

        data = []
        for contrat in contrats:
            employe = contrat.employe
            data.append({
                'id': str(contrat.id),
                'employe_id': str(employe.id),
                'employe_nom': employe.surnom or employe.nom,
                'employe_complet': f"{employe.prenom} {employe.nom}",
                'poste': employe.poste.nom_poste if employe.poste else '',
                'type_contrat': contrat.get_type_contrat_display() if contrat.type_contrat else '',
                'personnes_charge': employe.personnes_charge or 0,
                'debut_contrat': contrat.debut_contrat.strftime('%d/%m/%Y')
            })

        return JsonResponse({
            'success': True,
            'contrats': data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_calculer_salaire_brut(request):
    """
    API pour calculer le salaire brut depuis un salaire net cible
    Utilise la fonction valeur cible du modèle
    """
    try:
        data = json.loads(request.body)

        contrat_id = data.get('contrat_id')
        salaire_net_cible = data.get('salaire_net_cible')
        personnes_charge = data.get('personnes_charge', 0)
        nb_jours_presence = data.get('nb_jours_presence', 0)
        nb_jours_feries_gardien = data.get('nb_jours_feries_gardien', 0)
        a_travaille_1er_mai = bool(data.get('a_travaille_1er_mai'))
        nb_heures_remplacement_gardien = data.get('nb_heures_remplacement_gardien', 0)

        if not contrat_id or not salaire_net_cible:
            return JsonResponse({
                'success': False,
                'error': 'Contrat et salaire net cible requis'
            }, status=400)

        contrat = get_object_or_404(
            _filter_contrats_by_scope(Contrat.objects.all(), request.user),
            id=contrat_id
        )

        # Créer une grille temporaire pour calculer
        grille = GrilleSalaire(
            contrat=contrat,
            personnes_charge=int(personnes_charge),
            salaire_net_cible=Decimal(str(salaire_net_cible)),
            nb_jours_presence=int(nb_jours_presence),
            nb_jours_feries_gardien=int(nb_jours_feries_gardien),
            a_travaille_1er_mai=a_travaille_1er_mai,
            nb_heures_remplacement_gardien=Decimal(str(nb_heures_remplacement_gardien))
        )

        # Calculer le salaire brut (fonction valeur cible)
        salaire_brut = grille.calculer_salaire_brut_depuis_net(Decimal(str(salaire_net_cible)))

        # Recalculer tous les champs avec ce brut
        grille.salaire_brut_base = salaire_brut
        grille.calculer_tous_les_champs()

        return JsonResponse({
            'success': True,
            'salaire_brut_base': float(grille.salaire_brut_base),
            'salaire_brut_total': float(grille.salaire_brut_total),
            'salaire_net': float(grille.salaire_net),
            'irsa': float(grille.irsa),
            'charge_cnaps_employe': float(grille.charge_cnaps_employe),
            'base_imposable': float(grille.base_imposable),
            'deduction_impots': float(grille.deduction_impots),
            'majoration_nuit_gardien': float(grille.majoration_nuit_gardien),
            'majoration_dimanche_gardien': float(grille.majoration_dimanche_gardien),
            'montant_jours_feries_gardien': float(grille.montant_jours_feries_gardien),
            'montant_remplacement_gardien': float(grille.montant_remplacement_gardien),
            'ecart_net': float(abs(grille.salaire_net - Decimal(str(salaire_net_cible))))
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
