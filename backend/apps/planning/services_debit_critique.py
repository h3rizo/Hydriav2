"""Etat "debit de source" par ouvrage, partage entre les pages de connaissance.

Source de verite : les calculs de la page /plannings/debits-source/
(`_get_ouvrage_debit_context`, seuils forfaitaire / volumetrique). Ce module
les rejoue une seule fois pour tous les ouvrages mesures, met le resultat en
cache et le rend consultable ouvrage par ouvrage (badges) ou par perimetre
(bandeaux de synthese).

Les ouvrages "AEPG extension" n'ont pas de mesure propre : ils partagent la
source de leur ouvrage de reference et heritent donc de son etat.
"""
from decimal import Decimal

from django.core.cache import cache
from django.urls import reverse

CACHE_KEY = 'debit_source:etats_ouvrages:v1'
CACHE_TTL_SECONDS = 15 * 60

NIVEAU_CRITIQUE = 'critique'
NIVEAU_VIGILANCE = 'vigilance'
NIVEAUX_PRIORITE = {NIVEAU_CRITIQUE: 0, NIVEAU_VIGILANCE: 1}


def _niveau_vigilance(debit, seuil, delta):
    """Debit encore au-dessus du seuil : faut-il deja alerter ?

    debit, seuil : Decimal (L/s), debit >= seuil > 0 ; delta : Decimal ou None.
    Retourne True pour classer l'ouvrage en 'vigilance'.
    """
    # TODO(human)
    return False


def _niveau_debit(mesure, debit_info, delta):
    """Classe la derniere mesure d'un ouvrage : 'critique', 'vigilance' ou None.

    Critique = debit sous le seuil, quelle que soit la modalite :
    - forfaitaire/mixte : 0.05 L/s x nb BF
    - volume : debit de pointe (2 x debit moyen du mois le plus charge)
    """
    seuil = debit_info.get('seuil_minimum')
    if mesure.debit_l_s is None or seuil is None:
        return None
    seuil = Decimal(str(seuil))
    if seuil <= 0:
        return None
    debit = Decimal(str(mesure.debit_l_s))
    if debit < seuil:
        return NIVEAU_CRITIQUE
    if _niveau_vigilance(debit, seuil, delta):
        return NIVEAU_VIGILANCE
    return None


def _calculer_etats():
    from apps.organization.models import Ouvrage
    from apps.planning.models import DebitSourceMesure
    from apps.planning.views import _get_ouvrage_debit_context

    dernieres = (
        DebitSourceMesure.objects.select_related('ouvrage', 'ouvrage__type_ouvrage')
        .order_by('ouvrage_id', '-date_visite', '-created_at')
        .distinct('ouvrage_id')
    )

    etats = {}
    for mesure in dernieres:
        precedente = (
            DebitSourceMesure.objects.filter(
                ouvrage_id=mesure.ouvrage_id,
                date_visite__lt=mesure.date_visite,
            ).order_by('-date_visite', '-created_at').only('debit_l_s').first()
        )
        delta = None
        if precedente and precedente.debit_l_s is not None and mesure.debit_l_s is not None:
            delta = Decimal(str(mesure.debit_l_s)) - Decimal(str(precedente.debit_l_s))

        debit_info = _get_ouvrage_debit_context(mesure.ouvrage, mesure.date_visite)
        niveau = _niveau_debit(mesure, debit_info, delta)
        if not niveau:
            continue

        seuil = Decimal(str(debit_info['seuil_minimum']))
        debit = Decimal(str(mesure.debit_l_s))
        oid = str(mesure.ouvrage_id)
        etats[oid] = {
            'niveau': niveau,
            'ouvrage_id': oid,
            'ouvrage_nom': mesure.ouvrage.nom_ouvrage,
            'source_ouvrage_id': oid,
            'source_ouvrage_nom': mesure.ouvrage.nom_ouvrage,
            'herite': False,
            'debit_l_s': float(debit),
            'seuil_l_s': float(seuil),
            'ratio_pct': int(round(debit / seuil * 100)),
            'delta_l_s': float(delta) if delta is not None else None,
            'date_visite': mesure.date_visite.strftime('%d/%m/%Y'),
            'mode_paiement': debit_info.get('mode_paiement'),
        }

    if etats:
        extensions = Ouvrage.objects.filter(
            ouvrage_source_id__in=list(etats.keys()),
            type_ouvrage__nom_type_ouvrage__iexact='AEPG extension',
        ).only('id', 'nom_ouvrage', 'ouvrage_source_id')
        for extension in extensions:
            eid = str(extension.id)
            if eid in etats:
                continue
            etats[eid] = {
                **etats[str(extension.ouvrage_source_id)],
                'ouvrage_id': eid,
                'ouvrage_nom': extension.nom_ouvrage,
                'herite': True,
            }

    return etats


def get_etats_debit_ouvrages():
    """{ouvrage_id (str): etat} pour les ouvrages en critique/vigilance."""
    etats = cache.get(CACHE_KEY)
    if etats is None:
        try:
            etats = _calculer_etats()
        except Exception:  # noqa: BLE001 - information secondaire : ne jamais casser une page hote
            import logging
            logging.getLogger(__name__).exception("Calcul des etats de debit source impossible")
            return {}
        cache.set(CACHE_KEY, etats, CACHE_TTL_SECONDS)
    return etats


def get_etat_debit(ouvrage_id):
    if not ouvrage_id:
        return None
    return get_etats_debit_ouvrages().get(str(ouvrage_id))


def ids_ouvrages_par_niveau(niveau=NIVEAU_CRITIQUE):
    return [oid for oid, etat in get_etats_debit_ouvrages().items() if etat['niveau'] == niveau]


def resumer_debits(ouvrage_ids):
    """Synthese des alertes debit sur un perimetre d'ouvrages (ids UUID ou str)."""
    etats = get_etats_debit_ouvrages()
    items = [etats[oid] for oid in {str(o) for o in ouvrage_ids or []} if oid in etats]
    items.sort(key=lambda e: (
        NIVEAUX_PRIORITE.get(e['niveau'], 9),
        e['ratio_pct'],
        e['ouvrage_nom'] or '',
    ))
    return {
        'items': items,
        'critique_count': sum(1 for e in items if e['niveau'] == NIVEAU_CRITIQUE),
        'vigilance_count': sum(1 for e in items if e['niveau'] == NIVEAU_VIGILANCE),
        'page_url': reverse('planning:debit_source') + '?evolution=critique',
    }


def invalider_cache_debits():
    cache.delete(CACHE_KEY)
