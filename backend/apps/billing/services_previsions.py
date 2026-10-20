"""
Services pour le calcul automatique des prévisions budgétaires.
"""
from django.db import transaction
from django.db.models import Avg, Sum, Count, Q
from django.db import models
from decimal import Decimal
from apps.billing.tarifs_forfaitaires import tarif_pour_annee
from datetime import date, timedelta
from .models_previsions import PrevisionBudget, ConfigurationPrevision
from .models import PointEau, Releve
import logging

logger = logging.getLogger(__name__)


def recalculer_previsions_annee(annee, base=None):
    """
    Recalcule toutes les prévisions pour une année donnée.
    Supprime les anciennes prévisions calculées auto et les recrée.

    Args:
        annee (int): Année pour laquelle calculer les prévisions
        base (Base, optional): Filtrer par base spécifique

    Returns:
        dict: Statistiques du calcul
    """
    stats = {
        'annee': annee,
        'supprimees': 0,
        'creees': 0,
        'recettes_forfaitaires': 0,
        'recettes_volumetriques': 0,
        'recettes_nouveaux_pe': 0,
        'depenses_bons_avances': 0,
        'depenses_salaires': 0,
        'depenses_irsa': 0,
        'depenses_charges_sociales': 0,
        'nb_employes_salaires': 0,
        'nb_employes_irsa': 0,
        'nb_prix_manquants': 0,
        'designations_prix_manquants': [],
        'erreurs': [],
        'avertissements': []
    }

    try:
        with transaction.atomic():
            # Supprimer les prévisions auto existantes pour cette année
            queryset = PrevisionBudget.objects.filter(
                annee=annee,
                est_calculee_auto=True
            )
            if base:
                queryset = queryset.filter(base=base)

            stats['supprimees'] = queryset.count()
            queryset.delete()

            # Récupérer ou créer la configuration
            config, _ = ConfigurationPrevision.objects.get_or_create(
                annee_reference=annee,
                actif=True,
                defaults={
                    'nb_nouveaux_pe_prevus': 25,
                    'tarif_nouveau_pe_trimestre': Decimal('75000'),
                    'nb_mois_moyenne_volumetrique': 12
                }
            )

            # 1. Calcul recettes forfaitaires
            nb_forfait = calculer_recettes_forfaitaires(annee, base, config)
            stats['recettes_forfaitaires'] = nb_forfait
            stats['creees'] += nb_forfait

            # 2. Calcul recettes volumétriques
            nb_volume = calculer_recettes_volumetriques(annee, base, config)
            stats['recettes_volumetriques'] = nb_volume
            stats['creees'] += nb_volume

            # 3. Calcul recettes nouveaux points d'eau
            nb_nouveaux = calculer_recettes_nouveaux_pe(annee, base, config)
            stats['recettes_nouveaux_pe'] = nb_nouveaux
            stats['creees'] += nb_nouveaux

            # 4. Calcul dépenses bons de livraison et avances
            # Calculer les avances
            result_avances = calculer_depenses_avances(annee, base, config)
            stats['depenses_avances'] = result_avances['nb_created']
            stats['creees'] += result_avances['nb_created']

            # Calculer les bons de livraison
            result_bons_livraison = calculer_depenses_bons_livraison(annee, base, config)
            stats['depenses_bons_livraison'] = result_bons_livraison['nb_created']
            stats['creees'] += result_bons_livraison['nb_created']

            # 5. Calcul dépenses indemnités journalières
            result_indemnites = calculer_depenses_indemnites(annee, base, config)
            stats['depenses_indemnites'] = result_indemnites['nb_created']
            stats['creees'] += result_indemnites['nb_created']
            stats['nb_jours_terrain'] = result_indemnites['nb_jours_terrain']
            stats['nb_employes_indemnites'] = result_indemnites['nb_employes']

            # 6. Calcul depenses salaires
            result_salaires = calculer_previsions_salaires(annee, base, config)
            stats['depenses_salaires'] = result_salaires['nb_created']
            stats['creees'] += result_salaires['nb_created']
            stats['nb_employes_salaires'] = result_salaires['nb_employes']

            # 7. Calcul depenses IRSA
            result_irsa = calculer_previsions_irsa(annee, base, config)
            stats['depenses_irsa'] = result_irsa['nb_created']
            stats['creees'] += result_irsa['nb_created']
            stats['nb_employes_irsa'] = result_irsa['nb_employes']

            # 8. Calcul charges sociales (CNAPS, FMFP, Mutuelle)
            result_charges = calculer_previsions_charges_sociales(annee, base, config)
            stats['depenses_charges_sociales'] = result_charges['nb_created']
            stats['creees'] += result_charges['nb_created']

            # 9. Calcul loyers (compte 613100)
            result_loyers = calculer_previsions_loyers(annee, base, config)
            stats['depenses_loyers'] = result_loyers['nb_created']
            stats['creees'] += result_loyers['nb_created']

            # 10. Calcul dépenses récurrentes (comptes 602, 606, 615, 623100, 626222, 626320, 626321, 627203, 627204, 631104)
            result_recurrentes = calculer_previsions_depenses_recurrentes(annee, base, config)
            stats['depenses_recurrentes'] = result_recurrentes['nb_created']
            stats['creees'] += result_recurrentes['nb_created']

            # Agrégation des prix manquants
            stats['nb_prix_manquants'] = result_avances['nb_prix_manquants'] + result_bons_livraison['nb_prix_manquants']
            stats['designations_prix_manquants'] = list(set(
                result_avances['designations_prix_manquants'] + result_bons_livraison['designations_prix_manquants']
            ))

            # Ajouter avertissement si des prix sont manquants
            if stats['nb_prix_manquants'] > 0:
                stats['avertissements'].append(
                    f"⚠️ {stats['nb_prix_manquants']} désignation(s) sans prix unitaire. "
                    f"Les dépenses correspondantes ont été créées avec montant 0 Ar."
                )

            logger.info(f"Prévisions recalculées pour {annee}: {stats['creees']} lignes créées")

    except Exception as e:
        logger.error(f"Erreur lors du recalcul des prévisions: {str(e)}")
        stats['erreurs'].append(str(e))

    return stats


def calculer_recettes_forfaitaires(annee, base=None, config=None):
    """
    Calcule les recettes forfaitaires prévues pour l'année.
    Formule: tarifforfaitaire par trimestre (paiement tous les 3 mois).
    La date du premier paiement est récupérée depuis le dernier paiement forfaitaire.

    Returns:
        int: Nombre de lignes créées
    """
    from .models import PaiementForfaitaire

    nb_created = 0

    # Récupérer les points d'eau avec tarif forfaitaire
    queryset = PointEau.objects.filter(
        tarifforfaitaire__isnull=False,
        tarifforfaitaire__gt=0,
        datearretbranchement__isnull=True  # Points d'eau actifs uniquement
    ).select_related(
        'ouvrage',
        'parcelle__village__fokontany__commune__district'
    )

    if base:
        queryset = queryset.filter(ouvrage__bases=base)

    # Traiter chaque point d'eau
    for point_eau in queryset:
        try:
            # Tarif trimestriel
            tarif_trimestriel = tarif_pour_annee(point_eau, annee)

            # Récupérer la date du dernier paiement forfaitaire pour ce point d'eau
            dernier_paiement = PaiementForfaitaire.objects.filter(
                point_eau=point_eau,
                date_facture__lt=date(annee, 1, 1)  # Paiements avant l'année de prévision
            ).order_by('-date_facture').first()

            # Déterminer le mois de départ du premier trimestre
            if dernier_paiement and dernier_paiement.date_facture:
                # Calculer le prochain trimestre après le dernier paiement
                mois_dernier = dernier_paiement.date_facture.month
                # Trouver le prochain trimestre (mois 1, 4, 7, 10)
                if mois_dernier <= 1:
                    mois_premier_paiement = 1
                elif mois_dernier <= 4:
                    mois_premier_paiement = 4
                elif mois_dernier <= 7:
                    mois_premier_paiement = 7
                elif mois_dernier <= 10:
                    mois_premier_paiement = 10
                else:
                    mois_premier_paiement = 1  # Janvier de l'année suivante
            else:
                # Pas de paiement antérieur : commencer en janvier
                mois_premier_paiement = 1

            # Récupérer la première base de l'ouvrage (si existe)
            base_name = None
            base_obj = None
            district_obj = None
            commune_obj = None

            if point_eau.ouvrage:
                first_base = point_eau.ouvrage.bases.first()
                if first_base:
                    base_name = first_base.nom_base
                    base_obj = first_base

            # Reconstituer la chaîne géographique: PointEau → Parcelle → Village → Fokontany → Commune → District
            if point_eau.parcelle:
                village = point_eau.parcelle.village
                if village and village.fokontany:
                    fokontany = village.fokontany
                    if fokontany.commune:
                        commune_obj = fokontany.commune
                        if commune_obj.district:
                            district_obj = commune_obj.district

            # Créer une ligne de prévision pour chaque trimestre
            # Trimestres : mois 1, 4, 7, 10
            for mois_trimestre in [1, 4, 7, 10]:
                # Ne créer que si ce trimestre est après ou égal au premier paiement prévu
                if mois_trimestre < mois_premier_paiement:
                    continue

                date_prevision = date(annee, mois_trimestre, 1)

                # Détail avec nomabonne ou idxls
                detail_abonne = point_eau.nomabonne or point_eau.idxls or str(point_eau.id)

                PrevisionBudget.objects.create(
                    date=date_prevision,
                    cat='748411',  # Compte recettes forfaitaires (6 chiffres)
                    libelle=f"Recette forfaitaire - {point_eau.code_point_eau or point_eau.nomabonne}",
                    in_amount=tarif_trimestriel,
                    out_amount=Decimal('0'),
                    activ=base_name,
                    detail=detail_abonne,
                    quantite=Decimal('1'),  # 1 point d'eau
                    prix_unitaire=tarif_trimestriel,  # Tarif forfaitaire trimestriel
                    type_prevision='recette_forfaitaire',
                    base=base_obj,
                    ouvrage=point_eau.ouvrage,
                    district=district_obj,
                    commune=commune_obj,
                    annee=annee,
                    mois=mois_trimestre,
                    est_calculee_auto=True,
                    source_calcul=f"PointEau:{point_eau.id}"
                )
                nb_created += 1

        except Exception as e:
            logger.error(f"Erreur calcul forfait PE {point_eau.id}: {str(e)}")
            continue

    return nb_created


