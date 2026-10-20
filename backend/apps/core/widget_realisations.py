"""
Compteurs « fait » du widget Hydria : ce qui a été réalisé sur le jour, la
semaine ou le mois en cours, comparé à la période précédente À DATE ÉQUIVALENTE
(lundi→mercredi 10 h de cette semaine contre lundi→mercredi 10 h de la semaine
dernière), pour ne pas comparer une période entamée à une période complète.

Deux sources :
  - le journal ConstatRealisation (pointages au volume / forfaitaires, activités
    terminées), alimenté par constater() : ces actions n'ont pas de date fiable ;
  - les indemnités RBF payées (compte 621102), datées par date_m (date du
    mouvement DiameX, donc visibles seulement après l'import DiameX).
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytz
from django.core.cache import cache
from django.db.models import Count, Min, Q, Sum
from django.utils import timezone

TZ_MADAGASCAR = pytz.timezone('Indian/Antananarivo')
PERIODES = ('jour', 'semaine', 'mois')
# Mêmes bornes que les compteurs « reste à faire » du widget (views_widget).
RELEVES_DEPUIS = date(2025, 12, 1)
FORFAITS_DEPUIS = date(2026, 1, 1)
# Les activités terminées sont cherchées parmi celles prévues depuis ce délai.
ACTIVITES_FENETRE_JOURS = 400
COMPTE_INDEMNITES_RBF = '621102'
CACHE_CONSTAT = 'widget-realisations-dernier-constat'
CONSTAT_INTERVALLE_SECONDES = 300

FAMILLES_COMPTEURS = {
    'reparation': 'reparations_terminees',
    'rehabilitation': 'rehabilitations_terminees',
    'installation': 'installations_terminees',
    'autre': 'autres_activites_terminees',
}


def _paire_renseignee(field_numero, field_base):
    return (
        Q(**{f'{field_numero}__isnull': False}) & ~Q(**{field_numero: ''})
        & Q(**{f'{field_base}__isnull': False}) & ~Q(**{field_base: ''})
    )


# --------------------------------------------------------------------------
# État courant : ce qui est « fait » à cet instant
# --------------------------------------------------------------------------

def _etat_pointages_volume():
    from apps.billing.models import Releve

    rows = Releve.objects.filter(
        _paire_renseignee('numeroDiameX', 'baseDiameX'),
        datereleve__gte=RELEVES_DEPUIS,
        montant__gt=0,
    ).values_list('id', 'point_eau__ouvrage_id', 'montant')
    return {str(pk): (ouvrage_id, '', montant) for pk, ouvrage_id, montant in rows}


def _etat_pointages_forfait():
    from apps.billing.models import PaiementForfaitaire

    rows = PaiementForfaitaire.objects.filter(
        _paire_renseignee('numeroDiameX', 'baseDiameX'),
        date_facture__gte=FORFAITS_DEPUIS,
    ).values_list('id', 'point_eau__ouvrage_id', 'montant')
    return {str(pk): (ouvrage_id, '', montant) for pk, ouvrage_id, montant in rows}


def _ouvrage_du_planning(planning):
    if planning.ouvrage_id:
        return planning.ouvrage_id
    for detail in planning.details.all():
        if detail.point_eau_id and detail.point_eau.ouvrage_id:
            return detail.point_eau.ouvrage_id
        if detail.equipement_constitutif_id and detail.equipement_constitutif.ouvrage_id:
            return detail.equipement_constitutif.ouvrage_id
    return None


def _etat_activites_terminees(today):
    """Activités terminées, réparations comprises, hors « Collecte paiement »
    (déjà mesurée par les pointages forfaitaires)."""
    from apps.core.views_ouvrage_interventions import _planning_family
    from apps.planning.models import Planning

    plannings = (
        Planning.objects.filter(
            statut='termine',
            date__gte=timezone.make_aware(
                datetime.combine(today - timedelta(days=ACTIVITES_FENETRE_JOURS), datetime.min.time()),
                TZ_MADAGASCAR,
            ),
        )
        .exclude(type_activite__nomtype='Collecte paiement')
        .select_related('fiche_poste__type_activites', 'type_activite')
        .prefetch_related('details__point_eau', 'details__equipement_constitutif')
    )
    etat = {}
    for planning in plannings.iterator(chunk_size=500):
        etat[str(planning.id)] = (
            _ouvrage_du_planning(planning),
            _planning_family(planning) or 'autre',
            None,
        )
    return etat


def etat_courant(today=None):
    today = today or timezone.now().astimezone(TZ_MADAGASCAR).date()
    return {
        'pointage_volume': _etat_pointages_volume(),
        'pointage_forfait': _etat_pointages_forfait(),
        'activite_terminee': _etat_activites_terminees(today),
    }


# --------------------------------------------------------------------------
# Constat : comparer l'état courant au journal
# --------------------------------------------------------------------------

def reconcilier(constat, est_fait, now):
    """
    Met à jour un constat existant selon l'état courant de son objet et renvoie
    True si le constat a été modifié (il sera alors sauvegardé).

    Deux transitions à traiter :
      - l'objet n'est plus fait (dépointé, activité rouverte) alors que
        constat.retire_le est vide ;
      - l'objet est de nouveau fait alors que constat.retire_le est renseigné.
    Un constat compte dans une période quand constate_le y tombe ET retire_le est vide.
    """
    # Dépointage / réouverture : la réalisation cesse de compter, y compris dans
    # les périodes passées (elle n'était pas réellement acquise).
    if not est_fait and constat.retire_le is None:
        constat.retire_le = now
        return True
    # Repointage : on rétablit la réalisation à sa date d'origine (une ligne
    # initiale reste initiale), pour qu'une correction ne gonfle pas « aujourd'hui ».
    if est_fait and constat.retire_le is not None:
        constat.retire_le = None
        return True
    return False


def constater(now=None, etat=None):
    """
    Enregistre les nouvelles réalisations et les retraits. Le tout premier constat
    d'une catégorie marque l'existant comme « initial » (constate_le NULL), car on
    ignore quand ces objets ont été faits.
    """
    from apps.core.models import ConstatRealisation

    now = now or timezone.now()
    etat = etat if etat is not None else etat_courant(now.astimezone(TZ_MADAGASCAR).date())
    resume = {}
    for categorie, objets in etat.items():
        existants = {
            c.objet_id: c for c in ConstatRealisation.objects.filter(categorie=categorie)
        }
        initial = not existants
        nouveaux = [
            ConstatRealisation(
                categorie=categorie,
                objet_id=objet_id,
                ouvrage_id=ouvrage_id,
                famille=famille,
                montant=montant,
                constate_le=None if initial else now,
            )
            for objet_id, (ouvrage_id, famille, montant) in objets.items()
            if objet_id not in existants
        ]
        ConstatRealisation.objects.bulk_create(nouveaux, ignore_conflicts=True, batch_size=1000)

        modifies = [
            constat for objet_id, constat in existants.items()
            if reconcilier(constat, objet_id in objets, now)
        ]
        ConstatRealisation.objects.bulk_update(
            modifies, ['constate_le', 'retire_le'], batch_size=1000,
        )
        resume[categorie] = {'nouveaux': len(nouveaux), 'modifies': len(modifies), 'initial': initial}
    cache.set(CACHE_CONSTAT, now.isoformat(), None)
    return resume


def constater_si_necessaire(now=None):
    """Constat à la demande depuis l'API, au plus une fois toutes les 5 minutes,
    pour que le compteur « aujourd'hui » vive sans attendre le cron."""
    if cache.add(f'{CACHE_CONSTAT}-verrou', 1, CONSTAT_INTERVALLE_SECONDES):
        return constater(now)
    return None


