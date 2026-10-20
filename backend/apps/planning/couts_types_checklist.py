"""
Check-list des coûts types à renseigner.

Une ligne = une combinaison (activité, genre de cible, type de cible, composant éventuel).
Les combinaisons « possibles » viennent de trois sources :
  - observées : déjà rencontrées dans les plannings passés (base par défaut, ~quelques dizaines) ;
  - barèmes existants : y compris ceux qui ne correspondent à aucune intervention passée ;
  - théoriques (optionnel) : toutes celles que permettent les règles des activités
    (des milliers, la plupart sans objet) : à n'afficher qu'à la demande.

Clé d'une combinaison : (fiche_id, genre, type_id, composant_id | None), en chaînes.
Sans composant = barème de repli valable pour tout le type de cible.
"""
from collections import defaultdict
from statistics import mean

from django.db.models import Count, Sum

from apps.billing.models import TypePointEau
from apps.infrastructure.models import TypeEquipement
from apps.inspections.models import ComposantTypeEquipement, ComposantTypePointEau
from apps.planning.models import Planning
from apps.planning.repair_classification import (
    classify_repair_family,
    get_reparations_fiches_queryset,
    is_installation_type,
    is_remplacement_type,
)
from apps.planning.reparation_composants import normaliser_nom_composant, regles_fiche

FAMILLES = {
    'reparation': 'Réparation',
    'rehabilitation': 'Réhabilitation',
    'installation': 'Installation',
    'remplacement': 'Remplacement',
}

STATUT_A_REMPLIR = 'a_remplir'   # aucun barème
STATUT_VIDE = 'vide'             # barème créé mais sans aucune désignation
STATUT_REMPLI = 'rempli'


def famille_fiche(fiche):
    """Famille d'une activité : réparation, réhabilitation, installation ou remplacement."""
    type_name = getattr(getattr(fiche, 'type_activites', None), 'nomtype', '') or ''
    famille = classify_repair_family(type_name=type_name, fiche_label=fiche.tache or '')
    if famille == 'panne':
        return 'reparation'
    if famille:
        return famille
    if is_installation_type(type_name):
        return 'installation'
    if is_remplacement_type(type_name):
        return 'remplacement'
    return ''


def cle_combinaison(fiche_id, genre, type_id, composant_id=None):
    return (str(fiche_id), genre, str(type_id), str(composant_id) if composant_id else None)


def assembler_checklist(observees, bareme_par_cle, theoriques=()):
    """
    Fusionne les trois sources en lignes de check-list (fonction pure).

    observees : {cle: {'nb': int, 'nb_chiffrees': int, 'totaux': [float, ...]}}
    bareme_par_cle : {cle: {'id': str, 'nb_lignes': int}}
    theoriques : itérable de clés.
    """
    lignes = []
    for cle in set(observees) | set(bareme_par_cle) | set(theoriques):
        obs = observees.get(cle) or {'nb': 0, 'nb_chiffrees': 0, 'totaux': []}
        bareme = bareme_par_cle.get(cle)
        if not bareme:
            statut = STATUT_A_REMPLIR
        else:
            statut = STATUT_REMPLI if bareme['nb_lignes'] else STATUT_VIDE
        totaux = obs['totaux']
        lignes.append({
            'cle': cle,
            'cout_type_id': bareme['id'] if bareme else None,
            'statut': statut,
            'observee': cle in observees,
            'nb_historique': obs['nb'],
            'nb_chiffrees': obs['nb_chiffrees'],
            'reel_moyen': round(mean(totaux), 2) if totaux else None,
        })
    return lignes


