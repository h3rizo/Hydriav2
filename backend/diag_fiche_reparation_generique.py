from apps.employees.models_evaluation import FichePoste

qs = FichePoste.objects.filter(tache__iexact='Réparation')
print('--- tache exact "Réparation" ---')
for f in qs:
    print(f.id, repr(f.tache), '| type_activites=', f.type_activites_id, getattr(f.type_activites, 'nomtype', None))

print()
print('--- taches sous "Réparation et dépannage" ---')
for f in FichePoste.objects.filter(type_activites_id='6a3729a8-dced-457b-a1dd-549b456d09e4').order_by('tache'):
    print(f.id, repr(f.tache))
