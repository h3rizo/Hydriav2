from apps.planning.models import Planning

FICHE_SOURCE_ID = '0a763c38-b8a7-4816-8e92-b6ce0f9123a0'
FICHE_CIBLE_ID = '1aaeb267-f574-44a9-a004-e8dfb6709d9b'

restant_source = Planning.objects.filter(fiche_poste_id=FICHE_SOURCE_ID).count()
print(f'Plannings restants sous "Reparation des clotures autour des captages" : {restant_source}')

reclasses = Planning.objects.filter(fiche_poste_id=FICHE_CIBLE_ID)
print(f'Plannings sous "Reparation simple" : {reclasses.count()}')

avec_cloture = 0
for p in reclasses.prefetch_related('composants_equipement', 'composants_point_eau'):
    noms = {c.nom_composant for c in p.composants_equipement.all()} | {c.nom_composant for c in p.composants_point_eau.all()}
    if 'Clôture' in noms:
        avec_cloture += 1
print(f'  dont avec composant Cloture : {avec_cloture}')
