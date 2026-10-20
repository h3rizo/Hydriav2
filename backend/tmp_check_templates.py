import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.employees.models_grille_template import GrilleSalarialeTemplate

for t in GrilleSalarialeTemplate.objects.all():
    print(f"{t.nom_template} ({t.anciennete_min}-{t.anciennete_max}): B={t.fourchette_basse} H={t.fourchette_haute} Mode={t.mode_fourchette_haute} Ref={t.fourchette_haute_reference} Ratio={t.ratio_annuel_haute}")
