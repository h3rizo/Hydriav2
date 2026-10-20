"""
Selection et regroupement des "reparations" (Planning classifies
reparation/rehabilitation/panne, non valides et en retard) pour le moteur
de relance combine (voir apps.messaging.relance_engine).

Fonctions pures : lecture seule, aucun envoi ni ecriture en base.

Source de donnees : le vrai systeme de production est le modele
apps.planning.models.Planning (PAS apps.planning.models_reparations.
Reparation, vide et deconnecte de la production, PAS PlanningDetail qui
est une granularite materiel/ligne, pas la tache elle-meme).

Champ "termine" = Planning.estvalide (bool nullable), pas Planning.statut
(quasi jamais renseigne par le workflow reel, source d'incoherence
documentee ailleurs dans le projet - cf. apps.core.views_ouvrage_
interventions.unfinished_overdue_contributions_count - a ne pas
reproduire ici).
"""
from datetime import date

from django.conf import settings
from django.db.models import Q

from apps.employees.models import Employe
from apps.employees.permissions import est_agent_recouvrement
from apps.planning.models import Planning
from apps.planning.repair_classification import get_repair_fiche_ids
from apps.planning.repair_workflow_grading import get_repair_workflow_grading_from_plannings

from .monthly_billing_reminder import date_actuelle_madagascar

NIVEAUX_PRIORITE_CRITIQUE = ['haute', 'critique']

# Grades ouvrage (apps.planning.repair_workflow_grading) qui signalent une
# panne presente sur l'ouvrage : pousse la criticite au niveau ouvrage,
# independamment du niveau individuel de chaque Planning.
GRADES_PANNE = {'B_panne', 'D_panne'}

# Postes exclus des relances reparations - DELIBEREMENT DIFFERENT de
# POSTES_EXCLUS_RAPPEL (paiements) : le Superviseur technique gere le
# terrain/travaux et doit etre notifie des reparations echues, meme s'il
# reste exclu des relances paiements (qui concernent le suivi comptable,
# hors de son role). Mpikojakoja ifotony (poste d'execution) reste exclu
# pour les deux types.
POSTES_EXCLUS_RAPPEL_REPARATIONS = ['Mpikojakoja ifotony']


def _retard_attention_jours() -> int:
    return getattr(settings, 'REPARATION_RETARD_ATTENTION_JOURS', 15)


def _retard_critique_jours() -> int:
    return getattr(settings, 'REPARATION_RETARD_CRITIQUE_JOURS', 45)


def _nb_relances_critique() -> int:
    return getattr(settings, 'REPARATION_NB_RELANCES_CRITIQUE', 3)


def reparations_echues(date_reference: date):
    """Planning classifie reparation/rehabilitation/panne (fiche_poste_id
    dans get_repair_fiche_ids()), dont la date (convertie en date civile)
    est depassee a date_reference, et non valide (estvalide falsy - False
    ou None). Planning.statut est ignore volontairement (non fiable sur le
    workflow reel des reparations, cf. entete de module)."""
    return (
        Planning.objects
        .filter(fiche_poste_id__in=get_repair_fiche_ids())
        .filter(date__date__lt=date_reference)
        .filter(Q(estvalide=False) | Q(estvalide__isnull=True))
        .select_related('ouvrage', 'employe', 'employe__poste', 'fiche_poste', 'fiche_poste__type_activites', 'type_activite')
    )


def plannings_reparation_non_valides_ouvrage(ouvrage_id):
    """
    Tous les Planning classifies reparation de cet ouvrage, non valides,
    PASSES OU FUTURS (pas de filtre de date) - perimetre necessaire pour
    calculer fidelement le grading d'ouvrage
    (get_repair_workflow_grading_from_plannings), qui se base sur "non
    valide" et non sur "en retard" (get_open_repair_flags n'exclut que
    estvalide=True, jamais sur la date). Se limiter aux seules reparations
    echues sous-estimerait un ouvrage ayant une reparation/panne ouverte
    planifiee dans le futur.
    """
    return (
        Planning.objects
        .filter(ouvrage_id=ouvrage_id, fiche_poste_id__in=get_repair_fiche_ids())
        .filter(Q(estvalide=False) | Q(estvalide__isnull=True))
        .select_related('fiche_poste__type_activites', 'type_activite')
    )