def observer_combinaisons(fiche_ids):
    """
    Combinaisons rencontrées dans les plannings passés, avec leurs effectifs.

    Les composants sont une saisie récente et facultative : chaque planning compte pour sa
    combinaison « sans composant » (tout le type de cible) ET pour chacun de ses composants.
    """
    plannings = list(
        Planning.objects.filter(fiche_poste_id__in=fiche_ids)
        .annotate(total=Sum('details__montant'), nb_details=Count('details'))
        .values('id', 'fiche_poste_id', 'total', 'nb_details',
                'cible_equipement__type_equipement_id', 'cible_point_eau__type_point_eau_id')
    )
    observees = defaultdict(lambda: {'nb': 0, 'nb_chiffrees': 0, 'totaux': []})
    cles_planning = {}
    for p in plannings:
        if p['cible_equipement__type_equipement_id']:
            genre, type_id = 'equipement', p['cible_equipement__type_equipement_id']
        elif p['cible_point_eau__type_point_eau_id']:
            genre, type_id = 'point_eau', p['cible_point_eau__type_point_eau_id']
        else:
            continue
        cles_planning[p['id']] = (p, cle_combinaison(p['fiche_poste_id'], genre, type_id))

    def compter(cle, p):
        o = observees[cle]
        o['nb'] += 1
        if p['nb_details'] and (p['total'] or 0) > 0:
            o['nb_chiffrees'] += 1
            o['totaux'].append(float(p['total']))

    for p, cle in cles_planning.values():
        compter(cle, p)

    ids = list(cles_planning)
    liaisons = list(Planning.composants_equipement.through.objects.filter(planning_id__in=ids)
                    .values_list('planning_id', 'composanttypeequipement_id')) + \
        list(Planning.composants_point_eau.through.objects.filter(planning_id__in=ids)
             .values_list('planning_id', 'composanttypepointeau_id'))
    for planning_id, composant_id in liaisons:
        p, cle = cles_planning[planning_id]
        compter(cle[:3] + (str(composant_id),), p)
    return dict(observees)


def combinaisons_theoriques(fiches):
    """
    Toutes les combinaisons permises par les règles de chaque activité (type de cible admis,
    composants admis, composants facultatifs / obligatoires / sans objet).
    """
    types_eq = list(TypeEquipement.objects.all())
    types_pe = list(TypePointEau.objects.all())
    comp_eq, comp_pe = defaultdict(list), defaultdict(list)
    for c in ComposantTypeEquipement.objects.all():
        comp_eq[c.type_equipement_id].append(c)
    for c in ComposantTypePointEau.objects.all():
        comp_pe[c.type_point_eau_id].append(c)

    cles = set()
    for fiche in fiches:
        regles = regles_fiche(fiche)
        if regles['cible_mode'] == 'non':
            continue
        admis = {normaliser_nom_composant(n) for n in regles['composants_admis']}
        cibles = []
        if regles['cible_types'] in ('equipement', 'les_deux'):
            cibles += [('equipement', t, comp_eq[t.id]) for t in types_eq]
        if regles['cible_types'] in ('point_eau', 'les_deux'):
            cibles += [('point_eau', t, comp_pe[t.id]) for t in types_pe]
        for genre, type_cible, composants in cibles:
            if admis:
                composants = [c for c in composants if normaliser_nom_composant(c.nom_composant) in admis]
            mode = regles['composants_mode']
            if mode != 'obligatoire':
                cles.add(cle_combinaison(fiche.id, genre, type_cible.id))
            if mode != 'non':
                for c in composants:
                    cles.add(cle_combinaison(fiche.id, genre, type_cible.id, c.id))
    return cles


def referentiel():
    """Noms nécessaires à l'affichage : activités (avec famille), types et composants."""
    fiches = {
        str(f.id): {'nom': f.tache, 'famille': famille_fiche(f), 'objet': f}
        for f in get_reparations_fiches_queryset()
    }
    return {
        'fiches': fiches,
        'types': {
            'equipement': {str(t.id): t.nom_type for t in TypeEquipement.objects.all()},
            'point_eau': {str(t.id): t.nom_type for t in TypePointEau.objects.all()},
        },
        'composants': {
            'equipement': {str(c.id): c.nom_composant for c in ComposantTypeEquipement.objects.all()},
            'point_eau': {str(c.id): c.nom_composant for c in ComposantTypePointEau.objects.all()},
        },
    }
