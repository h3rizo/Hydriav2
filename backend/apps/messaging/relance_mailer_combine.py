"""
Rendu, re-verification et envoi du rappel combine (paiements non pointes +
reparations echues) - point d'entree unique envoyer_toutes_les_relances_combinees().

Reutilise enregistrer_trace_facture() de monthly_billing_mailer.py pour la
tracabilite RelanceFacturesNonPointees, et definit son equivalent pour
RelanceReparations. La re-verification d'eligibilite (juste avant l'envoi,
jamais figee sur la selection initiale) est le coeur de la garantie
"pas d'email vide, pas de trace fictive" de ce module.
"""
import logging
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from apps.billing.models import PaiementForfaitaire, Releve
from apps.planning.models import Planning

from .models import RelanceFacturesNonPointees, RelanceReparations
from .monthly_billing_links import lien_commentaire_point_eau, lien_point_eau, lien_reparation, lien_relance_consolide
from .monthly_billing_mailer import enregistrer_trace_facture
from .relance_engine import construire_regroupement_combine, trier_ouvrages_par_criticite
from .repair_reminder import GRADES_PANNE, grading_ouvrage_reparations

logger = logging.getLogger(__name__)


def construire_sujet_combine(nb_ouvrages: int, est_test: bool) -> str:
    sujet = f"Hydria — {nb_ouvrages} ouvrage{'s' if nb_ouvrages > 1 else ''} nécessitant votre attention"
    if est_test:
        sujet = f"TEST — {sujet}"
    return sujet


def _reverifier_paiements(ouvrage_entree: dict, date_fin_periode) -> dict:
    """Ne conserve, pour chaque point d'eau de l'ouvrage, que les lignes de
    factures encore reellement non pointees a l'instant present. Retourne
    un nouveau dict points_eau (jamais de mutation en place de la structure
    de selection initiale)."""
    points_eau_valides = {}
    for pe_id, pe_entree in ouvrage_entree['points_eau'].items():
        lignes_valides = []
        for ligne in pe_entree['lignes']:
            objet = ligne['objet']
            if ligne['type'] == 'releve':
                encore_valide = Releve.objects.filter(id=objet.id).filter(
                    Q(numeroDiameX__isnull=True) | Q(numeroDiameX__exact='')
                ).exists()
            else:
                encore_valide = PaiementForfaitaire.objects.filter(id=objet.id).filter(
                    Q(numeroDiameX__isnull=True) | Q(numeroDiameX__exact='')
                    | Q(baseDiameX__isnull=True) | Q(baseDiameX__exact='')
                ).exists()
            if encore_valide:
                lignes_valides.append(ligne)
        if lignes_valides:
            points_eau_valides[pe_id] = {**pe_entree, 'lignes': lignes_valides}
    return points_eau_valides


def _reverifier_reparations(ouvrage_entree: dict, date_reference_reparations) -> list:
    """Ne conserve que les Planning-reparation encore reellement echus
    (date toujours depassee, estvalide toujours falsy) a l'instant present.
    Recalcule aussi le grading ouvrage courant : si l'ouvrage est toujours
    en panne (B_panne/D_panne), le niveau reste force a 'critique', meme si
    le grade a change entre la selection initiale et l'envoi."""
    reparations_valides = []
    ouvrage = ouvrage_entree['ouvrage']
    grading_actuel = None

    for rep_entree in ouvrage_entree['reparations']:
        reparation = rep_entree['reparation']
        encore_valide = (
            Planning.objects
            .filter(id=reparation.id)
            .filter(date__date__lt=date_reference_reparations)
            .filter(Q(estvalide=False) | Q(estvalide__isnull=True))
            .exists()
        )
        if not encore_valide:
            continue

        if grading_actuel is None:
            grading_actuel = grading_ouvrage_reparations(ouvrage.id)
        niveau = rep_entree['niveau']
        if grading_actuel['code'] in GRADES_PANNE:
            niveau = 'critique'

        reparations_valides.append({**rep_entree, 'niveau': niveau, 'grade_ouvrage': grading_actuel})

    return reparations_valides


