# Guide VS Code pour Projet Soakoja - Setup Complet

## 📋 Table des Matières

2. [Extensions essentielles pour votre projet](#extensions)
3. [Configuration de l'environnement de travail](#config)
4. [Tester et déboguer votre code](#debug)
5. [Fonctionnalités avancées pour Node.js](#advanced)
6. [Workflow de développement quotidien](#workflow)
7. [Raccourcis indispensables](#shortcuts)


### 2. Premier démarrage

1. **Ouvrir VS Code**
2. **File → Open Folder** → Sélectionner votre dossier `soakoja-app/`
3. VS Code va détecter que c'est un projet Node.js

### 3. Interface VS Code - Les zones importantes

```
┌─────────────────────────────────────────────────────┐
│ Menu Bar (File, Edit, View...)                      │
├─────────┬───────────────────────────────┬───────────┤
│         │                               │           │
│ Sidebar │        Zone d'édition         │ Minimap   │
│         │      (vos fichiers code)      │           │
│ - Explorer                              │           │
│ - Search│                               │           │
│ - Git   │                               │           │
│ - Extensions                            │           │
│         │                               │           │
├─────────┴───────────────────────────────┴───────────┤
│ Terminal intégré                                    │
│ > npm start                                         │
│ > node server.js                                    │
└─────────────────────────────────────────────────────┘
```

---

## 🔧 Extensions essentielles pour votre projet {#extensions}

### Installation des extensions

**2 méthodes :**
1. **Via l'interface** : Cliquer sur l'icône Extensions (4 carrés) dans la sidebar
2. **Via le Quick Open** : `Ctrl+P` puis taper `ext install nom-extension`

### Extensions OBLIGATOIRES pour Soakoja

#### 1. **JavaScript et Node.js**

**JavaScript (ES6) code snippets**
- **ID** : `xabikos.JavaScriptSnippets`
- **Pourquoi** : Autocomplétion pour JavaScript
- **Installation** : `ext install xabikos.JavaScriptSnippets`

**Node.js Modules Intellisense**
- **ID** : `leizongmin.node-module-intellisense`
- **Pourquoi** : Autocomplétion des modules npm (express, sequelize, etc.)
- **Installation** : `ext install leizongmin.node-module-intellisense`

**npm Intellisense**
- **ID** : `christian-kohler.npm-intellisense`
- **Pourquoi** : Autocomplétion dans les require()
- **Installation** : `ext install christian-kohler.npm-intellisense`

#### 2. **Base de données**

**SQLite Viewer**
- **ID** : `qwtel.sqlite-viewer`
- **Pourquoi** : Voir votre base `soakoja.db` directement dans VS Code
- **Installation** : `ext install qwtel.sqlite-viewer`

**SQL Tools**
- **ID** : `mtxr.sqltools`
- **Pourquoi** : Exécuter des requêtes SQL
- **Installation** : `ext install mtxr.sqltools`

#### 3. **Templates et Web**

**EJS language support**
- **ID** : `DigitalBrainstem.javascript-ejs-support`
- **Pourquoi** : Coloration syntaxique pour vos templates EJS
- **Installation** : `ext install DigitalBrainstem.javascript-ejs-support`

**HTML CSS Support**
- **ID** : `ecmel.vscode-html-css`
- **Pourquoi** : Autocomplétion CSS dans HTML
- **Installation** : `ext install ecmel.vscode-html-css`

#### 4. **Débogage et qualité**

**Debugger for Chrome**
- **ID** : `msjsdiag.debugger-for-chrome`
- **Pourquoi** : Déboguer depuis VS Code dans Chrome
- **Installation** : `ext install msjsdiag.debugger-for-chrome`

**ESLint**
- **ID** : `dbaeumer.vscode-eslint`
- **Pourquoi** : Détection d'erreurs JavaScript
- **Installation** : `ext install dbaeumer.vscode-eslint`

#### 5. **Productivité**

**Auto Rename Tag**
- **ID** : `formulahendry.auto-rename-tag`
- **Pourquoi** : Renomme automatiquement les balises HTML/EJS
- **Installation** : `ext install formulahendry.auto-rename-tag`

**Bracket Pair Colorizer 2**
- **ID** : `CoenraadS.bracket-pair-colorizer-2`
- **Pourquoi** : Colore les parenthèses/accolades par paires
- **Installation** : `ext install CoenraadS.bracket-pair-colorizer-2`

**GitLens**
- **ID** : `eamodio.gitlens`
- **Pourquoi** : Intégration Git avancée
- **Installation** : `ext install eamodio.gitlens`

### Script d'installation rapide

**Créer un fichier `install-extensions.bat` (Windows) ou `install-extensions.sh` (Mac/Linux) :**



**Exécuter :** Double-clic sur le fichier ou dans le terminal : `./install-extensions.bat`

---

## ⚙️ Configuration de l'environnement {#config}

### 1. Configuration VS Code pour Node.js

**Créer `.vscode/settings.json` dans votre dossier projet :**

```json
{
  "editor.tabSize": 2,
  "editor.insertSpaces": true,
  "editor.detectIndentation": false,
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.fixAll.eslint": true
  },
  "files.autoSave": "onFocusChange",
  "emmet.includeLanguages": {
    "ejs": "html"
  },
  "files.associations": {
    "*.ejs": "ejs"
  },
  "javascript.suggest.autoImports": true,
  "typescript.suggest.autoImports": true,
  "editor.minimap.enabled": true,
  "workbench.editor.enablePreview": false,
  "terminal.integrated.defaultProfile.windows": "Command Prompt"
}
```

### 2. Configuration du terminal intégré

**Ouvrir le terminal :**
- **Raccourci** : `Ctrl+` (backtick)
- **Menu** : View → Terminal

**Terminal personnalisé pour votre projet :**

```json
// Dans settings.json, ajouter :
"terminal.integrated.profiles.windows": {
  "Soakoja Dev": {
    "path": "cmd.exe",
    "args": ["/k", "echo === Terminal Soakoja === && cd /d ${workspaceFolder}"]
  }
},
"terminal.integrated.defaultProfile.windows": "Soakoja Dev"
```

### 3. Configuration des tâches (Tasks)

**Créer `.vscode/tasks.json` :**

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "type": "shell",
      "label": "Start Soakoja Server",
      "command": "npm",
      "args": ["start"],
      "group": "build",
      "presentation": {
        "echo": true,
        "reveal": "always",
        "focus": false,
        "panel": "new"
      },
      "problemMatcher": [],
      "runOptions": {
        "runOn": "folderOpen"
      }
    },
    {
      "type": "shell",
      "label": "Install Dependencies",
      "command": "npm",
      "args": ["install"],
      "group": "build",
      "presentation": {
        "echo": true,
        "reveal": "always",
        "focus": false,
        "panel": "new"
      }
    },
    {
      "type": "shell",
      "label": "Run Setup",
      "command": "node",
      "args": ["setup.js"],
      "group": "build"
    }
  ]
}
```

**Utilisation :**
- `Ctrl+Shift+P` → "Tasks: Run Task" → Choisir la tâche

---

## 🐛 Tester et déboguer votre code {#debug}

### 1. Configuration du débogueur

**Créer `.vscode/launch.json` :**

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Lancer Soakoja Server",
      "type": "node",
      "request": "launch",
      "program": "${workspaceFolder}/server.js",
      "console": "integratedTerminal",
      "restart": true,
      "env": {
        "NODE_ENV": "development"
      }
    },
    {
      "name": "Attacher au processus Node",
      "type": "node",
      "request": "attach",
      "port": 9229,
      "restart": true,
      "localRoot": "${workspaceFolder}",
      "remoteRoot": "."
    },
    {
      "name": "Debug Tests",
      "type": "node",
      "request": "launch",
      "program": "${workspaceFolder}/node_modules/mocha/bin/_mocha",
      "args": [
        "--recursive",
        "--timeout",
        "5000"
      ],
      "console": "integratedTerminal"
    }
  ]
}
```

### 2. Utiliser les points d'arrêt (Breakpoints)

**Comment placer un breakpoint :**
1. **Cliquer** dans la marge gauche (à côté du numéro de ligne)
2. **Point rouge** apparaît = breakpoint actif

**Exemple - Déboguer la connexion dans server.js :**

```javascript
// Ligne 135 - Route POST /login
app.post('/login', async (req, res) => {
  try {
    const { email, password } = req.body;
    
    // 🔴 BREAKPOINT ICI - Cliquer dans la marge
    console.log('Tentative de connexion:', { email, password });
    
    const user = await Employe.findOne({ where: { email, statut: 'actif' } });
    
    // 🔴 BREAKPOINT ICI AUSSI
    console.log('Utilisateur trouvé:', user ? 'Oui' : 'Non');
    
    if (user && await bcrypt.compare(password, user.mot_de_passe)) {
      // 🔴 ET ICI
      console.log('Mot de passe correct');
      req.session.user = {
        id: user.id,
        nom: user.nom,
        // ... etc
      };
      res.redirect('/dashboard');
    } else {
      res.render('login', { error: 'Email ou mot de passe incorrect' });
    }
  } catch (error) {
    // 🔴 BREAKPOINT POUR CAPTURER LES ERREURS
    console.error('Erreur connexion:', error);
    res.render('login', { error: 'Erreur de connexion' });
  }
});
```

### 3. Démarrer le débogage

**Méthode 1 - Depuis l'interface :**
1. **Aller** dans l'onglet "Run and Debug" (Ctrl+Shift+D)
2. **Sélectionner** "Lancer Soakoja Server"
3. **Cliquer** sur le bouton Play ▶️

**Méthode 2 - Raccourci :**
- **F5** pour démarrer
- **F10** pour passer à la ligne suivante
- **F11** pour entrer dans une fonction
- **Shift+F11** pour sortir d'une fonction

### 4. Inspecter les variables

**Pendant le débogage, vous pouvez :**
- **Variables** : Voir toutes les variables locales
- **Watch** : Surveiller des expressions spécifiques
- **Call Stack** : Voir la pile d'appels
- **Console** : Exécuter du code JavaScript

**Exemples d'expressions à surveiller (Watch) :**
```javascript
req.body
user.email
req.session.user
process.env.NODE_ENV
```

### 5. Console de débogage

**Utiliser la console intégrée :**
```javascript
// Pendant une pause au breakpoint, taper dans la console :
console.log(user);
JSON.stringify(req.body, null, 2);
typeof password;
password.length;
```

### 6. Débogage des templates EJS

**Pour déboguer les erreurs de template :**

```javascript
// Dans server.js, améliorer la gestion d'erreur
app.get('/dashboard', requireAuth, async (req, res) => {
  try {
    const stats = {
      ouvrages_actifs: await Ouvrage.count({ where: { statut: 'actif' } }),
      // ... autres stats
    };

    // 🔴 BREAKPOINT ICI pour vérifier les données
    console.log('Stats pour dashboard:', stats);
    console.log('Utilisateur session:', req.session.user);

    res.render('dashboard', { 
      user: req.session.user, 
      stats,
      plannings_recents: []  // Données par défaut si erreur
    });
  } catch (error) {
    // 🔴 BREAKPOINT pour capturer erreurs template
    console.error('Erreur dashboard:', error);
    console.error('Stack trace:', error.stack);
    
    // Renvoyer données par défaut en cas d'erreur
    res.render('dashboard', { 
      user: req.session.user, 
      stats: { ouvrages_actifs: 0, points_eau_actifs: 0 },
      plannings_recents: [],
      error: 'Erreur de chargement des données'
    });
  }
});
```

---

## 🚀 Fonctionnalités avancées pour Node.js {#advanced}

### 1. IntelliSense et autocomplétion

**Ce que VS Code vous apporte automatiquement :**

```javascript
// Tapez "req." et VS Code suggère :
req.body
req.params
req.query
req.session
req.headers

// Tapez "res." et voyez :
res.render()
res.redirect()
res.json()
res.status()
res.send()

// Pour Sequelize, tapez "User." :
User.findAll()
User.findOne()
User.create()
User.update()
User.destroy()
```

### 2. Snippets personnalisés pour Soakoja

**Créer des snippets :** File → Preferences → User Snippets → javascript.json

```json
{
  "Route GET avec auth": {
    "prefix": "route-get-auth",
    "body": [
      "app.get('/$1', requireAuth, async (req, res) => {",
      "  try {",
      "    $2",
      "    res.render('$3', { user: req.session.user });",
      "  } catch (error) {",
      "    console.error('Erreur:', error);",
      "    res.status(500).send('Erreur serveur');",
      "  }",
      "});"
    ],
    "description": "Route GET avec authentification"
  },
  
  "Route POST pour formulaire": {
    "prefix": "route-post-form",
    "body": [
      "app.post('/$1', requireAuth, async (req, res) => {",
      "  try {",
      "    const data = req.body;",
      "    console.log('Données reçues:', data);",
      "    ",
      "    // TODO: Traitement des données",
      "    $2",
      "    ",
      "    res.redirect('/$3');",
      "  } catch (error) {",
      "    console.error('Erreur:', error);",
      "    res.redirect('/$1?error=1');",
      "  }",
      "});"
    ],
    "description": "Route POST pour traitement formulaire"
  },

  "Modèle Sequelize": {
    "prefix": "sequelize-model",
    "body": [
      "const $1 = sequelize.define('$1', {",
      "  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },",
      "  nom: { type: DataTypes.STRING, allowNull: false },",
      "  $2",
      "  date_creation: { type: DataTypes.DATE, defaultValue: DataTypes.NOW }",
      "});"
    ],
    "description": "Modèle Sequelize de base"
  }
}
```

**Utilisation :** Tapez `route-get-auth` puis Tab

### 3. Navigation rapide dans le code

**Go to Definition (F12) :**
```javascript
const user = await Employe.findOne(...);  // F12 sur Employe → va au modèle

app.use(requireAuth);  // F12 sur requireAuth → va à la fonction
```

**Find All References (Shift+F12) :**
- Clic droit sur une variable/fonction → "Find All References"
- Voit tous les endroits où elle est utilisée

**Quick Open (Ctrl+P) :**
```
server.js      → Ouvre server.js
@login         → Va aux symboles contenant "login"
:135           → Va à la ligne 135
#Employe       → Recherche les symboles "Employe"
```

### 4. Refactoring et renommage

**Rename Symbol (F2) :**
1. **Clic** sur une variable/fonction
2. **F2** → Nouveau nom
3. **Enter** → Renomme partout automatiquement

**Extract Method (Ctrl+Shift+R) :**
1. **Sélectionner** du code
2. **Ctrl+Shift+R** → VS Code propose d'extraire en fonction

---

## 📊 Visualiser la base de données SQLite {#database}

### 1. Extension SQLite Viewer

**Après installation de l'extension :**
1. **Ouvrir** `database/soakoja.db` dans VS Code
2. **Vue graphique** de vos tables apparaît
3. **Cliquer** sur une table pour voir les données

### 2. Exécuter des requêtes SQL

**Avec SQL Tools :**
1. **Ctrl+Shift+P** → "SQLTools: Add New Connection"
2. **Choisir** SQLite
3. **Database file** : `database/soakoja.db`
4. **Tester** la connexion

**Créer un fichier queries.sql :**
```sql
-- Voir tous les employés
SELECT * FROM Employes;

-- Voir les plannings avec employés
SELECT p.date, p.titre, e.prenom, e.nom 
FROM Plannings p 
JOIN Employes e ON p.employe_id = e.id;

-- Compter les ouvrages par type
SELECT type, COUNT(*) as nombre 
FROM Ouvrages 
GROUP BY type;

-- Voir les dernières connexions (à implémenter)
SELECT email, date_creation 
FROM Employes 
ORDER BY date_creation DESC;
```

**Exécuter :** Sélectionner la requête → Clic droit → "Run Selected Query"

### 3. Monitoring en temps réel

**Créer un fichier `db-monitor.js` :**
```javascript
const { Sequelize } = require('sequelize');

const sequelize = new Sequelize({
  dialect: 'sqlite',
  storage: 'database/soakoja.db',
  logging: console.log  // Affiche toutes les requêtes
});

// Test de connexion
async function testDB() {
  try {
    await sequelize.authenticate();
    console.log('✅ Connexion DB OK');
    
    // Statistiques rapides
    const stats = await Promise.all([
      sequelize.query("SELECT COUNT(*) as count FROM Employes"),
      sequelize.query("SELECT COUNT(*) as count FROM Ouvrages"),
      sequelize.query("SELECT COUNT(*) as count FROM Plannings")
    ]);
    
    console.log('📊 Stats DB:', {
      employes: stats[0][0][0].count,
      ouvrages: stats[1][0][0].count,
      plannings: stats[2][0][0].count
    });
    
  } catch (error) {
    console.error('❌ Erreur DB:', error.message);
  }
}

testDB();
```

**Utilisation :** `node db-monitor.js`

---

## 🔄 Workflow de développement quotidien {#workflow}

### 1. Routine de démarrage

**Checklist quotidienne :**
```bash
# 1. Ouvrir VS Code dans le projet
code /chemin/vers/soakoja-app

# 2. Vérifier Git status
git status

# 3. Mettre à jour les dépendances si nécessaire
npm update

# 4. Démarrer en mode développement
npm run dev  # ou npm start
```

### 2. Workflow de développement d'une nouvelle fonctionnalité

**Exemple : Ajouter une gestion des factures**

**Étape 1 - Planification :**
```javascript
// 1. Créer le modèle dans server.js
const Facture = sequelize.define('Facture', {
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  numero: { type: DataTypes.STRING, unique: true, allowNull: false },
  montant: { type: DataTypes.FLOAT, allowNull: false },
  date_emission: { type: DataTypes.DATE, defaultValue: DataTypes.NOW },
  statut: { type: DataTypes.ENUM('impayee', 'payee', 'annulee'), defaultValue: 'impayee' },
  point_eau_id: { type: DataTypes.INTEGER, references: { model: PointEau, key: 'id' } }
});

// 2. Définir les relations
Facture.belongsTo(PointEau, { foreignKey: 'point_eau_id' });
```

**Étape 2 - Routes :**
```javascript
// 3. Routes pour les factures
app.get('/factures', requireAuth, async (req, res) => {
  try {
    const factures = await Facture.findAll({
      include: [PointEau],
      order: [['date_emission', 'DESC']]
    });
    res.render('factures/liste', { user: req.session.user, factures });
  } catch (error) {
    console.error('Erreur factures:', error);
    res.render('factures/liste', { user: req.session.user, factures: [] });
  }
});

app.post('/factures', requireAuth, requireLevel(2), async (req, res) => {
  try {
    await Facture.create(req.body);
    res.redirect('/factures');
  } catch (error) {
    console.error('Erreur création facture:', error);
    res.redirect('/factures?error=creation');
  }
});
```

**Étape 3 - Template (créer views/factures/liste.ejs) :**
```html
<!-- Template similaire aux autres listes -->
<div class="container">
  <div class="page-header">
    <h1>💰 Factures</h1>
    <a href="/factures/nouvelle" class="btn btn-primary">+ Nouvelle facture</a>
  </div>
  
  <div class="table-container">
    <table class="data-table">
      <thead>
        <tr>
          <th>Numéro</th>
          <th>Point d'eau</th>
          <th>Montant</th>
          <th>Date émission</th>
          <th>Statut</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        <% factures.forEach(facture => { %>
        <tr>
          <td><%= facture.numero %></td>
          <td><%= facture.PointEau.nomAbonne %></td>
          <td><%= facture.montant %> Ar</td>
          <td><%= new Date(facture.date_emission).toLocaleDateString('fr-FR') %></td>
          <td>
            <span class="status <%= facture.statut %>">
              <%= facture.statut %>
            </span>
          </td>
          <td>
            <a href="/factures/<%= facture.id %>" class="btn btn-sm">Voir</a>
          </td>
        </tr>
        <% }) %>
      </tbody>
    </table>
  </div>
</div>
```

**Étape 4 - Test :**
1. **Démarrer** avec F5
2. **Placer breakpoints** dans les routes
3. **Tester** via le navigateur
4. **Vérifier** la base de données avec SQLite Viewer

### 3. Gestion des erreurs systématique

**Template d'error handling :**
```javascript
// Fonction utilitaire pour gérer les erreurs
const handleError = (error, req, res, redirectTo = '/') => {
  console.error(`Erreur ${req.path}:`, error);
  console.error('Stack:', error.stack);
  console.error('Body:', req.body);
  console.error('User:', req.session.user);
  
  if (req.headers.accept && req.headers.accept.includes('application/json')) {
    res.status(500).json({ error: error.message });
  } else {
    res.redirect(`${redirectTo}?error=${encodeURIComponent(error.message)}`);
  }
};

// Utilisation dans toutes les routes
app.post('/route-exemple', requireAuth, async (req, res) => {
  try {
    // Logique métier ici
  } catch (error) {
    handleError(error, req, res, '/fallback-route');
  }
});
```

---

## ⌨️ Raccourcis indispensables {#shortcuts}

### Raccourcis généraux

| Raccourci | Action |
|-----------|--------|
| `Ctrl+P` | Quick Open (ouvrir fichier rapidement) |
| `Ctrl+Shift+P` | Command Palette (toutes les commandes) |
| `Ctrl+,` | Settings (paramètres) |
| `Ctrl+Shift+E` | Explorer (sidebar fichiers) |
| `Ctrl+Shift+F` | Search (recherche globale) |
| `Ctrl+Shift+G` | Git (contrôle de version) |
| `Ctrl+Shift+X` | Extensions |
| `Ctrl+Shift+D` | Debug |

### Raccourcis d'édition

| Raccourci | Action |
|-----------|--------|
| `Ctrl+/` | Commenter/décommenter |
| `Alt+↑/↓` | Déplacer ligne |
| `Shift+Alt+↑/↓` | Dupliquer ligne |
| `Ctrl+D` | Sélectionner mot suivant (multi-curseur) |
| `Ctrl+Shift+L` | Sélectionner toutes les occurrences |
| `F2` | Renommer symbole |
| `F12` | Go to Definition |
| `Shift+F12` | Find All References |

### Raccourcis de débogage

| Raccourci | Action |
|-----------|--------|
| `F5` | Start Debugging |
| `Ctrl+F5` | Start Without Debugging |
| `F9` | Toggle Breakpoint |
| `F10` | Step Over |
| `F11` | Step Into |
| `Shift+F11` | Step Out |
| `Ctrl+Shift+F5` | Restart Debugging |

### Raccourcis terminal

| Raccourci | Action |
|-----------|--------|
| `Ctrl+` ` | Ouvrir/fermer terminal |
| `Ctrl+Shift+` ` | Nouveau terminal |
| `Ctrl+PageUp/PageDown` | Changer de terminal |

### Raccourcis personnalisés pour Soakoja

**Créer vos raccourcis :** File → Preferences → Keyboard Shortcuts

**Exemple de raccourcis utiles :**
```json
// Dans keybindings.json
[
  {
    "key": "ctrl+alt+s",
    "command": "workbench.action.tasks.runTask",
    "args": "Start Soakoja Server"
  },
  {
    "key": "ctrl+alt+d",
    "command": "sqlite.explorer.refresh"
  },
  {
    "key": "ctrl+alt+t",
    "command": "workbench.action.terminal.new"
  }
]
```

---

## 🎯 Conseils pratiques pour débuter

### 1. Habitudes à prendre

**Chaque matin :**
1. `git pull` pour récupérer les dernières modifications
2. `npm install` si package.json a changé
3. Vérifier que le serveur démarre avec `npm start`
4. Ouvrir la base de données avec SQLite Viewer pour vérifier l'état

**Pendant le développement :**
- **Sauvegarder souvent** (Ctrl+S - VS Code sauvegarde automatiquement)
- **Commenter votre code** pour vous souvenir
- **Utiliser console.log()** généreusement pour déboguer
- **Tester chaque petite modification** avant de continuer

### 2. Organisation du workspace

**Structure recommandée dans VS Code :**
```
📁 soakoja-app/
├── 📁 .vscode/           # Configuration VS Code
│   ├── settings.json     # Paramètres du projet
│   ├── launch.json       # Configuration debug
│   └── tasks.json        # Tâches automatisées
├── 📁 database/          # Base de données SQLite
├── 📁 views/             # Templates EJS
├── 📁 public/            # CSS, JS, images
├── 📁 routes/            # Routes séparées (future amélioration)
├── 📁 models/            # Modèles séparés (future amélioration)
├── 📁 utils/             # Fonctions utilitaires
├── 📁 tests/             # Tests automatisés
├── 📄 server.js          # Fichier principal
├── 📄 package.json       # Configuration npm
└── 📄 README.md          # Documentation
```

**Créer un fichier utils/helpers.js :**
```javascript
// Fonctions utilitaires réutilisables

// Formater une date en français
const formatDate = (date) => {
  return new Date(date).toLocaleDateString('fr-FR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });
};

// Formater un montant en ariary
const formatMoney = (amount) => {
  return new Intl.NumberFormat('fr-MG', {
    style: 'currency',
    currency: 'MGA',
    minimumFractionDigits: 0
  }).format(amount);
};

// Valider un email
const isValidEmail = (email) => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
};

// Logger personnalisé
const logger = {
  info: (message, data = {}) => {
    console.log(`[INFO] ${new Date().toISOString()} - ${message}`, data);
  },
  error: (message, error = {}) => {
    console.error(`[ERROR] ${new Date().toISOString()} - ${message}`, error);
  },
  debug: (message, data = {}) => {
    if (process.env.NODE_ENV === 'development') {
      console.log(`[DEBUG] ${new Date().toISOString()} - ${message}`, data);
    }
  }
};

module.exports = {
  formatDate,
  formatMoney,
  isValidEmail,
  logger
};
```

**Utilisation dans server.js :**
```javascript
const { formatDate, formatMoney, logger } = require('./utils/helpers');

// Dans vos routes
app.get('/dashboard', requireAuth, async (req, res) => {
  try {
    logger.info('Accès dashboard', { userId: req.session.user.id });
    
    const stats = {
      ouvrages_actifs: await Ouvrage.count({ where: { statut: 'actif' } }),
      // ... autres stats
    };

    res.render('dashboard', { 
      user: req.session.user, 
      stats,
      formatDate,  // Passer la fonction au template
      formatMoney
    });
  } catch (error) {
    logger.error('Erreur dashboard', error);
    res.render('error', { message: 'Erreur de chargement' });
  }
});
```

### 3. Configuration avancée du débogueur

**Créer plusieurs configurations dans launch.json :**

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "🚀 Démarrer Soakoja (Development)",
      "type": "node",
      "request": "launch",
      "program": "${workspaceFolder}/server.js",
      "console": "integratedTerminal",
      "restart": true,
      "env": {
        "NODE_ENV": "development",
        "DEBUG": "soakoja:*",
        "PORT": "3000"
      },
      "runtimeArgs": ["--inspect-brk=9229"],
      "skipFiles": [
        "<node_internals>/**"
      ]
    },
    {
      "name": "🐛 Debug Route Spécifique",
      "type": "node",
      "request": "launch",
      "program": "${workspaceFolder}/server.js",
      "console": "integratedTerminal",
      "env": {
        "NODE_ENV": "development",
        "DEBUG_ROUTES": "true"
      },
      "stopOnEntry": false
    },
    {
      "name": "🧪 Debug Tests",
      "type": "node",
      "request": "launch",
      "program": "${workspaceFolder}/node_modules/mocha/bin/_mocha",
      "args": [
        "--timeout",
        "10000",
        "--colors",
        "${workspaceFolder}/tests/**/*.test.js"
      ],
      "console": "integratedTerminal"
    },
    {
      "name": "🔧 Debug Setup Script",
      "type": "node",
      "request": "launch",
      "program": "${workspaceFolder}/setup.js",
      "console": "integratedTerminal"
    }
  ]
}
```

### 4. Techniques de débogage avancées

#### A. Débogage conditionnel

**Breakpoints avec conditions :**
1. **Clic droit** sur un breakpoint
2. **"Edit Breakpoint"**
3. **Condition :** `req.body.email === 'admin'`
4. Le breakpoint ne s'activera que si la condition est vraie

**Logpoints (messages sans arrêter) :**
1. **Clic droit** dans la marge
2. **"Add Logpoint"**
3. **Message :** `Utilisateur connecté: {req.session.user.email}`

#### B. Débogage des requêtes Sequelize

**Activer les logs SQL détaillés :**
```javascript
const sequelize = new Sequelize({
  dialect: 'sqlite',
  storage: 'database/soakoja.db',
  logging: (sql, timing) => {
    if (process.env.NODE_ENV === 'development') {
      console.log(`[SQL] ${sql}`);
      if (timing) console.log(`[TIMING] ${timing}ms`);
    }
  },
  benchmark: true  // Affiche le temps d'exécution
});
```

**Debugger les requêtes complexes :**
```javascript
// Exemple: Déboguer une requête avec jointures
app.get('/plannings', requireAuth, async (req, res) => {
  try {
    const plannings = await Planning.findAll({
      include: [
        {
          model: Employe,
          attributes: ['nom', 'prenom']  // 🔍 Voir quels champs sont récupérés
        },
        {
          model: Ouvrage,
          attributes: ['nom', 'type']
        }
      ],
      order: [['date_debut', 'DESC']],
      limit: 10  // 🔍 Limiter pour les tests
    });
    
    // 🔴 BREAKPOINT ICI pour inspecter le résultat
    console.log('Plannings trouvés:', plannings.length);
    console.log('Premier planning:', JSON.stringify(plannings[0], null, 2));
    
    res.render('plannings/liste', { 
      user: req.session.user, 
      plannings 
    });
  } catch (error) {
    // 🔴 BREAKPOINT pour erreurs SQL
    console.error('Erreur SQL détaillée:', {
      message: error.message,
      sql: error.sql,
      original: error.original
    });
    res.render('plannings/liste', { 
      user: req.session.user, 
      plannings: [],
      error: 'Erreur de chargement des plannings'
    });
  }
});
```

#### C. Débogage des templates EJS

**Créer un helper de debug pour EJS :**

**Dans utils/helpers.js :**
```javascript
// Helper pour déboguer dans les templates
const debugTemplate = (data, label = 'DEBUG') => {
  if (process.env.NODE_ENV === 'development') {
    console.log(`[TEMPLATE ${label}]`, JSON.stringify(data, null, 2));
  }
  return ''; // Ne rien afficher dans le template
};