# --------------------------------------------------------------------------
# Périodes et compteurs
# --------------------------------------------------------------------------

def bornes_periode(periode, now=None):
    """(debut, fin, debut_precedent, fin_precedent), datetimes aware de Madagascar.

    fin = now ; fin_precedent = debut_precedent + (now - debut), sans dépasser
    debut (31 mars contre un février de 28 jours)."""
    if periode not in PERIODES:
        raise ValueError(f'Période inconnue : {periode}')
    now_mg = (now or timezone.now()).astimezone(TZ_MADAGASCAR)
    minuit = TZ_MADAGASCAR.localize(datetime.combine(now_mg.date(), datetime.min.time()))
    if periode == 'jour':
        debut = minuit
        debut_prec = TZ_MADAGASCAR.localize(datetime.combine(now_mg.date() - timedelta(days=1), datetime.min.time()))
    elif periode == 'semaine':
        lundi = now_mg.date() - timedelta(days=now_mg.weekday())
        debut = TZ_MADAGASCAR.localize(datetime.combine(lundi, datetime.min.time()))
        debut_prec = TZ_MADAGASCAR.localize(datetime.combine(lundi - timedelta(days=7), datetime.min.time()))
    else:
        premier = now_mg.date().replace(day=1)
        premier_prec = (premier - timedelta(days=1)).replace(day=1)
        debut = TZ_MADAGASCAR.localize(datetime.combine(premier, datetime.min.time()))
        debut_prec = TZ_MADAGASCAR.localize(datetime.combine(premier_prec, datetime.min.time()))
    # Ecart calculé en temps « mural » de Madagascar (pas de changement d'heure).
    ecoule = now_mg.replace(tzinfo=None) - debut.replace(tzinfo=None)
    fin_prec = min(debut_prec.replace(tzinfo=None) + ecoule, debut.replace(tzinfo=None))
    return debut, now_mg, debut_prec, TZ_MADAGASCAR.localize(fin_prec)


