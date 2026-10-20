"""
Historique des interventions passées, pour aider à remplir un barème de coût type.

Pour une activité, un type de cible (équipement ou point d'eau) et un composant
optionnel, on retrouve les plannings déjà réalisés, leurs détails (désignations,
quantités, prix) et on en tire des statistiques par désignation.

Les composants sont une saisie récente : la plupart des interventions passées n'en
ont pas. L'historique est donc « souple » : la sélection s'élargit par niveaux de
précision décroissante tant qu'il n'y a pas assez d'interventions chiffrées.
"""
from collections import defaultdict
from statistics import mean, median

import pytz
from django.db.models import Q

from apps.planning.models import Planning

TZ_MADAGASCAR = pytz.timezone('Indian/Antananarivo')
LIMITE_PLANNINGS = 500        # plannings analysés au maximum (les plus récents)
LIMITE_INTERVENTIONS = 15     # interventions détaillées renvoyées à l'écran
SEUIL_AUTO = 3                # interventions chiffrées jugées suffisantes en mode auto

NIVEAU_COMPOSANT = 'composant'    # le composant est renseigné et correspond
NIVEAU_SOUPLE = 'souple'          # composant correspondant OU composant non renseigné
NIVEAU_TYPE = 'type'              # tout le type de cible, quels que soient les composants
NIVEAU_ACTIVITE = 'activite'      # toute l'activité, tous types de cible confondus
NIVEAU_AUTO = 'auto'
NIVEAUX = (NIVEAU_COMPOSANT, NIVEAU_SOUPLE, NIVEAU_TYPE, NIVEAU_ACTIVITE)


def niveaux_a_essayer(composant_id):
    """Niveaux évalués en mode auto, du plus précis au plus large."""
    if composant_id:
        return list(NIVEAUX)
    return [NIVEAU_TYPE, NIVEAU_ACTIVITE]


def choisir_niveau_auto(evaluations, seuil=SEUIL_AUTO):
    """
    evaluations : [(niveau, nb_interventions_chiffrees)] du plus précis au plus large.

    Retient le premier niveau qui atteint le seuil ; sinon celui qui a le plus
    d'interventions chiffrées (à égalité, le plus précis) ; sinon le plus précis.
    """
    for niveau, nb in evaluations:
        if nb >= seuil:
            return niveau
    meilleur = max(evaluations, key=lambda e: e[1])  # max garde le premier en cas d'égalité
    return meilleur[0] if meilleur[1] else evaluations[0][0]


def _libelle_cible(planning):
    if planning.cible_equipement_id:
        return planning.cible_equipement.nom
    if planning.cible_point_eau_id:
        point_eau = planning.cible_point_eau
        idxls = (point_eau.idxls or '').strip()
        return f"{idxls} {point_eau.nomabonne}".strip()
    return ''


def _plannings_du_niveau(niveau, fiche_id, genre, type_id, composant_id):
    plannings = Planning.objects.filter(fiche_poste_id=fiche_id)
    if niveau == NIVEAU_ACTIVITE:
        return plannings
    champ = 'composants_equipement' if genre == 'equipement' else 'composants_point_eau'
    if genre == 'equipement':
        plannings = plannings.filter(cible_equipement__type_equipement_id=type_id)
    else:
        plannings = plannings.filter(cible_point_eau__type_point_eau_id=type_id)
    if niveau == NIVEAU_COMPOSANT:
        plannings = plannings.filter(**{f'{champ}__id': composant_id})
    elif niveau == NIVEAU_SOUPLE:
        plannings = plannings.filter(Q(**{f'{champ}__id': composant_id}) | Q(**{f'{champ}__isnull': True}))
    return plannings


def _intervention(planning):
    lignes = []
    for detail in planning.details.all():
        designation = detail.designation
        lignes.append({
            'designation_id': str(designation.id),
            'designation': designation.nom,
            'type': designation.type_designation.nom,
            'unite': designation.unite or '',
            'pu_designation': float(designation.prix_unitaire or 0),
            'quantite': float(detail.quantity or 0),
            'pu': float(detail.pu or 0),
            'montant': float(detail.montant or 0),
        })
    composants = [c.nom_composant for c in planning.composants_equipement.all()] + \
                 [c.nom_composant for c in planning.composants_point_eau.all()]
    return {
        'planning_id': str(planning.id),
        'date': planning.date.astimezone(TZ_MADAGASCAR).strftime('%d/%m/%Y') if planning.date else '',
        'ouvrage': planning.ouvrage.nom_ouvrage if planning.ouvrage_id else '',
        'cible': _libelle_cible(planning),
        'composants': composants,
        'lignes': lignes,
        'total': sum(l['montant'] for l in lignes),
    }


