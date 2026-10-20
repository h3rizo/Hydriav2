"""
Generation du contenu et envoi du rappel mensuel des factures non pointees
aux responsables d'ouvrage.

Point d'entree unique : envoyer_toutes_les_relances(), utilise par la
commande de gestion, la tache Celery et la page de preview admin (en mode
dry_run pour cette derniere, qui ne touche jamais l'envoi ni la base).
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError
from django.template.loader import render_to_string
from django.utils import timezone

from datetime import date

from .models import RelanceFacturesNonPointees
from .monthly_billing_links import (
    lien_commentaire_point_eau,
    lien_point_eau,
    lien_relance_consolide,
)
from .monthly_billing_reminder import (
    calculer_periode_cible,
    compter_factures_sans_responsable,
    construire_regroupement,
    construire_regroupement_hierarchique,
)

logger = logging.getLogger(__name__)


def _construire_contexte_email(employe, annee, mois, entree_regroupement, est_test):
    """Transforme la structure imbriquee (dicts par id) issue de
    construire_regroupement() en listes ordonnees exploitables par les
    templates, avec les compteurs par point d'eau."""
    _, _, date_fin_periode = calculer_periode_cible(annee, mois)
    periode_date = date(annee, mois, 1)

    ouvrages_liste = []
    total_general = Decimal('0')
    a_un_montant = False
    nb_points_eau = 0
    nb_factures = 0

    for ouvrage_entree in sorted(
        entree_regroupement['ouvrages'].values(),
        key=lambda o: o['ouvrage'].nom_ouvrage,
    ):
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

        ouvrages_liste.append({
            'ouvrage': ouvrage_entree['ouvrage'],
            'points_eau': points_eau_liste,
        })

    return {
        'employe': employe,
        'periode_date': periode_date,
        'date_fin_periode': date_fin_periode,
        'ouvrages': ouvrages_liste,
        'nb_points_eau': nb_points_eau,
        'nb_factures': nb_factures,
        'total_general': total_general if a_un_montant else None,
        'est_test': est_test,
        'site_base_url': getattr(settings, 'SITE_BASE_URL', ''),
        'lien_relance_consolide': lien_relance_consolide(employe.id, annee, mois),
    }, nb_points_eau, nb_factures, (total_general if a_un_montant else None)


def construire_sujet(date_fin_periode, est_test: bool) -> str:
    sujet = f"Hydria — Factures non pointées au {date_fin_periode.strftime('%d/%m/%Y')}"
    if est_test:
        sujet = f"TEST — {sujet}"
    return sujet


def rendre_email(employe, annee, mois, entree_regroupement, est_test=False):
    """Retourne (sujet, corps_texte, corps_html, nb_points_eau, nb_factures, montant_total)."""
    contexte, nb_points_eau, nb_factures, montant_total = _construire_contexte_email(
        employe, annee, mois, entree_regroupement, est_test,
    )
    sujet = construire_sujet(contexte['date_fin_periode'], est_test)
    texte = render_to_string('messaging/emails/rappel_factures_non_pointees.txt', contexte)
    html = render_to_string('messaging/emails/rappel_factures_non_pointees.html', contexte)
    return sujet, texte, html, nb_points_eau, nb_factures, montant_total


def _construire_contexte_email_superieur(superieur, annee, mois, entree_hierarchique, est_test):
    """Meme logique que _construire_contexte_email, mais pour un superieur
    hierarchique : regroupe les subordonnes concernes, chacun avec ses
    propres ouvrages/points d'eau/lignes et son propre lien de commentaire
    (le commentaire reste toujours rattache au responsable direct, jamais
    au superieur)."""
    _, _, date_fin_periode = calculer_periode_cible(annee, mois)
    periode_date = date(annee, mois, 1)

    subordonnes_liste = []
    total_general = Decimal('0')
    a_un_montant = False
    nb_points_eau = 0
    nb_factures = 0

    for sub_entree in sorted(
        entree_hierarchique['subordonnes'].values(),
        key=lambda s: (s['employe'].surnom or s['employe'].nom_employe or ''),
    ):
        subordonne = sub_entree['employe']
        contexte_sub, nb_pe_sub, nb_fact_sub, montant_sub = _construire_contexte_email(
            subordonne, annee, mois, sub_entree, est_test,
        )
        subordonnes_liste.append(contexte_sub)
        nb_points_eau += nb_pe_sub
        nb_factures += nb_fact_sub
        if montant_sub is not None:
            total_general += montant_sub
            a_un_montant = True

    return {
        'employe': superieur,
        'periode_date': periode_date,
        'date_fin_periode': date_fin_periode,
        'subordonnes': subordonnes_liste,
        'nb_subordonnes': len(subordonnes_liste),
        'nb_points_eau': nb_points_eau,
        'nb_factures': nb_factures,
        'total_general': total_general if a_un_montant else None,
        'est_test': est_test,
        'site_base_url': getattr(settings, 'SITE_BASE_URL', ''),
    }, nb_points_eau, nb_factures, (total_general if a_un_montant else None)


