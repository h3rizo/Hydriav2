import re

# Pattern actuel
patterns = [
    r'_Indemnité terrain_(?:.*?_)?(\d{4})\s+(\d{1,2})',
    r'_Indemnité terrain_\s*\d+\s*x\s*[\d\s]+Ar?\s*(?:du\s+(?:\d{1,2}/\d{1,2}/\d{4}|\d+)\s*(?:au\s+\d+)?\s*)?_?(\d{4})\s+(\d{1,2})',
]

# Nouvelle inscription à tester
description = "_CM RANDRIANANTENAINA Alain_Indemnité terrain_2 x 10 000Ar 17 au 18 2025 01"

print(f"Test: {description}\n")

for i, pattern in enumerate(patterns, 1):
    match = re.search(pattern, description)
    if match:
        print(f"Pattern {i} MATCH!")
        print(f"  Année: {match.group(1)}")
        print(f"  Mois: {match.group(2)}")
        break
else:
    print("AUCUN PATTERN NE CORRESPOND")
    print("\nAnalyse:")
    print("  - Format: '2 x 10 000Ar 17 au 18' (sans 'du' avant le jour)")
    print("  - Il faut rendre 'du' optionnel dans le pattern")
