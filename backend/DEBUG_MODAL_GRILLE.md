# 🐛 Guide de débogage - Modal Grille Salaire

## Problème actuel
Le modal de grille de salaire ne met pas à jour les calculs automatiquement à l'ouverture.

## ✅ Ce qui fonctionne (confirmé)

### Backend
- ✅ API `/employes/api/calculer-grille-preview/` créée et fonctionnelle
- ✅ Calcul des majorations gardien correct
- ✅ Détection `est_gardien` et `est_journalier` correcte
- ✅ Retourne les bonnes données JSON

### Frontend
- ✅ Fonction `calculerGrillePreview()` créée avec logs détaillés
- ✅ Appel automatique après ouverture modal (ligne 828 + 921)
- ✅ Activation/désactivation des champs selon type

## 🔍 Étapes de débogage

### 1. Ouvrir la console du navigateur
**Comment faire :**
- Windows: `F12` ou `Ctrl+Shift+I`
- Chrome/Edge: Onglet "Console"
- Firefox: Onglet "Console"

### 2. Ouvrir le modal
1. Aller sur http://localhost:8000/employes-cascade/
2. Sélectionner un employé (clic sur ligne)
3. Sélectionner un contrat (clic sur ligne)
4. Cliquer sur "Nouvelle Grille"

### 3. Vérifier les logs dans la console

**Logs attendus (dans l'ordre) :**
```
🧮 [calculerGrillePreview] Début de la fonction
🧮 [calculerGrillePreview] Contrat ID: <uuid>
📤 [calculerGrillePreview] Données envoyées: {contrat_id: "...", salaire_brut_base: 0, ...}
📥 [calculerGrillePreview] Réponse HTTP: 200
✅ [calculerGrillePreview] Résultat JSON: {success: true, calculs: {...}}
📊 [calculerGrillePreview] Config: {type_contrat: "...", poste: "...", est_gardien: false, ...}
🔵 Est gardien: false
📅 Est journalier: false
🏁 [calculerGrillePreview] Fin de la fonction
```

## 🚨 Erreurs possibles

### Erreur 1: "Pas de contrat sélectionné"
```
⚠️ [calculerGrillePreview] Pas de contrat sélectionné
```
**Cause:** Le champ `formContrat` est vide
**Solution:** Vérifier que vous avez bien sélectionné un contrat avant d'ouvrir le modal

### Erreur 2: Erreur HTTP 403/404/500
```
📥 [calculerGrillePreview] Réponse HTTP: 500
❌ [calculerGrillePreview] Erreur calcul: ...
```
**Cause:** Problème serveur
**Solution:**
1. Vérifier que le serveur Django est démarré
2. Vérifier les logs du serveur Django
3. Vérifier que l'URL `/employes/api/calculer-grille-preview/` existe

### Erreur 3: Exception JavaScript
```
💥 [calculerGrillePreview] Exception: TypeError: ...
```
**Cause:** Problème dans le code JavaScript
**Solution:** Noter le message d'erreur exact et le contexte

### Erreur 4: Pas de logs du tout
**Cause:** La fonction n'est pas appelée
**Solutions possibles:**
1. Vérifier que le fichier template a bien été sauvegardé
2. Vider le cache du navigateur (`Ctrl+F5`)
3. Vérifier qu'il n'y a pas d'erreur JavaScript qui bloque l'exécution
4. Chercher des erreurs rouges dans la console

## 🧪 Test manuel de l'API

### Avec le navigateur (Console)
Ouvrir la console et exécuter:
```javascript
// Tester avec un contrat ID réel
const testData = {
    contrat_id: '9791eb33-c52d-4916-bc7f-09665309c722',  // Remplacer par un vrai ID
    salaire_brut_base: 100000,
    personnes_charge: 2,
    : 0,
    nb_jours_feries_gardien: 0,
    nb_heures_remplacement_gardien: 0
};

fetch('/employes/api/calculer-grille-preview/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify(testData)
})
.then(r => r.json())
.then(d => console.log('Résultat API:', d))
.catch(e => console.error('Erreur:', e));
```

## 📝 Informations à fournir en cas de bug

1. **Logs complets de la console**
2. **Message d'erreur exact** (si affiché)
3. **Type de contrat** testé (Temps plein, Journalier, etc.)
4. **Nom du poste** testé (Gardien, Technicien, etc.)
5. **Capture d'écran** du modal
6. **Logs du serveur Django** (dans le terminal où vous avez lancé `runserver`)

## 🔧 Vérifications supplémentaires

### Vérifier que le serveur est démarré
```bash
# Dans un terminal
cd "c:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend"
.venv\Scripts\python.exe manage.py runserver
```

### Vérifier que le template est à jour
1. Fermer le serveur (`Ctrl+C`)
2. Redémarrer le serveur
3. Vider le cache du navigateur (`Ctrl+F5`)

### Tester l'API backend directement
```bash
cd "c:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend"
.venv\Scripts\python.exe test_api_grille.py
```

**Résultat attendu:**
```
=== TEST API CALCUL GRILLE ===
Contrat ID: ...
Employé: ...
Type contrat: ...
Poste: ...

=== RÉSULTATS ===
Est gardien: True/False
Est journalier: True/False
```

## ✅ Checklist de résolution

- [ ] Serveur Django démarré
- [ ] Console navigateur ouverte (F12)
- [ ] Modal ouvert (Nouvelle Grille)
- [ ] Logs visibles dans la console
- [ ] Aucune erreur rouge dans la console
- [ ] Cache navigateur vidé (Ctrl+F5)

## 🎯 Prochaines étapes

Une fois les logs obtenus, nous pourrons identifier précisément:
- Si la fonction est appelée
- Si l'API répond
- Si les données sont correctes
- Où exactement le processus échoue
