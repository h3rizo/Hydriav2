# Guide de test - Modal Grille de Salaire

## Objectif
Vérifier que le modal de grille de salaire calcule correctement les valeurs à l'ouverture.

## Pré-requis
1. Serveur Django démarré : `python manage.py runserver`
2. Console développeur ouverte (F12)
3. Au moins un employé avec un contrat et une grille de salaire

## Test 1 : Édition d'une grille existante

### Étapes
1. Aller sur http://localhost:8000/employes-cascade/
2. Cocher le filtre "Actifs seulement"
3. Sélectionner un employé (clic sur le radio)
4. Sélectionner un contrat (clic sur le radio)
5. Dans le tableau des grilles, cliquer sur "Modifier" (icône crayon)

### Logs attendus dans la console
```
📝 [loadGrilleDataForEdit] Début - grilleId: <uuid>
📝 [loadGrilleDataForEdit] Grille trouvée: {id: "...", contrat_id: "...", ...}
✅ [loadGrilleDataForEdit] formContrat défini à: <uuid>
📝 [loadGrilleDataForEdit] Formulaire rempli - lancement du calcul dans 100ms
🧮 [calculerGrillePreview] Début de la fonction
🧮 [calculerGrillePreview] Contrat ID: <uuid>
📤 [calculerGrillePreview] Données envoyées: {contrat_id: "...", salaire_brut_base: ..., ...}
📥 [calculerGrillePreview] Réponse HTTP: 200 OK
📄 [calculerGrillePreview] Content-Type: application/json
✅ [calculerGrillePreview] Résultat JSON: {success: true, calculs: {...}}
📊 [calculerGrillePreview] Config: {type_contrat: "...", poste: "...", est_gardien: ..., est_journalier: ...}
🏁 [calculerGrillePreview] Fin de la fonction
```

### Résultat attendu dans le modal
- ✅ Bandeau bleu affiche : "Type de contrat: ... | Poste: ..." avec badges GARDIEN/JOURNALIER si applicable
- ✅ Champs calculés affichent des valeurs (pas de 0)
- ✅ Section majorations visible SEULEMENT si gardien
- ✅ Champ "Nb jours journalier" activé SEULEMENT si journalier
- ✅ Champs "Jours fériés" et "Heures remplacement" activés SEULEMENT si gardien

## Test 2 : Création d'une nouvelle grille

### Étapes
1. Sélectionner un employé
2. Sélectionner un contrat
3. Cliquer sur "Nouvelle Grille" (bouton vert avec icône +)

### Logs attendus dans la console
```
🔵 [showAddModal] Type grille - Setting formContrat to: <uuid>
🔵 [showAddModal] selectedContratId: <uuid>
🔵 [showAddModal] parentId: <uuid>
🔵 [showAddModal] formContrat.value: <uuid>
🧮 [calculerGrillePreview] Début de la fonction
🧮 [calculerGrillePreview] Contrat ID: <uuid>
... (suite identique au Test 1)
```

### Résultat attendu
- ✅ Modal s'ouvre avec formulaire vide
- ✅ Bandeau bleu affiche les infos du contrat
- ✅ Tous les champs sont à 0 (normal, nouvelle grille)
- ✅ Quand on modifie "Salaire brut base", le calcul se met à jour en temps réel

## Test 3 : Cas d'erreur - Aucun contrat sélectionné

### Étapes
1. Recharger la page (F5)
2. NE PAS sélectionner d'employé ni de contrat
3. Essayer de cliquer "Nouvelle Grille" directement

### Logs attendus
```
🔵 [showAddModal] selectedContratId: null
🔵 [showAddModal] parentId: null
🔵 [showAddModal] formContrat.value:
🧮 [calculerGrillePreview] Début de la fonction
🧮 [calculerGrillePreview] Contrat ID:
⚠️ [calculerGrillePreview] Pas de contrat sélectionné
🏁 [calculerGrillePreview] Fin de la fonction
```

### Résultat attendu
- ⚠️ Modal s'ouvre mais le bandeau bleu reste vide
- ⚠️ Aucun calcul n'est effectué (normal, pas de contrat)
- ℹ️ C'est un comportement attendu : il faut d'abord sélectionner un contrat

## Diagnostics en cas d'erreur

### Erreur "Unexpected token '<'"
**Cause** : Le serveur Django retourne du HTML (page d'erreur) au lieu de JSON
**Solution** :
1. Regarder les logs du terminal Django
2. Regarder le log `❌ [calculerGrillePreview] Réponse non-JSON:` dans la console
3. Vérifier que l'URL `/employes/api/calculer-grille-preview/` existe

### Erreur "contrat_id est requis"
**Cause** : Le champ `formContrat` est vide
**Solution** :
1. Vérifier les logs `🔵 [showAddModal]` ou `📝 [loadGrilleDataForEdit]`
2. S'assurer qu'un contrat est bien sélectionné avant d'ouvrir le modal

### Erreur "Contrat avec ID ... introuvable"
**Cause** : L'ID du contrat existe dans le frontend mais pas dans la base
**Solution** :
1. Recharger la page (F5)
2. Vérifier l'intégrité des données avec `python manage.py dbshell`

### Les calculs ne se mettent pas à jour quand on modifie les champs
**Cause** : Les événements `input` ne sont pas liés à `calculerGrillePreview()`
**Solution** : Vérifier que les inputs ont bien `oninput="calculerGrillePreview()"`

## Checklist de validation

- [ ] Mode édition : Le modal affiche les valeurs calculées dès l'ouverture
- [ ] Mode édition : Les champs sont pré-remplis avec les valeurs de la grille
- [ ] Mode édition : Le bandeau bleu affiche le type de contrat et le poste
- [ ] Mode édition : Les badges GARDIEN/JOURNALIER s'affichent correctement
- [ ] Mode création : Le modal affiche les infos du contrat sélectionné
- [ ] Mode création : Les champs sont vides (0) par défaut
- [ ] Temps réel : Quand on modifie un champ, les calculs se mettent à jour
- [ ] Activation : Les champs spécifiques sont désactivés selon le type de contrat
- [ ] Majorations : La section majorations est visible SEULEMENT pour les gardiens
- [ ] Logs : Tous les logs s'affichent correctement dans la console

## Prochaines étapes si tous les tests passent

1. Tester la sauvegarde d'une nouvelle grille
2. Tester la modification d'une grille existante
3. Vérifier que les valeurs sauvegardées correspondent aux calculs affichés
4. Tester avec différents types de contrats (journalier, gardien, temps plein)
