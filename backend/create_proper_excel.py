from apps.billing.models import TarifVolumetrique
from openpyxl import Workbook

# Récupérer un tarif existant
tarif = TarifVolumetrique.objects.first()
print(f'Tarif test: {tarif.id}')
print(f'Ouvrage: {tarif.ouvrage.nom_ouvrage}')

# Créer un fichier Excel avec les BONS noms de colonnes
wb = Workbook()
ws = wb.active
ws.title = "Tranches"

# En-têtes EXACTS selon la configuration
ws.append(['id', 'tarifvolumetrique_id', 'tranchesuperieur', 'tarif'])

# 3 tranches de test (sans ID pour créer de nouvelles)
ws.append(['', str(tarif.id), 5, 500])
ws.append(['', str(tarif.id), 10, 800])
ws.append(['', str(tarif.id), 15, 1200])

# Sauvegarder
test_file = 'test_tranches_correct.xlsx'
wb.save(test_file)
print(f'\nFichier Excel créé avec les bons noms de colonnes: {test_file}')
print('En-têtes: id, tarifvolumetrique_id, tranchesuperieur, tarif')
print(f'\n3 tranches pour le tarif {tarif.id}:')
print('  - 5m³ : 500 Ar/m³')
print('  - 10m³ : 800 Ar/m³')
print('  - 15m³ : 1200 Ar/m³')