module.exports = {
  // ... autres helpers
  debugTemplate
};
```

**Dans vos templates EJS :**
```html
<!-- views/dashboard.ejs -->
<%- debugTemplate(stats, 'STATS') %>
<%- debugTemplate(user, 'USER') %>

<div class="stats-grid">
  <% if (stats && stats.ouvrages_actifs !== undefined) { %>
    <div class="stat-card">
      <h3><%= stats.ouvrages_actifs %></h3>
      <p>Ouvrages actifs</p>
    </div>
  <% } else { %>
    <%- debugTemplate('Stats manquantes!', 'ERROR') %>
    <div class="error">Données non disponibles</div>
  <% } %>
</div>
```

### 5. Tests et validation

#### A. Créer des tests simples

**Installer les outils de test :**
```bash
npm install --save-dev mocha chai supertest
```

**Créer tests/basic.test.js :**
```javascript
const request = require('supertest');
const { expect } = require('chai');

// Importer votre app (il faut modifier server.js pour exporter app)
const app = require('../server');

describe('Tests de base Soakoja', () => {
  
  describe('Routes publiques', () => {
    it('GET /login devrait retourner 200', (done) => {
      request(app)
        .get('/login')
        .expect(200)
        .end(done);
    });

    it('GET / devrait rediriger vers /login', (done) => {
      request(app)
        .get('/')
        .expect(302)
        .expect('Location', '/login')
        .end(done);
    });
  });

  describe('Authentification', () => {
    it('POST /login avec mauvais credentials devrait retourner erreur', (done) => {
      request(app)
        .post('/login')
        .send({
          email: 'faux@email.com',
          password: 'mauvais'
        })
        .expect(200) // Reste sur la page login
        .end((err, res) => {
          if (err) return done(err);
          expect(res.text).to.include('Email ou mot de passe incorrect');
          done();
        });
    });

    it('POST /login avec bons credentials devrait rediriger', (done) => {
      request(app)
        .post('/login')
        .send({
          email: 'admin',
          password: 'admin123'
        })
        .expect(302)
        .expect('Location', '/dashboard')
        .end(done);
    });
  });

});
```

**Modifier server.js pour les tests :**
```javascript
// À la fin de server.js, ajouter :
if (require.main === module) {
  // Démarre le serveur seulement si exécuté directement
  app.listen(PORT, async () => {
    console.log(`🚀 Serveur Soakoja démarré sur http://localhost:${PORT}`);
    await initializeDatabase();
  });
}

