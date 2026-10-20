"""
Vues pour la gestion du changement de langue
"""
from django.shortcuts import redirect
from django.conf import settings
from django.utils import translation
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods


@require_http_methods(["POST"])
def set_language(request):
    """
    Change la langue de l'interface utilisateur
    Stocke le choix dans un cookie pour que Django LocaleMiddleware le détecte
    """
    language_code = request.POST.get('language', 'fr')

    # Vérifier que la langue est valide
    valid_languages = [lang[0] for lang in settings.LANGUAGES]
    if language_code not in valid_languages:
        language_code = 'fr'  # Défaut

    # Activer la langue pour cette requête
    translation.activate(language_code)

    # Créer la réponse JSON
    response = JsonResponse({
        'success': True,
        'language': language_code,
        'language_name': dict(settings.LANGUAGES).get(language_code, 'Français')
    })

    # Stocker dans un cookie pour que Django le détecte (durée: 1 an)
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        language_code,
        max_age=365 * 24 * 60 * 60,  # 1 an
        path=settings.LANGUAGE_COOKIE_PATH,
        domain=settings.LANGUAGE_COOKIE_DOMAIN,
        secure=settings.LANGUAGE_COOKIE_SECURE,
        httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
        samesite=settings.LANGUAGE_COOKIE_SAMESITE,
    )

    return response
