import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.employees.models_grille_template import GrilleSalarialeTemplate
from apps.employees.models_revalorisation import GrilleSalariale

def _normalize_choice_value(choices, value, default=None):
    if value in (None, ''):
        return default
    value_str = str(value).strip()
    for key, label in choices:
        if value_str == key or value_str.lower() == str(label).lower():
            return key
    return value_str.lower().replace(' ', '_') # Fallback robust

def repair_data():
    print("[REPAIR] Correction précise des valeurs de choix dans les templates...")
    templates = GrilleSalarialeTemplate.objects.all()
    count = 0
    for t in templates:
        modified = False
        
        # Normalisation de mode_fourchette_haute
        new_mode = _normalize_choice_value(GrilleSalarialeTemplate.MODE_FOURCHETTE_HAUTE_CHOICES, t.mode_fourchette_haute)
        if t.mode_fourchette_haute != new_mode:
            print(f"  Fixing template {t.id}: mode_fourchette_haute '{t.mode_fourchette_haute}' -> '{new_mode}'")
            t.mode_fourchette_haute = new_mode
            modified = True
            
        # Normalisation de mode_ratio_haute
        new_ratio_mode = _normalize_choice_value(GrilleSalarialeTemplate.MODE_RATIO_HAUTE_CHOICES, t.mode_ratio_haute)
        if t.mode_ratio_haute != new_ratio_mode:
            print(f"  Fixing template {t.id}: mode_ratio_haute '{t.mode_ratio_haute}' -> '{new_ratio_mode}'")
            t.mode_ratio_haute = new_ratio_mode
            modified = True
            
        if modified:
            try:
                t.save()
                count += 1
            except Exception as e:
                print(f"  [ERROR] Échec de sauvegarde pour {t.id}: {e}")
            
    print(f"[REPAIR] {count} templates corrigés avec succès.")

if __name__ == "__main__":
    repair_data()
