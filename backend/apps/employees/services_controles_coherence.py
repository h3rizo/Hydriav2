"""
Controles de coherence (non bloquants) pour la grille salariale par autonomie.

Ces controles portent a la fois sur GrilleAutonomie et RegleDePrime, d'ou leur
isolement dans un service dedie plutot que dans services_primes.py.
"""
from decimal import Decimal

from .models import ConfigSalaire
from .models_autonomie import GrilleAutonomie, RegleDePrime


def _alerte(type_alerte, severite, poste_id, poste_nom, message, stade_id=None, stade_nom=None,
            regle_id=None, valeurs=None):
    return {
        'type': type_alerte,
        'severite': severite,
        'poste_id': str(poste_id) if poste_id else None,
        'poste_nom': poste_nom,
        'stade_id': str(stade_id) if stade_id else None,
        'stade_nom': stade_nom,
        'regle_id': str(regle_id) if regle_id else None,
        'message': message,
        'valeurs': valeurs or {},
    }


def _controler_regression_et_progression(poste, grilles_du_poste, seuil_progression_pct, alertes):
    grilles_triees = sorted(
        (g for g in grilles_du_poste if g.statut != 'rejetee'),
        key=lambda g: g.stade.ordre,
    )

    precedent = None
    for grille in grilles_triees:
        if precedent is not None:
            fixe_precedent = precedent.salaire_net_fixe
            fixe_actuel = grille.salaire_net_fixe

            if fixe_actuel < fixe_precedent:
                alertes.append(_alerte(
                    'regression_salaire', 'error', poste.id, poste.nom_poste,
                    f"Le salaire net fixe diminue entre le stade '{precedent.stade.nom_stade}' "
                    f"({fixe_precedent} Ar) et le stade '{grille.stade.nom_stade}' ({fixe_actuel} Ar).",
                    stade_id=grille.stade_id, stade_nom=grille.stade.nom_stade,
                    valeurs={'salaire_precedent': float(fixe_precedent), 'salaire_actuel': float(fixe_actuel)},
                ))
            elif fixe_precedent and seuil_progression_pct is not None:
                progression_pct = (fixe_actuel - fixe_precedent) / fixe_precedent * Decimal('100')
                if progression_pct > seuil_progression_pct:
                    alertes.append(_alerte(
                        'progression_anormale', 'warning', poste.id, poste.nom_poste,
                        f"Progression de {progression_pct:.1f}% entre '{precedent.stade.nom_stade}' et "
                        f"'{grille.stade.nom_stade}', au-dessus du seuil configure ({seuil_progression_pct}%).",
                        stade_id=grille.stade_id, stade_nom=grille.stade.nom_stade,
                        valeurs={'progression_pct': float(progression_pct)},
                    ))

        precedent = grille


def _controler_prime_cible_vs_max(grille, alertes):
    if grille.prime_cible > grille.prime_maximale:
        alertes.append(_alerte(
            'prime_cible_superieure_max', 'error', grille.poste_id, grille.poste.nom_poste,
            f"La prime cible ({grille.prime_cible} Ar) est superieure a la prime maximale "
            f"({grille.prime_maximale} Ar) pour le stade '{grille.stade.nom_stade}'.",
            stade_id=grille.stade_id, stade_nom=grille.stade.nom_stade,
            valeurs={'prime_cible': float(grille.prime_cible), 'prime_maximale': float(grille.prime_maximale)},
        ))


def _controler_bornes_remuneration(grille, config, alertes):
    remuneration_max = grille.remuneration_maximale

    if config.remuneration_nette_min_autorisee is not None and grille.salaire_net_fixe < config.remuneration_nette_min_autorisee:
        alertes.append(_alerte(
            'remuneration_hors_bornes', 'warning', grille.poste_id, grille.poste.nom_poste,
            f"Le salaire net fixe ({grille.salaire_net_fixe} Ar) est sous la borne minimale autorisee "
            f"({config.remuneration_nette_min_autorisee} Ar) pour le stade '{grille.stade.nom_stade}'.",
            stade_id=grille.stade_id, stade_nom=grille.stade.nom_stade,
        ))

    if config.remuneration_nette_max_autorisee is not None and remuneration_max > config.remuneration_nette_max_autorisee:
        alertes.append(_alerte(
            'remuneration_hors_bornes', 'warning', grille.poste_id, grille.poste.nom_poste,
            f"La remuneration maximale ({remuneration_max} Ar) depasse la borne maximale autorisee "
            f"({config.remuneration_nette_max_autorisee} Ar) pour le stade '{grille.stade.nom_stade}'.",
            stade_id=grille.stade_id, stade_nom=grille.stade.nom_stade,
        ))


