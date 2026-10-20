from apps.employees.models_evaluation import FichePoste

for kw in ['clôture', 'cloture', 'captage']:
    qs = FichePoste.objects.filter(tache__icontains=kw)
    print(f'--- "{kw}" ({qs.count()}) ---')
    for f in qs:
        print(f.id, repr(f.tache), '| type_activites=', f.type_activites_id,
              getattr(f.type_activites, 'nomtype', None))
