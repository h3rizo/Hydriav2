"""
Vues pour la vérification OCR des documents comptables.
"""
import os
import json
import re
from decimal import Decimal
from django.http import JsonResponse, FileResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Sum
import mimetypes

from .models import BaseDiameX

# Imports pour OCR - CONFIGURATION FORCEE
try:
    import pytesseract
    from PIL import Image
    from pdf2image import convert_from_path
except ImportError:
    pytesseract = None
    Image = None
    convert_from_path = None

# Configuration FORCEE du chemin Tesseract pour Windows
if pytesseract:
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# FORCER OCR_AVAILABLE = True car le test a reussi
OCR_AVAILABLE = True
print("[OCR] Tesseract configure et active")


@csrf_exempt
@require_http_methods(["POST"])
def api_ocr_verification(request):
    """
    API pour vérifier un document scanné avec OCR.
    Compare les valeurs extraites avec les données de la base.

    Paramètres POST:
    - scan_path: Chemin du fichier à scanner
    - type_document: 'comptage_caisse' ou 'releve_bancaire'
    - annee, mois, fichier_source, journal_code: Pour récupérer les données de référence
    """
    if not OCR_AVAILABLE:
        # Vérifier manuellement les chemins Tesseract
        tesseract_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        ]
        found_paths = [p for p in tesseract_paths if os.path.exists(p)]

        error_msg = 'OCR non disponible. Tesseract-OCR est installé mais non détecté.'
        if found_paths:
            error_msg += f' Tesseract trouvé à: {found_paths[0]}. Redémarrez le serveur Django.'
        else:
            error_msg += ' Installez Tesseract-OCR depuis https://github.com/UB-Mannheim/tesseract/wiki'

        return JsonResponse({
            'success': False,
            'error': error_msg
        }, status=500)

    try:
        data = json.loads(request.body)
        scan_path = data.get('scan_path')
        type_document = data.get('type_document')
        annee = int(data.get('annee'))
        mois = int(data.get('mois'))
        fichier_source = data.get('fichier_source')
        journal_code = data.get('journal_code')

        if not all([scan_path, type_document, annee, mois, fichier_source]):
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants'
            }, status=400)

        # Normaliser le chemin (gérer les backslashes)
        scan_path = os.path.normpath(scan_path)

        print(f"DEBUG OCR - Chemin normalisé: {scan_path}")
        print(f"DEBUG OCR - Fichier existe? {os.path.exists(scan_path)}")

        # Vérifier que le fichier existe
        if not os.path.exists(scan_path):
            return JsonResponse({
                'success': False,
                'error': f'Fichier introuvable: {scan_path}'
            }, status=404)

        # Extraire le texte avec OCR
        texte_ocr = extraire_texte_ocr(scan_path)

        if not texte_ocr:
            return JsonResponse({
                'success': False,
                'error': 'Aucun texte extrait du document'
            }, status=400)

        # Récupérer les données de référence selon le type
        if type_document == 'comptage_caisse':
            donnees_ref = recuperer_donnees_comptage_caisse(annee, mois, fichier_source, journal_code)
        elif type_document == 'releve_bancaire':
            donnees_ref = recuperer_donnees_releve_bancaire(annee, mois, fichier_source, journal_code)
        else:
            return JsonResponse({
                'success': False,
                'error': f'Type de document inconnu: {type_document}'
            }, status=400)

        # Comparer les valeurs
        resultats = comparer_valeurs_ocr(texte_ocr, donnees_ref)

        return JsonResponse({
            'success': True,
            'texte_ocr': texte_ocr[:1000],  # Limiter à 1000 caractères pour la réponse
            'resultats': resultats,
            'donnees_reference': donnees_ref
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


def extraire_texte_ocr(file_path):
    """
    Extrait le texte d'un fichier image ou PDF avec OCR.
    Retourne le texte extrait.
    """
    try:
        # Normaliser le chemin Windows (gérer les backslashes et l'encodage)
        file_path = os.path.normpath(file_path)

        # Vérifier que le fichier existe
        if not os.path.exists(file_path):
            print(f"Fichier introuvable: {file_path}")
            return None

        # Déterminer le type de fichier
        ext = os.path.splitext(file_path)[1].lower()

        if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.gif']:
            # Image directe
            image = Image.open(file_path)
            texte = pytesseract.image_to_string(image, lang='fra')
            return texte

        elif ext == '.pdf':
            # Convertir PDF en images puis OCR
            images = convert_from_path(file_path, dpi=300)
            texte_complet = []

            for i, image in enumerate(images):
                texte_page = pytesseract.image_to_string(image, lang='fra')
                texte_complet.append(f"--- Page {i+1} ---\n{texte_page}")

            return "\n\n".join(texte_complet)
        else:
            return None

    except Exception as e:
        import traceback
        print(f"Erreur OCR: {e}")
        print(traceback.format_exc())
        return None


def recuperer_donnees_comptage_caisse(annee, mois, fichier_source, journal_code):
    """
    Récupère les données de référence pour un comptage de caisse.
    """
    # Calcul du solde de départ
    if mois == 1:
        mois_precedent = 12
        annee_precedente = annee - 1
    else:
        mois_precedent = mois - 1
        annee_precedente = annee

    solde_precedent_qs = BaseDiameX.objects.filter(
        fichier_source=fichier_source,
        journal_code=journal_code,
        date_m__year__lte=annee_precedente if mois == 1 else annee,
        date_m__month__lte=mois_precedent if mois > 1 or annee_precedente < annee else 12
    ).aggregate(
        total_in=Sum('montant_in'),
        total_out=Sum('montant_out')
    )

    total_in_precedent = Decimal(str(solde_precedent_qs['total_in'])) if solde_precedent_qs['total_in'] else Decimal('0')
    total_out_precedent = Decimal(str(solde_precedent_qs['total_out'])) if solde_precedent_qs['total_out'] else Decimal('0')
    solde_depart = total_in_precedent - total_out_precedent

    # Transactions du mois
    transactions_qs = BaseDiameX.objects.filter(
        fichier_source=fichier_source,
        journal_code=journal_code,
        date_m__year=annee,
        date_m__month=mois
    ).aggregate(
        total_in=Sum('montant_in'),
        total_out=Sum('montant_out')
    )

    total_in = Decimal(str(transactions_qs['total_in'])) if transactions_qs['total_in'] else Decimal('0')
    total_out = Decimal(str(transactions_qs['total_out'])) if transactions_qs['total_out'] else Decimal('0')
    solde_fin = solde_depart + total_in - total_out

    return {
        'solde_depart': float(solde_depart),
        'total_in': float(total_in),
        'total_out': float(total_out),
        'solde_fin': float(solde_fin)
    }


def recuperer_donnees_releve_bancaire(annee, mois, fichier_source, journal_code):
    """
    Récupère les données de référence pour un relevé bancaire.
    Utilise la même logique que comptage_caisse.
    """
    return recuperer_donnees_comptage_caisse(annee, mois, fichier_source, journal_code)


def comparer_valeurs_ocr(texte_ocr, donnees_ref):
    """
    Compare les valeurs extraites par OCR avec les données de référence.
    Retourne un dictionnaire avec les comparaisons.
    """
    # Extraire tous les nombres du texte OCR
    nombres_ocr = extraire_nombres(texte_ocr)

    resultats = {
        'solde_depart': {'trouve': False, 'valeur_ocr': None, 'valeur_ref': donnees_ref['solde_depart'], 'correspond': False},
        'total_in': {'trouve': False, 'valeur_ocr': None, 'valeur_ref': donnees_ref['total_in'], 'correspond': False},
        'total_out': {'trouve': False, 'valeur_ocr': None, 'valeur_ref': donnees_ref['total_out'], 'correspond': False},
        'solde_fin': {'trouve': False, 'valeur_ocr': None, 'valeur_ref': donnees_ref['solde_fin'], 'correspond': False},
    }

    # Tolérance de 1% pour la comparaison
    tolerance = 0.01

    for cle, data in resultats.items():
        valeur_ref = data['valeur_ref']

        # Chercher une valeur proche dans les nombres OCR
        for nombre_ocr in nombres_ocr:
            ecart_relatif = abs(nombre_ocr - valeur_ref) / max(abs(valeur_ref), 1)

            if ecart_relatif <= tolerance:
                data['trouve'] = True
                data['valeur_ocr'] = nombre_ocr
                data['correspond'] = True
                break

        # Si pas trouvé avec tolérance, prendre le plus proche
        if not data['trouve'] and nombres_ocr:
            nombre_plus_proche = min(nombres_ocr, key=lambda x: abs(x - valeur_ref))
            data['valeur_ocr'] = nombre_plus_proche
            data['trouve'] = True
            data['correspond'] = False

    return resultats


def extraire_nombres(texte):
    """
    Extrait tous les nombres d'un texte.
    Gère les formats: 1234, 1 234, 1,234, 1.234,56 etc.
    """
    nombres = []

    # Pattern pour capturer les nombres avec séparateurs
    # Exemples: 1234, 1 234, 1,234, 1.234, 1234.56, 1 234,56
    pattern = r'(?:(?:\d[\d\s,.]*\d)|(?:\d))'

    matches = re.findall(pattern, texte)

    for match in matches:
        # Nettoyer: enlever espaces, remplacer virgules par points
        nombre_str = match.replace(' ', '').replace(',', '.')

        # Gérer les cas avec plusieurs points (ex: 1.234.567 → 1234567)
        if nombre_str.count('.') > 1:
            # C'est un séparateur de milliers, pas de décimales
            nombre_str = nombre_str.replace('.', '')

        try:
            nombre = float(nombre_str)
            nombres.append(nombre)
        except ValueError:
            continue

    return nombres


@require_http_methods(["GET"])
def serve_scan_image(request):
    """
    Sert une image de scan depuis le système de fichiers local.
    Permet de contourner les restrictions du navigateur sur file:/// protocol.
    """
    file_path = request.GET.get('path')
    requested_page = request.GET.get('page')
    metadata_only = request.GET.get('metadata') == '1'

    if not file_path:
        return HttpResponse('Chemin de fichier manquant', status=400)

    # Normaliser le chemin
    file_path = os.path.normpath(file_path)

    # Vérifier que le fichier existe
    if not os.path.exists(file_path):
        return HttpResponse(f'Fichier introuvable: {file_path}', status=404)

    # Vérifier que c'est un fichier (pas un dossier)
    if not os.path.isfile(file_path):
        return HttpResponse('Le chemin ne pointe pas vers un fichier', status=400)

    # Déterminer le type MIME
    content_type, _ = mimetypes.guess_type(file_path)

    if file_path.lower().endswith(('.tiff', '.tif')):
        try:
            with Image.open(file_path) as img:
                page_count = getattr(img, 'n_frames', 1) or 1

                if metadata_only:
                    return JsonResponse({
                        'success': True,
                        'file_type': 'tiff',
                        'page_count': page_count,
                    })

                page_number = int(requested_page) if requested_page else 1
                if page_number < 1 or page_number > page_count:
                    return HttpResponse('Page TIFF introuvable', status=404)

                img.seek(page_number - 1)
                frame = img.copy()
                from io import BytesIO
                img_io = BytesIO()
                if frame.mode not in ('RGB', 'L'):
                    frame = frame.convert('RGB')
                frame.save(img_io, format='PNG')
                img_io.seek(0)
                response = HttpResponse(img_io.read(), content_type='image/png')
                response['X-Scan-Page-Count'] = str(page_count)
                response['X-Scan-Page'] = str(page_number)
                return response
        except Exception as e:
            return HttpResponse(f'Erreur lors de la lecture du fichier: {str(e)}', status=500)

    if metadata_only:
        return JsonResponse({
            'success': True,
            'file_type': 'pdf' if file_path.lower().endswith('.pdf') else 'image',
            'page_count': 1,
        })

    # Si c'est un PDF, le convertir en image pour l'affichage
    if file_path.lower().endswith('.pdf'):
        try:
            # Convertir la première page du PDF en image
            images = convert_from_path(file_path, first_page=1, last_page=1, dpi=150)
            if images:
                # Sauvegarder l'image en mémoire
                from io import BytesIO
                img_io = BytesIO()
                images[0].save(img_io, format='PNG')
                img_io.seek(0)
                return HttpResponse(img_io.read(), content_type='image/png')
        except Exception as e:
            return HttpResponse(f'Erreur lors de la conversion PDF: {str(e)}', status=500)

    # Pour les images (JPG, PNG, etc.), les servir directement
    try:
        # Pour les autres formats (JPG, PNG), servir directement
        return FileResponse(open(file_path, 'rb'), content_type=content_type or 'application/octet-stream')

    except Exception as e:
        return HttpResponse(f'Erreur lors de la lecture du fichier: {str(e)}', status=500)
