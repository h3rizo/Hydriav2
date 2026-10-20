"""
Vue pour télécharger le package portable d'import DiameX
"""
from django.http import HttpResponse, Http404
from django.contrib.auth.decorators import login_required
import os
import zipfile
from io import BytesIO


@login_required
def telecharger_package_portable(request):
    """
    Créé un fichier ZIP contenant tous les fichiers du package portable
    et le renvoie pour téléchargement
    """
    # Dossier backend (où se trouvent les fichiers du package)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Liste des fichiers à inclure dans le package
    fichiers_package = [
        'INSTALLER_IMPORT_DIAMEX.bat',
        'LANCER_IMPORT.bat',
        'LANCER_AGENT_DIAMEX.bat',
        'import_diamex_portable.py',
        'diamex_local_agent.py',
        'config_import.ini',
        'README_IMPORT_DIAMEX.txt'
    ]

    # Créer un buffer en mémoire pour le fichier ZIP
    zip_buffer = BytesIO()

    # Créer le fichier ZIP
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for fichier_nom in fichiers_package:
            fichier_path = os.path.join(base_dir, fichier_nom)

            # Vérifier que le fichier existe
            if os.path.exists(fichier_path):
                # Ajouter le fichier au ZIP avec son nom d'origine
                zip_file.write(fichier_path, fichier_nom)
            else:
                # Fichier manquant - on continue mais on pourrait logger
                print(f"[WARNING] Fichier manquant: {fichier_nom}")

    # Préparer la réponse HTTP
    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.read(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="Package_Import_DiameX_Portable.zip"'

    return response