def calculer_recettes_volumetriques(annee, base=None, config=None):
    """
    Calcule les recettes volumétriques prévues pour l'année.
    Formule: Moyenne mensuelle des 12 derniers mois × 12.

    Returns:
        int: Nombre de lignes créées
    """
    nb_created = 0

    if not config:
        config, _ = ConfigurationPrevision.objects.get_or_create(
            annee_reference=annee,
            actif=True,
            defaults={'nb_mois_moyenne_volumetrique': 12}
        )

    nb_mois = config.nb_mois_moyenne_volumetrique

    # Date de début pour la moyenne (nb_mois avant l'année de prévision)
    date_debut_moyenne = date(annee - 1, 1, 1)

    # Récupérer les points d'eau avec modalité volumétrique
    queryset = PointEau.objects.filter(
        ouvrage__modalites_gestion__modalitepaiement='au_volume',
        ouvrage__modalites_gestion__date_fin__isnull=True,  # Modalité active
        datearretbranchement__isnull=True  # Point d'eau actif
    ).distinct().select_related(
        'ouvrage',
        'parcelle__village__fokontany__commune__district'
    )

    if base:
        queryset = queryset.filter(ouvrage__bases=base)

    for point_eau in queryset:
        try:
            # Calculer la moyenne mensuelle des factures
            moyenne_stats = Releve.objects.filter(
                point_eau=point_eau,
                datereleve__gte=date_debut_moyenne,
                datereleve__lt=date(annee, 1, 1),
                montant__isnull=False,
                montant__gt=0
            ).aggregate(
                moyenne_mensuelle=Avg('montant'),
                nb_factures=Count('id')
            )

            moyenne_mensuelle = moyenne_stats['moyenne_mensuelle']
            nb_factures = moyenne_stats['nb_factures']

            # Si pas de données historiques, passer
            if not moyenne_mensuelle or nb_factures < 3:
                continue

            moyenne_mensuelle = Decimal(str(moyenne_mensuelle))

            # Créer une ligne de prévision pour chaque mois
            for mois in range(1, 13):
                date_prevision = date(annee, mois, 1)

                # Récupérer la première base de l'ouvrage (si existe)
                base_name = None
                base_obj = None
                district_obj = None
                commune_obj = None

                if point_eau.ouvrage:
                    first_base = point_eau.ouvrage.bases.first()
                    if first_base:
                        base_name = first_base.nom_base
                        base_obj = first_base

                # Reconstituer la chaîne géographique
                if point_eau.parcelle:
                    village = point_eau.parcelle.village
                    if village and village.fokontany:
                        fokontany = village.fokontany
                        if fokontany.commune:
                            commune_obj = fokontany.commune
                            if commune_obj.district:
                                district_obj = commune_obj.district

                # Détail avec nomabonne ou idxls
                detail_abonne = point_eau.nomabonne or point_eau.idxls or str(point_eau.id)

                PrevisionBudget.objects.create(
                    date=date_prevision,
                    cat='707401',  # Compte recettes volumétriques (6 chiffres)
                    libelle=f"Recette volumétrique - {point_eau.code_point_eau or point_eau.nomabonne}",
                    in_amount=moyenne_mensuelle,
                    out_amount=Decimal('0'),
                    activ=base_name,
                    detail=detail_abonne,
                    quantite=Decimal('1'),  # Quantité = 1 pour calcul avec prix unitaire
                    prix_unitaire=moyenne_mensuelle,  # Prix unitaire = montant moyen mensuel
                    type_prevision='recette_volumetrique',
                    base=base_obj,
                    ouvrage=point_eau.ouvrage,
                    district=district_obj,
                    commune=commune_obj,
                    annee=annee,
                    mois=mois,
                    est_calculee_auto=True,
                    source_calcul=f"PointEau:{point_eau.id}"
                )
                nb_created += 1

        except Exception as e:
            logger.error(f"Erreur calcul volumétrique PE {point_eau.id}: {str(e)}")
            continue

    return nb_created


def calculer_recettes_nouveaux_pe(annee, base=None, config=None):
    """
    Calcule les recettes prévues pour les nouveaux points d'eau.
    Formule: 25 nouveaux PE × 75 000 Ar/trimestre × 4 trimestres.

    Returns:
        int: Nombre de lignes créées
    """
    nb_created = 0

    if not config:
        config, _ = ConfigurationPrevision.objects.get_or_create(
            annee_reference=annee,
            actif=True,
            defaults={
                'nb_nouveaux_pe_prevus': 25,
                'tarif_nouveau_pe_trimestre': Decimal('75000')
            }
        )

    nb_nouveaux = config.nb_nouveaux_pe_prevus
    tarif_trimestre = config.tarif_nouveau_pe_trimestre

    # Recette annuelle totale
    recette_annuelle_totale = nb_nouveaux * tarif_trimestre * Decimal('4')

    # Répartir sur 12 mois
    recette_mensuelle = recette_annuelle_totale / Decimal('12')

    # Créer une ligne de prévision pour chaque mois
    for mois in range(1, 13):
        try:
            date_prevision = date(annee, mois, 1)

            PrevisionBudget.objects.create(
                date=date_prevision,
                cat='748411',  # Même compte que recettes forfaitaires
                libelle=f"Recettes nouveaux points d'eau prévus ({nb_nouveaux} PE)",
                in_amount=recette_mensuelle,
                out_amount=Decimal('0'),
                activ=base.nom_base if base else 'GLOBAL',
                detail=f"{nb_nouveaux} nouveaux PE × {tarif_trimestre} Ar/trim × 4 trim = {recette_annuelle_totale} Ar/an",
                type_prevision='recette_nouveaux_pe',
                base=base,
                ouvrage=None,
                annee=annee,
                mois=mois,
                est_calculee_auto=True,
                source_calcul=f"Config:nouveaux_pe_{annee}"
            )
            nb_created += 1

        except Exception as e:
            logger.error(f"Erreur calcul nouveaux PE mois {mois}: {str(e)}")
            continue

    return nb_created