def _reverifier_eligibilite(entree_destinataire: dict, date_fin_periode, date_reference_reparations) -> dict:
    """
    Reconstruit une entree destinataire "propre" en re-verifiant, ouvrage
    par ouvrage, que chaque paiement et chaque reparation est TOUJOURS
    eligible a l'instant present (pas seulement au moment de la selection
    initiale). Les ouvrages devenus entierement vides sont retires.

    Retourne un nouveau dict {ouvrage_id: {...}} (jamais de mutation de la
    structure de selection initiale).
    """
    ouvrages_valides = {}
    for ouvrage_id, ouvrage_entree in entree_destinataire['ouvrages'].items():
        points_eau_valides = _reverifier_paiements(ouvrage_entree, date_fin_periode)
        reparations_valides = _reverifier_reparations(ouvrage_entree, date_reference_reparations)
        if points_eau_valides or reparations_valides:
            ouvrages_valides[ouvrage_id] = {
                'ouvrage': ouvrage_entree['ouvrage'],
                'points_eau': points_eau_valides,
                'reparations': reparations_valides,
            }
    return ouvrages_valides


def _construire_contexte_email_combine(employe, type_destinataire, ouvrages_valides,
                                        annee, mois, date_fin_periode, est_test):
    """Transforme la structure ouvrage_id -> {...} (deja re-verifiee) en
    listes triees par criticite, exploitables par le template combine."""
    ouvrages_tries = trier_ouvrages_par_criticite(ouvrages_valides)

    ouvrages_contexte = []
    total_general = Decimal('0')
    a_un_montant = False
    nb_points_eau = 0
    nb_factures = 0
    nb_reparations = 0

    for ouvrage_entree in ouvrages_tries:
        points_eau_liste = []
        for pe_entree in sorted(
            ouvrage_entree['points_eau'].values(),
            key=lambda p: p['point_eau'].nomabonne or '',
        ):
            lignes = sorted(pe_entree['lignes'], key=lambda l: l['date'])
            montant_total_pe = None
            for ligne in lignes:
                if ligne['montant'] is not None:
                    montant_total_pe = (montant_total_pe or Decimal('0')) + Decimal(str(ligne['montant']))
                    total_general += Decimal(str(ligne['montant']))
                    a_un_montant = True
            point_eau_id = pe_entree['point_eau'].id
            points_eau_liste.append({
                'point_eau': pe_entree['point_eau'],
                'lignes': lignes,
                'nb_factures': len(lignes),
                'montant_total': montant_total_pe,
                'lien_point_eau': lien_point_eau(point_eau_id),
                'lien_commentaire': lien_commentaire_point_eau(employe.id, annee, mois, point_eau_id),
            })
            nb_points_eau += 1
            nb_factures += len(lignes)

        reparations_liste = sorted(
            ouvrage_entree['reparations'], key=lambda r: -r['jours_retard'],
        )
        for rep_entree in reparations_liste:
            rep_entree['lien_reparation'] = lien_reparation(ouvrage_entree['ouvrage'].id)
        nb_reparations += len(reparations_liste)

        ouvrages_contexte.append({
            'ouvrage': ouvrage_entree['ouvrage'],
            'niveau_ouvrage': ouvrage_entree['niveau_ouvrage'],
            'points_eau': points_eau_liste,
            'reparations': reparations_liste,
        })

    contexte = {
        'employe': employe,
        'type_destinataire': type_destinataire,
        'ouvrages': ouvrages_contexte,
        'nb_ouvrages': len(ouvrages_contexte),
        'nb_points_eau': nb_points_eau,
        'nb_factures': nb_factures,
        'nb_reparations': nb_reparations,
        'total_general': total_general if a_un_montant else None,
        'est_test': est_test,
        'site_base_url': getattr(settings, 'SITE_BASE_URL', ''),
        'lien_relance_consolide': lien_relance_consolide(employe.id, annee, mois),
    }
    return contexte, nb_points_eau, nb_factures, nb_reparations, (total_general if a_un_montant else None)


