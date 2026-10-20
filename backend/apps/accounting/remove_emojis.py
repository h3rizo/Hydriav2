import re

# Lire le fichier
with open('views.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Dictionnaire de remplacement emoji -> texte
replacements = {
    '📊': '[LOG]',
    '🔌': '[CONNECT]',
    '✅': '[OK]',
    '❌': '[ERROR]',
    '⏳': '[PROGRESS]',
    '⚠️': '[WARNING]',
    'ℹ️': '[INFO]',
    '📖': '[READ]',
    '💾': '[SAVE]',
    '🔍': '[SEARCH]',
    '📋': '[DATA]',
}

# Remplacer tous les emojis
for emoji, text in replacements.items():
    content = content.replace(emoji, text)

# Écrire le fichier modifié
with open('views.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("[OK] Emojis remplaces avec succes!")
print("Total de remplacements:")
for emoji, text in replacements.items():
    count = content.count(text)
    if count > 0:
        print(f"  {text}: {count} fois")
