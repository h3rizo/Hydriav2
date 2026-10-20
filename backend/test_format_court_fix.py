import re

# Pattern modifié - 'du' devient optionnel
patterns = [
    r'_Indemnité terrain_(?:.*?_)?(\d{4})\s+(\d{1,2})',
    r'_Indemnité terrain_\s*\d+\s*x\s*[\d\s]+Ar?\s*(?:(?:du\s+)?(?:\d{1,2}/\d{1,2}/\d{4}|\d+)\s*(?:au\s+\d+)?\s*)?_?(\d{4})\s+(\d{1,2})',
]

# Tests avec différents formats
tests = [
    "_CM RANDRIANANTENAINA Alain_Indemnité terrain_2 x 10 000Ar 17 au 18 2025 01",  # NOUVEAU - sans 'du'
    "_CM RANDRIANANTENAINA Alain_Indemnité terrain_7 x 10 000Ar du 24/12/2024 au 10 2025 01",  # Avec date complète
    "_CM RANDRIANANTENAINA Alain_Indemnité terrain_13 x 10 000Ar du 06 au 27 2025 02",  # Avec 'du'
]

for description in tests:
    print(f"Test: {description}")
    for i, pattern in enumerate(patterns, 1):
        match = re.search(pattern, description)
        if match:
            print(f"  ✓ Pattern {i} - Année: {match.group(1)}, Mois: {match.group(2)}")
            break
    else:
        print("  ✗ AUCUN MATCH")
    print()
