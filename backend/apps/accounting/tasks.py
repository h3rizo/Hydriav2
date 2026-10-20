"""
Point d'entree des taches Celery de l'app accounting.

Celery (`app.autodiscover_tasks()`) importe `apps.accounting.tasks` ; on y
re-exporte les taches definies dans les sous-packages pour qu'elles soient
enregistrees.
"""
from .ai_prefill.tasks import extract_basediamex_scan  # noqa: F401
