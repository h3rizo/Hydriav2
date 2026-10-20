from pathlib import Path
path = Path('backend/templates/inspections/equipment_selection.html')
lines = path.read_text(encoding='utf-8').splitlines()
start = next(i for i,l in enumerate(lines) if '// Sinon, utiliser l\'ancien format' in l)
end = start