// Exporter l'app pour les tests
module.exports = app;
```

**Ajouter script dans package.json :**
```json
{
  "scripts": {
    "start": "node server.js",
    "test": "mocha tests/**/*.test.js --timeout 10000",
    "test-watch": "mocha tests/**/*.test.js --watch"
  }
}
```

#### B. Tests de la base de données

**Créer tests/database.test.js :**
```javascript
const { expect } = require('chai');
const { Sequelize, DataTypes } = require('sequelize');
const bcrypt = require('bcrypt');

describe('Tests de base de données', () => {
  let sequelize;
  let Employe;

  before(async () => {
    // Base de test en mémoire
    sequelize = new Sequelize('sqlite::memory:', { logging: false });
    
    // Définir le modèle
    Employe = sequelize.define('Employe', {
      id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
      nom: { type: DataTypes.STRING, allowNull: false },
      email: { type: DataTypes.STRING, unique: true, allowNull: false },
      mot_de_passe: { type: DataTypes.STRING, allowNull: false }
    });

    await sequelize.sync();
  });

  after(async () => {
    await sequelize.close();
  });

  it('devrait créer un employé', async () => {
    const employe = await Employe.create({
      nom: 'Test',
      email: 'test@soakoja.mg',
      mot_de_passe: await bcrypt.hash('password123', 10)
    });

    expect(employe.nom).to.equal('Test');
    expect(employe.email).to.equal('test@soakoja.mg');
  });

  it('devrait empêcher les doublons d\'email', async () => {
    try {
      await Employe.create({
        nom: 'Test2',
        email: 'test@soakoja.mg', // Email déjà utilisé
        mot_de_passe: 'password'
      });
      // Si ça arrive ici, c'est une erreur
      expect.fail('Devrait avoir rejeté le doublon');
    } catch (error) {
      expect(error.name).to.equal('SequelizeUniqueConstraintError');
    }
  });
});
```

### 6. Monitoring et logs avancés

#### A. Configuration de Winston (logging professionnel)

**Installer Winston :**
```bash
npm install winston
```

**Créer utils/logger.js :**
```javascript
const winston = require('winston');
const path = require('path');