def grading_ouvrage_reparations(ouvrage_id) -> dict:
    """Grading A/B/B_panne/C/D/D_panne pour un ouvrage, calcule sur TOUS
    ses Planning reparation non valides (passes et futurs). Wrapper fin
    autour de get_repair_workflow_grading_from_plannings pour centraliser
    ce point d'integration dans le moteur de relance."""
    plannings = list(plannings_reparation_non_valides_ouvrage(ouvrage_id))
    return get_repair_workflow_grading_from_plannings(plannings)


def responsables_actifs_pour_ouvrage_reparations(ouvrage_id, date_reference: date):
    """
    Retourne les Employe distincts assignes (Planning.employe) sur des
    Planning reparation ECHUS de cet ouvrage a date_reference (memes
    criteres que reparations_echues : classification reparation, estvalide
    falsy, date depassee). Planning.employe est l'agent EXECUTANT/assigne
    a la tache - concept different d'EmployeOuvrages (responsable
    administratif utilise pour les paiements).

    Exclut les employes debauches et les titulaires de
    POSTES_EXCLUS_RAPPEL_REPARATIONS (Superviseur technique inclus,
    contrairement aux paiements).
    """
    employe_ids = (
        Planning.objects
        .filter(
            ouvrage_id=ouvrage_id,
            fiche_poste_id__in=get_repair_fiche_ids(),
            employe__isnull=False,
        )
        .filter(date__date__lt=date_reference)
        .filter(Q(estvalide=False) | Q(estvalide__isnull=True))
        .values_list('employe_id', flat=True)
    )
    return Employe.objects.filter(
        id__in=employe_ids,
        date_debauchage__isnull=True,
    ).exclude(
        poste__nom_poste__in=POSTES_EXCLUS_RAPPEL_REPARATIONS
    ).distinct()


def superieurs_hierarchiques_reparations(employe, date_reference: date):
    """
    Equivalent de monthly_billing_reminder.superieurs_hierarchiques() mais
    avec POSTES_EXCLUS_RAPPEL_REPARATIONS. Meme logique anti-boucle et de
    skip-mais-continue pour un superieur exclu."""
    from apps.employees.models import HierarchieEmploye

    superieurs = []
    visites = {employe.id}
    courant = employe

    while True:
        relation = HierarchieEmploye.objects.filter(
            employe=courant, date_debut__lte=date_reference,
        ).filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=date_reference)
        ).select_related('superieur', 'superieur__poste').first()

        if relation is None or relation.superieur_id in visites:
            break

        superieur = relation.superieur
        visites.add(superieur.id)

        est_exclu = (
            superieur.date_debauchage is not None
            or (superieur.poste and superieur.poste.nom_poste in POSTES_EXCLUS_RAPPEL_REPARATIONS)
        )
        if not est_exclu:
            superieurs.append(superieur)

        courant = superieur

    return superieurs


def calculer_jours_retard(reparation, date_reference: date) -> int:
    """Nombre de jours entre Planning.date (converti en date civile) et
    date_reference. N'est appelee que sur des Planning deja filtres comme
    echus (retard toujours positif dans ce contexte)."""
    return (date_reference - reparation.date.date()).days


def nb_relances_anterieures(reparation) -> int:
    """Nombre de cycles d'envoi distincts (batch_id) ayant deja notifie ce
    Planning, hors envois de test. Compte de cycles, pas de lignes brutes
    (un meme cycle peut generer plusieurs lignes RelanceReparations pour
    des destinataires differents)."""
    from .models import RelanceReparations

    return (
        RelanceReparations.objects
        .filter(reparation=reparation, est_test=False)
        .values('batch_id')
        .distinct()
        .count()
    )


def calculer_niveau_reparation(reparation, jours_retard: int, nb_relances_ant: int) -> str:
    """
    Niveau de criticite INDIVIDUEL d'un Planning-reparation = le plus
    eleve parmi :
    - seuil de jours de retard,
    - nombre de relances anterieures (cycles distincts) >= seuil critique,
    - priorite_suivi du Planning (haute/critique pousse vers critique).

    Ne prend PAS en compte le grading ouvrage (panne) - c'est un signal
    global a l'ouvrage, applique separement dans
    construire_regroupement_reparations() sur toutes les entrees d'un
    meme ouvrage.
    """
    if (
        jours_retard >= _retard_critique_jours()
        or nb_relances_ant >= _nb_relances_critique()
        or reparation.priorite_suivi in NIVEAUX_PRIORITE_CRITIQUE
    ):
        return 'critique'
    if jours_retard >= _retard_attention_jours():
        return 'attention'
    return 'normal'