def rendre_email_combine(employe, type_destinataire, ouvrages_valides, annee, mois,
                          date_fin_periode, est_test=False):
    """Retourne (sujet, texte, html, nb_points_eau, nb_factures,
    nb_reparations, montant_total) pour un destinataire donne, a partir de
    ses ouvrages deja re-verifies."""
    contexte, nb_points_eau, nb_factures, nb_reparations, montant_total = _construire_contexte_email_combine(
        employe, type_destinataire, ouvrages_valides, annee, mois, date_fin_periode, est_test,
    )
    sujet = construire_sujet_combine(contexte['nb_ouvrages'], est_test)
    texte = render_to_string('messaging/emails/situations_attention.txt', contexte)
    html = render_to_string('messaging/emails/situations_attention.html', contexte)
    return sujet, texte, html, nb_points_eau, nb_factures, nb_reparations, montant_total


def _enregistrer_trace_reparation(reparation, employe, type_destinataire, batch_id, est_test, **kwargs):
    """Equivalent de enregistrer_trace_facture() pour RelanceReparations.
    Idempotence sur (reparation, employe, type_destinataire, batch_id).
    Calcule nb_relances/date_premiere_relance par agregation sur les cycles
    anterieurs hors test pour ce triplet (Option A actee : une ligne par
    cycle, jamais d'update en place)."""
    anterieures = RelanceReparations.objects.filter(
        reparation=reparation, employe=employe, type_destinataire=type_destinataire, est_test=False,
    ).order_by('created_at')
    premiere = anterieures.first()
    nb_relances = anterieures.count() + 1
    date_premiere_relance = premiere.date_premiere_relance if premiere else kwargs.get('date_envoi') or timezone.now()

    kwargs = {
        **kwargs,
        'nb_relances': nb_relances,
        'date_premiere_relance': date_premiere_relance,
        'date_derniere_relance': kwargs.get('date_envoi') or timezone.now(),
    }

    if est_test:
        return RelanceReparations.objects.create(
            reparation=reparation, employe=employe, type_destinataire=type_destinataire,
            batch_id=batch_id, est_test=True, **kwargs,
        )
    try:
        obj, created = RelanceReparations.objects.get_or_create(
            reparation=reparation, employe=employe, type_destinataire=type_destinataire,
            batch_id=batch_id, est_test=False,
            defaults=kwargs,
        )
        if not created:
            logger.info(
                "Relance reparation deja enregistree pour reparation_id=%s employe_id=%s type=%s batch=%s — pas de doublon",
                reparation.id, employe.id, type_destinataire, batch_id,
            )
        return obj
    except IntegrityError:
        logger.info(
            "Course detectee sur relance reparation reparation_id=%s employe_id=%s type=%s batch=%s — traite par un autre worker",
            reparation.id, employe.id, type_destinataire, batch_id,
        )
        return RelanceReparations.objects.filter(
            reparation=reparation, employe=employe, type_destinataire=type_destinataire,
            batch_id=batch_id, est_test=False,
        ).first()


