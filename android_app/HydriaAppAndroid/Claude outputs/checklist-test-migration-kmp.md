# Checklist de test — refactor Repairs/Planning/Terrain/Relevés/Sync

Objectif : vérifier qu'aucune régression de comportement n'a été introduite par l'extraction de logique métier hors de `MainActivity`. Rien de nouveau n'a été inventé — chaque case ci-dessous doit se comporter **exactement comme avant**.

Cocher au fur et à mesure. Pour chaque anomalie : noter l'action exacte + ce qui s'est affiché, ça permet de remonter directement au fichier concerné.

---

## 🔴 Priorité haute — comportement changé de structure (pas juste déplacé)

Ces cas passent par `TerrainRepository.applyLocalTerrainCompletion`, qui renvoie maintenant un `Boolean` au lieu d'appeler `updateStatus()` en interne — c'est le seul endroit où la logique a été restructurée, pas juste déplacée.

- [ ] Écran **Terrain** : compléter un **nom d'abonné** manquant sur un point → le compteur "Noms d'abonnés à renseigner" doit se décrémenter immédiatement
- [ ] Compléter des **coordonnées GPS** manquantes sur un point → le compteur "Coordonnées à compléter" doit se décrémenter
- [ ] Prendre une **photo** de point/équipement manquante → le compteur correspondant doit se décrémenter
- [ ] Refaire la même action une **deuxième fois** sur un point déjà complété (ou hors ligne, avant confirmation serveur) → le compteur ne doit **pas** redescendre en dessous de 0, et l'app ne doit pas planter
- [ ] Enchaîner un traitement **"en lot"** (bouton lot GPS/abonné/photo) sur plusieurs points d'affilée → chaque complétion doit avancer à l'élément suivant normalement, jusqu'au message "Série terminée"

## 🟠 Priorité haute — calculs de facturation (Relevés)

Formules déplacées dans `ReadingsRules` — à vérifier que les chiffres affichés sont identiques à avant.

- [ ] Démarrer une campagne de relevé sur un ouvrage avec points **kiosques** (cartes sociales)
- [ ] Saisir un nouvel index → la conso affichée (`+ X m³`) est cohérente (nouvel index − ancien index)
- [ ] Ajouter une carte sociale, saisir un nombre de bidons 20L → le volume affiché doit être `bidons × 0,02 m³` (ex. 5 bidons = 0,10 m³)
- [ ] Vérifier le **volume facturé** affiché = conso − cartes sociales − non facturé (saisir une valeur dans "Volume non facturé" et vérifier que ça se répercute)
- [ ] Saisir un index **inférieur** à l'ancien → doit afficher "index < dernier" en rouge, pas de volume facturé calculé
- [ ] Enregistrer le relevé → doit partir dans la file (hors ligne) puis se synchroniser normalement

## 🟡 Réparations

- [ ] Le badge du menu (nombre de réparations à faire) correspond au nombre réellement affiché dans la liste
- [ ] Liste triée : les plus critiques (priorité) en premier, dans chaque groupe d'ouvrage
- [ ] Basculer "Afficher les réparations terminées" / "Afficher hors périmètre" → filtre correct
- [ ] Le badge de retard (jours) est correct pour une réparation en retard / à venir / sans date
- [ ] **Marquer une réparation terminée** → passe en état "terminée", part en synchro
- [ ] **Créer une nouvelle réparation** (formulaire partagé avec Planning) → apparaît bien dans la liste après sync
- [ ] **Modifier** une réparation existante → les champs sont bien pré-remplis, la modif est prise en compte

## 🟡 Planning

- [ ] Agenda : navigation par date (bandeau du haut) fait bien défiler jusqu'à la bonne section
- [ ] Les libellés de date (jour de semaine, date complète) s'affichent correctement en français, avec accents
- [ ] Badges "Jour férié" / "Week-end" corrects
- [ ] Filtres (employé/région/district/commune) fonctionnent
- [ ] **Créer un nouveau planning** → apparaît à la bonne date après sync
- [ ] **Modifier** un planning existant

## 🟢 Terrain (hors complétion de fiches, déjà couvert plus haut)

- [ ] Écran Terrain : nombre total de tâches restantes affiché en haut est correct
- [ ] Âge affiché sur un ouvrage (ex. "Âge : 5 ans") cohérent avec sa date de réalisation
- [ ] **Mesure de débit source** (formulaire dédié) → s'enregistre et s'affiche localement même hors connexion
- [ ] **Relevé compteur de tête** → le calcul d'écart tête/aval affiché est cohérent avec avant

## 🟢 Synchro générale (SyncDispatch)

Le `when` géant qui routait chaque type d'opération vers son appel API a été remplacé par un registre. Comportement identique attendu, mais c'est le tuyau par lequel **tout** transite désormais — un test de bout en bout par domaine est le plus important de cette checklist.

- [ ] Couper le réseau, faire une action dans **chaque** domaine (réparation, planning, relevé, terrain, marquage GPS/repère en Navigation), puis réactiver le réseau → tout part en synchro sans erreur, la file se vide
- [ ] Centre de synchro (icône file d'attente) : les libellés affichés pour chaque type d'opération en attente sont corrects (pas de "type inconnu")
- [ ] Provoquer si possible un conflit (modifier la même réparation depuis deux appareils/sessions) → le comportement de conflit (409) reste le même qu'avant
- [ ] Écran **Volume** (menu session → Facturation/Encaissement/Pointage) — non touché par le refactor, mais partage la même boucle de synchro : vérifier qu'il fonctionne toujours normalement en parallèle des autres domaines

---

## En cas d'anomalie

Note pour chaque cas en échec :
1. L'action exacte effectuée
2. Ce qui était attendu vs. ce qui s'est passé
3. Hors ligne ou en ligne au moment du test

Avec ça je peux remonter directement au fichier (`RepairRules`, `TerrainRepository`, `ReadingsRules`, etc.) et au commit logique concerné plutôt que de re-fouiller tout `MainActivity`.
