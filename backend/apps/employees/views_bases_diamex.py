"""
API pour récupérer la liste des bases DiameX à importer
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from apps.core.auth_tokens import diamex_agent_required
from .models import EmployeBaseDiameX


@require_http_methods(["GET"])
@diamex_agent_required
def api_bases_diamex(request):
    """
    API pour récupérer la liste des fichiers Access DiameX à importer.

    Cette API permet aux scripts clients de récupérer dynamiquement
    les chemins des fichiers Access configurés pour chaque employé,
    au lieu de hardcoder les chemins.

    Returns:
        JSON avec la liste des fichiers:
        {
            "success": true,
            "fichiers": [
                {
                    "path": "G:\\...\\fichier.accde",
                    "nom": "fichier.accde",
                    "employe": "Nom de l'employé",
                    "employe_id": "uuid"
                }
            ]
        }
    """
    try:
        # Récupérer toutes les bases DiameX configurées
        bases = EmployeBaseDiameX.objects.select_related('employe').all()

        fichiers = []
        for base in bases:
            fichiers.append({
                'path': base.chemin_complet,  # Utilise la propriété qui joint chemin + nom
                'nom': base.base_diamex,
                'employe': f"{base.employe.surnom or base.employe.prenom} {base.employe.nom}",
                'employe_id': str(base.employe.id),
                'employe_surnom': base.employe.surnom or base.employe.prenom  # Surnom pour imported_by
            })

        return JsonResponse({
            'success': True,
            'fichiers': fichiers,
            'count': len(fichiers)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
