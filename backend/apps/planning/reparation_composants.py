"""
Cible et composants d'une réparation.

Une réparation (Planning) cible un équipement OU un point d'eau, et précise
le ou les composants concernés, pris dans le catalogue du type de la cible
(ComposantTypeEquipement / ComposantTypePointEau).
"""
import unicodedata

from apps.inspections.models import ComposantTypeEquipement, ComposantTypePointEau


def normaliser_nom_composant(nom):
    """Clé de comparaison d'un nom de composant : sans accents, casse, tirets ni espaces multiples."""
    texte = unicodedata.normalize('NFD', str(nom or ''))
    texte = ''.join(c for c in texte if unicodedata.category(c) != 'Mn').lower()
    return ' '.join(texte.replace('-', ' ').replace('_', ' ').split())


def composants_admis_fiche(fiche):
    """Noms admis (normalisés) pour l'activité, ou ensemble vide = aucune restriction."""
    liste = fiche.composants_admis_liste() if fiche is not None and hasattr(fiche, 'composants_admis_liste') else []
    return {normaliser_nom_composant(nom) for nom in liste}


class ComposantsError(ValueError):
    """Erreur de validation exposable telle quelle à l'utilisateur."""


def regles_fiche(fiche):
    """Règles de saisie de la cible / des composants pour une activité (FichePoste)."""
    mode_cible = getattr(fiche, 'cible_mode', 'optionnel') or 'optionnel'
    mode_comp = getattr(fiche, 'composants_mode', 'optionnel') or 'optionnel'
    if mode_comp == 'obligatoire':
        mode_cible = 'obligatoire'          # un composant se choisit sur une cible
    if mode_cible == 'non':
        mode_comp = 'non'                   # pas de cible -> pas de composants
    return {
        'cible_mode': mode_cible,
        'cible_types': getattr(fiche, 'cible_types', 'les_deux') or 'les_deux',
        'composants_mode': mode_comp,
        'composants_multiple': bool(getattr(fiche, 'composants_multiple', True)),
        # Noms tels que saisis ; le mobile et la page web comparent sans accents ni casse.
        'composants_admis': (fiche.composants_admis_liste()
                             if hasattr(fiche, 'composants_admis_liste') else []),
    }


def verifier_regles_fiche(fiche, equipement, point_eau, composant_ids):
    """
    Vérifie cible et composants d'une réparation par rapport aux règles de son activité.

    composant_ids : liste finale des composants (les ids déjà enregistrés si inchangés).
    Lève ComposantsError avec un message affichable. Sans fiche, rien n'est exigé.
    """
    if fiche is None:
        return
    regles = regles_fiche(fiche)
    nom = getattr(fiche, 'tache', '') or "cette activité"
    a_cible = bool(equipement or point_eau)

    if a_cible:
        if equipement and regles['cible_types'] == 'point_eau':
            raise ComposantsError(f"« {nom} » se rapporte à un point d'eau, pas à un équipement")
        if point_eau and regles['cible_types'] == 'equipement':
            raise ComposantsError(f"« {nom} » se rapporte à un équipement, pas à un point d'eau")
    elif regles['cible_mode'] == 'obligatoire':
        cible = {'point_eau': "le point d'eau", 'equipement': "l'équipement"}.get(
            regles['cible_types'], "le point d'eau ou l'équipement")
        raise ComposantsError(f"Précisez {cible} concerné pour « {nom} »")

    composant_ids = list(composant_ids or [])
    admis = composants_admis_fiche(fiche)
    if admis and composant_ids:
        choisis = (list(ComposantTypeEquipement.objects.filter(id__in=composant_ids))
                   + list(ComposantTypePointEau.objects.filter(id__in=composant_ids)))
        refuses = [c.nom_composant for c in choisis if normaliser_nom_composant(c.nom_composant) not in admis]
        if refuses:
            raise ComposantsError(
                f"« {nom} » ne s'applique pas à : {', '.join(refuses)}. "
                f"Composants admis : {', '.join(fiche.composants_admis_liste())}")
    if regles['composants_mode'] == 'obligatoire' and a_cible and not composant_ids:
        # On n'exige rien quand le catalogue (filtré) du type de la cible est vide (impossible à satisfaire)
        disponibles = composants_disponibles(equipement=equipement, point_eau=point_eau, fiche=fiche)
        if disponibles:
            raise ComposantsError(f"Précisez le ou les composants concernés pour « {nom} »")
    if not regles['composants_multiple'] and len(composant_ids) > 1:
        raise ComposantsError(f"Un seul composant peut être indiqué pour « {nom} »")


