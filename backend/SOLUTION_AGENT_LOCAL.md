# Solution : Agent Local DiameX - "Agent local non lancé"

## Problème

Le modal d'import DiameX affiche "Agent local non lancé" bien que l'agent soit en cours d'exécution sur `http://127.0.0.1:8765`.

## Cause

**Restriction de sécurité du navigateur** : Les navigateurs modernes bloquent les requêtes depuis un site HTTPS (`https://www.hydria.mg`) vers un serveur HTTP local (`http://127.0.0.1:8765`), même avec les bons en-têtes CORS.

Ceci s'appelle :
- **Mixed Content** : HTTPS → HTTP
- **Private Network Access** : Site public → Réseau privé (localhost)

## Solutions

### Solution 1 : Tester depuis localhost (RECOMMANDÉ)

Au lieu d'accéder à `https://www.hydria.mg`, utilisez `http://localhost:8000` pour le développement local.

**Étapes :**
1. Accéder à : `http://localhost:8000/comptabilite/import/`
2. Cliquer sur le bouton "Importer depuis Windows" (vert)
3. L'agent local devrait maintenant se connecter correctement

**Pourquoi ça fonctionne :**
- `http://localhost:8000` → `http://127.0.0.1:8765` : Même protocole (HTTP)
- Pas de restriction Mixed Content

### Solution 2 : Diagnostiquer l'erreur exacte

**Étapes :**
1. Ouvrir le navigateur sur `https://www.hydria.mg/comptabilite/import/`
2. Appuyer sur **F12** pour ouvrir la Console du navigateur
3. Cliquer sur "Tester la connexion" dans le modal
4. Observer les messages d'erreur en **rouge** dans la Console
5. Partager ces messages pour un diagnostic précis

**Erreurs typiques :**
- `Mixed Content: The page was loaded over HTTPS, but requested an insecure XMLHttpRequest endpoint` → Utiliser solution 1
- `Failed to fetch` → Vérifier que l'agent est bien lancé
- `CORS policy` → Problème de configuration CORS (rare, déjà configuré)

### Solution 3 : Script de test CORS

Exécuter le script de diagnostic pour vérifier la configuration CORS de l'agent :

```bash
cd "C:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend"
python test_agent_cors.py
```

**Résultat attendu :**
```
1. Test OPTIONS preflight (CORS)...
   Status: 204
   Headers CORS:
     Access-Control-Allow-Origin: https://www.hydria.mg
     Access-Control-Allow-Methods: GET,POST,OPTIONS
     ...
   ✓ Preflight OK

2. Test GET /health avec Origin...
   Status: 200
   Access-Control-Allow-Origin: https://www.hydria.mg
   ✓ Agent répond : {'ok': True, ...}
```

Si tous les tests passent (✓), l'agent est correctement configuré. Le problème vient uniquement de la restriction du navigateur (Mixed Content).

## Workflow complet recommandé

### Pour le développement local :

1. **Lancer l'agent local** :
   ```bash
   cd "C:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend"
   LANCER_AGENT_DIAMEX.bat
   ```

2. **Accéder à l'interface depuis localhost** :
   - URL : `http://localhost:8000/comptabilite/import/`
   - Cliquer sur "Importer depuis Windows" (bouton vert)
   - Tester la connexion → Devrait afficher "Agent local connecté"

3. **Sélectionner les bases DiameX** :
   - Cocher les bases à importer
   - Cliquer "Importer les bases sélectionnées"
   - Suivre la progression dans l'interface

### Pour la production (VPS) :

L'agent local ne fonctionne PAS en production car il doit être sur le même ordinateur que les fichiers Access (.accde).

**Workflow production :**
1. **Depuis Windows** : Exécuter `python import_access_local.py`
   - Script qui lit les fichiers Access sur G:\ (Google Drive)
   - Envoie les données directement à l'API Django sur le VPS
   - Pas besoin d'agent HTTP local

2. **Depuis VPS** : Importer depuis fichiers copiés sur le serveur
   - Utiliser le bouton bleu "Importer depuis VPS"
   - Les fichiers doivent être déjà copiés dans `/home/soakoja/bases_diamex/`

## Vérification

### L'agent est bien lancé si vous voyez :

```
DiameX Local Agent running
Listening on http://127.0.0.1:8765
Django server: https://www.hydria.mg
Allowed origins:
  - https://www.hydria.mg
  - https://hydria.mg
  - http://localhost:8000
```

### Test rapide de connexion :

**PowerShell/CMD :**
```bash
curl http://127.0.0.1:8765/health
```

**Résultat attendu :**
```json
{"ok":true,"version":"1.0","server_url":"https://www.hydria.mg","allowed_origins":["https://www.hydria.mg","https://hydria.mg","http://localhost:8000"]}
```

## Résumé

| Scénario | Solution |
|----------|----------|
| Développement local (Windows) | Utiliser `http://localhost:8000` au lieu de `https://www.hydria.mg` |
| Production (VPS) | Utiliser `python import_access_local.py` (pas l'agent HTTP) |
| Debugging | Ouvrir Console navigateur (F12) et partager les erreurs |

**Question fréquente :** "Pourquoi ça ne marche pas depuis https://www.hydria.mg ?"

**Réponse :** Les navigateurs bloquent les requêtes HTTPS → HTTP pour des raisons de sécurité (Mixed Content). C'est une limitation du navigateur, pas de notre code.