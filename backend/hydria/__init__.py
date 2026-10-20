# Import Celery app pour que Django le charge au d�marrage
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    # Celery n'est pas install� - ignorer silencieusement
    pass
