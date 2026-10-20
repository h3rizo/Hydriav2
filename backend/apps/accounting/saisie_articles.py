"""
Detail des articles d'une saisie comptable d'achat (comptes 218 / 601 / 602 / 605).

Une saisie d'achat peut porter sur :
  - des articles qui entrent au stock de la base (Stock + FicheStock, a la validation de la saisie) ;
  - des articles livres directement a un ouvrage, un employe ou un vehicule (hors stock) : la mention
    est portee par le champ « detail » de la saisie et un suivi des restes a livrer est conserve.

Dans les deux cas, le prix saisi met a jour Designation.prix_unitaire / date_prix quand il est plus recent.
"""
from datetime import datetime, time
from decimal import Decimal, InvalidOperation

import pytz
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import SaisieComptableArticle

COMPTES_PREFIXES = ('218', '601', '602', '605')
DETAIL_MAX = 50  # SaisieComptable.detail = CharField(50)
TZ_MADAGASCAR = pytz.timezone('Indian/Antananarivo')
TOLERANCE_TOTAL = Decimal('1.00')


def compte_concerne(compte_code):
    return str(compte_code or '').strip().startswith(COMPTES_PREFIXES)


def _decimal(value, default=None):
    if value in (None, ''):
        return default
    try:
        return Decimal(str(value).replace(',', '.').replace(' ', ''))
    except (InvalidOperation, ValueError):
        return None


def _fmt(value):
    """12.00 -> 12 ; 1.50 -> 1.5"""
    text = f'{Decimal(value):f}'
    return text.rstrip('0').rstrip('.') if '.' in text else text


def _destination(user, dest_type, dest_id):
    """Retourne l'objet destination autorise, ou None."""
    if not dest_id:
        return None
    try:
        if dest_type == 'ouvrage':
            from apps.core.views_ouvrage_interventions import _accessible_ouvrages
            return _accessible_ouvrages(user, include_other_bases=True).filter(id=dest_id).first()
        if dest_type == 'employe':
            from apps.employees.models import Employe
            qs = Employe.objects.all()
            try:
                qs = qs.filter(base__organisation_id=user.employe.base.organisation_id)
            except Exception:
                if not getattr(user, 'is_superuser', False):
                    return None
            return qs.filter(id=dest_id).first()
        if dest_type == 'vehicule':
            from apps.inventory.models import Vehicule
            return Vehicule.objects.filter(id=dest_id).first()
    except (ValidationError, ValueError):
        return None
    return None


def destination_label(ligne):
    if ligne['destination_type'] == 'ouvrage' and ligne['ouvrage']:
        return ligne['ouvrage'].nom_ouvrage
    if ligne['destination_type'] == 'employe' and ligne['employe']:
        e = ligne['employe']
        return getattr(e, 'surnom', '') or e.nom
    if ligne['destination_type'] == 'vehicule' and ligne['vehicule']:
        return ligne['vehicule'].immatriculation
    return ''


def composer_detail(lignes):
    """
    Mention portee par le champ « detail » pour les articles hors stock :
    « Ambanja BP ; RAKOTO (RAL 3) » — RAL = reste a livrer. Tronquee a DETAIL_MAX caracteres.
    """
    par_destination = {}
    for ligne in lignes:
        if ligne['mode'] != SaisieComptableArticle.MODE_HORS_STOCK:
            continue
        label = destination_label(ligne)
        if not label:
            continue
        par_destination[label] = par_destination.get(label, Decimal('0')) + (ligne['quantite'] - ligne['quantite_recue'])
    morceaux = [f'{label} (RAL {_fmt(reste)})' if reste > 0 else label for label, reste in par_destination.items()]
    return ' ; '.join(morceaux)[:DETAIL_MAX]