// Créer le dossier logs s'il n'existe pas
const logDir = 'logs';
const fs = require('fs');
if (!fs.existsSync(logDir)) {
  fs.mkdirSync(logDir);
}

// Configuration des formats de logs
const logFormat = winston.format.printf(({ timestamp, level, message, ...meta }) => {
  let log = `${timestamp} [${level.toUpperCase()}]: ${message}`;
  if (Object.keys(meta).length > 0) {
    log += ` ${JSON.stringify(meta)}`;
  }
  return log;
});

// Créer le logger
const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp({
      format: 'YYYY-MM-DD HH:mm:ss'
    }),
    winston.format.errors({ stack: true }),
    winston.format.json()
  ),
  defaultMeta: { service: 'soakoja-app' },
  transports: [
    // Fichier pour les erreurs
    new winston.transports.File({ 
      filename: path.join(logDir, 'error.log'), 
      level: 'error',
      format: logFormat
    }),
    // Fichier pour tous les logs
    new winston.transports.File({ 
      filename: path.join(logDir, 'combined.log'),
      format: logFormat
    }),
    // Console en développement
    new winston.transports.Console({
      level: 'debug',
      format: winston.format.combine(
        winston.format.colorize(),
        logFormat
      )
    })
  ]
});

// Fonction helper pour les logs d'activité utilisateur
logger.logUserActivity = (userId, action, details = {}) => {
  logger.info('User Activity', {
    userId,
    action,
    timestamp: new Date().toISOString(),
    ...details
  });
};