def calculer_depenses_avances(annee, base=None, config=None):
    """
    Calcule les dépenses prévues basées sur les AVANCES de l'année en cours.
    Reprend les mêmes dépenses de l'année courante en changeant juste l'année.
    Utilise les prix de la table Designation.prix_unitaire ou PlanningDetail.montant.

    Returns:
        dict: {
            'nb_created': int,
            'nb_prix_manquants': int,
            'designations_prix_manquants': list
        }
    """
    from apps.planning.models import PlanningDetail, Designation, Planning
    from datetime import datetime

    nb_created = 0
    nb_prix_manquants = 0
    designations_prix_manquants = []

    # Année de référence = année en cours
    annee_courante = datetime.now().year

    # Récupérer tous les PlanningDetails de l'année courante
    # qui concernent SEULEMENT LES AVANCES (numero_bon_avance)
    details_annee_courante = PlanningDetail.objects.filter(
        planning__date__year=annee_courante,
        numero_bon_avance__isnull=False  # SEULEMENT les avances
    ).select_related(
        'designation',
        'planning',
        'planning__employe',
        'compte',
        'equipement_constitutif',
        'point_eau__ouvrage',
        'point_eau__parcelle__village__fokontany__commune__district'
    )

    if base:
        # Filtrer par base si spécifié
        details_annee_courante = details_annee_courante.filter(
            planning__organisation__bases=base
        )

    logger.info(f"Calcul dépenses: {details_annee_courante.count()} lignes trouvées pour {annee_courante}")

    for detail in details_annee_courante:
        try:
            # Utiliser le montant déjà calculé dans PlanningDetail (prioritaire)
            # Sinon calculer avec detail.pu * quantity
            # En dernier recours : utiliser designation.prix_unitaire

            if detail.montant and detail.montant > 0:
                # Montant déjà calculé - on l'utilise directement
                montant_total = Decimal(str(detail.montant))
            elif detail.pu and detail.pu > 0 and detail.quantity:
                # Calculer avec le PU du détail
                montant_total = Decimal(str(detail.pu)) * Decimal(str(detail.quantity))
            elif detail.designation and detail.designation.prix_unitaire and detail.quantity:
                # Fallback : utiliser le prix de la désignation
                prix_unitaire = Decimal(str(detail.designation.prix_unitaire))
                montant_total = prix_unitaire * Decimal(str(detail.quantity))
            else:
                # Aucun prix disponible - signaler
                nb_prix_manquants += 1
                designation_info = f"{detail.designation.nom if detail.designation else 'N/A'} (Detail ID: {detail.id})"
                if designation_info not in designations_prix_manquants:
                    designations_prix_manquants.append(designation_info)
                montant_total = Decimal('0')

            # Déterminer la date dans l'année de prévision
            # Garder le même mois que l'année courante
            mois_original = detail.planning.date.month if detail.planning and detail.planning.date else 1
            date_prevision = date(annee, mois_original, 1)

            # Récupérer les infos géographiques
            base_obj = None
            district_obj = None
            commune_obj = None
            ouvrage_obj = None

            # IMPORTANT : Pour les avances, l'ouvrage est dans Planning.ouvrage (pas dans point_eau)
            # Priorité 1 : Ouvrage depuis Planning (pour les avances)
            if detail.planning and detail.planning.ouvrage:
                ouvrage_obj = detail.planning.ouvrage
                # Récupérer base depuis l'ouvrage
                first_base = ouvrage_obj.bases.first()
                if first_base:
                    base_obj = first_base
            # Priorité 2 : Ouvrage depuis point_eau (pour les autres cas)
            elif detail.point_eau and detail.point_eau.ouvrage:
                ouvrage_obj = detail.point_eau.ouvrage

            # Si pas de base encore, essayer depuis l'employé
            if not base_obj and detail.planning and detail.planning.employe and detail.planning.employe.base:
                base_obj = detail.planning.employe.base

            # Récupérer la géographie depuis point_eau (si disponible)
            if detail.point_eau and detail.point_eau.parcelle:
                village = detail.point_eau.parcelle.village
                if village and village.fokontany:
                    fokontany = village.fokontany
                    if fokontany.commune:
                        commune_obj = fokontany.commune
                        if commune_obj.district:
                            district_obj = commune_obj.district

            # Si pas de géo depuis point_eau, essayer depuis l'ouvrage via ses points d'eau
            if not commune_obj and ouvrage_obj:
                from apps.billing.models import PointEau
                premier_pe = PointEau.objects.filter(ouvrage=ouvrage_obj).select_related(
                    'parcelle__village__fokontany__commune__district'
                ).first()
                if premier_pe and premier_pe.parcelle:
                    village = premier_pe.parcelle.village
                    if village and village.fokontany:
                        fokontany = village.fokontany
                        if fokontany.commune:
                            commune_obj = fokontany.commune
                            if commune_obj.district:
                                district_obj = commune_obj.district

            # Type de dépense : Avance (forcé car cette fonction traite uniquement les avances)
            type_depense = 'depense_avance'
            type_display = 'Avance'

            # Récupérer le compte depuis DesignationCompte (première valeur pour cette désignation)
            cat = '421000'  # Compte avances par défaut
            if detail.designation:
                from apps.planning.models import DesignationCompte
                designation_compte = DesignationCompte.objects.filter(
                    designation=detail.designation
                ).select_related('compte').first()
                if designation_compte and designation_compte.compte and designation_compte.compte.compte:
                    cat = designation_compte.compte.compte  # Numéro de compte (ex: "421000")

            # Détail : seulement nom employé (pas de répétition de la désignation)
            detail_text = ""
            if detail.planning and detail.planning.employe:
                detail_text = detail.planning.employe.surnom

            # Calculer quantité et prix unitaire
            quantite_value = Decimal(str(detail.quantity)) if detail.quantity else None
            prix_unitaire_value = None
            if detail.pu and detail.pu > 0:
                prix_unitaire_value = Decimal(str(detail.pu))
            elif detail.designation and detail.designation.prix_unitaire:
                prix_unitaire_value = Decimal(str(detail.designation.prix_unitaire))

            # Créer la prévision
            PrevisionBudget.objects.create(
                date=date_prevision,
                cat=cat,
                libelle=f"{type_display} - {detail.designation.nom}",
                in_amount=Decimal('0'),
                out_amount=montant_total,
                activ=base_obj.nom_base if base_obj else 'GLOBAL',
                detail=detail_text,
                designation=detail.designation.nom if detail.designation else None,
                quantite=quantite_value,
                prix_unitaire=prix_unitaire_value,
                type_prevision=type_depense,
                base=base_obj,
                ouvrage=ouvrage_obj,
                district=district_obj,
                commune=commune_obj,
                annee=annee,
                mois=mois_original,
                est_calculee_auto=True,
                source_calcul=f"PlanningDetail:{detail.id}"
            )
            nb_created += 1

        except Exception as e:
            logger.error(f"Erreur calcul dépense PlanningDetail {detail.id}: {str(e)}")
            continue

    return {
        'nb_created': nb_created,
        'nb_prix_manquants': nb_prix_manquants,
        'designations_prix_manquants': designations_prix_manquants
    }


def calculer_depenses_bons_livraison(annee, base=None, config=None):
    """
    Calcule les dépenses prévues basées sur les BONS DE LIVRAISON de l'année en cours.
    Utilise la table BonLivraison (pas PlanningDetail).
    Reprend les mêmes dépenses de l'année courante en changeant juste l'année.

    Args:
        annee (int): Année de prévision
        base (Base, optional): Base pour filtrer
        config (dict, optional): Configuration additionnelle

    Returns:
        dict: {
            'nb_created': int,
            'nb_prix_manquants': int,
            'designations_prix_manquants': list
        }
    """
    from apps.planning.models import BonLivraison
    from datetime import datetime

    nb_created = 0
    nb_prix_manquants = 0
    designations_prix_manquants = []

    # Année de référence = année en cours
    annee_courante = datetime.now().year

    # Récupérer tous les BonLivraison de l'année courante
    bons_annee_courante = BonLivraison.objects.filter(
        planning__date__year=annee_courante
    ).select_related(
        'designation',
        'planning',
        'planning__ouvrage',  # Ouvrage depuis Planning
        'planning__employe',
        'point_eau__ouvrage',
        'point_eau__parcelle__village__fokontany__commune__district'
    )

    if base:
        # Filtrer par base si spécifié (via employé)
        bons_annee_courante = bons_annee_courante.filter(
            planning__employe__base=base
        )

    logger.info(f"Calcul bons de livraison: {bons_annee_courante.count()} lignes trouvées pour {annee_courante}")

    for bon in bons_annee_courante:
        try:
            # Calculer le montant : quantite * prix_unitaire de la désignation
            if bon.designation and bon.designation.prix_unitaire and bon.quantite:
                prix_unitaire = Decimal(str(bon.designation.prix_unitaire))
                montant_total = prix_unitaire * Decimal(str(bon.quantite))
            else:
                # Aucun prix disponible - signaler
                nb_prix_manquants += 1
                designation_info = f"{bon.designation.nom if bon.designation else 'N/A'} (BonLivraison ID: {bon.id})"
                if designation_info not in designations_prix_manquants:
                    designations_prix_manquants.append(designation_info)
                montant_total = Decimal('0')

            # Déterminer la date dans l'année de prévision
            mois_original = bon.planning.date.month if bon.planning and bon.planning.date else 1
            date_prevision = date(annee, mois_original, 1)

            # Récupérer les infos géographiques
            base_obj = None
            district_obj = None
            commune_obj = None
            ouvrage_obj = None

            # IMPORTANT : Ouvrage depuis Planning (pour bons de livraison)
            if bon.planning and bon.planning.ouvrage:
                ouvrage_obj = bon.planning.ouvrage
                # Récupérer base depuis l'ouvrage
                first_base = ouvrage_obj.bases.first()
                if first_base:
                    base_obj = first_base
            # Fallback : Ouvrage depuis point_eau
            elif bon.point_eau and bon.point_eau.ouvrage:
                ouvrage_obj = bon.point_eau.ouvrage

            # Si pas de base encore, essayer depuis l'employé
            if not base_obj and bon.planning and bon.planning.employe and bon.planning.employe.base:
                base_obj = bon.planning.employe.base

            # Récupérer la géographie depuis point_eau (si disponible)
            if bon.point_eau and bon.point_eau.parcelle:
                village = bon.point_eau.parcelle.village
                if village and village.fokontany:
                    fokontany = village.fokontany
                    if fokontany.commune:
                        commune_obj = fokontany.commune
                        if commune_obj.district:
                            district_obj = commune_obj.district

            # Si pas de géo depuis point_eau, essayer depuis l'ouvrage via ses points d'eau
            if not commune_obj and ouvrage_obj:
                from apps.billing.models import PointEau
                premier_pe = PointEau.objects.filter(ouvrage=ouvrage_obj).select_related(
                    'parcelle__village__fokontany__commune__district'
                ).first()
                if premier_pe and premier_pe.parcelle:
                    village = premier_pe.parcelle.village
                    if village and village.fokontany:
                        fokontany = village.fokontany
                        if fokontany.commune:
                            commune_obj = fokontany.commune
                            if commune_obj.district:
                                district_obj = commune_obj.district

            # Type de dépense : Bon de livraison
            type_depense = 'depense_bon_livraison'
            type_display = 'Bon de livraison'

            # Récupérer le compte depuis DesignationCompte (première valeur pour cette désignation)
            cat = '600000'  # Compte achats par défaut
            if bon.designation:
                from apps.planning.models import DesignationCompte
                designation_compte = DesignationCompte.objects.filter(
                    designation=bon.designation
                ).select_related('compte').first()
                if designation_compte and designation_compte.compte and designation_compte.compte.compte:
                    cat = designation_compte.compte.compte  # Numéro de compte (ex: "600000")

            # Détail : seulement nom employé (pas de répétition de la désignation)
            detail_text = ""
            if bon.planning and bon.planning.employe:
                detail_text = bon.planning.employe.surnom

            # Calculer quantité et prix unitaire
            quantite_value = Decimal(str(bon.quantite)) if bon.quantite else None
            prix_unitaire_value = None
            if bon.designation and bon.designation.prix_unitaire:
                prix_unitaire_value = Decimal(str(bon.designation.prix_unitaire))

            # Créer la prévision
            PrevisionBudget.objects.create(
                date=date_prevision,
                cat=cat,
                libelle=f"{type_display} - {bon.designation.nom}",
                in_amount=Decimal('0'),
                out_amount=montant_total,
                activ=base_obj.nom_base if base_obj else 'GLOBAL',
                detail=detail_text,  # Only employee name, no designation repetition
                designation=bon.designation.nom if bon.designation else None,
                quantite=quantite_value,  # NEW
                prix_unitaire=prix_unitaire_value,  # NEW
                type_prevision=type_depense,
                base=base_obj,
                ouvrage=ouvrage_obj,
                district=district_obj,
                commune=commune_obj,
                annee=annee,
                mois=mois_original,
                est_calculee_auto=True,
                source_calcul=f"BonLivraison:{bon.id}"
            )
            nb_created += 1

        except Exception as e:
            logger.error(f"Erreur calcul dépense BonLivraison {bon.id}: {str(e)}")
            continue

    return {
        'nb_created': nb_created,
        'nb_prix_manquants': nb_prix_manquants,
        'designations_prix_manquants': designations_prix_manquants
    }


