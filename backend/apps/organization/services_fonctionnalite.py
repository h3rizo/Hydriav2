"""Détermination du statut fonctionnel d'un ouvrage.

Règles (validées produit, 22/09/2026) :

1. Si un ``ChantierWorkflow`` actif (``statut`` hors ``brouillon``/``cloture``) existe
   pour l'ouvrage -> l'ouvrage est considéré NON FONCTIONNEL (source ``chantier``).
   La case manuelle ``Ouvrage.marque_non_fonctionnel`` n'est alors plus modifiable
   pour cet ouvrage : le chantier fait foi.
2. Sinon, si une ``Reparation`` active (``statut`` hors ``terminee``/``validee``/
   ``annulee``) existe pour l'ouvrage -> déjà suivi via le module Réparations : la
   case manuelle est masquée/non modifiable pour cet ouvrage (pour éviter les
   doublons de saisie), mais elle continue de déterminer le statut fonctionnel
   (une réparation en cours ne rend pas, à elle seule, l'ouvrage non fonctionnel).
3. Sinon, le statut est déterminé uniquement par la case manuelle
   ``marque_non_fonctionnel``.
"""

CHANTIER_STATUTS_ACTIFS = ['besoins_generes', 'devis', 'contrat', 'execution', 'recollement']
REPARATION_STATUTS_ACTIFS = ['signalee', 'planifiee', 'en_cours']


def get_ouvrages_chantier_actif_ids(ouvrage_ids=None):
    """Retourne l'ensemble des ouvrage_id ayant un ChantierWorkflow actif."""
    from apps.chantiers.models_workflow import ChantierWorkflow

    qs = ChantierWorkflow.objects.filter(statut__in=CHANTIER_STATUTS_ACTIFS)
    if ouvrage_ids is not None:
        qs = qs.filter(ouvrage_id__in=list(ouvrage_ids))
    return set(qs.values_list('ouvrage_id', flat=True))


def get_ouvrages_reparation_active_ids(ouvrage_ids=None):
    """Retourne l'ensemble des ouvrage_id ayant une Reparation active."""
    from apps.planning.models_reparations import Reparation

    qs = Reparation.objects.filter(statut__in=REPARATION_STATUTS_ACTIFS)
    if ouvrage_ids is not None:
        qs = qs.filter(ouvrage_id__in=list(ouvrage_ids))
    return set(qs.values_list('ouvrage_id', flat=True))


def get_statuts_fonctionnel_bulk(ouvrage_ids):
    """Calcule le statut fonctionnel d'une liste d'ouvrages (par id).

    Retourne un dict {ouvrage_id: {...}} avec pour chaque ouvrage:
      - fonctionnel (bool)
      - source ('chantier' | 'manuel' | 'defaut')
      - checkbox_modifiable (bool) : False si masquée (chantier actif ou réparation active)
      - chantier_actif (bool)
      - reparation_active (bool)
      - marque_manuel (bool) : valeur brute de la case à cocher

    Chaque clé du dict retourné est EXACTEMENT l'objet passé dans `ouvrage_ids`
    (UUID ou str, peu importe) : les comparaisons internes avec les résultats
    des requêtes (qui renvoient toujours des UUID) sont normalisées en str
    pour éviter tout bug de correspondance UUID vs str.
    """
    from .models import Ouvrage

    ouvrage_ids = [oid for oid in ouvrage_ids if oid]
    if not ouvrage_ids:
        return {}

    id_strs = [str(oid) for oid in ouvrage_ids]

    marques = {
        str(oid): marque
        for oid, marque in Ouvrage.objects.filter(id__in=id_strs).values_list('id', 'marque_non_fonctionnel')
    }
    chantier_ids = {str(oid) for oid in get_ouvrages_chantier_actif_ids(id_strs)}
    reparation_ids = {str(oid) for oid in get_ouvrages_reparation_active_ids(id_strs)}

    resultats = {}
    for ouvrage_id in ouvrage_ids:
        key = str(ouvrage_id)
        marque_manuel = bool(marques.get(key, False))
        chantier_actif = key in chantier_ids
        reparation_active = key in reparation_ids

        if chantier_actif:
            fonctionnel = False
            source = 'chantier'
            checkbox_modifiable = False
        else:
            fonctionnel = not marque_manuel
            source = 'manuel' if marque_manuel else 'defaut'
            checkbox_modifiable = not reparation_active

        resultats[ouvrage_id] = {
            'fonctionnel': fonctionnel,
            'source': source,
            'checkbox_modifiable': checkbox_modifiable,
            'chantier_actif': chantier_actif,
            'reparation_active': reparation_active,
            'marque_manuel': marque_manuel,
        }
    return resultats
