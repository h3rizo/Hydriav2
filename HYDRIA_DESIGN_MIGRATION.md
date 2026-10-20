# Migration du design Hydria V1

Ce document suit l'adoption progressive du design de reference defini dans
`HYDRIA_DESIGN_SYSTEM.md`. La page pilote est le dashboard Paiements Volume.

## Principes de migration

- Conserver les routes, permissions, formulaires et traitements JavaScript existants.
- Utiliser les composants `hydria-v1-*` de `backend/static/css/hydria-design-v1.css`.
- Garder une forte densite d'information sur les ecrans metier.
- Tester chaque page en theme clair, theme sombre, mobile et bureau.
- Ne pas appliquer de remplacement CSS global aux anciens workflows complexes.

## Etat

| Vague | Perimetre | Etat |
| --- | --- | --- |
| Reference | `accounting/dashboard_paiements_volume.html` | Valide |
| Fondation | Socle global, tokens, focus, mouvement reduit, composants opt-in | Termine |
| Vague 1 | `usagers/reunions_list.html`, `accounting/dashboard_paiements_forfaitaire.html` | Termine |
| Vague 2 | Dashboard principal, factures pointees, releves, recoupement | Termine |
| Vague 3 | Organisation, geographie, employes | En cours - 11 pages principales et socle CRUD migres |
| Vague 4 | Planning, stock, inspections | A faire |
| Vague 5 | Formulaires, details, modales et pages restantes | A faire |

## Composants disponibles

- `hydria-v1-page` : largeur et respiration de page.
- `hydria-v1-page-header` : en-tete encadre reserve aux pages denses ; `hydria-v1-page-title` peut etre utilise seul.
- `hydria-v1-filter-card` : surface reservee aux filtres complexes ; `hydria-v1-compact-filters` fonctionne aussi sans cadre.
- `hydria-v1-kpi-grid` et `hydria-v1-stat` : KPI individuels adaptatifs.
- `hydria-v1-tone-*` : tons semantiques compatibles clair et sombre.
- `hydria-v1-table-card` : conteneur pour les tableaux lourds ou difficiles a distinguer, pas pour chaque liste.
- `hydria-v1-panel` : panneaux et sections pliables lorsque le regroupement aide la lecture.
- `hydria-v1-empty`, `hydria-v1-loading`, `hydria-v1-error` : etats coherents.

## Controle avant validation d'une page

1. Aucun changement de nom de champ, URL, permission ou identifiant JavaScript.
2. Filtres lisibles sans espace perdu et annee limitee a sa largeur utile.
3. KPI visibles comme cartes individuelles avec unite explicite.
4. Tableaux lisibles, regroupements contrastes dans les deux themes.
5. Navigation clavier et focus visibles.
6. Aucun debordement horizontal non intentionnel sur mobile.
7. Compilation du template et `manage.py check` sans erreur.
8. Chaque cadre ajoute doit avoir une fonction de regroupement ou de ventilation explicite.
