#!/usr/bin/env python
"""
Script pour générer les icônes PWA à partir du SVG source.
Nécessite : pip install cairosvg pillow
"""

import os
from pathlib import Path

# Tailles d'icônes requises pour la PWA
ICON_SIZES = [72, 96, 128, 144, 152, 192, 384, 512]

def generate_icons():
    """Génère toutes les icônes PNG à partir du SVG"""

    # Chemins
    script_dir = Path(__file__).parent
    svg_path = script_dir / 'static' / 'images' / 'icons' / 'icon.svg'
    icons_dir = script_dir / 'static' / 'images' / 'icons'

    # Vérifier que le SVG existe
    if not svg_path.exists():
        print(f"❌ Fichier SVG introuvable: {svg_path}")
        return False

    try:
        import cairosvg
        from PIL import Image
        import io
    except ImportError:
        print("❌ Dépendances manquantes. Installez avec:")
        print("   pip install cairosvg pillow")
        return False

    print(f"📁 Génération des icônes depuis: {svg_path}")
    print(f"📂 Répertoire de sortie: {icons_dir}")
    print()

    # Générer chaque taille
    for size in ICON_SIZES:
        output_path = icons_dir / f'icon-{size}x{size}.png'

        try:
            # Convertir SVG → PNG avec cairosvg
            png_data = cairosvg.svg2png(
                url=str(svg_path),
                output_width=size,
                output_height=size
            )

            # Ouvrir avec Pillow pour vérification
            img = Image.open(io.BytesIO(png_data))

            # Sauvegarder
            img.save(output_path, 'PNG', optimize=True)

            print(f"✅ {output_path.name:20s} - {size}x{size}px - {output_path.stat().st_size:,} bytes")

        except Exception as e:
            print(f"❌ Erreur pour {size}x{size}: {e}")
            return False

    print()
    print("✨ Toutes les icônes ont été générées avec succès!")
    print()
    print("📋 Fichiers créés:")
    for size in ICON_SIZES:
        print(f"   - icon-{size}x{size}.png")

    return True

if __name__ == '__main__':
    success = generate_icons()
    exit(0 if success else 1)
