from django.db import transaction
from apps.planning.models import TypeActivite, Activite

DEPANNAGE_ID = '93b4e71c-49b4-4ddb-ae39-7dfc45894b90'

# activite_id -> nouveau type_activite_id (deduit du type_activites de leur fiche de poste actuelle)
REASSIGN = {
    'ee4cf4a3-89bf-4f0d-b68a-c45b2826819f': '6a3729a8-dced-457b-a1dd-549b456d09e4',  # Au cas ou Reparation -> Reparation et depannage
    '1043cdcb-2c27-4bd9-8991-b0e6525bdb52': '266b61a0-5ceb-49d4-8fd8-8e6cd3bc9513',  # Course en ville -> Gestion logistique
    'f79a7b47-9717-4bae-8689-f7366cae1b21': '6a3729a8-dced-457b-a1dd-549b456d09e4',  # Enterrement tuyau -> Reparation et depannage
    'c6f72ba6-ffde-42cb-94e2-27f52cc9782f': 'ac573330-72a9-4540-bd84-6ded299d8428',  # Installation BP -> Installation et remplacement
    '7847e223-c298-4b7c-be31-242f1f2ced00': 'ac573330-72a9-4540-bd84-6ded299d8428',  # Installation PMH -> Installation et remplacement
    'ba353ba4-fbe0-4e4b-bea1-4713ba804489': '6a3729a8-dced-457b-a1dd-549b456d09e4',  # Reamenagement BF -> Reparation et depannage
    '785fba11-c5c2-43df-9833-f53d2e303e27': '0622c85a-36b1-430a-bde1-cb29c821813b',  # Recaptage -> Rehabilitation
    '1f60671a-a0ea-4143-a188-c33a8fa76e9d': 'cd75339d-0e2a-46d6-a1cc-f269264d85a7',  # Rehabilitation -> Encadrement et management d'equipe
    'c5f74f7f-8124-4e7b-820b-d2dc935a1661': '6a3729a8-dced-457b-a1dd-549b456d09e4',  # Reparation : bulle d'air -> Reparation et depannage
    'b7e5f017-8040-48f1-a8c0-cc19842de821': '6a3729a8-dced-457b-a1dd-549b456d09e4',  # Reparation fuite -> Reparation et depannage
    'f2d761ad-523f-4699-a8a7-c4876806df1a': '6a3729a8-dced-457b-a1dd-549b456d09e4',  # Reparation panne -> Reparation et depannage
    'd1aff308-4356-439c-bc2e-99de696d3c60': 'ac573330-72a9-4540-bd84-6ded299d8428',  # Reparation simple -> Installation et remplacement
    '531641da-5620-495c-bcec-5d4d69143b51': '295967e1-047d-49a4-8600-89140bd6520b',  # Suivi chantier -> Chantier
    '38f8583c-f36f-475d-bac0-b5be4cd275d4': '6a3729a8-dced-457b-a1dd-549b456d09e4',  # Travaux lourds -> Reparation et depannage
}

types_cache = {t.id: t.nomtype for t in TypeActivite.objects.all()}

print('Avant : nb Activite sous Depannage =', Activite.objects.filter(type_activite_id=DEPANNAGE_ID).count())

with transaction.atomic():
    for activite_id, new_type_id in REASSIGN.items():
        a = Activite.objects.get(id=activite_id)
        old_type_name = types_cache.get(a.type_activite_id, '?')
        new_type_name = types_cache.get(new_type_id, '?')
        print(f'{a.nom!r}: {old_type_name!r} -> {new_type_name!r}')
        a.type_activite_id = new_type_id
        a.save(update_fields=['type_activite'])

restants = Activite.objects.filter(type_activite_id=DEPANNAGE_ID)
print()
print('Apres : nb Activite sous Depannage =', restants.count())
for a in restants:
    print('  restant:', a.nom, a.id)
