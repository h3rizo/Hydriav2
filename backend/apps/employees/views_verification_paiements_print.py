"""
Vue pour la version imprimable de la vérification des paiements employés
Utilise la même logique que l'API principale pour garantir la cohérence des données
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import HttpRequest
from datetime import datetime
import json

from .views_verification_paiements import api_verification_paiements_employes


@login_required
def verification_paiements_print(request):
    """
    Version imprimable de la vérification des paiements employés
    Réutilise la logique de l'API pour garantir la cohérence

    Filtres: prog, mois, annee, conformite (via paramètres GET)
    """
    # Créer une fausse requête interne pour appeler l'API
    # On réutilise les mêmes paramètres GET
    internal_request = HttpRequest()
    internal_request.GET = request.GET.copy()
    internal_request.user = request.user
    internal_request.method = 'GET'

    # Appeler l'API de vérification
    api_response = api_verification_paiements_employes(internal_request)

    # Décoder la réponse JSON
    data = json.loads(api_response.content)

    # Extraire les données
    resultats = data.get('resultats', [])
    stats = data.get('stats', {})

    # Récupérer les filtres pour l'affichage
    prog_filter = request.GET.get('prog', '')
    mois_filter = request.GET.get('mois', '')
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    conformite_filter = request.GET.get('statut', '')  # Note: L'API utilise 'statut' au lieu de 'conformite'

    # Nom du mois pour l'affichage
    mois_nom = ''
    if mois_filter:
        try:
            mois_int = int(mois_filter)
            mois_noms = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                         'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
            if 1 <= mois_int <= 12:
                mois_nom = mois_noms[mois_int]
        except ValueError:
            pass

    # Grouper les résultats par Prog → Employé pour l'affichage hiérarchique
    resultats_groupes = {}
    for resultat in resultats:
        prog = resultat.get('prog') or 'Sans Prog'
        employe = resultat.get('employe_surnom') or 'Non trouvé'

        if prog not in resultats_groupes:
            resultats_groupes[prog] = {}

        if employe not in resultats_groupes[prog]:
            resultats_groupes[prog][employe] = []

        resultats_groupes[prog][employe].append(resultat)

    # Récupérer les listes de filtres disponibles depuis l'API
    progs_disponibles = data.get('progs_disponibles', [])
    annees_disponibles = data.get('annees_disponibles', [])

    context = {
        'resultats': resultats,
        'resultats_groupes': resultats_groupes,
        'stats': stats,
        'prog_filter': prog_filter,
        'mois_filter': mois_filter,
        'mois_nom': mois_nom,
        'annee_filter': annee_filter,
        'conformite_filter': conformite_filter,
        'date_impression': datetime.now(),
        'annees_disponibles': annees_disponibles,
        'progs_disponibles': progs_disponibles,
    }

    return render(request, 'employees/verification_paiements_print.html', context)
