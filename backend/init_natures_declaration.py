"""
Script pour initialiser les natures de déclaration par défaut
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.models import ConfigDeclarationCommunication

# Natures de déclaration courantes
natures = [
    ('Fournitures', 10),
    ('Matériaux', 20),
    ('Services', 30),
    ('Travaux', 40),
    ('Équipements', 50),
    ('Carburant', 60),
    ('Loyer', 70),
    ('Honoraires', 80),
    ('Maintenance', 90),
    ('Transport', 100),
]

print("[LOG] Création des natures de déclaration...")

created = 0
existing = 0

for nom, ordre in natures:
    nature, created_flag = ConfigDeclarationCommunication.objects.get_or_create(
        nom=nom,
        defaults={'ordre': ordre, 'actif': True}
    )

    if created_flag:
        print(f"[OK] Nature créée: {nom} (ordre: {ordre})")
        created += 1
    else:
        print(f"[INFO] Nature existante: {nom}")
        existing += 1

print(f"\n[LOG] Résumé: {created} créées, {existing} existantes")
print(f"[LOG] Total: {ConfigDeclarationCommunication.objects.count()} natures")
