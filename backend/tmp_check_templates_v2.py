import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.employees.models_grille_template import GrilleSalarialeTemplate

templates = GrilleSalarialeTemplate.objects.all()
print(f"Total templates: {templates.count()}")

for t in templates:
    # Simuler le calcul de la fourchette haute si dynamique
    fh_calc = t.get_fourchette_haute_for_anciennete(t.anciennete_min)
    if t.fourchette_basse > fh_calc:
        print(f"ALERTE: Template '{t.nom_template}' ({t.anciennete_min}-{t.anciennete_max}) a Basse({t.fourchette_basse}) > HauteCalc({fh_calc})")
    else:
        print(f"OK: {t.nom_template} ({t.anciennete_min}-{t.anciennete_max})")
