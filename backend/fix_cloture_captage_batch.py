"""Traitement en masse des "Reparation des clotures autour des captages" :
1. Pour les plannings sans cible : cible = premier equipement de type "Captage"
   de l'ouvrage (par nom), s'il en existe un. Sinon, ligne laissee de cote.
2. Pour toute ligne ayant desormais une cible (deja presente ou venant d'etre
   remplie) : ajoute le composant "Cloture" (catalogue du type de la cible) et
   reclasse l'activite en "Reparation simple".

DRY_RUN = True (par defaut) : n'ecrit rien, affiche juste ce qui serait fait.
Repasser DRY_RUN a False puis relancer pour appliquer reellement.
"""
from apps.planning.models import Planning
from apps.infrastructure.models import EquipementConstitutif
from apps.planning.reparation_composants import (
    apply_repair_target, verifier_regles_fiche, composants_disponibles, ComposantsError,
)
from apps.employees.models_evaluation import FichePoste

DRY_RUN = False

FICHE_SOURCE_ID = '0a763c38-b8a7-4816-8e92-b6ce0f9123a0'  # Reparation des clotures autour des captages
FICHE_CIBLE_ID = '1aaeb267-f574-44a9-a004-e8dfb6709d9b'   # Reparation simple
COMPOSANT_NOM = 'Clôture'

fiche_cible = FichePoste.objects.select_related('type_activites').get(id=FICHE_CIBLE_ID)

plannings = list(
    Planning.objects.filter(fiche_poste_id=FICHE_SOURCE_ID)
    .select_related('ouvrage', 'cible_equipement', 'cible_point_eau')
    .prefetch_related('composants_equipement', 'composants_point_eau')
)

print(f'MODE : {"DRY RUN (aucune ecriture)" if DRY_RUN else "APPLICATION REELLE"}')
print(f'{len(plannings)} planning(s) a traiter\n')

cibles_remplies = 0
cibles_ignorees = 0
reclasses = 0
refuses = []

for p in plannings:
    a_cible_avant = bool(p.cible_equipement_id or p.cible_point_eau_id)
    equipement = p.cible_equipement
    point_eau = p.cible_point_eau

    if not a_cible_avant:
        equip = EquipementConstitutif.objects.filter(
            ouvrage_id=p.ouvrage_id, type_equipement__nom_type__icontains='captage'
        ).order_by('nom').first()
        if not equip:
            cibles_ignorees += 1
            print(f'IGNORE (aucun captage)  : {p.id} | ouvrage={p.ouvrage.nom_ouvrage if p.ouvrage else "?"}')
            continue
        equipement, point_eau = equip, None
        cibles_remplies += 1
        print(f'CIBLE -> {equip.nom:40s} : {p.id} | ouvrage={p.ouvrage.nom_ouvrage if p.ouvrage else "?"}')
        if not DRY_RUN:
            p.cible_equipement = equip
            p.cible_point_eau = None
            p.save(update_fields=['cible_equipement', 'cible_point_eau'])

    # Etape 2 : composant Cloture + reclassement
    catalogue = composants_disponibles(equipement=equipement, point_eau=point_eau)
    match = next((c for c in catalogue if c['nom'].strip().lower() == COMPOSANT_NOM.lower()), None)
    if not match:
        refuses.append((p.id, 'composant "Cloture" absent du catalogue de ce type de cible'))
        print(f'  REFUSE composant : {p.id} (pas de "Cloture" pour ce type)')
        continue

    composants_existants = (
        [str(c.id) for c in p.composants_equipement.all()]
        + [str(c.id) for c in p.composants_point_eau.all()]
    )
    composants_finaux = list(dict.fromkeys(composants_existants + [match['id']]))

    try:
        verifier_regles_fiche(fiche_cible, equipement, point_eau, composants_finaux)
    except ComposantsError as exc:
        refuses.append((p.id, str(exc)))
        print(f'  REFUSE regles : {p.id} -> {exc}')
        continue

    reclasses += 1
    print(f'  OK -> composant Cloture + Reparation simple : {p.id}')
    if not DRY_RUN:
        apply_repair_target(p, equipement, point_eau, composants_finaux)
        p.fiche_poste = fiche_cible
        p.type_activite = fiche_cible.type_activites
        p.save(update_fields=['fiche_poste', 'type_activite'])

print()
print(f'Cibles remplies (captage trouve)   : {cibles_remplies}')
print(f'Lignes ignorees (aucun captage)    : {cibles_ignorees}')
print(f'Reclassees en Reparation simple    : {reclasses}')
print(f'Refusees (regles/composant)        : {len(refuses)}')
for pid, raison in refuses:
    print(f'  - {pid} : {raison}')
