#!/usr/bin/env python3
"""
Script pour générer les icônes PWA à partir d'une icône Font Awesome
Utilise l'API de Font Awesome pour obtenir le SVG et le convertir en PNG
"""

import os
from PIL import Image, ImageDraw
from io import BytesIO

# Créer le dossier icons s'il n'existe pas
icons_dir = 'static/images/icons'
os.makedirs(icons_dir, exist_ok=True)

# Tailles d'icônes PWA requises
SIZES = [72, 96, 128, 144, 152, 192, 384, 512]

# SVG de l'icône de vase/amphore grec (unicode: f669)
# Utilisation du SVG intégré de Font Awesome
VASE_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512">
  <path fill="#D2691E" d="M192 384c-61.9 0-112-50.1-112-112V96h224v176c0 61.9-50.1 112-112 112zM176 96v96c0 8.8 7.2 16 16 16s16-7.2 16-16V96h-32zM384 64V32c0-17.7-14.3-32-32-32H32C14.3 0 0 14.3 0 32v32c0 17.7 14.3 32 32 32v176c0 97.2 78.8 176 176 176h32v64H80c-26.5 0-48 21.5-48 48v16c0 8.8 7.2 16 16 16h288c8.8 0 16-7.2 16-16v-16c0-26.5-21.5-48-48-48H144v-64h32c97.2 0 176-78.8 176-176V96c17.7 0 32-14.3 32-32z"/>
</svg>'''

def create_icon_from_svg(size, svg_content, output_path):
    """
    Convertit un SVG en PNG avec transparence
    """
    try:
        # Convertir SVG en PNG avec cairosvg
        png_data = cairosvg.svg2png(
            bytestring=svg_content.encode('utf-8'),
            output_width=size,
            output_height=size,
            background_color='transparent'
        )

        # Sauvegarder
        with open(output_path, 'wb') as f:
            f.write(png_data)

        print(f'[OK] Créé: {output_path} ({len(png_data)} bytes)')
        return True

    except Exception as e:
        print(f'[ERREUR] {output_path}: {e}')
        return False

def create_icon_pillow_fallback(size, output_path):
    """
    Méthode de secours si cairosvg n'est pas disponible
    Dessine un vase grec simple avec PIL
    """
    # Créer image avec fond transparent
    img = Image.new('RGBA', (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    # Couleur terre cuite
    color = (210, 105, 30, 255)
    outline_color = (139, 69, 19, 255)

    # Dimensions proportionnelles
    center_x = size // 2
    vase_width = size * 0.5
    vase_height = size * 0.8

    # Corps du vase (ellipse principale)
    top = size * 0.15
    bottom = size * 0.85

    draw.ellipse(
        [center_x - vase_width//2, top,
         center_x + vase_width//2, bottom],
        fill=color,
        outline=outline_color,
        width=max(2, size//100)
    )

    # Col du vase (partie supérieure)
    neck_width = vase_width * 0.3
    neck_height = vase_height * 0.2

    draw.ellipse(
        [center_x - neck_width//2, top - neck_height//2,
         center_x + neck_width//2, top + neck_height],
        fill=color,
        outline=outline_color,
        width=max(1, size//120)
    )

    # Anses (handles) - gauche et droite
    handle_width = vase_width * 0.15
    handle_y_start = top + vase_height * 0.2
    handle_y_end = top + vase_height * 0.5

    # Anse gauche
    draw.arc(
        [center_x - vase_width//2 - handle_width, handle_y_start,
         center_x - vase_width//2 + handle_width, handle_y_end],
        start=90, end=270,
        fill=outline_color,
        width=max(3, size//80)
    )

    # Anse droite
    draw.arc(
        [center_x + vase_width//2 - handle_width, handle_y_start,
         center_x + vase_width//2 + handle_width, handle_y_end],
        start=270, end=90,
        fill=outline_color,
        width=max(3, size//80)
    )

    # Motifs grecs (lignes horizontales)
    motif_y = top + vase_height * 0.4
    motif_width = vase_width * 0.7

    draw.line(
        [center_x - motif_width//2, motif_y,
         center_x + motif_width//2, motif_y],
        fill=outline_color,
        width=max(2, size//100)
    )

    # Sauvegarder
    img.save(output_path, 'PNG')
    print(f'[OK] Créé (fallback): {output_path} ({os.path.getsize(output_path)} bytes)')

def main():
    print("=" * 70)
    print("Génération des icônes PWA avec vase grec Font Awesome")
    print("=" * 70)

    # Vérifier si cairosvg est disponible
    try:
        import cairosvg
        use_svg = True
        print("\n[INFO] cairosvg disponible - utilisation du SVG Font Awesome")
    except ImportError:
        use_svg = False
        print("\n[WARN] cairosvg non disponible - utilisation de PIL (fallback)")
        print("       Pour de meilleurs résultats, installez: pip install cairosvg")

    print("\nGénération des icônes principales...")
    print("-" * 70)

    # Créer toutes les icônes principales
    for size in SIZES:
        output_path = f'{icons_dir}/icon-{size}x{size}.png'

        if use_svg:
            create_icon_from_svg(size, VASE_SVG, output_path)
        else:
            create_icon_pillow_fallback(size, output_path)

    print("\nGénération des icônes de raccourcis...")
    print("-" * 70)

    # Créer les icônes pour les raccourcis (96x96)
    shortcuts = ['feed', 'planning', 'accounting']
    for shortcut in shortcuts:
        output_path = f'{icons_dir}/shortcut-{shortcut}.png'

        if use_svg:
            create_icon_from_svg(96, VASE_SVG, output_path)
        else:
            create_icon_pillow_fallback(96, output_path)

    print("\n" + "=" * 70)
    print(f"✓ Terminé! {len(SIZES) + len(shortcuts)} icônes générées.")
    print("\nPour voir les changements:")
    print("1. Désinstaller l'ancienne PWA de votre appareil")
    print("2. Vider le cache du navigateur (Ctrl+Shift+Del)")
    print("3. Réinstaller la PWA")
    print("=" * 70)

if __name__ == '__main__':
    main()