def construire_sujet_superieur(date_fin_periode, est_test: bool) -> str:
    sujet = f"Hydria — Pour information — Factures non pointées au {date_fin_periode.strftime('%d/%m/%Y')}"
    if est_test:
        sujet = f"TEST — {sujet}"
    return sujet


def rendre_email_superieur(superieur, annee, mois, entree_hierarchique, est_test=False):
    """Retourne (sujet, corps_texte, corps_html, nb_points_eau, nb_factures, montant_total)
    pour l'email consolide envoye a un superieur hierarchique."""
    contexte, nb_points_eau, nb_factures, montant_total = _construire_contexte_email_superieur(
        superieur, annee, mois, entree_hierarchique, est_test,
    )
    sujet = construire_sujet_superieur(contexte['date_fin_periode'], est_test)
    texte = render_to_string('messaging/emails/rappel_factures_non_pointees_superieur.txt', contexte)
    html = render_to_string('messaging/emails/rappel_factures_non_pointees_superieur.html', contexte)
    return sujet, texte, html, nb_points_eau, nb_factures, montant_total


def enregistrer_trace_facture(employe, annee, mois, est_test, type_destinataire='responsable', **kwargs):
    """
    Enregistre (idempotent hors test) une trace RelanceFacturesNonPointees.
    Fonction publique reutilisable depuis d'autres modules (ex.
    relance_mailer_combine.py) - eviter de dupliquer cette logique
    idempotente get_or_create/IntegrityError ailleurs.
    """
    if est_test:
        return RelanceFacturesNonPointees.objects.create(
            employe=employe, annee=annee, mois=mois, est_test=True,
            type_destinataire=type_destinataire, **kwargs,
        )
    try:
        obj, created = RelanceFacturesNonPointees.objects.get_or_create(
            employe=employe, annee=annee, mois=mois, est_test=False,
            type_destinataire=type_destinataire,
            defaults=kwargs,
        )
        if not created:
            logger.info(
                "Relance deja enregistree pour employe_id=%s mois=%s/%s type=%s (statut existant=%s) — pas de doublon",
                employe.id, mois, annee, type_destinataire, obj.statut,
            )
        return obj
    except IntegrityError:
        logger.info(
            "Course detectee sur relance employe_id=%s mois=%s/%s type=%s — traite par un autre worker",
            employe.id, mois, annee, type_destinataire,
        )
        return RelanceFacturesNonPointees.objects.filter(
            employe=employe, annee=annee, mois=mois, est_test=False,
            type_destinataire=type_destinataire,
        ).first()


# Alias conserve pour compatibilite avec le code existant de ce fichier
# (envoyer_relance_pour_employe/envoyer_relance_pour_superieur) - eviter de
# renommer tous les appels internes deja testes.
_enregistrer_trace = enregistrer_trace_facture