def envoyer_relance_pour_destinataire(employe, type_destinataire, ouvrages_selectionnes,
                                       annee, mois, date_fin_periode, date_reference_reparations,
                                       batch_id, est_test=False, email_test_override=None):
    """
    Traite UN destinataire du regroupement combine : re-verifie
    l'eligibilite reelle, envoie (si contenu restant) et trace. Retourne un
    dict resume {statut, nb_points_eau, nb_factures, nb_reparations,
    montant_total} ou None si aucun envoi n'a eu lieu (destinataire vide
    apres re-verification — aucune trace n'est creee dans ce cas).
    """
    ouvrages_valides = _reverifier_eligibilite(
        {'ouvrages': ouvrages_selectionnes}, date_fin_periode, date_reference_reparations,
    )

    if not ouvrages_valides:
        logger.info(
            "Destinataire employe_id=%s vide apres re-verification (mois=%s/%s) — aucun envoi",
            employe.id, mois, annee,
        )
        return None

    email_reel = (employe.mail or '').strip()
    email_cible = (email_test_override or '').strip() if est_test else email_reel

    reparations_du_mail = [
        rep_entree['reparation']
        for ouvrage_entree in ouvrages_valides.values()
        for rep_entree in ouvrage_entree['reparations']
    ]
    ouvrages_avec_paiements = any(o['points_eau'] for o in ouvrages_valides.values())

    if not email_cible:
        logger.warning(
            "Relance combinee : email manquant pour employe_id=%s (mois=%s/%s)",
            employe.id, mois, annee,
        )
        if ouvrages_avec_paiements:
            enregistrer_trace_facture(
                employe, annee, mois, est_test, type_destinataire=type_destinataire,
                statut='email_manquant', email_destinataire=None,
            )
        for reparation in reparations_du_mail:
            _enregistrer_trace_reparation(
                reparation, employe, type_destinataire, batch_id, est_test,
                statut='email_manquant', email_destinataire=None,
            )
        return {'statut': 'email_manquant', 'nb_points_eau': 0, 'nb_factures': 0,
                'nb_reparations': len(reparations_du_mail), 'montant_total': None}

    sujet, texte, html, nb_points_eau, nb_factures, nb_reparations, montant_total = rendre_email_combine(
        employe, type_destinataire, ouvrages_valides, annee, mois, date_fin_periode, est_test=est_test,
    )

    try:
        message = EmailMultiAlternatives(
            subject=sujet, body=texte, from_email=settings.DEFAULT_FROM_EMAIL, to=[email_cible],
        )
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
    except Exception as exc:
        logger.error(
            "Echec envoi relance combinee employe_id=%s mois=%s/%s : %s",
            employe.id, mois, annee, exc, exc_info=True,
        )
        if ouvrages_avec_paiements:
            enregistrer_trace_facture(
                employe, annee, mois, est_test, type_destinataire=type_destinataire,
                statut='echec', email_destinataire=email_cible, message_erreur=str(exc),
                nb_points_eau=nb_points_eau, nb_factures=nb_factures, montant_total=montant_total,
            )
        for reparation in reparations_du_mail:
            _enregistrer_trace_reparation(
                reparation, employe, type_destinataire, batch_id, est_test,
                statut='echec', email_destinataire=email_cible, message_erreur=str(exc),
            )
        return {'statut': 'echec', 'nb_points_eau': nb_points_eau, 'nb_factures': nb_factures,
                'nb_reparations': nb_reparations, 'montant_total': montant_total}

    date_envoi = timezone.now()
    logger.info(
        "Relance combinee envoyee employe_id=%s mois=%s/%s destinataire=%s test=%s ouvrages=%s",
        employe.id, mois, annee, email_cible, est_test, len(ouvrages_valides),
    )
    if ouvrages_avec_paiements:
        enregistrer_trace_facture(
            employe, annee, mois, est_test, type_destinataire=type_destinataire,
            statut='envoye', email_destinataire=email_cible,
            nb_points_eau=nb_points_eau, nb_factures=nb_factures, montant_total=montant_total,
            date_envoi=date_envoi,
        )
    for reparation in reparations_du_mail:
        _enregistrer_trace_reparation(
            reparation, employe, type_destinataire, batch_id, est_test,
            statut='envoye', email_destinataire=email_cible, date_envoi=date_envoi,
        )

    return {'statut': 'envoye', 'nb_points_eau': nb_points_eau, 'nb_factures': nb_factures,
            'nb_reparations': nb_reparations, 'montant_total': montant_total}


