from django.apps import AppConfig


class PlanningConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.planning'

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from apps.planning.models import DebitSourceMesure
        from apps.planning.services_debit_critique import invalider_cache_debits

        def _invalider(sender, **kwargs):
            invalider_cache_debits()

        post_save.connect(_invalider, sender=DebitSourceMesure, dispatch_uid='debit_source_cache_save')
        post_delete.connect(_invalider, sender=DebitSourceMesure, dispatch_uid='debit_source_cache_delete')
