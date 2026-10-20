from apps.planning.models import TypeActivite, Activite, ActivitePoste

t = TypeActivite.objects.get(id='93b4e71c-49b4-4ddb-ae39-7dfc45894b90')
print('TypeActivite:', repr(t.id), repr(t.nomtype))
activites = Activite.objects.filter(type_activite=t)
print('Nb Activite (legacy) sous ce type:', activites.count())
for a in activites:
    aps = ActivitePoste.objects.filter(activite=a)
    print('--', 'Activite:', repr(a.nom), 'id=', a.id, 'is_active=', a.is_active,
          '| nb ActivitePoste:', aps.count())
    for ap in aps:
        print('    ActivitePoste id=', ap.id, 'nom=', repr(ap.nom),
              '| poste_id=', ap.poste_id,
              '| fiche_poste_id=', ap.fiche_poste_id,
              '| is_active=', ap.is_active)
        if ap.fiche_poste_id:
            fp = ap.fiche_poste
            print('        -> FichePoste existe:', fp is not None,
                  'tache=', getattr(fp, 'tache', None) if fp else None,
                  'type_activites_id=', getattr(fp, 'type_activites_id', None) if fp else None)
        if ap.poste_id:
            print('        -> Poste id=', ap.poste_id, 'nom=', getattr(ap.poste, 'nom_poste', None))
