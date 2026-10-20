"""
Generation des liens profonds (deep links) utilises dans les emails de
relance de factures non pointees : lien direct vers un point d'eau, lien
vers le formulaire de commentaire d'un point d'eau, lien vers le
formulaire consolide d'une relance.

Les liens sont construits a partir de (annee, mois, employe_id) plutot que
du PK de la trace RelanceFacturesNonPointees, pour fonctionner de maniere
identique en preview (dry_run, aucune trace creee) et en envoi reel - la vue
cible resout/cree la relance a la volee.
"""
from django.conf import settings
from django.urls import reverse


def _absolutiser(chemin: str) -> str:
    base = getattr(settings, 'SITE_BASE_URL', '').rstrip('/')
    return f"{base}{chemin}"


def lien_point_eau(point_eau_id) -> str:
    """Lien direct vers la page de detail du point d'eau (core:search_detail)."""
    chemin = reverse('core:search_detail', kwargs={'entity_type': 'point_eau', 'entity_id': str(point_eau_id)})
    return _absolutiser(chemin)


def lien_relance_consolide(employe_id, annee: int, mois: int) -> str:
    """Lien vers le formulaire consolide (tous les points d'eau de la relance
    d'un responsable pour une periode donnee)."""
    chemin = reverse(
        'messaging:commentaire_relance',
        kwargs={'annee': annee, 'mois': mois, 'employe_id': str(employe_id)},
    )
    return _absolutiser(chemin)


def lien_commentaire_point_eau(employe_id, annee: int, mois: int, point_eau_id) -> str:
    """Lien vers le formulaire consolide, avec ancre positionnee sur un point
    d'eau precis."""
    return f"{lien_relance_consolide(employe_id, annee, mois)}#point-eau-{point_eau_id}"


def lien_reparation(ouvrage_id) -> str:
    """
    Lien vers la page de suivi des reparations, filtree par ouvrage.

    Il n'existe pas de route de detail individuel par UUID de Reparation
    dans apps/planning/urls.py (verifie a l'implementation) - uniquement la
    page de suivi (planning:suivi_reparations) et des APIs internes basees
    sur planning_id (systeme different, non lie a ce modele). Le lien pointe
    donc vers la liste filtree par ouvrage plutot que d'inventer une route
    de detail inexistante.
    """
    chemin = reverse('planning:suivi_reparations')
    return f"{_absolutiser(chemin)}?ouvrage_id={ouvrage_id}"
