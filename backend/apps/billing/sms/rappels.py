"""
Rappels SMS de paiement : selection des factures NON pointees a J-3 / J-1 et envoi.

Regle metier essentielle : un SMS n'est envoye que pour une facture non pointee
(couple numeroDiameX + baseDiameX incomplet, meme regle que le widget Hydria).
Les factures anterieures non pointees du meme abonne sont incluses dans le rappel.
"""
import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from .config import reglage
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from .echeances import jour_limite_pour_type, mois_facture_releve, prochaine_date_limite
from .gateway import ErreurPasserelle, envoyer_sms, etat_sms_detail, normaliser_numero
from .messages import construire_messages

logger = logging.getLogger(__name__)

CLE_VERROU_PG = 726204
_verrou_processus = threading.Lock()


class ExecutionEnCours(Exception):
    """Une autre execution des rappels SMS est deja en cours."""


@dataclass(frozen=True)
class FactureDue:
    type: str          # 'releve' | 'forfait'
    id: str
    reference: str     # numero de facture, ou "mois MM/AAAA" quand il est vide
    montant: Decimal
    date_limite: date


@dataclass(frozen=True)
class Abonne:
    point_eau_id: str
    telephone_brut: str
    type_nom: str
    idxls: str
    nom: str


@dataclass
class RappelPlan:
    abonne: Abonne
    type_rappel: str            # "J-3", "J-1"
    date_echeance: date
    courantes: list = field(default_factory=list)
    anterieures: list = field(default_factory=list)

    @property
    def factures(self):
        return list(self.courantes) + list(self.anterieures)

    @property
    def montant_total(self):
        return sum((f.montant for f in self.factures), Decimal('0'))


def est_pointee(numero_diamex, base_diamex):
    """Une facture n'est pointee que si le couple DiameX est complet."""
    return bool(str(numero_diamex or '').strip() and str(base_diamex or '').strip())


def jours_rappel():
    return [int(x) for x in str(reglage('SMS_RAPPEL_JOURS')).split(',') if x.strip()]


# --------------------------------------------------------------------------- chargement

def charger_factures_non_pointees(today):
    """{point_eau_id: (Abonne, [FactureDue])} pour les abonnes joignables ayant des factures non pointees."""
    from apps.billing.models import PaiementForfaitaire, PointEau, Releve
    from apps.core.views_widget import (
        WIDGET_ACCOUNTING_CUTOFF, _is_widget_releve_non_recouvrable, _widget_coupure_periods,
    )

    abonnes, jours = {}, {}
    points = (
        PointEau.objects.select_related('type_point_eau')
        .filter(datearretbranchement__isnull=True)
        .exclude(numeroteleph__isnull=True).exclude(numeroteleph='')
    )
    for p in points:
        jour = jour_limite_pour_type(p.type_point_eau.nom_type if p.type_point_eau else None)
        if jour is None:
            continue
        abonnes[p.id] = Abonne(str(p.id), p.numeroteleph, p.type_point_eau.nom_type,
                               p.idxls or '', p.nomabonne or '')
        jours[p.id] = jour
    if not abonnes:
        return {}

    resultat = {pid: (a, []) for pid, a in abonnes.items()}
    debut_mois = today.replace(day=1)
    periodes = _widget_coupure_periods(list(abonnes))

    releves = (
        Releve.objects.select_related('point_eau')
        .filter(point_eau_id__in=list(abonnes), montant__gt=0, datereleve__gte=date(2025, 12, 1))
        .exclude(remarque__icontains='coupé')
        .filter(Q(numeroDiameX__isnull=True) | Q(numeroDiameX__exact='')
                | Q(baseDiameX__isnull=True) | Q(baseDiameX__exact=''))
    )
    for r in releves:
        if est_pointee(r.numeroDiameX, r.baseDiameX):
            continue
        mois = mois_facture_releve(r.datereleve)
        if not mois or mois < WIDGET_ACCOUNTING_CUTOFF or mois > debut_mois:
            continue
        if _is_widget_releve_non_recouvrable(r, periodes):
            continue
        resultat[r.point_eau_id][1].append(FactureDue(
            'releve', str(r.id), r.numero_facture or f"mois {mois:%m/%Y}", Decimal(r.montant),
            prochaine_date_limite(mois, jours[r.point_eau_id])))

    forfaits = (
        PaiementForfaitaire.objects
        .filter(point_eau_id__in=list(abonnes), montant__gt=0,
                date_facture__gte=WIDGET_ACCOUNTING_CUTOFF, date_facture__lte=today)
        .filter(Q(numeroDiameX__isnull=True) | Q(numeroDiameX__exact='')
                | Q(baseDiameX__isnull=True) | Q(baseDiameX__exact=''))
    )
    for pf in forfaits:
        if est_pointee(pf.numeroDiameX, pf.baseDiameX):
            continue
        resultat[pf.point_eau_id][1].append(FactureDue(
            'forfait', str(pf.id), f"forfait {pf.date_facture:%m/%Y}", Decimal(pf.montant),
            prochaine_date_limite(pf.date_facture, jours[pf.point_eau_id])))

    return {pid: (a, f) for pid, (a, f) in resultat.items() if f}