// Fonction helper pour les logs d'erreur avec contexte
logger.logError = (error, context = {}) => {
  logger.error('Application Error', {
    message: error.message,
    stack: error.stack,
    ...context
  });
};

module.exports = logger;
```

**Utilisation dans server.js :**
```javascript
const logger = require('./utils/logger');

// Remplacer tous les console.log par logger
app.post('/login', async (req, res) => {
  try {
    const { email, password } = req.body;
    logger.info('Tentative de connexion', { email });

    const user = await Employe.findOne({ where: { email, statut: 'actif' } });
    
    if (user && await bcrypt.compare(password, user.mot_de_passe)) {
      req.session.user = { /* ... */ };
      
      logger.logUserActivity(user.id, 'LOGIN_SUCCESS', {
        email: user.email,
        ip: req.ip,
        userAgent: req.get('User-Agent')
      });
      
      res.redirect('/dashboard');
    } else {
      logger.warn('Echec de connexion', { 
        email, 
        ip: req.ip,
        reason: user ? 'wrong_password' : 'user_not_found'
      });
      res.render('login', { error: 'Email ou mot de passe incorrect' });
    }
  } catch (error) {
    logger.logError(error, {
      route: '/login',
      body: req.body,
      ip: req.ip
    });
    res.render('login', { error: 'Erreur de connexion' });
  }
});
```

#### B. Monitoring en temps réel

**Créer utils/monitor.js :**
```javascript
const os = require('os');
const logger = require('./logger');

