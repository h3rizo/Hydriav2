import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.system.models import PageVisit, UserPresence

print("--- 5 dernières visites de pages ---")
visits = PageVisit.objects.all()[:5]
if not visits:
    print("Aucune visite enregistrée pour le moment.")
else:
    for v in visits:
        print(f"[{v.timestamp}] {v.user or 'Anonyme'} -> {v.path}")

print("\n--- Utilisateurs actuellement présents ---")
presences = UserPresence.objects.all()
if not presences:
    print("Aucun utilisateur détecté pour le moment.")
else:
    for p in presences:
        print(f"{p.user.username} sur {p.path} (vu {p.last_seen})")