def parse_articles(raw_articles, user, compte_code, montant_out):
    """
    Valide les lignes d'articles recues du formulaire.
    Retourne (lignes, errors, warnings, rules) ; lignes = dicts normalises (objets Django inclus).
    """
    from apps.planning.models import Designation

    errors, warnings, rules = [], [], []
    lignes = []
    raw_articles = raw_articles if isinstance(raw_articles, list) else []

    if compte_concerne(compte_code):
        rules.append("Compte d'achat : detail des articles (stock ou livraison directe) a renseigner.")
        if not raw_articles:
            warnings.append("Aucun article detaille pour ce compte d'achat (stock / ouvrage / employe / vehicule).")

    total = Decimal('0')
    for index, raw in enumerate(raw_articles, start=1):
        prefix = f'Article {index} : '
        raw = raw if isinstance(raw, dict) else {}
        try:
            designation = Designation.objects.filter(id=raw.get('designation_id'), actif=True).first()
        except (ValidationError, ValueError):
            designation = None
        if not designation:
            errors.append(prefix + 'designation invalide ou inactive.')
            continue

        mode = raw.get('mode') or SaisieComptableArticle.MODE_STOCK
        if mode not in dict(SaisieComptableArticle.MODE_CHOICES):
            errors.append(prefix + 'mode invalide.')
            continue

        quantite = _decimal(raw.get('quantite'))
        if quantite is None or quantite <= 0:
            errors.append(prefix + f'quantite invalide pour « {designation.nom} ».')
            continue
        quantite_recue = _decimal(raw.get('quantite_recue'), default=quantite)
        if quantite_recue is None or quantite_recue < 0 or quantite_recue > quantite:
            errors.append(prefix + f'quantite recue invalide (entre 0 et {_fmt(quantite)}) pour « {designation.nom} ».')
            continue
        prix = _decimal(raw.get('prix_unitaire'))
        if raw.get('prix_unitaire') not in (None, '') and (prix is None or prix < 0):
            errors.append(prefix + f'prix invalide pour « {designation.nom} ».')
            continue

        ligne = {
            'designation': designation, 'mode': mode, 'quantite': quantite, 'quantite_recue': quantite_recue,
            'prix_unitaire': prix, 'destination_type': '', 'ouvrage': None, 'employe': None, 'vehicule': None,
        }
        if mode == SaisieComptableArticle.MODE_HORS_STOCK:
            dest_type = raw.get('destination_type')
            if dest_type not in dict(SaisieComptableArticle.DEST_CHOICES):
                errors.append(prefix + f'destination (ouvrage, employe ou vehicule) obligatoire pour « {designation.nom} ».')
                continue
            cible = _destination(user, dest_type, raw.get('destination_id'))
            if cible is None:
                errors.append(prefix + f'destination introuvable ou non autorisee pour « {designation.nom} ».')
                continue
            ligne['destination_type'] = dest_type
            ligne[dest_type] = cible
        lignes.append(ligne)

        if prix is not None:
            total += quantite * prix
        if quantite_recue < quantite:
            warnings.append(
                f'« {designation.nom} » : reste a livrer {_fmt(quantite - quantite_recue)} '
                f'sur {_fmt(quantite)}.'
            )

    if lignes and total > 0 and montant_out and abs(total - montant_out) > TOLERANCE_TOTAL:
        warnings.append(
            f'Total des articles ({_fmt(total.quantize(Decimal("0.01")))} Ar) different du montant de la saisie '
            f'({_fmt(montant_out)} Ar).'
        )
    return lignes, errors, warnings, rules


def enregistrer_articles(saisie, lignes):
    """Cree les lignes d'articles de la saisie (sans effet de stock : voir appliquer_effets)."""
    for ligne in lignes:
        SaisieComptableArticle.objects.create(
            saisie=saisie,
            designation=ligne['designation'],
            mode=ligne['mode'],
            quantite=ligne['quantite'],
            quantite_recue=ligne['quantite_recue'],
            prix_unitaire=ligne['prix_unitaire'],
            destination_type=ligne['destination_type'],
            ouvrage=ligne['ouvrage'],
            employe=ligne['employe'],
            vehicule=ligne['vehicule'],
        )


def _maj_prix_designation(designation, prix, date_m):
    """Prix de la designation : mis a jour seulement s'il est plus recent (ou si aucun prix n'est date)."""
    if prix is None:
        return
    if designation.date_prix is None or date_m >= designation.date_prix:
        designation.prix_unitaire = prix
        designation.date_prix = date_m
        designation.save(update_fields=['prix_unitaire', 'date_prix'])


def appliquer_effets(saisie):
    """
    Applique les effets des articles d'une saisie VALIDEE : entree en stock + FicheStock (mode stock),
    prix de la designation. Idempotent (appliquee_at). Retourne le nombre de lignes traitees.
    """
    if saisie.statut != 'valide':
        return 0
    from apps.inventory.models import FicheStock, Stock

    traitees = 0
    with transaction.atomic():
        lignes = saisie.articles.select_related('designation').select_for_update().filter(appliquee_at__isnull=True)
        for article in lignes:
            if article.mode == SaisieComptableArticle.MODE_STOCK and article.quantite_recue > 0:
                stock, _ = Stock.objects.select_for_update().get_or_create(
                    designation=article.designation, base=saisie.base,
                    defaults={'current_quantity': Decimal('0')},
                )
                stock.current_quantity = (stock.current_quantity or Decimal('0')) + article.quantite_recue
                stock.save()
                fiche = FicheStock.objects.create(
                    operation_date=TZ_MADAGASCAR.localize(datetime.combine(saisie.date_m, time(8, 0))),
                    operation_type='achat',
                    quantity=article.quantite_recue,
                    unit_price=article.prix_unitaire,
                    reference=f'SAISIE-{str(saisie.id)[:8]}',
                    designation=article.designation,
                    base=saisie.base,
                    employee=saisie.created_by,
                    notes=f'Saisie comptable {saisie.compte_code} - {saisie.description}'[:500],
                )
                article.fiche_stock_id = str(fiche.id)
            _maj_prix_designation(article.designation, article.prix_unitaire, saisie.date_m)
            article.appliquee_at = timezone.now()
            article.save(update_fields=['fiche_stock_id', 'appliquee_at'])
            traitees += 1
    return traitees