class AppMonitor {
  constructor() {
    this.startTime = Date.now();
    this.requestCount = 0;
    this.errorCount = 0;
  }

  // Middleware pour compter les requêtes
  requestCounter() {
    return (req, res, next) => {
      this.requestCount++;
      const startTime = Date.now();
      
      // Log de la requête
      logger.debug('Incoming request', {
        method: req.method,
        url: req.url,
        ip: req.ip,
        userAgent: req.get('User-Agent')
      });

      // Intercepter la fin de la réponse
      const originalSend = res.send;
      res.send = function(data) {
        const duration = Date.now() - startTime;
        logger.info('Request completed', {
          method: req.method,
          url: req.url,
          statusCode: res.statusCode,
          duration: `${duration}ms`
        });
        originalSend.call(this, data);
      };

      next();
    };
  }

  // Middleware pour compter les erreurs
  errorHandler() {
    return (error, req, res, next) => {
      this.errorCount++;
      logger.logError(error, {
        route: req.path,
        method: req.method,
        body: req.body,
        user: req.session?.user?.id
      });
      next(error);
    };
  }

  // Statistiques système
  getSystemStats() {
    const uptime = Math.floor((Date.now() - this.startTime) / 1000);
    return {
      uptime: `${uptime}s`,
      requests: this.requestCount,
      errors: this.errorCount,
      memory: {
        used: Math.round(process.memoryUsage().rss / 1024 / 1024) + ' MB',
        free: Math.round(os.freemem() / 1024 / 1024) + ' MB',
        total: Math.round(os.totalmem() / 1024 / 1024) + ' MB'
      },
      cpu: os.loadavg(),
      platform: os.platform(),
      nodeVersion: process.version
    };
  }