def envoyer_relance_pour_employe(employe, annee, mois, entree_regroupement,
                                  est_test=False, email_test_override=None):
    """
    Envoie (ou tente d'envoyer) UN email de rappel direct pour UN employe
    responsable d'ouvrage, et enregistre la tracabilite. N'interrompt jamais
    le traitement des autres employes en cas d'erreur (isolation complete).
    """
    if not est_test:
        deja_traite = RelanceFacturesNonPointees.objects.filter(
            employe=employe, annee=annee, mois=mois, est_test=False,
            type_destinataire='responsable',
        ).first()
        if deja_traite is not None:
            logger.info(
                "Relance deja traitee pour employe_id=%s mois=%s/%s (statut=%s) — envoi ignore",
                employe.id, mois, annee, deja_traite.statut,
            )
            return deja_traite

    email_reel = (employe.mail or '').strip()
    email_cible = (email_test_override or '').strip() if est_test else email_reel

    if not email_cible:
        logger.warning(
            "Relance factures non pointees : email manquant pour employe_id=%s (mois=%s/%s)",
            employe.id, mois, annee,
        )
        return _enregistrer_trace(
            employe, annee, mois, est_test,
            statut='email_manquant', email_destinataire=None,
        )

    sujet, texte, html, nb_points_eau, nb_factures, montant_total = rendre_email(
        employe, annee, mois, entree_regroupement, est_test=est_test,
    )

    try:
        message = EmailMultiAlternatives(
            subject=sujet,
            body=texte,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email_cible],
        )
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
    except Exception as exc:
        logger.error(
            "Echec envoi relance factures non pointees employe_id=%s mois=%s/%s : %s",
            employe.id, mois, annee, exc, exc_info=True,
        )
        return _enregistrer_trace(
            employe, annee, mois, est_test,
            statut='echec', email_destinataire=email_cible, message_erreur=str(exc),
            nb_points_eau=nb_points_eau, nb_factures=nb_factures, montant_total=montant_total,
        )

    logger.info(
        "Relance factures non pointees envoyee employe_id=%s mois=%s/%s destinataire=%s test=%s",
        employe.id, mois, annee, email_cible, est_test,
    )
    return _enregistrer_trace(
        employe, annee, mois, est_test,
        statut='envoye', email_destinataire=email_cible,
        nb_points_eau=nb_points_eau, nb_factures=nb_factures, montant_total=montant_total,
        date_envoi=timezone.now(),
    )


def envoyer_relance_pour_superieur(superieur, annee, mois, entree_hierarchique,
                                    est_test=False, email_test_override=None):
    """
    Envoie (ou tente d'envoyer) UN email consolide pour information a UN
    superieur hierarchique, et enregistre la tracabilite avec
    type_destinataire='superieur' (n'entre jamais en conflit avec une
    eventuelle relance 'responsable' du meme employe sur la meme periode).
    """
    if not est_test:
        deja_traite = RelanceFacturesNonPointees.objects.filter(
            employe=superieur, annee=annee, mois=mois, est_test=False,
            type_destinataire='superieur',
        ).first()
        if deja_traite is not None:
            logger.info(
                "Relance hierarchique deja traitee pour employe_id=%s mois=%s/%s (statut=%s) — envoi ignore",
                superieur.id, mois, annee, deja_traite.statut,
            )
            return deja_traite

    email_reel = (superieur.mail or '').strip()
    email_cible = (email_test_override or '').strip() if est_test else email_reel

    if not email_cible:
        logger.warning(
            "Relance hierarchique : email manquant pour employe_id=%s (mois=%s/%s)",
            superieur.id, mois, annee,
        )
        return _enregistrer_trace(
            superieur, annee, mois, est_test,
            type_destinataire='superieur',
            statut='email_manquant', email_destinataire=None,
        )

    sujet, texte, html, nb_points_eau, nb_factures, montant_total = rendre_email_superieur(
        superieur, annee, mois, entree_hierarchique, est_test=est_test,
    )

    try:
        message = EmailMultiAlternatives(
            subject=sujet,
            body=texte,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email_cible],
        )
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
    except Exception as exc:
        logger.error(
            "Echec envoi relance hierarchique employe_id=%s mois=%s/%s : %s",
            superieur.id, mois, annee, exc, exc_info=True,
        )
        return _enregistrer_trace(
            superieur, annee, mois, est_test,
            type_destinataire='superieur',
            statut='echec', email_destinataire=email_cible, message_erreur=str(exc),
            nb_points_eau=nb_points_eau, nb_factures=nb_factures, montant_total=montant_total,
        )

    logger.info(
        "Relance hierarchique envoyee employe_id=%s mois=%s/%s destinataire=%s test=%s",
        superieur.id, mois, annee, email_cible, est_test,
    )
    return _enregistrer_trace(
        superieur, annee, mois, est_test,
        type_destinataire='superieur',
        statut='envoye', email_destinataire=email_cible,
        nb_points_eau=nb_points_eau, nb_factures=nb_factures, montant_total=montant_total,
        date_envoi=timezone.now(),
    )