def apercu(today):
    """Diagnostic (lecture seule) : pourquoi et quand des rappels partiraient-ils ?"""
    from collections import Counter
    from apps.billing.models import PointEau

    points = (PointEau.objects.select_related('type_point_eau')
              .filter(datearretbranchement__isnull=True)
              .exclude(numeroteleph__isnull=True).exclude(numeroteleph=''))
    avec_tel = valides = avec_regle = 0
    for p in points:
        avec_tel += 1
        if normaliser_numero(p.numeroteleph):
            valides += 1
            if jour_limite_pour_type(p.type_point_eau.nom_type if p.type_point_eau else None) is not None:
                avec_regle += 1
    donnees = charger_factures_non_pointees(today)
    par_echeance = Counter()
    for _, factures in donnees.values():
        for date_limite in {f.date_limite for f in factures}:
            par_echeance[date_limite] += 1
    return {
        'points_avec_telephone': avec_tel, 'telephones_valides': valides, 'valides_avec_regle_de_date': avec_regle,
        'abonnes_avec_factures': len(donnees), 'factures': sum(len(f) for _, f in donnees.values()),
        'echeances': sorted(par_echeance.items(), reverse=True),
    }


# --------------------------------------------------------------------------- selection

def selectionner_rappels(donnees, today, jours):
    """Pur (sans base) : un rappel par abonne et par jour J-x, factures anterieures incluses."""
    plans = []
    for j in jours:
        cible = today + timedelta(days=j)
        for abonne, factures in donnees.values():
            courantes = [f for f in factures if f.date_limite == cible]
            if not courantes:
                continue
            anterieures = [f for f in factures if f.date_limite < cible]
            plans.append(RappelPlan(abonne, f"J-{j}", cible, courantes, anterieures))
    return plans


# --------------------------------------------------------------------------- verifications

def ids_toujours_non_pointes(factures):
    """Revérifie en base l'etat de pointage : ensemble des ids encore non pointes."""
    from apps.billing.models import PaiementForfaitaire, Releve
    vivants = set()
    for modele, type_ in ((Releve, 'releve'), (PaiementForfaitaire, 'forfait')):
        ids = [f['id'] if isinstance(f, dict) else f.id for f in factures
               if (f['type'] if isinstance(f, dict) else f.type) == type_]
        if not ids:
            continue
        for pk, numero, base in modele.objects.filter(pk__in=ids).values_list('pk', 'numeroDiameX', 'baseDiameX'):
            if not est_pointee(numero, base):
                vivants.add(str(pk))
    return vivants


def reverifier_plan(plan):
    """Retire les factures pointees depuis la selection ; None s'il ne reste aucune facture courante."""
    vivants = ids_toujours_non_pointes(plan.factures)
    courantes = [f for f in plan.courantes if f.id in vivants]
    if not courantes:
        return None
    return RappelPlan(plan.abonne, plan.type_rappel, plan.date_echeance, courantes,
                      [f for f in plan.anterieures if f.id in vivants])


# --------------------------------------------------------------------------- journal