def _controler_anciennete(grille, config, alertes):
    """Controles specifiques a la majoration d'anciennete (anti-plafond)."""
    if not grille.anciennete_activee:
        return

    # Un stade superieur au pivot est aussi eligible : on ne verifie pas le stade
    # ici (pas de pivot charge), on n'alerte que sur le taux et le plafond.
    taux = grille.anciennete_taux_annuel_pct
    if taux is None:
        taux = getattr(config, 'taux_anciennete_autonomie_defaut_pct', None)
    if taux is None:
        alertes.append(_alerte(
            'anciennete_taux_manquant', 'error', grille.poste_id, grille.poste.nom_poste,
            f"La majoration d'anciennete est activee pour le stade '{grille.stade.nom_stade}' mais aucun "
            f"taux annuel n'est defini (ni sur la grille, ni dans la configuration).",
            stade_id=grille.stade_id, stade_nom=grille.stade.nom_stade,
        ))

    plafond_annees = grille.anciennete_plafond_annees
    if plafond_annees is None:
        plafond_annees = getattr(config, 'plafond_anciennete_autonomie_annees', None)
    if plafond_annees is None and grille.anciennete_plafond_majoration_pct is None:
        alertes.append(_alerte(
            'anciennete_sans_plafond', 'warning', grille.poste_id, grille.poste.nom_poste,
            f"La majoration d'anciennete du stade '{grille.stade.nom_stade}' n'a aucun plafond "
            f"(ni annees, ni pourcentage, ni valeur par defaut) : la remuneration peut croitre sans limite.",
            stade_id=grille.stade_id, stade_nom=grille.stade.nom_stade,
        ))

    if config.remuneration_nette_max_autorisee is not None:
        try:
            net_plafond = grille.net_effectif(
                grille._plafond_anciennete_annees_effectif(config), config,
            )
            if net_plafond > config.remuneration_nette_max_autorisee:
                alertes.append(_alerte(
                    'remuneration_hors_bornes', 'warning', grille.poste_id, grille.poste.nom_poste,
                    f"Avec la majoration d'anciennete au plafond, le salaire net du stade "
                    f"'{grille.stade.nom_stade}' atteint {net_plafond:.0f} Ar, au-dessus de la borne "
                    f"maximale autorisee ({config.remuneration_nette_max_autorisee} Ar).",
                    stade_id=grille.stade_id, stade_nom=grille.stade.nom_stade,
                ))
        except Exception:
            pass


def _controler_ponderations_regle(regle, alertes):
    if regle.type_calcul != 'paliers_resultats':
        return

    indicateurs_actifs = list(regle.indicateurs.all())
    if not indicateurs_actifs:
        return

    total_ponderation = sum((i.ponderation for i in indicateurs_actifs), Decimal('0'))
    if total_ponderation != Decimal('100'):
        alertes.append(_alerte(
            'ponderation_indicateurs_incorrecte', 'error', regle.poste_id, regle.poste.nom_poste,
            f"La somme des ponderations des indicateurs de la regle '{regle.nom_regle}' est de "
            f"{total_ponderation}% au lieu de 100%.",
            stade_id=regle.stade_id, stade_nom=regle.stade.nom_stade if regle.stade_id else None,
            regle_id=regle.id,
            valeurs={'total_ponderation': float(total_ponderation)},
        ))


def calculer_alertes_coherence(organisation=None, poste=None):
    """
    Calcule la liste des alertes de coherence (non bloquantes) pour les grilles
    par autonomie et les regles de primes, filtrable par organisation et/ou poste.
    """
    config = ConfigSalaire.get_config()
    alertes = []

    grilles_qs = GrilleAutonomie.objects.select_related('poste', 'stade').exclude(statut='rejetee')
    if organisation is not None:
        grilles_qs = grilles_qs.filter(models_q_organisation(organisation))
    if poste is not None:
        grilles_qs = grilles_qs.filter(poste=poste)

    grilles_par_poste = {}
    postes_par_id = {}
    for grille in grilles_qs:
        grilles_par_poste.setdefault(grille.poste_id, []).append(grille)
        postes_par_id[grille.poste_id] = grille.poste
        _controler_prime_cible_vs_max(grille, alertes)
        _controler_bornes_remuneration(grille, config, alertes)
        _controler_anciennete(grille, config, alertes)

    for poste_id, grilles_du_poste in grilles_par_poste.items():
        _controler_regression_et_progression(
            postes_par_id[poste_id], grilles_du_poste, config.seuil_alerte_progression_pct, alertes,
        )

    regles_qs = RegleDePrime.objects.select_related('poste', 'stade').prefetch_related('indicateurs').filter(actif=True)
    if organisation is not None:
        regles_qs = regles_qs.filter(models_q_organisation(organisation))
    if poste is not None:
        regles_qs = regles_qs.filter(poste=poste)

    for regle in regles_qs:
        _controler_ponderations_regle(regle, alertes)

    return alertes


def models_q_organisation(organisation):
    from django.db.models import Q
    return Q(organisation=organisation) | Q(organisation__isnull=True, poste__organisation=organisation)