def envoyer_toutes_les_relances(annee=None, mois=None, dry_run=False,
                                 est_test=False, email_test_override=None):
    """
    Point d'entree unique. Retourne un resume :
    {
        'annee', 'mois',
        'nb_responsables', 'nb_superieurs',
        'nb_envoyes', 'nb_echecs', 'nb_email_manquant',
        'factures_sans_responsable',
        'details': [ {employe, type_destinataire, statut, nb_points_eau,
                      nb_factures, montant_total, sujet, texte, html}, ... ],
    }

    Envoie deux vagues d'emails pour la meme periode : d'abord un rappel
    direct a chaque responsable actif d'ouvrage, puis un email consolide
    pour information a chaque superieur hierarchique concerne (regroupant
    tous ses subordonnes ayant eux-memes recu un rappel).

    Si dry_run=True : ne fait AUCUN envoi ni AUCUNE ecriture en base. La
    fonction s'arrete apres le rendu du contenu, garantie structurelle (pas
    seulement conditionnelle) que rien n'est envoye/ecrit en mode preview.
    """
    annee_cible, mois_cible, date_fin_periode = calculer_periode_cible(annee, mois)
    regroupement = construire_regroupement(annee_cible, mois_cible)
    regroupement_hierarchique = construire_regroupement_hierarchique(regroupement, date_fin_periode)
    factures_sans_responsable = compter_factures_sans_responsable(date_fin_periode)

    resultat = {
        'annee': annee_cible,
        'mois': mois_cible,
        'date_fin_periode': date_fin_periode,
        'nb_responsables': len(regroupement),
        'nb_superieurs': len(regroupement_hierarchique),
        'nb_envoyes': 0,
        'nb_echecs': 0,
        'nb_email_manquant': 0,
        'factures_sans_responsable': factures_sans_responsable,
        'details': [],
    }

    for entree in regroupement.values():
        employe = entree['employe']

        if dry_run:
            sujet, texte, html, nb_points_eau, nb_factures, montant_total = rendre_email(
                employe, annee_cible, mois_cible, entree, est_test=est_test,
            )
            resultat['details'].append({
                'employe': employe,
                'type_destinataire': 'responsable',
                'statut': 'apercu',
                'nb_points_eau': nb_points_eau,
                'nb_factures': nb_factures,
                'montant_total': montant_total,
                'sujet': sujet,
                'texte': texte,
                'html': html,
            })
            continue

        trace = envoyer_relance_pour_employe(
            employe, annee_cible, mois_cible, entree,
            est_test=est_test, email_test_override=email_test_override,
        )
        resultat['details'].append({
            'employe': employe,
            'type_destinataire': 'responsable',
            'statut': trace.statut,
            'nb_points_eau': trace.nb_points_eau,
            'nb_factures': trace.nb_factures,
            'montant_total': trace.montant_total,
        })
        if trace.statut == 'envoye':
            resultat['nb_envoyes'] += 1
        elif trace.statut == 'echec':
            resultat['nb_echecs'] += 1
        elif trace.statut == 'email_manquant':
            resultat['nb_email_manquant'] += 1

    for entree_hierarchique in regroupement_hierarchique.values():
        superieur = entree_hierarchique['employe']

        if dry_run:
            sujet, texte, html, nb_points_eau, nb_factures, montant_total = rendre_email_superieur(
                superieur, annee_cible, mois_cible, entree_hierarchique, est_test=est_test,
            )
            resultat['details'].append({
                'employe': superieur,
                'type_destinataire': 'superieur',
                'statut': 'apercu',
                'nb_points_eau': nb_points_eau,
                'nb_factures': nb_factures,
                'montant_total': montant_total,
                'sujet': sujet,
                'texte': texte,
                'html': html,
            })
            continue

        trace = envoyer_relance_pour_superieur(
            superieur, annee_cible, mois_cible, entree_hierarchique,
            est_test=est_test, email_test_override=email_test_override,
        )
        resultat['details'].append({
            'employe': superieur,
            'type_destinataire': 'superieur',
            'statut': trace.statut,
            'nb_points_eau': trace.nb_points_eau,
            'nb_factures': trace.nb_factures,
            'montant_total': trace.montant_total,
        })
        if trace.statut == 'envoye':
            resultat['nb_envoyes'] += 1
        elif trace.statut == 'echec':
            resultat['nb_echecs'] += 1
        elif trace.statut == 'email_manquant':
            resultat['nb_email_manquant'] += 1

    return resultat