class SmsLogStore:
    """Acces au journal `sms_log` (remplacable dans les tests)."""

    def existant(self, point_eau_id, date_echeance, type_rappel, partie):
        from apps.billing.models import SmsLog
        return SmsLog.objects.filter(point_eau_id=point_eau_id, date_echeance=date_echeance,
                                     type_rappel=type_rappel, partie=partie).first()

    def enregistrer(self, existant, plan, partie, telephone, message):
        from apps.billing.models import SmsLog
        valeurs = dict(
            telephone=telephone, message=message, montant_total=plan.montant_total,
            statut='en_attente', gateway_id='', erreur='',
            factures=[{'type': f.type, 'id': f.id, 'reference': f.reference,
                       'montant': str(f.montant), 'courante': f in plan.courantes}
                      for f in plan.factures],
        )
        if existant is not None:
            for cle, val in valeurs.items():
                setattr(existant, cle, val)
            existant.save()
            return existant
        return SmsLog.objects.create(point_eau_id=plan.abonne.point_eau_id, date_echeance=plan.date_echeance,
                                     type_rappel=plan.type_rappel, partie=partie, **valeurs)

    def maj(self, ligne, **champs):
        for cle, val in champs.items():
            setattr(ligne, cle, val)
        ligne.save()


class StoreNul:
    """Journal factice du mode test : rien n'est enregistre, aucun anti-doublon n'est consomme."""

    def existant(self, *args):
        return None

    def enregistrer(self, existant, plan, partie, telephone, message):
        return SimpleNamespace(statut='en_attente')

    def maj(self, ligne, **champs):
        pass


def _deja_traite(existant, dry_run):
    """Un rappel deja journalise n'est jamais renvoye ; seule une simulation peut etre rejouee en reel."""
    if existant is None:
        return False
    if existant.statut == 'simule':
        return dry_run
    return True


# --------------------------------------------------------------------------- verrou

@contextmanager
def verrou_execution():
    """Empeche deux executions simultanees (cron, bouton, autre worker) ; leve ExecutionEnCours."""
    if connection.vendor == 'postgresql':
        with connection.cursor() as cur:
            cur.execute('SELECT pg_try_advisory_lock(%s)', [CLE_VERROU_PG])
            if not cur.fetchone()[0]:
                raise ExecutionEnCours('Une execution des rappels SMS est deja en cours.')
        try:
            yield
        finally:
            with connection.cursor() as cur:
                cur.execute('SELECT pg_advisory_unlock(%s)', [CLE_VERROU_PG])
    else:
        if not _verrou_processus.acquire(blocking=False):
            raise ExecutionEnCours('Une execution des rappels SMS est deja en cours.')
        try:
            yield
        finally:
            _verrou_processus.release()


def verrou_libre():
    """True si aucune execution n'est en cours (test non bloquant, verrou relache aussitot)."""
    try:
        with verrou_execution():
            return True
    except ExecutionEnCours:
        return False


# --------------------------------------------------------------------------- execution

def executer_rappels(*, today=None, dry_run=None, jours=None, delai=None, donnees=None,
                     store=None, envoyer=envoyer_sms, reverifier=reverifier_plan, pause=time.sleep,
                     telephone_test=None, limite=None):
    """
    Envoie les rappels J-x. Retourne le bilan {'envoyes', 'simules', 'ignores', 'echecs'}.

    Mode test (`telephone_test`) : tous les SMS vont a ce numero au lieu de celui des abonnes,
    rien n'est journalise (aucun anti-doublon consomme) ; `limite` borne le nombre de rappels.

    Les parametres `donnees`, `store`, `envoyer`, `reverifier` et `pause` permettent de
    tester sans base ni reseau.
    """
    today = today or timezone.localdate()
    dry_run = reglage('SMS_DRY_RUN') if dry_run is None else dry_run
    jours = jours if jours is not None else jours_rappel()
    delai = reglage('SMS_DELAI_SECONDES') if delai is None else delai
    numero_mvola = reglage('SMS_NUMERO_MVOLA')
    if not numero_mvola:
        if not dry_run:
            raise ImproperlyConfigured('SMS_NUMERO_MVOLA doit etre defini pour envoyer de vrais SMS.')
        numero_mvola = '034 00 000 00'
    if telephone_test:
        numero_test = normaliser_numero(telephone_test)
        if not numero_test:
            raise ValueError(f"Numero de test invalide : {telephone_test}")
        store = StoreNul()
        limite = 3 if limite is None else limite
    store = store or SmsLogStore()
    bilan = {'envoyes': 0, 'simules': 0, 'ignores': 0, 'echecs': 0}
    traites = 0

    with verrou_execution():
        if donnees is None:
            donnees = charger_factures_non_pointees(today)
        for plan in selectionner_rappels(donnees, today, jours):
            if limite is not None and traites >= limite:
                break
            telephone = numero_test if telephone_test else normaliser_numero(plan.abonne.telephone_brut)
            if not telephone:
                bilan['ignores'] += 1
                continue
            # Facture pointee entre la selection et l'envoi : pas de SMS
            plan = reverifier(plan)
            if plan is None:
                bilan['ignores'] += 1
                continue
            traites += 1
            _envoyer_plan(plan, telephone, numero_mvola, dry_run, delai, store, envoyer, pause, bilan)
    logger.info('[Rappels SMS] bilan : %s (dry_run=%s)', bilan, dry_run)
    return bilan


