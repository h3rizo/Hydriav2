from django.contrib.auth import authenticate
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.models import WidgetAuthToken
from apps.core.auth_tokens import token_or_session_required

# Décorateur figé sur le scope mobile — un token créé pour le widget
# desktop (scope='widget') ne passera jamais ici. Importé tel quel par les
# vues terrain (relevés, réparations, plannings) qui doivent être
# accessibles depuis l'app Android.
mobile_auth_required = token_or_session_required(scope=WidgetAuthToken.SCOPE_MOBILE)


@csrf_exempt
@require_POST
def api_mobile_login(request):
    """
    Login dédié à l'app terrain Android (WebView + écrans natifs hors
    ligne) : vérifie les identifiants Hydria habituels et retourne un
    token opaque à conserver localement sur le téléphone. Ce token ne
    donne accès qu'aux endpoints décorés par mobile_auth_required, jamais
    à ceux réservés au widget desktop (scope différent).

    @csrf_exempt : l'appel vient d'un client natif Android, pas d'un
    formulaire dans une page Hydria — pas de cookie CSRF disponible.
    """
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')
    device_label = request.POST.get('device_label', '').strip()[:120]

    if not username or not password:
        return JsonResponse({'success': False, 'error': "Nom d'utilisateur et mot de passe requis"}, status=400)

    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_active:
        return JsonResponse({'success': False, 'error': 'Identifiants invalides'}, status=401)

    token = WidgetAuthToken.objects.create(
        user=user, device_label=device_label, scope=WidgetAuthToken.SCOPE_MOBILE,
    )

    employe = getattr(user, 'employe', None)

    return JsonResponse({
        'success': True,
        'token': token.key,
        'user': user.username,
        'employe_id': str(employe.id) if employe is not None else None,
        # Règle CRITICAL du projet : toujours nom_affichage (surnom en
        # priorité), jamais prenom seul — certains employés n'en ont pas.
        'employe_nom': employe.nom_affichage if employe is not None else None,
    })