def _jours(debut, fin):
    """Jours civils [premier, dernier] couverts par l'intervalle [debut, fin[ (fin incluse si non minuit)."""
    dernier = fin.date() if fin.time() != datetime.min.time() else fin.date() - timedelta(days=1)
    return debut.date(), max(dernier, debut.date())


def _compter_journal(qs, debut, fin):
    agg = qs.filter(constate_le__gte=debut, constate_le__lt=fin).aggregate(
        nombre=Count('id'), montant=Sum('montant'),
    )
    return agg['nombre'] or 0, float(agg['montant'] or 0)


def _indemnites_rbf(ouvrage_ids, premier_jour, dernier_jour):
    """(nombre, montant) des lignes 621102 payées entre deux dates incluses, rattachées au périmètre."""
    from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
    from apps.accounting.models import BaseDiameX
    from apps.accounting.resolution_memoire import resolution_memoire

    lignes = BaseDiameX.objects.filter(
        compte_code=COMPTE_INDEMNITES_RBF,
        montant_out__gt=0,
        date_m__gte=premier_jour,
        date_m__lte=dernier_jour,
    ).only('description', 'compte_code', 'montant_out')
    nombre, montant = 0, Decimal('0')
    with resolution_memoire():
        for ligne in lignes.iterator(chunk_size=500):
            if ouvrage_ids is not None:
                extraction = extraire_ouvrage_et_mois_generique(ligne.description or '', ligne.compte_code)
                if isinstance(extraction, list):
                    continue
                ouvrage = (extraction or {}).get('ouvrage_obj')
                if not ouvrage or str(ouvrage.id) not in ouvrage_ids:
                    continue
            nombre += 1
            montant += Decimal(str(ligne.montant_out or 0))
    return nombre, float(montant)


def _bloc(courant, precedent):
    return {
        'courant': courant[0],
        'precedent': precedent[0],
        'montant': courant[1],
        'montant_precedent': precedent[1],
    }


def compteurs(periode, ouvrage_ids=None, now=None):
    """Compteurs « fait » sur la période en cours et la période précédente à date équivalente.

    ouvrage_ids : périmètre du widget (None = pas de restriction)."""
    from apps.core.models import ConstatRealisation

    debut, fin, debut_prec, fin_prec = bornes_periode(periode, now)
    scope = None if ouvrage_ids is None else {str(o) for o in ouvrage_ids}
    base = ConstatRealisation.objects.filter(retire_le__isnull=True)
    if scope is not None:
        base = base.filter(ouvrage_id__in=list(scope))

    resultat = {}
    for categorie, cle in (('pointage_volume', 'pointages_volume'), ('pointage_forfait', 'pointages_forfait')):
        qs = base.filter(categorie=categorie)
        resultat[cle] = _bloc(_compter_journal(qs, debut, fin), _compter_journal(qs, debut_prec, fin_prec))
    activites = base.filter(categorie='activite_terminee')
    for famille, cle in FAMILLES_COMPTEURS.items():
        qs = activites.filter(famille=famille)
        resultat[cle] = _bloc(_compter_journal(qs, debut, fin), _compter_journal(qs, debut_prec, fin_prec))
    resultat['indemnites_rbf_payees'] = _bloc(
        _indemnites_rbf(scope, *_jours(debut, fin)),
        _indemnites_rbf(scope, *_jours(debut_prec, fin_prec)),
    )

    suivi_depuis = ConstatRealisation.objects.filter(constate_le__isnull=False).aggregate(
        premier=Min('constate_le'),
    )['premier']
    return {
        'periode': periode,
        'debut': debut.isoformat(),
        'fin': fin.isoformat(),
        'precedente': {'debut': debut_prec.isoformat(), 'fin': fin_prec.isoformat()},
        'compteurs': resultat,
        'dernier_constat': cache.get(CACHE_CONSTAT),
        # Avant cette date, le journal ne sait rien : la période précédente peut être vide à tort.
        'suivi_depuis': suivi_depuis.astimezone(TZ_MADAGASCAR).isoformat() if suivi_depuis else None,
    }