def _ajouter_reparation(regroupement, employe, ouvrage, entree_reparation):
    entree_employe = regroupement.setdefault(employe.id, {
        'employe': employe,
        'ouvrages': {},
    })
    entree_ouvrage = entree_employe['ouvrages'].setdefault(ouvrage.id, {
        'ouvrage': ouvrage,
        'reparations': [],
    })
    entree_ouvrage['reparations'].append(entree_reparation)


def construire_regroupement_reparations(date_reference: date = None) -> dict:
    """
    Construit le regroupement employe responsable -> ouvrage -> reparations
    echues, meme forme que construire_regroupement() des paiements.

    Le destinataire direct est Planning.employe (agent execute/assigne).
    Un Planning sans employe assigne ne peut etre rattache a personne en
    direct : il est exclu de la selection (voir
    compter_reparations_sans_responsable pour le comptage informatif).

    Le niveau individuel de chaque reparation est corrige par le grading
    ouvrage (panne => critique), calcule une seule fois par ouvrage
    rencontre et mis en cache localement pour la duree de l'appel.
    """
    date_reference = date_reference or date_actuelle_madagascar()

    regroupement = {}
    responsables_par_ouvrage = {}
    grading_par_ouvrage = {}

    def _responsables_pour(ouvrage_id):
        if ouvrage_id not in responsables_par_ouvrage:
            responsables_par_ouvrage[ouvrage_id] = [
                e for e in responsables_actifs_pour_ouvrage_reparations(ouvrage_id, date_reference)
                if not est_agent_recouvrement(e)
            ]
        return responsables_par_ouvrage[ouvrage_id]

    for reparation in reparations_echues(date_reference):
        ouvrage = reparation.ouvrage
        if ouvrage is None or reparation.employe_id is None:
            continue

        jours_retard = calculer_jours_retard(reparation, date_reference)
        nb_relances_ant = nb_relances_anterieures(reparation)
        niveau = calculer_niveau_reparation(reparation, jours_retard, nb_relances_ant)

        if ouvrage.id not in grading_par_ouvrage:
            grading_par_ouvrage[ouvrage.id] = grading_ouvrage_reparations(ouvrage.id)
        grade_ouvrage = grading_par_ouvrage[ouvrage.id]
        if grade_ouvrage['code'] in GRADES_PANNE:
            niveau = 'critique'

        entree_reparation = {
            'reparation': reparation,
            'jours_retard': jours_retard,
            'niveau': niveau,
            'grade_ouvrage': grade_ouvrage,
        }
        for employe in _responsables_pour(ouvrage.id):
            _ajouter_reparation(regroupement, employe, ouvrage, entree_reparation)

    return regroupement


def construire_regroupement_hierarchique_reparations(regroupement: dict, date_reference: date) -> dict:
    """
    Meme forme que construire_regroupement_hierarchique() des paiements.
    Utilise superieurs_hierarchiques_reparations() (deja skip
    debauches/POSTES_EXCLUS_RAPPEL_REPARATIONS) PUIS exclut en aval les
    agents de recouvrement croises dans la chaine (on saute, la chaine
    continue au-dela)."""
    regroupement_hierarchique = {}

    for employe_id, entree in regroupement.items():
        employe = entree['employe']
        for superieur in superieurs_hierarchiques_reparations(employe, date_reference):
            if est_agent_recouvrement(superieur):
                continue
            entree_superieur = regroupement_hierarchique.setdefault(superieur.id, {
                'employe': superieur,
                'subordonnes': {},
            })
            entree_superieur['subordonnes'][employe_id] = entree

    return regroupement_hierarchique


def compter_reparations_sans_responsable(date_reference: date = None) -> int:
    """Compte les Planning-reparation echus dont l'employe assigne est
    None (Planning.employe = None) - equivalent de
    compter_factures_sans_responsable() cote paiements. Ces Planning sont
    exclus de la selection principale (aucun destinataire direct possible)
    mais comptes ici a des fins de suivi/alerte operationnelle."""
    date_reference = date_reference or date_actuelle_madagascar()
    return (
        Planning.objects
        .filter(fiche_poste_id__in=get_repair_fiche_ids(), employe__isnull=True)
        .filter(date__date__lt=date_reference)
        .filter(Q(estvalide=False) | Q(estvalide__isnull=True))
        .count()
    )
