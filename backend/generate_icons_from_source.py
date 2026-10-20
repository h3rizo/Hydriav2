#!/usr/bin/env python3
"""
Script pour générer les icônes PWA à partir de icons8-vase-94.png
"""

from PIL import Image
import os

# Créer le dossier icons s'il n'existe pas
icons_dir = 'static/images/icons'
os.makedirs(icons_dir, exist_ok=True)

# Tailles d'icônes PWA requises
SIZES = [72, 96, 128, 144, 152, 192, 384, 512]

# Couleur de fond (bleu Hydria)
BACKGROUND_COLOR = (41, 128, 185)

def create_icon_from_source(source_path, size):
    """
    Crée une icône redimensionnée à partir de l'image source
    """
    # Ouvrir l'image source
    source_img = Image.open(source_path)

    # Convertir en RGBA si nécessaire
    if source_img.mode != 'RGBA':
        source_img = source_img.convert('RGBA')

    # Créer une nouvelle image avec fond coloré
    img = Image.new('RGB', (size, size), BACKGROUND_COLOR)

    # Redimensionner l'image source (garder proportions)
    # Utiliser 80% de la taille pour laisser une marge
    icon_size = int(size * 0.8)
    source_img.thumbnail((icon_size, icon_size), Image.Resampling.LANCZOS)

    # Convertir l'image source en RGB avec le fond bleu
    source_rgb = Image.new('RGB', source_img.size, BACKGROUND_COLOR)
    source_rgb.paste(source_img, (0, 0), source_img if source_img.mode == 'RGBA' else None)

    # Calculer la position pour centrer
    x = (size - source_rgb.width) // 2
    y = (size - source_rgb.height) // 2

    # Coller l'image centrée
    img.paste(source_rgb, (x, y))

    # Sauvegarder
    filename = f'{icons_dir}/icon-{size}x{size}.png'
    img.save(filename, 'PNG', optimize=True)
    print(f'[OK] Créé: {filename} ({os.path.getsize(filename)} bytes)')

def create_shortcut_icons(source_path):
    """
    Crée les icônes pour les raccourcis avec couleurs différentes
    """
    shortcuts = [
        ('feed', (241, 196, 15)),      # Orange
        ('planning', (46, 204, 113)),   # Vert
        ('accounting', (52, 152, 219))  # Bleu
    ]

    source_img = Image.open(source_path)
    if source_img.mode != 'RGBA':
        source_img = source_img.convert('RGBA')

    for name, bg_color in shortcuts:
        img = Image.new('RGB', (96, 96), bg_color)

        # Redimensionner à 70% pour les raccourcis
        icon_size = int(96 * 0.7)
        resized = source_img.copy()
        resized.thumbnail((icon_size, icon_size), Image.Resampling.LANCZOS)

        # Convertir en RGB avec fond coloré
        source_rgb = Image.new('RGB', resized.size, bg_color)
        source_rgb.paste(resized, (0, 0), resized if resized.mode == 'RGBA' else None)

        # Centrer
        x = (96 - source_rgb.width) // 2
        y = (96 - source_rgb.height) // 2
        img.paste(source_rgb, (x, y))

        filename = f'{icons_dir}/shortcut-{name}.png'
        img.save(filename, 'PNG', optimize=True)
        print(f'[OK] Créé: {filename} ({os.path.getsize(filename)} bytes)')

if __name__ == '__main__':
    source_file = 'icons8-vase-94.png'

    if not os.path.exists(source_file):
        print(f"[ERREUR] Fichier source non trouvé: {source_file}")
        exit(1)

    print(f"Génération des icônes PWA depuis {source_file}...")
    print("=" * 60)

    for size in SIZES:
        create_icon_from_source(source_file, size)

    print("\nGénération des icônes de raccourcis...")
    print("-" * 60)
    create_shortcut_icons(source_file)

    print("\n" + "=" * 60)
    print(f"Terminé! {len(SIZES) + 3} icônes générées.")
    print("\nProchaine étape: Vider le cache du navigateur et réinstaller la PWA")