def calculer_depenses_indemnites(annee, base=None, config=None):
    """
    Calcule les dépenses prévues pour les indemnités journalières.
    Reprend la logique du workflow indemnités (views_indemnites.py):
    - Une journée terrain = un planning avec ouvrage != bureau de l'employé
    - Montant = poste.tarif_indemnite par jour
    - Basé sur les plannings de l'année en cours, projetés sur l'année cible

    Returns:
        dict: {
            'nb_created': int,
            'nb_jours_terrain': int,
            'employes_concernes': list
        }
    """
    from apps.planning.models import Planning
    from apps.employees.models import Employe
    from apps.organization.models import TypeOuvrage
    from datetime import datetime
    import pytz

    nb_created = 0
    nb_jours_terrain_total = 0
    employes_avec_indemnites = set()

    # Année de référence = année en cours
    annee_courante = datetime.now().year
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer le type "Bureau"
    type_bureau = TypeOuvrage.objects.filter(nom_type_ouvrage__iexact='Bureau').first()

    # Récupérer tous les employés ayant droit aux indemnités
    employes = Employe.objects.filter(
        poste__tarif_indemnite__isnull=False,
        poste__tarif_indemnite__gt=0
    ).select_related('poste', 'base', 'base__ouvrage_correspondant')

    if base:
        employes = employes.filter(base=base)

    for employe in employes:
        tarif_indemnite = employe.poste.tarif_indemnite

        # Récupérer tous les plannings de l'employé pour l'année courante
        plannings = Planning.objects.filter(
            Q(employe=employe) | Q(planning_employees__employee=employe),
            date__year=annee_courante,
            ouvrage__isnull=False
        ).select_related('ouvrage', 'ouvrage__type_ouvrage').distinct().order_by('date')

        # Grouper par jour pour éviter les doublons
        jours_terrain = {}

        for planning in plannings:
            # Convertir en timezone Madagascar
            date_aware = planning.date
            if date_aware.tzinfo:
                date_mg = date_aware.astimezone(tz_madagascar).date()
            else:
                date_mg = date_aware.date()

            # Vérifier si c'est une journée terrain
            est_terrain = True

            # Si c'est un bureau
            if type_bureau and planning.ouvrage.type_ouvrage_id == type_bureau.id:
                # Vérifier si c'est le bureau de l'employé
                if employe.base and employe.base.ouvrage_correspondant_id == planning.ouvrage.id:
                    est_terrain = False  # C'est son propre bureau

            if est_terrain:
                date_str = str(date_mg)
                if date_str not in jours_terrain:
                    jours_terrain[date_str] = {
                        'date': date_mg,
                        'montant': tarif_indemnite
                    }

        # Si l'employé a des jours terrain, créer les prévisions pour l'année cible
        if jours_terrain:
            employes_avec_indemnites.add(employe.id)
            nb_jours = len(jours_terrain)
            nb_jours_terrain_total += nb_jours

            # Calculer le montant mensuel moyen
            montant_total_annee_courante = nb_jours * tarif_indemnite
            montant_moyen_mensuel = montant_total_annee_courante / 12

            # Récupérer la géographie ET l'ouvrage depuis les plannings terrain de l'employé
            district_obj = None
            commune_obj = None
            ouvrage_obj = None

            # Méthode 1 : Essayer depuis les plannings avec ouvrage (qui ont des points d'eau)
            from apps.billing.models import PointEau
            for planning in plannings.filter(ouvrage__isnull=False):
                # Garder le premier ouvrage rencontré
                if not ouvrage_obj:
                    ouvrage_obj = planning.ouvrage

                point_eau = PointEau.objects.filter(
                    ouvrage=planning.ouvrage
                ).select_related(
                    'parcelle__village__fokontany__commune__district'
                ).first()

                if point_eau and point_eau.parcelle:
                    parcelle = point_eau.parcelle
                    if parcelle.village and parcelle.village.fokontany:
                        fokontany = parcelle.village.fokontany
                        if fokontany.commune:
                            commune_obj = fokontany.commune
                            if commune_obj.district:
                                district_obj = commune_obj.district
                            break  # Trouvé, on arrête

            # Méthode 2 : Fallback - utiliser la géographie via l'ouvrage de la base
            if not commune_obj and employe.base and employe.base.ouvrage_correspondant:
                # Garder l'ouvrage de la base si on n'en a pas trouvé
                if not ouvrage_obj:
                    ouvrage_obj = employe.base.ouvrage_correspondant

                # Relation: Base -> ouvrage_correspondant -> PointEau -> Parcelle -> Village -> Fokontany -> Commune -> District
                point_eau_base = PointEau.objects.filter(
                    ouvrage=employe.base.ouvrage_correspondant
                ).select_related(
                    'parcelle__village__fokontany__commune__district'
                ).first()

                if point_eau_base and point_eau_base.parcelle:
                    parcelle = point_eau_base.parcelle
                    if parcelle.village and parcelle.village.fokontany:
                        fokontany = parcelle.village.fokontany
                        if fokontany.commune:
                            commune_obj = fokontany.commune
                            if commune_obj.district:
                                district_obj = commune_obj.district

            # Créer 12 prévisions (une par mois) pour l'année cible
            for mois in range(1, 13):
                try:
                    # Date de prévision = 1er du mois
                    date_prevision = date(annee, mois, 1)

                    # Base et organisation
                    base_obj = employe.base if employe.base else None
                    activ = base_obj.nom_base if base_obj else 'GLOBAL'

                    # Compte indemnités (6415 - Indemnités de mission)
                    cat = '641500'

                    # Libellé clair
                    libelle = f"Indemnités journalières - {employe.nom} {employe.prenom}"

                    # Detail = surnom ou prénom
                    detail_text = employe.surnom if employe.surnom else employe.prenom

                    # Calculer quantité (NOMBRE ENTIER de jours terrain)
                    # Moyenne de jours par mois, arrondie à l'entier le plus proche
                    quantite_jours_mois_exacte = nb_jours / 12
                    quantite_jours_mois = round(quantite_jours_mois_exacte)  # Arrondi mathématique

                    # Si 0 mais il y a des jours terrain, mettre au moins 1
                    if quantite_jours_mois == 0 and nb_jours > 0:
                        quantite_jours_mois = 1

                    # Calculer le prix unitaire AJUSTÉ pour que Quantité × PU = Montant mensuel moyen
                    # Montant mensuel moyen = (nb_jours × tarif) / 12
                    if quantite_jours_mois > 0:
                        prix_unitaire_ajuste = montant_moyen_mensuel / Decimal(str(quantite_jours_mois))
                        # Arrondir à 2 décimales
                        prix_unitaire_ajuste = prix_unitaire_ajuste.quantize(Decimal('0.01'))
                    else:
                        prix_unitaire_ajuste = tarif_indemnite

                    # Le montant reste le montant moyen mensuel (montant exact)
                    montant_mensuel_final = montant_moyen_mensuel

                    PrevisionBudget.objects.create(
                        date=date_prevision,
                        cat=cat,
                        libelle=libelle,
                        in_amount=Decimal('0'),
                        out_amount=montant_mensuel_final,  # Montant mensuel moyen exact
                        activ=activ,
                        detail=detail_text,
                        designation='Indemnité journalière',
                        quantite=Decimal(str(quantite_jours_mois)),  # Nombre ENTIER de jours
                        prix_unitaire=prix_unitaire_ajuste,  # Prix unitaire ajusté
                        type_prevision='depense_indemnites',
                        base=base_obj,
                        ouvrage=ouvrage_obj,    # Ajout ouvrage
                        district=district_obj,  # Ajout district
                        commune=commune_obj,    # Ajout commune
                        annee=annee,
                        mois=mois,
                        est_calculee_auto=True,
                        source_calcul=f"Employe:{employe.id}|JoursTerrain:{nb_jours}"
                    )
                    nb_created += 1

                except Exception as e:
                    logger.error(f"Erreur calcul indemnités {employe.nom} mois {mois}: {str(e)}")
                    continue

    return {
        'nb_created': nb_created,
        'nb_jours_terrain': nb_jours_terrain_total,
        'nb_employes': len(employes_avec_indemnites)
    }


