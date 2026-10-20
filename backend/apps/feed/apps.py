from django.apps import AppConfig


class FeedConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.feed'

    def ready(self):
        """Importer les signaux quand l'app est prête"""
        import apps.feed.signals
