#!/usr/bin/env python3
"""
Script pour générer les icônes PWA avec le vase grec HYDRIA
AVEC fond coloré (pas transparent) pour éviter que le navigateur ajoute du blanc
"""

from PIL import Image, ImageDraw
import os

# Créer le dossier icons s'il n'existe pas
icons_dir = 'static/images/icons'
os.makedirs(icons_dir, exist_ok=True)

# Tailles d'icônes PWA requises
SIZES = [72, 96, 128, 144, 152, 192, 384, 512]

# Couleurs du vase grec (style terre cuite)
BACKGROUND_COLOR = (41, 128, 185)  # Bleu hydria (couleur du thème)
VASE_COLOR = (210, 105, 30)  # Chocolat/terre cuite
ACCENT_COLOR = (139, 69, 19)  # Marron foncé pour les détails

def draw_greek_vase(draw, size):
    """
    Dessine un vase grec stylisé (amphore)
    """
    # Échelle relative à la taille
    center_x = size // 2
    center_y = size // 2

    # Dimensions du vase (proportionnelles à la taille)
    vase_width = size * 0.45
    vase_height = size * 0.7

    # Position de départ (en haut)
    top_y = center_y - vase_height // 2
    bottom_y = center_y + vase_height // 2

    # Col du vase
    neck_top = top_y
    neck_bottom = top_y + vase_height * 0.2
    neck_width = vase_width * 0.3

    draw.ellipse(
        [center_x - neck_width//2, neck_top,
         center_x + neck_width//2, neck_top + neck_width],
        fill=VASE_COLOR, outline=ACCENT_COLOR, width=max(1, size//100)
    )

    # Corps principal (ventre de l'amphore)
    body_top = neck_bottom - neck_width//2
    body_bottom = bottom_y - vase_height * 0.15

    draw.ellipse(
        [center_x - vase_width//2, body_top,
         center_x + vase_width//2, body_bottom],
        fill=VASE_COLOR, outline=ACCENT_COLOR, width=max(2, size//80)
    )

    # Base du vase
    base_top = body_bottom - vase_height * 0.1
    base_width = vase_width * 0.4

    draw.ellipse(
        [center_x - base_width//2, base_top,
         center_x + base_width//2, bottom_y],
        fill=VASE_COLOR, outline=ACCENT_COLOR, width=max(1, size//100)
    )

    # Anses (poignées) du vase
    handle_width = vase_width * 0.15
    handle_height = vase_height * 0.35
    handle_top = body_top + vase_height * 0.1

    # Anse gauche
    draw.arc(
        [center_x - vase_width//2 - handle_width, handle_top,
         center_x - vase_width//2 + handle_width//2, handle_top + handle_height],
        start=90, end=270, fill=ACCENT_COLOR, width=max(3, size//60)
    )

    # Anse droite
    draw.arc(
        [center_x + vase_width//2 - handle_width//2, handle_top,
         center_x + vase_width//2 + handle_width, handle_top + handle_height],
        start=270, end=90, fill=ACCENT_COLOR, width=max(3, size//60)
    )

    # Motifs grecs (lignes horizontales)
    motif_y1 = body_top + vase_height * 0.25
    motif_y2 = body_top + vase_height * 0.45
    motif_width = vase_width * 0.7

    draw.line(
        [center_x - motif_width//2, motif_y1,
         center_x + motif_width//2, motif_y1],
        fill=ACCENT_COLOR, width=max(2, size//120)
    )

    draw.line(
        [center_x - motif_width//2, motif_y2,
         center_x + motif_width//2, motif_y2],
        fill=ACCENT_COLOR, width=max(2, size//120)
    )

def create_icon(size):
    """
    Crée une icône PNG avec le vase grec sur fond bleu
    """
    # Créer image avec fond bleu
    img = Image.new('RGB', (size, size), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)

    # Dessiner le vase grec
    draw_greek_vase(draw, size)

    # Sauvegarder
    filename = f'{icons_dir}/icon-{size}x{size}.png'
    img.save(filename, 'PNG')
    print(f'[OK] Créé: {filename} ({os.path.getsize(filename)} bytes)')

def create_shortcut_icons():
    """
    Crée les icônes pour les raccourcis avec couleurs différentes
    """
    shortcuts = [
        ('feed', (241, 196, 15)),      # Orange
        ('planning', (46, 204, 113)),   # Vert
        ('accounting', (52, 152, 219))  # Bleu
    ]

    for name, bg_color in shortcuts:
        img = Image.new('RGB', (96, 96), bg_color)
        draw = ImageDraw.Draw(img)
        draw_greek_vase(draw, 96)

        filename = f'{icons_dir}/shortcut-{name}.png'
        img.save(filename, 'PNG')
        print(f'[OK] Créé: {filename} ({os.path.getsize(filename)} bytes)')

if __name__ == '__main__':
    print("Génération des icônes PWA avec vase grec HYDRIA...")
    print("=" * 60)

    for size in SIZES:
        create_icon(size)

    print("\nGénération des icônes de raccourcis...")
    print("-" * 60)
    create_shortcut_icons()

    print("\n" + "=" * 60)
    print(f"Terminé! {len(SIZES) + 3} icônes générées.")