def interventions_niveau(niveau, fiche_id, genre, type_id, composant_id=None):
    """Interventions d'un niveau de précision donné (les plus récentes d'abord)."""
    plannings = (
        _plannings_du_niveau(niveau, fiche_id, genre, type_id, composant_id)
        .distinct()
        .select_related('ouvrage', 'cible_equipement', 'cible_point_eau')
        .prefetch_related('details__designation__type_designation',
                          'composants_equipement', 'composants_point_eau')
        .order_by('-date')[:LIMITE_PLANNINGS]
    )
    return [_intervention(p) for p in plannings]


def interventions_historiques(fiche_id, genre, type_id, composant_id=None, niveau=NIVEAU_AUTO):
    """
    Retourne (interventions, niveau_utilise).

    En mode auto, essaie les niveaux du plus précis au plus large (voir choisir_niveau_auto).
    Un niveau demandé explicitement est utilisé tel quel ; « composant » et « souple »
    sans composant choisi retombent sur « type ». Critères obligatoires manquants : ([], niveau).
    """
    if not (fiche_id and genre in ('equipement', 'point_eau')):
        return [], niveau
    if niveau == NIVEAU_ACTIVITE:
        return interventions_niveau(NIVEAU_ACTIVITE, fiche_id, genre, type_id, composant_id), NIVEAU_ACTIVITE
    if not type_id:
        return [], niveau

    if niveau in (NIVEAU_COMPOSANT, NIVEAU_SOUPLE, NIVEAU_TYPE):
        if not composant_id:
            niveau = NIVEAU_TYPE
        return interventions_niveau(niveau, fiche_id, genre, type_id, composant_id), niveau

    # Mode auto
    evaluations, resultats = [], {}
    for candidat in niveaux_a_essayer(composant_id):
        resultats[candidat] = interventions_niveau(candidat, fiche_id, genre, type_id, composant_id)
        nb_chiffrees = sum(1 for i in resultats[candidat] if i['lignes'])
        evaluations.append((candidat, nb_chiffrees))
        if nb_chiffrees >= SEUIL_AUTO:
            break
    retenu = choisir_niveau_auto(evaluations)
    return resultats[retenu], retenu


def agreger_historique(interventions):
    """
    Statistiques à partir de la liste d'interventions.

    Seules les interventions ayant au moins une ligne servent aux statistiques :
    une intervention sans coût saisi fausserait les fréquences. Retourne un dict
    {nb_interventions, nb_sans_detail, total_moyen, total_median, designations}.
    """
    avec_lignes = [i for i in interventions if i['lignes']]
    nb = len(avec_lignes)
    par_designation = defaultdict(list)
    for intervention in avec_lignes:
        # Une désignation saisie plusieurs fois dans la même intervention : on cumule.
        cumul = {}
        for ligne in intervention['lignes']:
            c = cumul.setdefault(ligne['designation_id'], {**ligne, 'quantite': 0.0, 'montant': 0.0})
            c['quantite'] += ligne['quantite']
            c['montant'] += ligne['montant']
        for did, ligne in cumul.items():
            par_designation[did].append(ligne)

    designations = []
    for did, lignes in par_designation.items():
        quantites = [l['quantite'] for l in lignes]
        designations.append({
            'designation_id': did,
            'designation': lignes[0]['designation'],
            'type': lignes[0]['type'],
            'unite': lignes[0]['unite'],
            'pu_designation': lignes[0]['pu_designation'],
            'nb': len(lignes),
            'frequence': round(100 * len(lignes) / nb) if nb else 0,
            'quantite_mediane': round(median(quantites), 2),
            'quantite_moyenne': round(mean(quantites), 2),
            'pu_moyen': round(mean(l['pu'] for l in lignes), 2),
            'montant_moyen': round(mean(l['montant'] for l in lignes), 2),
        })
    designations.sort(key=lambda d: (-d['nb'], -d['montant_moyen'], d['designation']))

    totaux = [i['total'] for i in avec_lignes]
    return {
        'nb_interventions': nb,
        'nb_sans_detail': len(interventions) - nb,
        'total_moyen': round(mean(totaux), 2) if totaux else 0,
        'total_median': round(median(totaux), 2) if totaux else 0,
        'designations': designations,
    }
