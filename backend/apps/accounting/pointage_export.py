"""
Pointage automatique à l'export d'une ligne DiameXTemporaire vers Access.

Une fois la ligne insérée dans DATA (par l'agent local), Access renvoie son numéro (Id). Ce module le
reporte (avec le PROG de la base) sur tous les objets Hydria qui ont généré la ligne, pour qu'ils
apparaissent comme « comptabilisés » : factures/relevés, paiements forfaitaires, avances, achats,
salaires, demandes et devis de branchement.

Chaque cible est traitée indépendamment du type de transaction : une recette peut être liée à un relevé,
à un paiement forfaitaire (individuel ou groupé) ou à un point d'eau, sans que l'une masque les autres.
Une erreur sur une cible n'empêche jamais les autres, ni l'enregistrement du numéro sur la ligne.
"""
import logging
import re
from datetime import datetime, time

import pytz

logger = logging.getLogger(__name__)
TZ_MADAGASCAR = pytz.timezone('Indian/Antananarivo')

# Description générée par l'encaissement des factures au volume :
#   Paiement au volume "Nom de l'ouvrage" JJ/MM/AAAA (1;2;3)  ou  (8 relevés)
VOLUME_DESCRIPTION_RE = re.compile(r'^Paiement au volume "(.+)" (\d{2}/\d{2}/\d{4}) \((.+)\)$')


def _aware(day):
    """Date -> minuit à Madagascar (règle du projet : tz_madagascar.localize, jamais de datetime naïf)."""
    return TZ_MADAGASCAR.localize(datetime.combine(day, time.min)) if day else None


def _is_bp_request(transaction):
    description = transaction.description or ''
    return transaction.info == 'hydria paiement demande' or 'Paiement demande BP' in description


def _is_bp_quote_payment(transaction):
    description = transaction.description or ''
    return transaction.info == 'hydria paiement devis' or 'Paiement devis BP' in description


def parse_bp_subscriber(description):
    """« Paiement demande BP - NOM (Village) » -> « NOM » ; None si le format n'est pas reconnu."""
    if ' - ' not in (description or ''):
        return None
    part = description.split(' - ')[1]
    if '(' not in part:
        return None
    return part.split('(')[0].strip() or None


def parse_volume_description(description):
    """(nom de l'ouvrage, date JJ/MM/AAAA) ou None."""
    match = VOLUME_DESCRIPTION_RE.match(description or '')
    return (match.group(1), match.group(2)) if match else None


