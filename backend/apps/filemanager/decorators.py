"""
Décorateurs personnalisés pour le mode développement
"""
from functools import wraps
from django.conf import settings


def dev_login_required(view_func):
    """
    Décorateur qui remplace @login_required en mode développement
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # En mode DEBUG, on bypass complètement l'authentification
        if settings.DEBUG:
            # Créer un utilisateur fictif si nécessaire
            if not hasattr(request, 'user') or not request.user.is_authenticated:
                request.user = type('MockUser', (), {
                    'id': 1,
                    'username': 'dev_user',
                    'email': 'dev@hydria.mg',
                    'first_name': 'Dev',
                    'last_name': 'User',
                    'is_authenticated': True,
                    'is_staff': True,
                    'is_superuser': True,
                    'is_active': True,
                    'get_full_name': lambda: 'Dev User'
                })()

        return view_func(request, *args, **kwargs)

    return wrapper