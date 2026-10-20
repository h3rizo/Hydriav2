"""
Vues pour l'analyse croisée des paiements employés (matrice employé × mois × type)
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Q, Count, Value
from django.db.models.functions import Concat
from datetime import datetime
from apps.accounting.models import BaseDiameX
from apps.employees.models import Employe, Contrat
from apps.organization.models import Compte
from .views_verification_paiements import (
    extraire_info_description,
    _filter_employes_by_scope,
    _filter_comptes_by_scope,
    _filter_diamex_by_scope,
)


def _get_mois_croise_entry(entry, info):
    """
    Retourne le mois effectif d'une ecriture pour l'analyse croisee.
    Priorite au mois extrait de la description, sinon fallback sur date_m.
    """
    mois = info.get('mois') if info else None
    if mois:
        return mois
    return entry.date_m.month if getattr(entry, 'date_m', None) else None


def _get_annee_croise_entry(entry, info):
    """
    Retourne l'annee effective d'une ecriture pour l'analyse croisee.
    Priorite a l'annee extraite de la description, sinon fallback sur date_m.
    """
    annee = info.get('annee') if info else None
    if annee:
        return annee
    return entry.date_m.year if getattr(entry, 'date_m', None) else None


@login_required
def verification_paiements_croisee(request):
    """
    Page d'analyse croisée : Employés × Mois × Types de paiement
    """
    # Années disponibles
    comptes_employes = list(_filter_comptes_by_scope(
        Compte.objects.filter(employe_obligatoire=True),
        request.user
    ).values_list('compte', flat=True))
    annees_disponibles = _filter_diamex_by_scope(
        BaseDiameX.objects.filter(compte_code__in=comptes_employes),
        request.user
    ).dates('date_m', 'year', order='DESC')
    annees = [date.year for date in annees_disponibles]
    if not annees:
        annees = [datetime.now().year]

    # Année sélectionnée
    annee_selectionnee = request.GET.get('annee', str(datetime.now().year))

    # Liste des employés actifs ou ayant été actifs pendant l'année
    # Récupérer les employés ayant un contrat actif ou ayant été actif pendant l'année
    employes_ids = Contrat.objects.filter(
        Q(fin_contrat__isnull=True) |  # Contrat toujours actif
        Q(fin_contrat__year__gte=int(annee_selectionnee)) |  # Contrat actif pendant l'année
        Q(debut_contrat__year__lte=int(annee_selectionnee))  # Contrat commencé avant/pendant l'année
    ).values_list('employe_id', flat=True).distinct()

    employes = _filter_employes_by_scope(
        Employe.objects.filter(id__in=employes_ids),
        request.user
    ).order_by('surnom')

    context = {
        'annees': annees,
        'annee_selectionnee': annee_selectionnee,
        'employes': employes,
    }

    return render(request, 'employees/verification_paiements_croisee.html', context)


@login_required
def api_verification_paiements_croisee(request):
    """
    API pour récupérer les données de la matrice croisée
    Retourne : {
        employe_id: {
            'surnom': str,
            'prefixe': str,
            'actif': bool,
            'mois': {
                '1': {'salaire': 1, 'irsa': 1, ...},
                '2': {...},
                ...
            },
            'moyennes': {'salaire': 0.5, 'irsa': 0.92, ...},
            'anomalies': {'salaire': 2, 'irsa': 0, ...}  # Nombre de mois avec >1 paiement
        },
        'statistiques': {
            'total_employes': int,
            'employes_actifs': int,
            'employes_inactifs': int,
            'anomalies_par_type': {'salaire': 15, 'irsa': 3, ...},  # Total anomalies par type
            'employes_avec_anomalies': 12  # Nombre d'employés avec au moins une anomalie
        }
    }
    """
    # Filtres
    annee = request.GET.get('annee', str(datetime.now().year))
    annee_int = int(annee)
    employe_id_filtre = request.GET.get('employe_id')  # Nouveau filtre
    statut_filtre = request.GET.get('statut')  # 'actif', 'inactif', 'all'

    # Récupérer les comptes employés
    comptes_employes = list(_filter_comptes_by_scope(
        Compte.objects.filter(employe_obligatoire=True),
        request.user
    ).values_list('compte', flat=True))

    # Initialiser tous les employés actifs dans l'année
    employes_query = Contrat.objects.filter(
        Q(fin_contrat__isnull=True) |  # Contrat toujours actif
        Q(fin_contrat__year__gte=annee_int) |  # Actif pendant l'année
        Q(debut_contrat__year__lte=annee_int)  # Commencé avant/pendant l'année
    ).values_list('employe_id', flat=True).distinct()

    # Filtre par employé spécifique
    if employe_id_filtre:
        employes = _filter_employes_by_scope(
            Employe.objects.filter(id=employe_id_filtre),
            request.user
        ).select_related('poste')
    else:
        employes = _filter_employes_by_scope(
            Employe.objects.filter(id__in=employes_query),
            request.user
        ).select_related('poste')

    employes_scope = _filter_employes_by_scope(Employe.objects.all(), request.user)

    # Filtre par statut actif/inactif
    if statut_filtre == 'actif':
        employes = employes.filter(date_debauchage__isnull=True)
    elif statut_filtre == 'inactif':
        employes = employes.filter(date_debauchage__isnull=False)

    # Initialiser tous les employés dans les résultats
    resultats = {}
    for employe in employes:
        employe_id = str(employe.id)
        resultats[employe_id] = {
            'surnom': employe.surnom,
            'nom_complet': f"{employe.prenom} {employe.nom}",
            'prefixe': employe.poste.prefixe if employe.poste else '',
            'actif': employe.date_debauchage is None,
            'base_id': str(employe.base.id) if employe.base else None,
            'base_nom': employe.base.nom_base if employe.base else 'Sans base',
            'mois': {},
            'totaux': {},
        }

    # Filtrer une fenêtre autour de l'année demandée pour récupérer les paiements
    # comptabilisés juste avant/après mais rattachés à l'année du libellé.
    query = _filter_diamex_by_scope(BaseDiameX.objects.filter(
        compte_code__in=comptes_employes,
        date_m__year__gte=annee_int - 1,
        date_m__year__lte=annee_int + 1
    ), request.user).exclude(
        description__isnull=True
    ).exclude(
        description=''
    )

    # Analyser chaque transaction
    for entry in query:
        # Extraire infos de la description
        info = extraire_info_description(entry.description)

        # Chercher l'employé - AMÉLIORÉ avec préfixe ET recherche par nom complet
        employe_obj = None
        if info['nom_employe']:
            # 1. Tentative avec surnom exact
            employe_obj = employes_scope.filter(surnom__iexact=info['nom_employe']).first()

            # 2. Tentative avec nom complet partiel (Prénom + Nom) - permet prénoms incomplets
            if not employe_obj:
                employe_obj = employes_scope.annotate(
                    nom_concat=Concat('prenom', Value(' '), 'nom')
                ).filter(nom_concat__icontains=info['nom_employe']).first()

            # 3. CRITIQUE: Tentative avec nom complet inversé (Nom + Prénom) - Format DiameX
            if not employe_obj:
                employe_obj = employes_scope.annotate(
                    nom_inv=Concat('nom', Value(' '), 'prenom')
                ).filter(nom_inv__icontains=info['nom_employe']).first()

            # 4. Si préfixe disponible, chercher avec préfixe + nom/prenom/surnom
            if not employe_obj and info['prefixe']:
                employe_obj = employes_scope.filter(
                    poste__prefixe=info['prefixe']
                ).filter(
                    Q(surnom__icontains=info['nom_employe']) |
                    Q(nom__icontains=info['nom_employe']) |
                    Q(prenom__icontains=info['nom_employe'])
                ).first()

            # 5. Fallback : chercher par nom/prénom en inversant l'ordre (NOM d'abord)
            if not employe_obj:
                nom_parts = info['nom_employe'].split()
                if len(nom_parts) >= 2:
                    # Essayer d'abord avec seulement les 2 premiers mots (ex: "FENOMANANA Syressi")
                    # Car parfois il y a un surnom en 3ème position (ex: "FENOMANANA Syressi Tilamb")
                    employe_obj = employes_scope.filter(
                        Q(nom__icontains=nom_parts[0]) & Q(prenom__icontains=nom_parts[1])
                    ).first()

                    # Si pas trouvé avec 2 mots, essayer avec tous les mots
                    if not employe_obj and len(nom_parts) > 2:
                        employe_obj = employes_scope.filter(
                            Q(nom__icontains=nom_parts[0]) & Q(prenom__icontains=' '.join(nom_parts[1:]))
                        ).first()

            # 6. Dernier fallback : recherche large
            if not employe_obj:
                employe_obj = employes_scope.filter(
                    Q(surnom__icontains=info['nom_employe']) |
                    Q(nom__icontains=info['nom_employe']) |
                    Q(prenom__icontains=info['nom_employe'])
                ).first()

        if not employe_obj:
            continue

        # Vérifier que l'employé est dans notre liste (actif pendant l'année)
        employe_id = str(employe_obj.id)
        if employe_id not in resultats:
            continue

        # Type de paiement groupé - passer la description complète pour distinction fine
        type_groupe = mapper_type_groupe(info['type_paiement'], entry.description)
        if not type_groupe:
            continue

        annee_effective = _get_annee_croise_entry(entry, info)
        if annee_effective != annee_int:
            continue

        # CRITIQUE: Utiliser le mois de la description (ex: "Salaire_2025 07") au lieu de date_m
        # Car un paiement peut être enregistré en août mais concerner juillet
        mois = _get_mois_croise_entry(entry, info)
        if not mois:
            continue

        # Initialiser le mois si pas encore fait
        if str(mois) not in resultats[employe_id]['mois']:
            resultats[employe_id]['mois'][str(mois)] = {}

        # Incrémenter le compteur pour ce type et ce mois
        if type_groupe not in resultats[employe_id]['mois'][str(mois)]:
            resultats[employe_id]['mois'][str(mois)][type_groupe] = 0

        resultats[employe_id]['mois'][str(mois)][type_groupe] += 1

        # Incrémenter le total pour ce type
        if type_groupe not in resultats[employe_id]['totaux']:
            resultats[employe_id]['totaux'][type_groupe] = 0
        resultats[employe_id]['totaux'][type_groupe] += 1

    # Calculer les moyennes et anomalies par type pour chaque employé
    types_a_suivre = [
        'salaire', 'ajustement_salaire', 'prime', 'solde_tout_compte',
        'allocation_terrain', 'indemnite_compensatrice',
        'irsa', 'cnaps', 'fmfp', 'mutuelle_sante',
        'frais_medicaux', 'frais_scolarite',
        'indemnite_terrain', 'indemnite_hors_zone', 'indemnite_stage', 'frais_deplacement'
    ]

    # Statistiques globales
    stats_anomalies_par_type = {}
    employes_avec_anomalies = set()
    total_employes = len(resultats)
    employes_actifs = sum(1 for data in resultats.values() if data['actif'])
    employes_inactifs = total_employes - employes_actifs

    for employe_id, data in resultats.items():
        data['moyennes'] = {}
        data['anomalies'] = {}  # Nouveau : nombre de mois avec >1 paiement par type

        nb_mois_actifs = len(data['mois']) if len(data['mois']) > 0 else 12  # Si pas de mois, utiliser 12 pour moyenne

        for type_groupe in types_a_suivre:
            total = data['totaux'].get(type_groupe, 0)
            data['moyennes'][type_groupe] = round(total / nb_mois_actifs, 2) if nb_mois_actifs > 0 else 0

            # Compter les anomalies (mois avec >1 paiement)
            nb_anomalies = 0
            for mois_data in data['mois'].values():
                count = mois_data.get(type_groupe, 0)
                if count > 1:
                    nb_anomalies += 1

            data['anomalies'][type_groupe] = nb_anomalies

            # Ajouter aux statistiques globales
            if nb_anomalies > 0:
                employes_avec_anomalies.add(employe_id)
                if type_groupe not in stats_anomalies_par_type:
                    stats_anomalies_par_type[type_groupe] = 0
                stats_anomalies_par_type[type_groupe] += nb_anomalies

    # Construire les statistiques globales
    statistiques = {
        'total_employes': total_employes,
        'employes_actifs': employes_actifs,
        'employes_inactifs': employes_inactifs,
        'employes_avec_anomalies': len(employes_avec_anomalies),
        'anomalies_par_type': stats_anomalies_par_type
    }

    return JsonResponse({
        'success': True,
        'resultats': resultats,
        'statistiques': statistiques,
        'annee': annee
    })


@login_required
def api_details_paiements_mois(request):
    """
    API pour récupérer les détails des paiements d'un employé pour un mois donné
    Paramètres: employe_id, annee, mois, type_paiement
    """
    employe_id = request.GET.get('employe_id')
    annee = request.GET.get('annee')
    mois = request.GET.get('mois')
    type_paiement = request.GET.get('type_paiement')

    if not all([employe_id, annee, mois]):
        return JsonResponse({
            'success': False,
            'error': 'Paramètres manquants'
        }, status=400)

    annee_int = int(annee)
    mois_int = int(mois)

    try:
        employe = _filter_employes_by_scope(
            Employe.objects.all(),
            request.user
        ).get(id=employe_id)
    except Employe.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Employé introuvable'
        }, status=404)

    # Récupérer les comptes employés
    comptes_employes = list(_filter_comptes_by_scope(
        Compte.objects.filter(employe_obligatoire=True),
        request.user
    ).values_list('compte', flat=True))

    # Filtrer les paiements de l'annee. Le mois est determine apres analyse
    # de la description pour rester coherent avec la matrice.
    query = _filter_diamex_by_scope(BaseDiameX.objects.filter(
        compte_code__in=comptes_employes,
        date_m__year__gte=annee_int - 1,
        date_m__year__lte=annee_int + 1
    ), request.user).exclude(
        description__isnull=True
    ).exclude(
        description=''
    ).order_by('date_m')

    employes_scope = _filter_employes_by_scope(Employe.objects.all(), request.user)

    paiements = []
    for entry in query:
        info = extraire_info_description(entry.description)

        # Vérifier que c'est bien le bon employé - AMÉLIORÉ
        if info['nom_employe']:
            # 1. Tentative avec surnom exact
            employe_obj = employes_scope.filter(surnom__iexact=info['nom_employe']).first()

            # 2. Tentative avec nom complet partiel (Prénom + Nom) - permet prénoms incomplets
            if not employe_obj:
                employe_obj = employes_scope.annotate(
                    nom_concat=Concat('prenom', Value(' '), 'nom')
                ).filter(nom_concat__icontains=info['nom_employe']).first()

            # 3. CRITIQUE: Tentative avec nom complet inversé (Nom + Prénom) - Format DiameX
            if not employe_obj:
                employe_obj = employes_scope.annotate(
                    nom_inv=Concat('nom', Value(' '), 'prenom')
                ).filter(nom_inv__icontains=info['nom_employe']).first()

            # 4. Fallback : recherche par parties du nom (format DiameX: NOM d'abord)
            if not employe_obj:
                nom_parts = info['nom_employe'].split()
                if len(nom_parts) >= 2:
                    employe_obj = employes_scope.filter(
                        Q(nom__icontains=nom_parts[0]) & Q(prenom__icontains=' '.join(nom_parts[1:]))
                    ).first()

            # 5. Dernier fallback : recherche large
            if not employe_obj:
                employe_obj = employes_scope.filter(
                    Q(surnom__icontains=info['nom_employe']) |
                    Q(nom__icontains=info['nom_employe']) |
                    Q(prenom__icontains=info['nom_employe'])
                ).first()

            if not employe_obj or employe_obj.id != employe.id:
                continue

        # Filtrer par type si demandé
        if type_paiement:
            type_groupe = mapper_type_groupe(info['type_paiement'], entry.description)
            if type_groupe != type_paiement:
                continue

        annee_effective = _get_annee_croise_entry(entry, info)
        mois_effectif = _get_mois_croise_entry(entry, info)
        if annee_effective != annee_int or mois_effectif != mois_int:
            continue

        paiements.append({
            'id': entry.id,
            'date': entry.date_m.strftime('%Y-%m-%d') if entry.date_m else '',
            'description': entry.description,
            'type': info['type_paiement'],
            'montant': float(entry.montant_out) if entry.montant_out else 0,
            'compte': entry.compte_code,
            'base': entry.fichier_source or '',
        })

    return JsonResponse({
        'success': True,
        'employe': {
            'id': str(employe.id),
            'surnom': employe.surnom,
            'nom_complet': f"{employe.prenom} {employe.nom}",
            'prefixe': employe.poste.prefixe if employe.poste else ''
        },
        'mois': mois_int,
        'annee': annee_int,
        'type_paiement': type_paiement,
        'paiements': paiements,
        'total': len(paiements)
    })


def mapper_type_groupe(type_paiement, description=''):
    """
    Mapper les types de paiement détaillés vers des groupes pour l'analyse
    Utilise la description complète pour distinguer les sous-types de salaire
    """
    # Normaliser la description (supprimer accents + minuscules)
    from .views_verification_paiements import normaliser_texte
    desc_lower = normaliser_texte(description) if description else ''

    # Si c'est un type de salaire, faire une distinction fine
    if type_paiement == 'salaire':
        # Solde de tout compte
        if 'solde de tout compte' in desc_lower:
            return 'solde_tout_compte'

        # Prime
        if '_prime_' in desc_lower or desc_lower.endswith('_prime') or 'prime' in desc_lower:
            return 'prime'

        # Ajustement (détecté par patterns spécifiques)
        if 'ajustement' in desc_lower or 'regularisation' in desc_lower or 'rappel' in desc_lower:
            return 'ajustement_salaire'

        # Allocation terrain
        if 'allocation terrain' in desc_lower:
            return 'allocation_terrain'

        # Indemnité compensatrice de congé
        if 'indemnite compensatrice' in desc_lower:
            return 'indemnite_compensatrice'

        # Salaire standard (par défaut)
        return 'salaire'

    # Types directs
    mapping = {
        'irsa': 'irsa',
        'cnaps': 'cnaps',
        'fmfp': 'fmfp',
        'mutuelle_sante': 'mutuelle_sante',
        'frais_medicaux': 'frais_medicaux',
        'frais_scolarite': 'frais_scolarite',
        'indemnite_terrain': 'indemnite_terrain',
        'indemnite_hors_zone': 'indemnite_hors_zone',
        'indemnite_stage': 'indemnite_stage',
        'frais_deplacement': 'frais_deplacement',
    }

    return mapping.get(type_paiement, None)