def get_resume_previsions(annee, mois=None, base=None):
    """
    Récupère un résumé des prévisions pour une période donnée.

    Args:
        annee (int): Année
        mois (int, optional): Mois spécifique (1-12)
        base (Base, optional): Filtrer par base

    Returns:
        dict: Résumé avec totaux par type
    """
    queryset = PrevisionBudget.objects.filter(annee=annee)

    if mois:
        queryset = queryset.filter(mois=mois)
    if base:
        queryset = queryset.filter(base=base)

    # Totaux par type
    resume = {
        'recettes_forfaitaires': queryset.filter(
            type_prevision='recette_forfaitaire'
        ).aggregate(total=Sum('in_amount'))['total'] or Decimal('0'),

        'recettes_volumetriques': queryset.filter(
            type_prevision='recette_volumetrique'
        ).aggregate(total=Sum('in_amount'))['total'] or Decimal('0'),

        'recettes_nouveaux_pe': queryset.filter(
            type_prevision='recette_nouveaux_pe'
        ).aggregate(total=Sum('in_amount'))['total'] or Decimal('0'),

        'depenses': queryset.aggregate(total=Sum('out_amount'))['total'] or Decimal('0'),

        'depenses_indemnites': queryset.filter(
            type_prevision='depense_indemnites'
        ).aggregate(total=Sum('out_amount'))['total'] or Decimal('0'),
    }

    # Totaux globaux
    resume['total_recettes'] = (
        resume['recettes_forfaitaires'] +
        resume['recettes_volumetriques'] +
        resume['recettes_nouveaux_pe']
    )

    resume['solde_previsionnel'] = resume['total_recettes'] - resume['depenses']

    return resume


def calculer_previsions_salaires(annee, base=None, config=None):
    """Calcule les previsions de salaires pour l'annee entiere."""
    from apps.employees.models import Employe, GrilleSalaire
    from django.db.models import Q

    nb_created = 0
    nb_employes = 0

    employes_qs = Employe.objects.filter(date_debauchage__isnull=True).select_related('poste', 'poste__compte_salaire', 'base')

    if base:
        employes_qs = employes_qs.filter(base=base)

    for employe in employes_qs:
        # Recuperer la derniere grille de salaire pour cet employe
        derniere_grille = GrilleSalaire.objects.filter(
            contrat__employe=employe
        ).order_by('-date_salaire').first()

        if not derniere_grille or not derniere_grille.salaire_net:
            continue

        salaire_net = derniere_grille.salaire_net or Decimal('0')

        if salaire_net == 0:
            continue

        nb_employes += 1

        # Les salaires/IRSA/charges sociales ne sont PAS des dépenses géographiques
        # Ils doivent rester SANS district/commune (NULL)
        district_obj = None
        commune_obj = None
        ouvrage_obj = None

        for mois in range(1, 13):
            try:
                date_prevision = date(annee, mois, 1)

                base_obj = employe.base if employe.base else None
                activ = base_obj.nom_base if base_obj else 'GLOBAL'

                cat = ''
                if employe.poste and employe.poste.compte_salaire:
                    cat = employe.poste.compte_salaire.compte

                prefixe_poste = employe.poste.prefixe if employe.poste else ''
                libelle = f"{prefixe_poste} {employe.nom} {employe.prenom}_Salaire_{annee} {mois:02d}"

                detail_text = employe.surnom if employe.surnom else employe.prenom

                PrevisionBudget.objects.create(
                    date=date_prevision,
                    cat=cat,
                    libelle=libelle,
                    in_amount=Decimal('0'),
                    out_amount=salaire_net,
                    activ=activ,
                    detail=detail_text,
                    designation='Salaire',
                    quantite=Decimal('1'),
                    prix_unitaire=salaire_net,
                    type_prevision='depense_salaires',
                    base=base_obj,
                    ouvrage=ouvrage_obj,
                    district=district_obj,
                    commune=commune_obj,
                    annee=annee,
                    mois=mois,
                    est_calculee_auto=True,
                    source_calcul=f"Employe:{employe.id}|GrilleSalaire:{derniere_grille.id}"
                )
                nb_created += 1

            except Exception as e:
                logger.error(f"Erreur calcul salaire {employe.nom} mois {mois}: {str(e)}")
                continue

    return {'nb_created': nb_created, 'nb_employes': nb_employes}




def calculer_previsions_irsa(annee, base=None, config=None):
    """Calcule les previsions IRSA pour l'annee entiere."""
    from apps.employees.models import Employe, GrilleSalaire
    from django.db.models import Q

    nb_created = 0
    nb_employes = 0

    employes_qs = Employe.objects.filter(date_debauchage__isnull=True).select_related('poste', 'poste__compte_irsa', 'base')

    if base:
        employes_qs = employes_qs.filter(base=base)

    for employe in employes_qs:
        # Recuperer la derniere grille de salaire pour cet employe
        derniere_grille = GrilleSalaire.objects.filter(
            contrat__employe=employe
        ).order_by('-date_salaire').first()

        if not derniere_grille or not derniere_grille.irsa:
            continue

        irsa = derniere_grille.irsa or Decimal('0')

        if irsa == 0:
            continue

        nb_employes += 1

        # Les salaires/IRSA/charges sociales ne sont PAS des dépenses géographiques
        # Ils doivent rester SANS district/commune (NULL)
        district_obj = None
        commune_obj = None
        ouvrage_obj = None

        for mois in range(1, 13):
            try:
                date_prevision = date(annee, mois, 1)

                base_obj = employe.base if employe.base else None
                activ = employe.volet if employe.volet else (base_obj.nom_base if base_obj else 'GLOBAL')

                cat = ''
                if employe.poste and employe.poste.compte_irsa:
                    cat = employe.poste.compte_irsa.compte

                prefixe_poste = employe.poste.prefixe if employe.poste else ''
                libelle = f"_{prefixe_poste} {employe.nom} {employe.prenom}_IRSA_{annee} {mois:02d}"

                detail_text = employe.surnom if employe.surnom else employe.prenom

                PrevisionBudget.objects.create(
                    date=date_prevision,
                    cat=cat,
                    libelle=libelle,
                    in_amount=Decimal('0'),
                    out_amount=irsa,
                    activ=activ,
                    detail=detail_text,
                    designation='IRSA',
                    quantite=Decimal('1'),
                    prix_unitaire=irsa,
                    type_prevision='depense_irsa',
                    base=base_obj,
                    ouvrage=ouvrage_obj,
                    district=district_obj,
                    commune=commune_obj,
                    annee=annee,
                    mois=mois,
                    est_calculee_auto=True,
                    source_calcul=f"Employe:{employe.id}|GrilleSalaire:{derniere_grille.id}"
                )
                nb_created += 1

            except Exception as e:
                logger.error(f"Erreur calcul IRSA {employe.nom} mois {mois}: {str(e)}")
                continue

    return {'nb_created': nb_created, 'nb_employes': nb_employes}