def _envoyer_plan(plan, telephone, numero_mvola, dry_run, delai, store, envoyer, pause, bilan):
    echec_precedent = False
    for partie, texte in enumerate(construire_messages(plan, numero_mvola), start=1):
        existant = store.existant(plan.abonne.point_eau_id, plan.date_echeance, plan.type_rappel, partie)
        if _deja_traite(existant, dry_run):
            bilan['ignores'] += 1
            continue
        ligne = store.enregistrer(existant, plan, partie, telephone, texte)
        if echec_precedent:
            continue  # la partie 1 a echoue : la suite reste en attente (bouton « Relancer »)
        try:
            resultat = envoyer(telephone, texte, dry_run)
        except ErreurPasserelle as exc:
            store.maj(ligne, statut='echec', erreur=str(exc))
            bilan['echecs'] += 1
            echec_precedent = True
            continue
        store.maj(ligne, statut='simule' if resultat['simule'] else 'envoye', gateway_id=resultat['id'] or '')
        bilan['simules' if resultat['simule'] else 'envoyes'] += 1
        if not dry_run and delai:
            pause(delai)


def verifier_etats(heures=48):
    """
    Interroge la passerelle sur les SMS journalises « envoye » depuis `heures` heures : ceux que le
    telephone a refuses (etat Failed, ex. RESULT_NO_DEFAULT_SMS_APP) passent en « echec » et
    deviennent relancables. Sans cela, l'historique afficherait « envoye » un SMS jamais parti.
    """
    from apps.billing.models import SmsLog
    depuis = timezone.now() - timedelta(hours=heures)
    bilan = {'controles': 0, 'echecs': 0}
    for ligne in SmsLog.objects.filter(statut='envoye', created_at__gte=depuis).exclude(gateway_id=''):
        etat = etat_sms_detail(ligne.gateway_id)
        if etat is None:
            continue
        bilan['controles'] += 1
        if etat['state'] == 'Failed':
            ligne.statut = 'echec'
            ligne.erreur = etat['error'] or "Echec signale par la passerelle (telephone)."
            ligne.save()
            bilan['echecs'] += 1
    return bilan


def relancer_groupe(ligne, *, dry_run=None, pause=time.sleep):
    """
    Renvoie les SMS non envoyes (echec / en attente) du rappel auquel appartient `ligne`,
    en reutilisant les lignes existantes de sms_log. Refuse si une facture visee a ete pointee.
    Retourne (ok, message_utilisateur).
    """
    from apps.billing.models import SmsLog
    dry_run = reglage('SMS_DRY_RUN') if dry_run is None else dry_run
    with verrou_execution():
        if not dry_run and not reglage('SMS_NUMERO_MVOLA'):
            return False, "SMS_NUMERO_MVOLA n'est pas configure."
        groupe = list(SmsLog.objects.filter(
            point_eau_id=ligne.point_eau_id, date_echeance=ligne.date_echeance,
            type_rappel=ligne.type_rappel, statut__in=('echec', 'en_attente')).order_by('partie'))
        if not groupe:
            return False, "Rien a relancer pour ce rappel."
        factures = groupe[0].factures
        if ids_toujours_non_pointes(factures) != {f['id'] for f in factures}:
            return False, "Une facture concernee a ete pointee depuis l'envoi : le rappel n'a plus lieu d'etre."
        envoyes = 0
        for sms in groupe:
            try:
                resultat = envoyer_sms(sms.telephone, sms.message, dry_run)
            except ErreurPasserelle as exc:
                sms.statut, sms.erreur = 'echec', str(exc)
                sms.save()
                return False, f"Echec de la relance : {exc}"
            sms.statut = 'simule' if resultat['simule'] else 'envoye'
            sms.gateway_id, sms.erreur = resultat['id'] or '', ''
            sms.save()
            envoyes += 1
            if not dry_run and reglage('SMS_DELAI_SECONDES'):
                pause(reglage('SMS_DELAI_SECONDES'))
        return True, f"{envoyes} SMS {'simule(s)' if dry_run else 'renvoye(s)'}."