class LivraisonError(ValueError):
    """Erreur de livraison exposable telle quelle a l'utilisateur."""


def enregistrer_livraison(article_id, quantite, date_livraison, remarque, employe):
    """
    Enregistre la livraison d'un reste a livrer.
    Mode stock : le stock augmente et une NOUVELLE ligne de fiche de stock est ajoutee (la fiche est un
    journal de mouvements : on ne modifie pas la ligne d'origine). Mode hors stock : suivi seul.
    """
    from apps.inventory.models import FicheStock, Stock
    from .models import LivraisonArticle

    quantite = _decimal(quantite)
    if quantite is None or quantite <= 0:
        raise LivraisonError('Quantite livree invalide.')
    if date_livraison is None:
        raise LivraisonError('Date de livraison invalide.')
    if date_livraison > timezone.localdate():
        raise LivraisonError('La date de livraison ne peut pas etre dans le futur.')

    with transaction.atomic():
        try:
            article = (SaisieComptableArticle.objects.select_for_update(of=('self',))
                       .select_related('saisie', 'saisie__base', 'designation').get(id=article_id))
        except (SaisieComptableArticle.DoesNotExist, ValidationError, ValueError):
            raise LivraisonError('Article introuvable.')
        saisie = article.saisie
        if saisie.statut != 'valide' or article.appliquee_at is None:
            raise LivraisonError("La saisie n'est pas encore validee : aucune livraison possible.")
        reste = article.quantite - article.quantite_recue
        if quantite > reste:
            raise LivraisonError(f'La quantite livree ({_fmt(quantite)}) depasse le reste a livrer ({_fmt(reste)}).')

        fiche_id = ''
        if article.mode == SaisieComptableArticle.MODE_STOCK:
            stock, _ = Stock.objects.select_for_update().get_or_create(
                designation=article.designation, base=saisie.base, defaults={'current_quantity': Decimal('0')})
            stock.current_quantity = (stock.current_quantity or Decimal('0')) + quantite
            stock.save()
            fiche = FicheStock.objects.create(
                operation_date=TZ_MADAGASCAR.localize(datetime.combine(date_livraison, time(8, 0))),
                operation_type='achat', quantity=quantite, unit_price=article.prix_unitaire,
                reference=f'SAISIE-{str(saisie.id)[:8]}', designation=article.designation, base=saisie.base,
                employee=employe,
                notes=f'Complement de livraison (reste a livrer) - saisie {saisie.compte_code} {saisie.description}'[:500],
            )
            fiche_id = str(fiche.id)

        article.quantite_recue = article.quantite_recue + quantite
        article.save(update_fields=['quantite_recue'])
        return LivraisonArticle.objects.create(
            article=article, quantite=quantite, date_livraison=date_livraison,
            remarque=(remarque or '').strip()[:255], fiche_stock_id=fiche_id, created_by=employe,
        )


def annuler_livraison(livraison_id, employe):
    """Annule une livraison : retire la quantite du stock (ligne d'ajustement negative) et retablit le reste."""
    from apps.inventory.models import FicheStock, Stock
    from .models import LivraisonArticle

    with transaction.atomic():
        try:
            livraison = (LivraisonArticle.objects.select_for_update(of=('self',))
                         .select_related('article', 'article__saisie', 'article__saisie__base',
                                         'article__designation').get(id=livraison_id))
        except (LivraisonArticle.DoesNotExist, ValidationError, ValueError):
            raise LivraisonError('Livraison introuvable.')
        if livraison.annulee:
            raise LivraisonError('Cette livraison est deja annulee.')
        article = SaisieComptableArticle.objects.select_for_update(of=('self',)).get(id=livraison.article_id)
        saisie = livraison.article.saisie

        if article.mode == SaisieComptableArticle.MODE_STOCK:
            stock = Stock.objects.select_for_update().filter(
                designation=article.designation, base=saisie.base).first()
            if stock is None or (stock.current_quantity or Decimal('0')) < livraison.quantite:
                raise LivraisonError("Annulation impossible : le stock actuel est inferieur a la quantite livree "
                                     "(deja consommee ?). Corriger par un inventaire.")
            stock.current_quantity = stock.current_quantity - livraison.quantite
            stock.save()
            FicheStock.objects.create(
                operation_date=timezone.now(), operation_type='ajustement', quantity=-livraison.quantite,
                unit_price=article.prix_unitaire, reference=f'SAISIE-{str(saisie.id)[:8]}',
                designation=article.designation, base=saisie.base, employee=employe,
                notes=f'Annulation de livraison du {livraison.date_livraison:%d/%m/%Y} (saisie {saisie.compte_code})'[:500],
            )

        article.quantite_recue = article.quantite_recue - livraison.quantite
        article.save(update_fields=['quantite_recue'])
        livraison.annulee = True
        livraison.annulee_at = timezone.now()
        livraison.annulee_par = employe
        livraison.save(update_fields=['annulee', 'annulee_at', 'annulee_par'])
        return livraison