def calculer_previsions_charges_sociales(annee, base=None, config=None):
    """Calcule les charges sociales trimestrielles (CNAPS, FMFP, Mutuelle)."""
    from apps.employees.models import Salaire

    nb_created = 0
    trimestres = [
        (1, [(annee-1, 10), (annee-1, 11), (annee-1, 12)]),
        (4, [(annee, 1), (annee, 2), (annee, 3)]),
        (7, [(annee, 4), (annee, 5), (annee, 6)]),
        (10, [(annee, 7), (annee, 8), (annee, 9)])
    ]

    for mois_trim, mois_sources in trimestres:
        salaires_sources = Salaire.objects.filter(
            date_paiement__year__in=[annee-1, annee],
            date_paiement__month__in=[m for (a, m) in mois_sources]
        ).select_related('grille_salaire__contrat__employe', 'grille_salaire__contrat__employe__poste', 'grille_salaire__contrat__employe__base')

        if base:
            salaires_sources = salaires_sources.filter(grille_salaire__contrat__employe__base=base)

        employes_data = {}
        for salaire in salaires_sources:
            employe = salaire.grille_salaire.contrat.employe
            emp_id = str(employe.id)

            if emp_id not in employes_data:
                employes_data[emp_id] = {
                    'employe': employe,
                    'cnaps_total': Decimal('0'),
                    'fmfp_total': Decimal('0'),
                    'mutuelle_total': Decimal('0')
                }

            employes_data[emp_id]['cnaps_total'] += salaire.cnaps_paye or Decimal('0')
            employes_data[emp_id]['fmfp_total'] += salaire.fmfp_paye or Decimal('0')
            employes_data[emp_id]['mutuelle_total'] += salaire.mutuelle_sante_paye or Decimal('0')

        date_prevision = date(annee, mois_trim, 1)

        for emp_id, data in employes_data.items():
            employe = data['employe']

            # Les charges sociales ne sont PAS des dépenses géographiques
            # Elles doivent rester SANS district/commune (NULL)
            district_obj = None
            commune_obj = None
            ouvrage_obj = None

            base_obj = employe.base if employe.base else None
            activ = employe.volet if employe.volet else (base_obj.nom_base if base_obj else 'GLOBAL')
            detail_text = employe.surnom if employe.surnom else employe.prenom
            prefixe_poste = employe.poste.prefixe if employe.poste else ''

            if data['cnaps_total'] > 0:
                try:
                    cat_cnaps = ''
                    if employe.poste and hasattr(employe.poste, 'compte_cnaps') and employe.poste.compte_cnaps:
                        cat_cnaps = employe.poste.compte_cnaps.compte

                    PrevisionBudget.objects.create(
                        date=date_prevision,
                        cat=cat_cnaps,
                        libelle=f"_{prefixe_poste} {employe.nom} {employe.prenom}_CNAPS_T{mois_trim//3+1}_{annee}",
                        in_amount=Decimal('0'),
                        out_amount=data['cnaps_total'],
                        activ=activ,
                        detail=detail_text,
                        designation='CNAPS',
                        quantite=Decimal('3'),
                        prix_unitaire=data['cnaps_total'] / Decimal('3'),
                        type_prevision='depense_cnaps',
                        base=base_obj,
                        ouvrage=ouvrage_obj,
                        district=district_obj,
                        commune=commune_obj,
                        annee=annee,
                        mois=mois_trim,
                        est_calculee_auto=True,
                        source_calcul=f"Employe:{employe.id}|Trimestre:{mois_trim}"
                    )
                    nb_created += 1
                except Exception as e:
                    logger.error(f"Erreur CNAPS {employe.nom} trim {mois_trim}: {str(e)}")

            if data['fmfp_total'] > 0:
                try:
                    cat_fmfp = ''
                    if employe.poste and hasattr(employe.poste, 'compte_fmfp') and employe.poste.compte_fmfp:
                        cat_fmfp = employe.poste.compte_fmfp.compte

                    PrevisionBudget.objects.create(
                        date=date_prevision,
                        cat=cat_fmfp,
                        libelle=f"_{prefixe_poste} {employe.nom} {employe.prenom}_FMFP_T{mois_trim//3+1}_{annee}",
                        in_amount=Decimal('0'),
                        out_amount=data['fmfp_total'],
                        activ=activ,
                        detail=detail_text,
                        designation='FMFP',
                        quantite=Decimal('3'),
                        prix_unitaire=data['fmfp_total'] / Decimal('3'),
                        type_prevision='depense_fmfp',
                        base=base_obj,
                        ouvrage=ouvrage_obj,
                        district=district_obj,
                        commune=commune_obj,
                        annee=annee,
                        mois=mois_trim,
                        est_calculee_auto=True,
                        source_calcul=f"Employe:{employe.id}|Trimestre:{mois_trim}"
                    )
                    nb_created += 1
                except Exception as e:
                    logger.error(f"Erreur FMFP {employe.nom} trim {mois_trim}: {str(e)}")

            if data['mutuelle_total'] > 0:
                try:
                    cat_mutuelle = ''
                    if employe.poste and hasattr(employe.poste, 'compte_mutuelle') and employe.poste.compte_mutuelle:
                        cat_mutuelle = employe.poste.compte_mutuelle.compte

                    PrevisionBudget.objects.create(
                        date=date_prevision,
                        cat=cat_mutuelle,
                        libelle=f"_{prefixe_poste} {employe.nom} {employe.prenom}_Mutuelle_{annee} T{mois_trim//3+1}",
                        in_amount=Decimal('0'),
                        out_amount=data['mutuelle_total'],
                        activ=activ,
                        detail=detail_text,
                        designation='Mutuelle Sante',
                        quantite=Decimal('3'),
                        prix_unitaire=data['mutuelle_total'] / Decimal('3'),
                        type_prevision='depense_mutuelle',
                        base=base_obj,
                        ouvrage=ouvrage_obj,
                        district=district_obj,
                        commune=commune_obj,
                        annee=annee,
                        mois=mois_trim,
                        est_calculee_auto=True,
                        source_calcul=f"Employe:{employe.id}|Trimestre:{mois_trim}"
                    )
                    nb_created += 1
                except Exception as e:
                    logger.error(f"Erreur Mutuelle {employe.nom} trim {mois_trim}: {str(e)}")

    return {'nb_created': nb_created}


def calculer_previsions_salaires(annee, base=None, config=None):
    """Calcule les previsions de salaires pour l'annee entiere."""
    from apps.employees.models import Employe, GrilleSalaire
    from django.db.models import Q

    nb_created = 0
    nb_employes = 0

    employes_qs = Employe.objects.filter(date_debauchage__isnull=True).select_related('poste', 'poste__compte_salaire', 'base')

    if base:
        employes_qs = employes_qs.filter(base=base)

    for employe in employes_qs:
        # Recuperer la derniere grille de salaire pour cet employe
        derniere_grille = GrilleSalaire.objects.filter(
            contrat__employe=employe
        ).order_by('-date_salaire').first()

        if not derniere_grille or not derniere_grille.salaire_net:
            continue

        salaire_net = derniere_grille.salaire_net or Decimal('0')

        if salaire_net == 0:
            continue

        nb_employes += 1

        # Les salaires/IRSA/charges sociales ne sont PAS des dépenses géographiques
        # Ils doivent rester SANS district/commune (NULL)
        district_obj = None
        commune_obj = None
        ouvrage_obj = None

        for mois in range(1, 13):
            try:
                date_prevision = date(annee, mois, 1)

                base_obj = employe.base if employe.base else None
                activ = base_obj.nom_base if base_obj else 'GLOBAL'

                cat = ''
                if employe.poste and employe.poste.compte_salaire:
                    cat = employe.poste.compte_salaire.compte

                prefixe_poste = employe.poste.prefixe if employe.poste else ''
                libelle = f"{prefixe_poste} {employe.nom} {employe.prenom}_Salaire_{annee} {mois:02d}"

                detail_text = employe.surnom if employe.surnom else employe.prenom

                PrevisionBudget.objects.create(
                    date=date_prevision,
                    cat=cat,
                    libelle=libelle,
                    in_amount=Decimal('0'),
                    out_amount=salaire_net,
                    activ=activ,
                    detail=detail_text,
                    designation='Salaire',
                    quantite=Decimal('1'),
                    prix_unitaire=salaire_net,
                    type_prevision='depense_salaires',
                    base=base_obj,
                    ouvrage=ouvrage_obj,
                    district=district_obj,
                    commune=commune_obj,
                    annee=annee,
                    mois=mois,
                    est_calculee_auto=True,
                    source_calcul=f"Employe:{employe.id}|GrilleSalaire:{derniere_grille.id}"
                )
                nb_created += 1

            except Exception as e:
                logger.error(f"Erreur calcul salaire {employe.nom} mois {mois}: {str(e)}")
                continue

    return {'nb_created': nb_created, 'nb_employes': nb_employes}




def calculer_previsions_irsa(annee, base=None, config=None):
    """Calcule les previsions IRSA pour l'annee entiere."""
    from apps.employees.models import Employe, GrilleSalaire
    from django.db.models import Q

    nb_created = 0
    nb_employes = 0

    employes_qs = Employe.objects.filter(date_debauchage__isnull=True).select_related('poste', 'poste__compte_irsa', 'base')

    if base:
        employes_qs = employes_qs.filter(base=base)

    for employe in employes_qs:
        # Recuperer la derniere grille de salaire pour cet employe
        derniere_grille = GrilleSalaire.objects.filter(
            contrat__employe=employe
        ).order_by('-date_salaire').first()

        if not derniere_grille or not derniere_grille.irsa:
            continue

        irsa = derniere_grille.irsa or Decimal('0')

        if irsa == 0:
            continue

        nb_employes += 1

        # Les salaires/IRSA/charges sociales ne sont PAS des dépenses géographiques
        # Ils doivent rester SANS district/commune (NULL)
        district_obj = None
        commune_obj = None
        ouvrage_obj = None

        for mois in range(1, 13):
            try:
                date_prevision = date(annee, mois, 1)

                base_obj = employe.base if employe.base else None
                activ = employe.volet if employe.volet else (base_obj.nom_base if base_obj else 'GLOBAL')

                cat = ''
                if employe.poste and employe.poste.compte_irsa:
                    cat = employe.poste.compte_irsa.compte

                prefixe_poste = employe.poste.prefixe if employe.poste else ''
                libelle = f"_{prefixe_poste} {employe.nom} {employe.prenom}_IRSA_{annee} {mois:02d}"

                detail_text = employe.surnom if employe.surnom else employe.prenom

                PrevisionBudget.objects.create(
                    date=date_prevision,
                    cat=cat,
                    libelle=libelle,
                    in_amount=Decimal('0'),
                    out_amount=irsa,
                    activ=activ,
                    detail=detail_text,
                    designation='IRSA',
                    quantite=Decimal('1'),
                    prix_unitaire=irsa,
                    type_prevision='depense_irsa',
                    base=base_obj,
                    ouvrage=ouvrage_obj,
                    district=district_obj,
                    commune=commune_obj,
                    annee=annee,
                    mois=mois,
                    est_calculee_auto=True,
                    source_calcul=f"Employe:{employe.id}|GrilleSalaire:{derniere_grille.id}"
                )
                nb_created += 1

            except Exception as e:
                logger.error(f"Erreur calcul IRSA {employe.nom} mois {mois}: {str(e)}")
                continue

    return {'nb_created': nb_created, 'nb_employes': nb_employes}