def envoyer_toutes_les_relances_combinees(annee=None, mois=None, dry_run=False,
                                           est_test=False, email_test_override=None,
                                           date_reference_reparations=None) -> dict:
    """
    Point d'entree unique du moteur combine. Genere un batch_id (uuid4)
    partage par toutes les RelanceReparations de ce cycle.

    Retourne un resume dict :
    {
        'annee', 'mois', 'date_fin_periode', 'date_reference_reparations', 'batch_id',
        'nb_destinataires', 'nb_envoyes', 'nb_echecs', 'nb_email_manquant',
        'nb_reparations_echues', 'factures_sans_responsable',
        'details': [{employe, type_destinataire, statut, nb_points_eau,
                     nb_factures, nb_reparations, montant_total,
                     sujet?, texte?, html?}, ...],
    }

    Si dry_run=True : retour anticipe structurel apres rendu, aucun envoi ni
    ecriture (meme garantie que le moteur paiements-only existant).
    """
    batch_id = uuid.uuid4()
    (
        regroupement_combine, annee_cible, mois_cible, date_fin_periode,
        date_reference_reparations, factures_sans_responsable,
        reparations_sans_responsable,
    ) = construire_regroupement_combine(annee, mois, date_reference_reparations)

    nb_reparations_echues = sum(
        len(rep_entree['reparations'])
        for entree in regroupement_combine.values()
        for rep_entree in entree['ouvrages'].values()
    ) if regroupement_combine else 0
    # nb_reparations_echues calcule ci-dessus compte les occurrences par
    # destinataire (peut inclure des doublons si une reparation touche
    # plusieurs destinataires) - recalcule proprement via un set d'ids.
    ids_reparations_vues = set()
    for entree in regroupement_combine.values():
        for ouvrage_entree in entree['ouvrages'].values():
            for rep_entree in ouvrage_entree['reparations']:
                ids_reparations_vues.add(rep_entree['reparation'].id)
    nb_reparations_echues = len(ids_reparations_vues)

    resultat = {
        'annee': annee_cible,
        'mois': mois_cible,
        'date_fin_periode': date_fin_periode,
        'date_reference_reparations': date_reference_reparations,
        'batch_id': batch_id,
        'nb_destinataires': len(regroupement_combine),
        'nb_envoyes': 0,
        'nb_echecs': 0,
        'nb_email_manquant': 0,
        'nb_reparations_echues': nb_reparations_echues,
        'factures_sans_responsable': factures_sans_responsable,
        'reparations_sans_responsable': reparations_sans_responsable,
        'details': [],
    }

    for entree in regroupement_combine.values():
        employe = entree['employe']
        type_destinataire = entree['type_destinataire']

        if dry_run:
            ouvrages_valides = _reverifier_eligibilite(entree, date_fin_periode, date_reference_reparations)
            if not ouvrages_valides:
                continue
            sujet, texte, html, nb_pe, nb_fact, nb_rep, montant = rendre_email_combine(
                employe, type_destinataire, ouvrages_valides, annee_cible, mois_cible,
                date_fin_periode, est_test=est_test,
            )
            resultat['details'].append({
                'employe': employe, 'type_destinataire': type_destinataire, 'statut': 'apercu',
                'nb_points_eau': nb_pe, 'nb_factures': nb_fact, 'nb_reparations': nb_rep,
                'montant_total': montant, 'sujet': sujet, 'texte': texte, 'html': html,
            })
            continue

        trace = envoyer_relance_pour_destinataire(
            employe, type_destinataire, entree['ouvrages'], annee_cible, mois_cible,
            date_fin_periode, date_reference_reparations, batch_id,
            est_test=est_test, email_test_override=email_test_override,
        )
        if trace is None:
            continue

        resultat['details'].append({
            'employe': employe, 'type_destinataire': type_destinataire, **trace,
        })
        if trace['statut'] == 'envoye':
            resultat['nb_envoyes'] += 1
        elif trace['statut'] == 'echec':
            resultat['nb_echecs'] += 1
        elif trace['statut'] == 'email_manquant':
            resultat['nb_email_manquant'] += 1

    return resultat