def pointer_transaction(transaction, access_id, prog):
    """
    Reporte `access_id` / `prog` sur les objets liés à `transaction`.

    Retourne {'targets': [(libellé, nombre d'objets mis à jour)], 'warnings': [str]}.
    """
    access_id = int(access_id)
    prog = prog or ''
    targets, warnings = [], []

    def run(label, action):
        try:
            count = action()
        except ValueError as exc:  # cas attendu (cible introuvable) : signalé à l'écran, sans trace
            logger.warning("Pointage %s non effectué (transaction %s) : %s", label, transaction.id, exc)
            warnings.append(f"{label} : {exc}")
            return
        except Exception as exc:  # noqa: BLE001 - une cible en échec ne bloque pas les autres
            logger.exception("Pointage %s impossible (transaction %s)", label, transaction.id)
            warnings.append(f"{label} : {exc}")
            return
        targets.append((label, count))

    # --- Matériel de planning : avance / bon de livraison / recette forfaitaire ---
    detail = transaction.planning_detail
    if detail:
        if transaction.type_transaction == 'avance':
            def point_advance():
                detail.numeroDiameXAvance = access_id
                detail.BaseDiameXAvance = prog
                detail.save(update_fields=['numeroDiameXAvance', 'BaseDiameXAvance'])
                return 1
            run('PlanningDetail (avance)', point_advance)
        else:
            def point_detail():
                detail.numeroDiameX = access_id
                detail.BaseDiameX = prog
                detail.save(update_fields=['numeroDiameX', 'BaseDiameX'])
                return 1
            run('PlanningDetail', point_detail)

    # --- Achat réceptionné (+ mise à jour des prix unitaires des désignations) ---
    purchase = transaction.purchase
    if purchase:
        def point_purchase():
            purchase.numeroDiameX = str(access_id)
            purchase.baseDiameX = prog
            purchase.save(update_fields=['numeroDiameX', 'baseDiameX'])
            _update_designation_prices(purchase)
            return 1
        run('Achat', point_purchase)

    # --- Salaire ---
    salaire = transaction.salaire
    if salaire:
        def point_salary():
            salaire.numero_diamex_salaire = str(access_id)
            salaire.base_diamex_salaire = prog
            salaire.save(update_fields=['numero_diamex_salaire', 'base_diamex_salaire'])
            return 1
        run('Salaire', point_salary)

    # --- Paiements forfaitaires : un seul (FK) et/ou plusieurs (encaissement groupé) ---
    forfait_ids = {str(i) for i in (transaction.paiements_forfaitaires_ids or []) if i}
    if transaction.paiement_forfaitaire_id:
        forfait_ids.add(str(transaction.paiement_forfaitaire_id))
    if forfait_ids:
        def point_forfaits():
            from apps.billing.models import PaiementForfaitaire
            return PaiementForfaitaire.objects.filter(id__in=forfait_ids).update(
                numeroDiameX=str(access_id), baseDiameX=prog)
        run('Paiement(s) forfaitaire(s)', point_forfaits)

    # --- Relevés : encaissement de factures au volume ---
    volume = parse_volume_description(transaction.description)
    if volume and transaction.type_transaction == 'recette':
        def point_readings():
            from apps.billing.models import Releve
            from apps.organization.models import Ouvrage
            ouvrage_ids = list(Ouvrage.objects.filter(nom_ouvrage=volume[0]).values_list('id', flat=True))
            if not ouvrage_ids:
                raise ValueError(f"ouvrage « {volume[0]} » introuvable")
            readings = Releve.objects.filter(
                point_eau__ouvrage_id__in=ouvrage_ids, datepaiement=transaction.date_rec)
            detail_value = (transaction.detail or '').strip()
            if detail_value.startswith('IDXLS:'):
                idxls = [v.strip() for v in detail_value[6:].split(';') if v.strip()]
                readings = readings.filter(point_eau__idxls__in=idxls)
            elif detail_value.startswith('NB_RELEVES:'):
                readings = readings.filter(numeroDiameX__isnull=True)
            return readings.update(numeroDiameX=str(access_id), baseDiameX=prog)
        run(f'Relevés ({volume[0]} {volume[1]})', point_readings)

    # --- Demande / devis de branchement (BP) : retrouvés par le nom de l'abonné ---
    for is_match, label, values in (
        (_is_bp_request(transaction), 'Point d\'eau (demande BP)', lambda: {
            'numerodiamexdemande': access_id, 'basediamexdemande': prog,
            'datepaiementdemande': _aware(transaction.date_rec)}),
        (_is_bp_quote_payment(transaction), 'Point d\'eau (devis BP)', lambda: {
            'numerodiamexpaiementdevis': str(access_id), 'basediamexpaiementdevis': prog,
            'datepaiementdevis': _aware(transaction.date_rec)}),
    ):
        if not is_match:
            continue
        subscriber = parse_bp_subscriber(transaction.description)

        def point_water_point(subscriber=subscriber, values=values):
            from apps.billing.models import PointEau
            if not subscriber:
                raise ValueError("nom de l'abonné introuvable dans la description")
            count = PointEau.objects.filter(nomabonne__iexact=subscriber).update(**values())
            if not count:
                raise ValueError(f"aucun point d'eau pour l'abonné « {subscriber} »")
            return count
        run(label, point_water_point)

    return {'targets': targets, 'warnings': warnings}


def _update_designation_prices(purchase):
    """Aligne le prix unitaire des désignations sur celui de l'achat réceptionné."""
    from apps.inventory.models import PurchaseItem

    for item in PurchaseItem.objects.filter(purchase=purchase).select_related('designation'):
        if item.designation and item.unit_price:
            item.designation.prix_unitaire = item.unit_price
            item.designation.date_prix = purchase.order_date or purchase.purchase_date
            item.designation.save(update_fields=['prix_unitaire', 'date_prix'])


def summarize(result):
    """(libellé pour l'écran, nombre total d'objets pointés) à partir du résultat de pointer_transaction."""
    labels = [f"{label} ×{count}" if count != 1 else label for label, count in result['targets']]
    total = sum(count for _, count in result['targets'])
    if not labels:
        return 'Aucun objet lié à pointer', 0
    return ' + '.join(labels), total