  // Route de status pour monitoring externe
  statusRoute() {
    return (req, res) => {
      const stats = this.getSystemStats();
      res.json({
        status: 'OK',
        timestamp: new Date().toISOString(),
        ...stats
      });
    };
  }
}

module.exports = AppMonitor;
```

**Utilisation dans server.js :**
```javascript
const AppMonitor = require('./utils/monitor');
const monitor = new AppMonitor();

// Appliquer le monitoring
app.use(monitor.requestCounter());

// Route de status
app.get('/api/status', monitor.statusRoute());

// Handler d'erreur global
app.use(monitor.errorHandler());
```

---

## 🎯 Conclusion et prochaines étapes

### Ce que vous savez maintenant faire avec VS Code :

✅ **Installer et configurer** VS Code pour Node.js  
✅ **Déboguer efficacement** avec des breakpoints  
✅ **Visualiser votre base** SQLite directement  
✅ **Utiliser l'autocomplétion** pour coder plus vite  
✅ **Créer des snippets** personnalisés  
✅ **Monitorer votre application** en temps réel  
✅ **Écrire des tests** automatisés  
✅ **Gérer les erreurs** de façon professionnelle  

### Roadmap d'apprentissage suggérée :

#### **Semaine 1-2 : Maîtrise de base**
- Installer toutes les extensions recommandées
- Configurer le débogueur
- Apprendre les raccourcis essentiels
- Pratiquer avec des breakpoints

#### **Semaine 3-4 : Développement avancé**  
- Créer vos propres snippets
- Maîtriser la navigation dans le code
- Utiliser les outils de refactoring
- Intégrer le monitoring

#### **Semaine 5+ : Expertise**
- Écrire des tests automatisés
- Optimiser votre workflow
- Contribuer à des projets open source
- Apprendre TypeScript pour plus de robustesse

### Ressources pour aller plus loin :

📚 **Documentation officielle :**
- [VS Code Node.js Tutorial](https://code.visualstudio.com/docs/nodejs/nodejs-tutorial)
- [VS Code Debugging Guide](https://code.visualstudio.com/docs/editor/debugging)

🎥 **Vidéos recommandées :**
- Rechercher "VS Code Node.js debugging" sur YouTube
- Tutoriels sur les extensions JavaScript

🌟 **Conseils finaux :**
- **Pratiquez régulièrement** - L'efficacité vient avec l'habitude
- **Personnalisez votre environnement** selon vos besoins
- **N'hésitez pas à explorer** les fonctionnalités avancées
- **Rejoignez la communauté** VS Code pour des astuces

---

*Vous avez maintenant tous les outils pour développer efficacement avec VS Code sur votre projet Soakoja ! 🚀*