def calculer_previsions_charges_sociales(annee, base=None, config=None):
    """Calcule les charges sociales trimestrielles (CNAPS, FMFP, Mutuelle)."""
    from apps.employees.models import Salaire

    nb_created = 0
    trimestres = [
        (1, [(annee-1, 10), (annee-1, 11), (annee-1, 12)]),
        (4, [(annee, 1), (annee, 2), (annee, 3)]),
        (7, [(annee, 4), (annee, 5), (annee, 6)]),
        (10, [(annee, 7), (annee, 8), (annee, 9)])
    ]

    for mois_trim, mois_sources in trimestres:
        salaires_sources = Salaire.objects.filter(
            date_paiement__year__in=[annee-1, annee],
            date_paiement__month__in=[m for (a, m) in mois_sources]
        ).select_related('grille_salaire__contrat__employe', 'grille_salaire__contrat__employe__poste', 'grille_salaire__contrat__employe__base')

        if base:
            salaires_sources = salaires_sources.filter(grille_salaire__contrat__employe__base=base)

        employes_data = {}
        for salaire in salaires_sources:
            employe = salaire.grille_salaire.contrat.employe
            emp_id = str(employe.id)

            if emp_id not in employes_data:
                employes_data[emp_id] = {
                    'employe': employe,
                    'cnaps_total': Decimal('0'),
                    'fmfp_total': Decimal('0'),
                    'mutuelle_total': Decimal('0')
                }

            employes_data[emp_id]['cnaps_total'] += salaire.cnaps_paye or Decimal('0')
            employes_data[emp_id]['fmfp_total'] += salaire.fmfp_paye or Decimal('0')
            employes_data[emp_id]['mutuelle_total'] += salaire.mutuelle_sante_paye or Decimal('0')

        date_prevision = date(annee, mois_trim, 1)

        for emp_id, data in employes_data.items():
            employe = data['employe']

            # Les charges sociales ne sont PAS des dépenses géographiques
            # Elles doivent rester SANS district/commune (NULL)
            district_obj = None
            commune_obj = None
            ouvrage_obj = None

            base_obj = employe.base if employe.base else None
            activ = employe.volet if employe.volet else (base_obj.nom_base if base_obj else 'GLOBAL')
            detail_text = employe.surnom if employe.surnom else employe.prenom
            prefixe_poste = employe.poste.prefixe if employe.poste else ''

            if data['cnaps_total'] > 0:
                try:
                    cat_cnaps = ''
                    if employe.poste and hasattr(employe.poste, 'compte_cnaps') and employe.poste.compte_cnaps:
                        cat_cnaps = employe.poste.compte_cnaps.compte

                    PrevisionBudget.objects.create(
                        date=date_prevision,
                        cat=cat_cnaps,
                        libelle=f"_{prefixe_poste} {employe.nom} {employe.prenom}_CNAPS_T{mois_trim//3+1}_{annee}",
                        in_amount=Decimal('0'),
                        out_amount=data['cnaps_total'],
                        activ=activ,
                        detail=detail_text,
                        designation='CNAPS',
                        quantite=Decimal('3'),
                        prix_unitaire=data['cnaps_total'] / Decimal('3'),
                        type_prevision='depense_cnaps',
                        base=base_obj,
                        ouvrage=ouvrage_obj,
                        district=district_obj,
                        commune=commune_obj,
                        annee=annee,
                        mois=mois_trim,
                        est_calculee_auto=True,
                        source_calcul=f"Employe:{employe.id}|Trimestre:{mois_trim}"
                    )
                    nb_created += 1
                except Exception as e:
                    logger.error(f"Erreur CNAPS {employe.nom} trim {mois_trim}: {str(e)}")

            if data['fmfp_total'] > 0:
                try:
                    cat_fmfp = ''
                    if employe.poste and hasattr(employe.poste, 'compte_fmfp') and employe.poste.compte_fmfp:
                        cat_fmfp = employe.poste.compte_fmfp.compte

                    PrevisionBudget.objects.create(
                        date=date_prevision,
                        cat=cat_fmfp,
                        libelle=f"_{prefixe_poste} {employe.nom} {employe.prenom}_FMFP_T{mois_trim//3+1}_{annee}",
                        in_amount=Decimal('0'),
                        out_amount=data['fmfp_total'],
                        activ=activ,
                        detail=detail_text,
                        designation='FMFP',
                        quantite=Decimal('3'),
                        prix_unitaire=data['fmfp_total'] / Decimal('3'),
                        type_prevision='depense_fmfp',
                        base=base_obj,
                        ouvrage=ouvrage_obj,
                        district=district_obj,
                        commune=commune_obj,
                        annee=annee,
                        mois=mois_trim,
                        est_calculee_auto=True,
                        source_calcul=f"Employe:{employe.id}|Trimestre:{mois_trim}"
                    )
                    nb_created += 1
                except Exception as e:
                    logger.error(f"Erreur FMFP {employe.nom} trim {mois_trim}: {str(e)}")

            if data['mutuelle_total'] > 0:
                try:
                    cat_mutuelle = ''
                    if employe.poste and hasattr(employe.poste, 'compte_mutuelle') and employe.poste.compte_mutuelle:
                        cat_mutuelle = employe.poste.compte_mutuelle.compte

                    PrevisionBudget.objects.create(
                        date=date_prevision,
                        cat=cat_mutuelle,
                        libelle=f"_{prefixe_poste} {employe.nom} {employe.prenom}_Mutuelle_{annee} T{mois_trim//3+1}",
                        in_amount=Decimal('0'),
                        out_amount=data['mutuelle_total'],
                        activ=activ,
                        detail=detail_text,
                        designation='Mutuelle Sante',
                        quantite=Decimal('3'),
                        prix_unitaire=data['mutuelle_total'] / Decimal('3'),
                        type_prevision='depense_mutuelle',
                        base=base_obj,
                        ouvrage=ouvrage_obj,
                        district=district_obj,
                        commune=commune_obj,
                        annee=annee,
                        mois=mois_trim,
                        est_calculee_auto=True,
                        source_calcul=f"Employe:{employe.id}|Trimestre:{mois_trim}"
                    )
                    nb_created += 1
                except Exception as e:
                    logger.error(f"Erreur Mutuelle {employe.nom} trim {mois_trim}: {str(e)}")

    return {'nb_created': nb_created}


