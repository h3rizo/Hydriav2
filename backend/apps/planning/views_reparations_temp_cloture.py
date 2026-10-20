"""Page TEMPORAIRE et légère pour rattraper les « Réparation des clôtures autour des
captages » : définir cible + composants (par lot ou un par un), puis reclasser en
« Réparation simple » une fois prêt.

À SUPPRIMER une fois le rattrapage terminé : ce fichier, l'entrée d'URL associée dans
apps/planning/urls.py, et le template templates/planning/temp_cloture_captage.html.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

# Fiche de poste "Réparation des clôtures autour des captages" (source à traiter)
FICHE_SOURCE_ID = '0a763c38-b8a7-4816-8e92-b6ce0f9123a0'
FICHE_SOURCE_NOM = 'Réparation des clôtures autour des captages'

# Fiche de poste cible une fois cible + composants renseignés
FICHE_CIBLE_ID = '1aaeb267-f574-44a9-a004-e8dfb6709d9b'
FICHE_CIBLE_NOM = 'Réparation simple'


@login_required
def temp_cloture_captage(request):
    return render(request, 'planning/temp_cloture_captage.html', {
        'fiche_source_id': FICHE_SOURCE_ID,
        'fiche_source_nom': FICHE_SOURCE_NOM,
        'fiche_cible_id': FICHE_CIBLE_ID,
        'fiche_cible_nom': FICHE_CIBLE_NOM,
        'title': 'Rattrapage clôtures / captages (temporaire)',
    })
