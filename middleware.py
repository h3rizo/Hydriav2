from collections import defaultdict
from django.http import JsonResponse

# Ce dictionnaire stockera les comptes en mémoire.
# Il sera réinitialisé à chaque redémarrage du serveur.
VISIT_COUNTS = defaultdict(int)

class PageVisitCounterMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # On ne compte que les visites de pages HTML, en excluant :
        # - Les API
        # - Les fichiers statiques et médias
        # - L'interface d'administration
        # - La page de résultats du compteur elle-même
        # - Les URLs du framework de debug (si installé)
        if (not path.startswith('/api/') and
            not path.startswith('/static/') and
            not path.startswith('/media/') and
            not path.startswith('/admin/') and
            not path.startswith('/__debug__/') and
            path != '/page-visits/'):
            
            # On vérifie que la réponse est bien du HTML
            response = self.get_response(request)
            if 'text/html' in response.get('Content-Type', ''):
                VISIT_COUNTS[path] += 1
        else:
            response = self.get_response(request)

        return response