def calculer_previsions_loyers(annee, base=None, config=None):
    """
    Calcule les prévisions de loyers (compte 613100) pour l'année.

    Méthode:
    1. Récupère tous les loyers dans BaseDiameX (compte 613100)
    2. Groupe par motif (bénéficiaire + lieu)
    3. Calcule la fréquence basée sur l'intervalle entre paiements
    4. Extrapole pour l'année de prévision

    Returns:
        dict: Statistiques du calcul
    """
    from apps.accounting.models import BaseDiameX
    from collections import defaultdict
    from datetime import timedelta
    import re

    nb_created = 0
    patterns_detectes = []

    def extraire_beneficiaire_et_lieu(description):
        """Extrait le bénéficiaire et le lieu depuis la description du loyer"""
        if not description:
            return "Sans description", None, None, None, []

        # Pattern: ISI PREST_{Beneficiaire}_{Details}_Mois_{Montant}_x {N} {Mois...}
        match = re.search(
            r'ISI PREST_([^_]+)_([^_]+)_(?:Mois|Journ[ée]+|Fft)_([0-9 ]+)_?\s*x?\s*(\d+)?\s*((?:\d{4}\s+\d{2}\s*)+)?',
            description
        )

        if match:
            beneficiaire = match.group(1).strip()
            details = match.group(2).strip()
            montant_str = match.group(3).replace(' ', '').replace('Ar', '')
            nb_mois_str = match.group(4)

            try:
                montant_unitaire = float(montant_str)
            except:
                montant_unitaire = None

            try:
                nb_mois_couverts = int(nb_mois_str) if nb_mois_str else 1
            except:
                nb_mois_couverts = 1

            motif = f"{beneficiaire} - {details}"
            return motif, beneficiaire, montant_unitaire, nb_mois_couverts, []
        else:
            return description[:50], None, None, None, []

    try:
        # Récupérer tous les loyers compte 613100
        loyers = BaseDiameX.objects.filter(
            compte_code='613100'
        ).exclude(
            montant_out__isnull=True
        ).exclude(
            montant_out=0
        ).order_by('date_m')

        # Grouper par motif (bénéficiaire + lieu)
        groupes = defaultdict(list)
        for loyer in loyers:
            motif, beneficiaire, montant_unit, nb_mois, _ = extraire_beneficiaire_et_lieu(loyer.description)

            groupes[motif].append({
                'date': loyer.date_m,
                'montant_total': float(loyer.montant_out),
                'montant_unitaire': montant_unit,
                'nb_mois_couverts': nb_mois,
                'pers': loyer.pers,
                'description_originale': loyer.description,
                'beneficiaire': beneficiaire
            })

        logger.info(f"[LOG] Loyers - {len(groupes)} motifs detectes, {loyers.count()} transactions")

        # Analyser chaque groupe et créer les prévisions
        for motif, transactions in groupes.items():
            # Trier par date
            transactions_triees = sorted(transactions, key=lambda x: x['date'])

            # Déterminer la fréquence
            if len(transactions_triees) >= 2:
                # Calculer l'intervalle moyen
                intervalles = []
                for i in range(1, len(transactions_triees)):
                    delta = (transactions_triees[i]['date'] - transactions_triees[i-1]['date']).days
                    intervalles.append(delta)

                moyenne_jours = sum(intervalles) / len(intervalles)

                # Classifier la fréquence
                if 25 <= moyenne_jours <= 35:
                    frequence = "MENSUEL"
                    nb_paiements_an = 12
                    nb_mois_par_paiement = 1
                elif 55 <= moyenne_jours <= 70:
                    frequence = "BIMENSUEL"
                    nb_paiements_an = 6
                    nb_mois_par_paiement = 2
                elif 85 <= moyenne_jours <= 100:
                    frequence = "TRIMESTRIEL"
                    nb_paiements_an = 4
                    nb_mois_par_paiement = 3
                else:
                    # Irrégulier - estimer
                    nb_paiements_an = max(1, round(365 / moyenne_jours))
                    frequence = "IRREGULIER"
                    # Calculer nb mois moyen
                    nb_mois_hist = [t['nb_mois_couverts'] for t in transactions_triees if t['nb_mois_couverts']]
                    nb_mois_par_paiement = round(sum(nb_mois_hist) / len(nb_mois_hist)) if nb_mois_hist else 1

                # Calculer montant unitaire moyen
                montants_unit = [t['montant_unitaire'] for t in transactions_triees if t['montant_unitaire']]
                if montants_unit:
                    montant_unitaire_moyen = sum(montants_unit) / len(montants_unit)
                else:
                    montant_unitaire_moyen = sum([t['montant_total'] / max(t['nb_mois_couverts'], 1)
                                                  for t in transactions_triees]) / len(transactions_triees)

                # Date du dernier paiement
                derniere_date = transactions_triees[-1]['date']

            else:
                # Un seul paiement - supposer trimestriel par défaut
                trans = transactions_triees[0]
                frequence = "SUPPOSE_TRIMESTRIEL"
                nb_paiements_an = 4
                nb_mois_par_paiement = trans['nb_mois_couverts'] or 3
                montant_unitaire_moyen = trans['montant_unitaire'] or (trans['montant_total'] / max(trans['nb_mois_couverts'], 1))
                derniere_date = trans['date']
                moyenne_jours = 90

            # Calculer montant par paiement
            montant_par_paiement = montant_unitaire_moyen * nb_mois_par_paiement

            # Créer les prévisions pour l'année
            # Partir du dernier paiement + intervalle moyen
            date_suivante = derniere_date + timedelta(days=int(moyenne_jours))

            mois_deja_crees = set()  # Pour éviter les doublons

            for i in range(nb_paiements_an + 2):  # +2 pour être sûr de couvrir toute l'année
                # Vérifier que la date est dans l'année de prévision
                if date_suivante.year == annee:
                    mois_prevision = date_suivante.month

                    # Éviter les doublons
                    if mois_prevision not in mois_deja_crees:
                        try:
                            # Créer la prévision
                            PrevisionBudget.objects.create(
                                cat='613100',  # Compte loyers
                                libelle=f"Loyer {motif}",
                                detail=f"{frequence} ({nb_mois_par_paiement} mois)",
                                date=date(annee, mois_prevision, 1),
                                in_amount=Decimal('0'),
                                out_amount=Decimal(str(montant_par_paiement)),
                                type_prevision='depense_loyer',
                                base=base,
                                annee=annee,
                                mois=mois_prevision,
                                est_calculee_auto=True,
                                source_calcul=f"BaseDiameX|613100|{motif}|{frequence}"
                            )
                            nb_created += 1
                            mois_deja_crees.add(mois_prevision)

                            logger.info(f"[LOG] Loyer cree: {motif} - {date_suivante} - {montant_par_paiement:,.0f} Ar")
                        except Exception as e:
                            logger.error(f"[ERROR] Loyer {motif} mois {mois_prevision}: {str(e)}")

                elif date_suivante.year > annee:
                    # Dépassé l'année de prévision
                    break

                # Prochaine date
                date_suivante = date_suivante + timedelta(days=int(moyenne_jours))

            patterns_detectes.append({
                'motif': motif,
                'frequence': frequence,
                'nb_paiements_an': nb_paiements_an,
                'montant_unitaire': montant_unitaire_moyen,
                'montant_par_paiement': montant_par_paiement
            })

        logger.info(f"[LOG] Loyers - {nb_created} previsions creees")

    except Exception as e:
        logger.error(f"[ERROR] Calcul loyers: {str(e)}")

    return {
        'nb_created': nb_created,
        'patterns_detectes': patterns_detectes
    }


def calculer_previsions_depenses_recurrentes(annee, base=None, config=None):
    """
    Calcule les prévisions pour les dépenses récurrentes en extrapolant
    les transactions du dernier mois connu pour chaque compte.

    Comptes concernés:
    - 602, 606, 615: Achats/services
    - 623100: Publicité
    - 626222: Téléphone
    - 626320: Internet mobile
    - 626321: Internet fixe
    - 627203: Frais bancaires
    - 627204: Frais MVola/transferts
    - 631104: IRI (impôts)

    Méthode:
    1. Pour chaque compte, récupère les transactions du dernier mois connu
    2. Répète ces transactions pour tous les mois de l'année de prévision

    Returns:
        dict: Statistiques du calcul avec détails par compte
    """
    from apps.accounting.models import BaseDiameX
    from django.db.models import Max
    from datetime import date

    nb_created = 0
    details_par_compte = {}

    # Liste des comptes à traiter
    comptes_recurrents = [
        ('602', 'Achats stockés'),
        ('606', 'Achats non stockés'),
        ('615', 'Entretien et réparations'),
        ('623100', 'Publicité'),
        ('626222', 'Téléphone'),
        ('626320', 'Internet mobile'),
        ('626321', 'Internet fixe'),
        ('627203', 'Frais bancaires'),
        ('627204', 'Frais MVola/transferts'),
        ('631104', 'IRI'),
    ]

    try:
        for compte_code, libelle_compte in comptes_recurrents:
            nb_created_compte = 0

            # Récupérer toutes les transactions de ce compte
            transactions = BaseDiameX.objects.filter(
                compte_code=compte_code
            ).exclude(
                montant_out__isnull=True
            ).exclude(
                montant_out=0
            )

            if transactions.count() == 0:
                logger.info(f"[LOG] Depenses recurrentes - Compte {compte_code}: Aucune transaction")
                continue

            # Trouver le dernier mois connu
            derniere_date = transactions.aggregate(Max('date_m'))['date_m__max']

            if not derniere_date:
                continue

            # Récupérer les transactions du dernier mois
            transactions_dernier_mois = transactions.filter(
                date_m__month=derniere_date.month,
                date_m__year=derniere_date.year
            )

            nb_trans_dernier_mois = transactions_dernier_mois.count()

            if nb_trans_dernier_mois == 0:
                logger.info(f"[LOG] Depenses recurrentes - Compte {compte_code}: Aucune transaction dans dernier mois {derniere_date.strftime('%Y-%m')}")
                continue

            logger.info(f"[LOG] Depenses recurrentes - Compte {compte_code}: {nb_trans_dernier_mois} transaction(s) dans {derniere_date.strftime('%Y-%m')}")

            # Pour chaque mois de l'année de prévision
            for mois in range(1, 13):
                # Pour chaque transaction du dernier mois, créer une prévision
                for idx, trans in enumerate(transactions_dernier_mois, start=1):
                    try:
                        # Extraire description courte (sans les détails de dates)
                        description = trans.description if trans.description else f"{libelle_compte}"
                        # Limiter à 100 caractères
                        if len(description) > 100:
                            description = description[:97] + "..."

                        PrevisionBudget.objects.create(
                            cat=compte_code,
                            libelle=libelle_compte,
                            detail=description,
                            date=date(annee, mois, 1),
                            in_amount=Decimal('0'),
                            out_amount=Decimal(str(trans.montant_out)),
                            type_prevision='depense_recurrente',
                            base=base,
                            annee=annee,
                            mois=mois,
                            est_calculee_auto=True,
                            source_calcul=f"BaseDiameX|{compte_code}|{derniere_date.strftime('%Y-%m')}|T{idx}"
                        )
                        nb_created += 1
                        nb_created_compte += 1

                    except Exception as e:
                        logger.error(f"[ERROR] Depense recurrente {compte_code} mois {mois} transaction {idx}: {str(e)}")

            details_par_compte[compte_code] = {
                'libelle': libelle_compte,
                'dernier_mois': derniere_date.strftime('%Y-%m'),
                'nb_transactions_source': nb_trans_dernier_mois,
                'nb_previsions_creees': nb_created_compte
            }

            logger.info(f"[LOG] Depenses recurrentes - Compte {compte_code}: {nb_created_compte} previsions creees (base: {nb_trans_dernier_mois} trans x 12 mois)")

        logger.info(f"[LOG] Depenses recurrentes - TOTAL: {nb_created} previsions creees")

    except Exception as e:
        logger.error(f"[ERROR] Calcul depenses recurrentes: {str(e)}")

    return {
        'nb_created': nb_created,
        'details_par_compte': details_par_compte
    }