def parse_composants_ids(data):
    """Retourne la liste d'ids (str) reçue sous composants_ids / composants[], ou None si absente."""
    for key in ('composants_ids', 'composants', 'composants[]'):
        if key in data:
            raw = data.get(key)
            if raw in (None, ''):
                return []
            if isinstance(raw, str):
                # Formulaire mobile : request.POST.dict() ne garde qu'une valeur par cle,
                # les identifiants arrivent donc en une chaine "a,b,c".
                raw = raw.split(',')
            elif not isinstance(raw, (list, tuple)):
                raw = [raw]
            seen, ids = set(), []
            for item in raw:
                value = str(item or '').strip()
                if value and value not in seen:
                    seen.add(value)
                    ids.append(value)
            return ids
    return None


def apply_repair_target(planning, equipement, point_eau, composant_ids):
    """
    Enregistre la cible et les composants sur le planning.

    composant_ids=None laisse les composants inchangés (sauf si la cible change :
    ils sont alors vidés, car ils appartiennent au type de l'ancienne cible).
    """
    if equipement and point_eau:
        raise ComposantsError("La réparation ne peut pas cibler à la fois un point d'eau et un équipement")

    target_changed = (
        (planning.cible_equipement_id or None) != (equipement.id if equipement else None)
        or (planning.cible_point_eau_id or None) != (point_eau.id if point_eau else None)
    )
    planning.cible_equipement = equipement
    planning.cible_point_eau = point_eau
    planning.save(update_fields=['cible_equipement', 'cible_point_eau'])

    if composant_ids is None:
        if not target_changed:
            return
        composant_ids = []

    if composant_ids and not (equipement or point_eau):
        raise ComposantsError("Précisez l'équipement ou le point d'eau avant de choisir des composants")

    eq_comps, pe_comps = [], []
    if composant_ids:
        if equipement:
            if not equipement.type_equipement_id:
                raise ComposantsError("Cet équipement n'a pas de type : aucun composant disponible")
            eq_comps = list(ComposantTypeEquipement.objects.filter(
                id__in=composant_ids, type_equipement_id=equipement.type_equipement_id))
            found = len(eq_comps)
        else:
            if not point_eau.type_point_eau_id:
                raise ComposantsError("Ce point d'eau n'a pas de type : aucun composant disponible")
            pe_comps = list(ComposantTypePointEau.objects.filter(
                id__in=composant_ids, type_point_eau_id=point_eau.type_point_eau_id))
            found = len(pe_comps)
        if found != len(composant_ids):
            raise ComposantsError("Certains composants ne correspondent pas au type de la cible")

    planning.composants_equipement.set(eq_comps)
    planning.composants_point_eau.set(pe_comps)


def serialize_repair_target(planning):
    """Cible et composants d'un planning, pour les API JSON."""
    comps = (
        [{'id': str(c.id), 'nom': c.nom_composant} for c in planning.composants_equipement.all()]
        + [{'id': str(c.id), 'nom': c.nom_composant} for c in planning.composants_point_eau.all()]
    )
    return {
        'cible_equipement_id': str(planning.cible_equipement_id) if planning.cible_equipement_id else None,
        'cible_point_eau_id': str(planning.cible_point_eau_id) if planning.cible_point_eau_id else None,
        'composants': comps,
        'composants_ids': [c['id'] for c in comps],
    }


def composants_disponibles(equipement=None, point_eau=None, fiche=None):
    """Composants proposables pour une cible, triés comme dans le catalogue.

    Avec une activité (fiche) restreinte, seuls ses composants admis sont proposés.
    """
    if equipement is not None and equipement.type_equipement_id:
        qs = ComposantTypeEquipement.objects.filter(type_equipement_id=equipement.type_equipement_id)
    elif point_eau is not None and point_eau.type_point_eau_id:
        qs = ComposantTypePointEau.objects.filter(type_point_eau_id=point_eau.type_point_eau_id)
    else:
        return []
    admis = composants_admis_fiche(fiche)
    return [{'id': str(c.id), 'nom': c.nom_composant} for c in qs
            if not admis or normaliser_nom_composant(c.nom_composant) in admis]


def catalogue_composants_par_type():
    """
    Catalogue complet pour le mode hors ligne du mobile :
    {'equipement': {type_id: [{id, nom}]}, 'point_eau': {type_id: [{id, nom}]}}
    """
    out = {'equipement': {}, 'point_eau': {}}
    for c in ComposantTypeEquipement.objects.all():
        out['equipement'].setdefault(str(c.type_equipement_id), []).append(
            {'id': str(c.id), 'nom': c.nom_composant})
    for c in ComposantTypePointEau.objects.all():
        out['point_eau'].setdefault(str(c.type_point_eau_id), []).append(
            {'id': str(c.id), 'nom': c.nom_composant})
    return out
