from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import datetime
import pytz
from apps.planning.models import PlanningDetail, BonLivraison
from .models import FicheStock, Purchase, Transfert


def date_to_datetime_madagascar(date_obj):
    """
    Convertit un objet date en datetime avec timezone Madagascar

    Args:
        date_obj: date object ou datetime object

    Returns:
        datetime aware avec timezone Madagascar
    """
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    if date_obj is None:
        return timezone.now()

    # Si c'est déjà un datetime
    if isinstance(date_obj, datetime):
        if timezone.is_aware(date_obj):
            return date_obj.astimezone(tz_madagascar)
        else:
            return tz_madagascar.localize(date_obj)

    # Si c'est une date, créer un datetime à minuit Madagascar
    naive_datetime = datetime.combine(date_obj, datetime.min.time())
    return tz_madagascar.localize(naive_datetime)


@receiver(post_save, sender=PlanningDetail)
def create_fiche_stock_from_livraison(sender, instance, created, **kwargs):
    """
    Signal pour créer automatiquement une FicheStock lors qu'une livraison est effectuée
    """
    # Vérifier si c'est une livraison effectuée (livraison=True)
    # et que la désignation concerne bien une livraison
    if instance.livraison and instance.designation and instance.designation.concerne_livraison:
        # Vérifier si une fiche de stock n'existe pas déjà pour ce planning_detail
        existing_fiche = FicheStock.objects.filter(
            planning_detail_id=str(instance.id)
        ).first()

        if not existing_fiche:
            # Récupérer la base depuis le planning
            base = None
            employe = None
            if hasattr(instance, 'planning') and instance.planning:
                if hasattr(instance.planning, 'employe') and instance.planning.employe:
                    employe = instance.planning.employe
                    if hasattr(employe, 'base'):
                        base = employe.base

            # Si on n'a pas de base, on ne peut pas créer la fiche
            if base:
                FicheStock.objects.create(
                    operation_date=instance.date_livraison or timezone.now(),
                    operation_type='livraison',
                    quantity=instance.quantity,
                    unit_price=instance.pu,
                    planning_detail_id=str(instance.id),
                    designation=instance.designation,
                    base=base,
                    employee=employe,
                    notes=f"Livraison depuis planning {instance.planning.id if instance.planning else 'N/A'}"
                )


@receiver(post_save, sender=Purchase)
def create_fiche_stock_from_purchase(sender, instance, created, **kwargs):
    """
    Signal pour créer automatiquement des FicheStock lors qu'un achat est livré
    """
    if instance.purchase_status in ['livre', 'recu']:
        from .views import _sync_purchase_inventory
        _sync_purchase_inventory(instance)


@receiver(post_save, sender=BonLivraison)
def create_fiche_stock_from_bon_livraison(sender, instance, created, **kwargs):
    """
    Signal pour créer automatiquement une FicheStock lors qu'un bon de livraison est utilisé.
    """
    from .views import _sync_bon_livraison_to_fiche_stock
    _sync_bon_livraison_to_fiche_stock(instance)


@receiver(post_save, sender=Transfert)
def create_fiche_stock_from_transfert(sender, instance, created, **kwargs):
    """
    Signal pour créer automatiquement des FicheStock lors qu'un transfert est reçu
    """
    # Vérifier si le transfert est marqué comme reçu
    if instance.status == 'recu':
        # Récupérer les bases depuis les magasins
        base_origine = instance.magasin_origine.base if instance.magasin_origine else None
        base_destination = instance.magasin_destination.base if instance.magasin_destination else None

        # Récupérer les items du transfert
        for item in instance.items.all():
            # Fiche de sortie pour la base d'origine
            if base_origine:
                existing_sortie = FicheStock.objects.filter(
                    transfert_id=str(instance.id),
                    designation=item.designation,
                    base=base_origine,
                    operation_type='transfert_sortie'
                ).first()

                if not existing_sortie:
                    # Convertir la date en datetime aware
                    operation_date = date_to_datetime_madagascar(instance.transfer_date)

                    FicheStock.objects.create(
                        operation_date=operation_date,
                        operation_type='transfert_sortie',
                        quantity=item.quantity_sent,
                        transfert_id=str(instance.id),
                        designation=item.designation,
                        base=base_origine,
                        employee=instance.initiated_by,
                        reference=instance.transfer_number,
                        notes=f"Transfert {instance.transfer_number} vers {instance.magasin_destination.nom_magasin if instance.magasin_destination else 'N/A'}"
                    )

            # Fiche d'entrée pour la base de destination
            if base_destination:
                existing_entree = FicheStock.objects.filter(
                    transfert_id=str(instance.id),
                    designation=item.designation,
                    base=base_destination,
                    operation_type='transfert_entree'
                ).first()

                if not existing_entree:
                    # Convertir la date en datetime aware
                    operation_date = date_to_datetime_madagascar(
                        instance.actual_arrival_date or instance.transfer_date
                    )

                    FicheStock.objects.create(
                        operation_date=operation_date,
                        operation_type='transfert_entree',
                        quantity=item.quantity_received or item.quantity_sent,
                        transfert_id=str(instance.id),
                        designation=item.designation,
                        base=base_destination,
                        employee=instance.received_by,
                        reference=instance.transfer_number,
                        notes=f"Transfert {instance.transfer_number} depuis {instance.magasin_origine.nom_magasin if instance.magasin_origine else 'N/A'}"
                    )
