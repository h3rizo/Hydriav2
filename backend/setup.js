const fs = require('fs');
const path = require('path');

console.log('🚀 Configuration de l\'application Soakoja...\n');

// Créer la structure des dossiers
const directories = [
  'views',
  'views/plannings',
  'views/points-eau',
  'views/partials',
  'views/cartes-sociales',
  'views/admin',
  'public',
  'public/css',
  'public/js',
  'database',
  'logs'
];

directories.forEach(dir => {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
    console.log(`✅ Dossier créé: ${dir}`);
  }
});

// Créer le fichier CSS principal
const cssContent = `
/* =============================================== */
/* STYLES GLOBAUX SOAKOJA AVEC THÈMES */
/* =============================================== */

/* Définition des variables de couleur */
:root {
    --bg-primary: #f5f5f5;
    --bg-secondary: white;
    --bg-tertiary: #f8f9fa;
    --bg-navbar: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    --text-primary: #333;
    --text-secondary: #666;
    --text-on-accent: white;
    --border-color: #dee2e6;
    --shadow-color: rgba(0,0,0,0.08);
    --accent-color: #667eea;
    --btn-primary-bg: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    --btn-secondary-bg: #6c757d;
    --btn-success-bg: #28a745;
    --btn-warning-bg: #ffc107;
    --btn-info-bg: #17a2b8;
    --btn-edit-hover-bg: #e0e0e0;
}

[data-theme="dark"] {
    --bg-primary: #121212;
    --bg-secondary: #1e1e1e;
    --bg-tertiary: #2a2a2a;
    --text-primary: #e0e0e0;
    --text-secondary: #a0a0c0;
    --border-color: #444;
    --shadow-color: rgba(0,0,0,0.4);
    --btn-edit-hover-bg: #3a3a5a;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

html {
    transition: background-color 0.3s, color 0.3s;
}

body {
    font-family: 'Arial', sans-serif;
    background-color: var(--bg-primary);
    line-height: 1.6;
    color: var(--text-primary);
    transition: background-color 0.3s, color 0.3s;
}

/* Navigation */
.navbar {
    background: var(--bg-navbar);
    color: var(--text-on-accent);
    padding: 1rem 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    position: sticky;
    top: 0;
    z-index: 100;
}

.nav-brand h2 {
    margin: 0;
    font-size: 1.5rem;
}

.nav-user {
    display: flex;
    align-items: center;
    gap: 1rem;
}

/* Boutons */
.btn {
    display: inline-block;
    padding: 0.75rem 1.5rem;
    background: #007bff; /* Fallback */
    color: var(--text-on-accent);
    text-decoration: none;
    border-radius: 5px;
    border: none;
    font-size: 1rem;
    cursor: pointer;
    transition: all 0.3s ease;
}

.btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 5px 15px var(--shadow-color);
}

.btn-primary {
    background: var(--btn-primary-bg);
}

.btn-secondary {
    background: var(--btn-secondary-bg);
}

.btn-success {
    background: var(--btn-success-bg);
}

.btn-warning {
    background: var(--btn-warning-bg);
    color: #000;
}

.btn-info {
    background: var(--btn-info-bg);
}

.btn-sm {
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
}

/* Container et Layout */
.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem;
}

.page-header {
    margin-bottom: 2rem;
}

.page-header h1 {
    margin: 0;
    color: var(--text-primary);
    font-size: 2.5rem;
}

.page-header p {
    margin: 0.5rem 0 0 0;
    color: var(--text-secondary);
    font-size: 1.1rem;
}

/* Grilles */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1.5rem;
    margin-bottom: 3rem;
}

.menu-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1.5rem;
}

/* Cartes */
.stat-card, .menu-card, .form-container, .table-container {
    background: var(--bg-secondary);
    padding: 1.5rem;
    border-radius: 10px;
    box-shadow: 0 5px 15px var(--shadow-color);
    transition: transform 0.3s, box-shadow 0.3s;
}

.stat-card {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.menu-card {
    text-decoration: none;
    color: var(--text-primary);
    text-align: center;
    padding: 2rem;
}

.menu-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 10px 25px var(--shadow-color);
}

.stat-icon, .menu-icon {
    font-size: 2.5rem;
}

.menu-icon {
    margin-bottom: 1rem;
}

/* Tableaux */
.table-container {
    overflow: hidden;
    padding: 0; /* Remove padding for table to fit */
}

.data-table {
    width: 100%;
    border-collapse: collapse;
}

.data-table th {
    background: var(--bg-tertiary);
    padding: 1rem;
    text-align: left;
    font-weight: bold;
    border-bottom: 2px solid var(--border-color);
}

.data-table td {
    padding: 1rem;
    border-bottom: 1px solid var(--border-color);
    vertical-align: top;
}

.data-table tr:hover {
    background: var(--bg-tertiary);
}

/* Formulaires */
.form-container {
    padding: 2rem;
}

.form-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 1.5rem;
    margin-bottom: 2rem;
}

.form-group {
    display: flex;
    flex-direction: column;
}

.form-group.full-width {
    grid-column: 1 / -1;
}

label {
    margin-bottom: 0.5rem;
    font-weight: bold;
    color: var(--text-primary);
}

input, select, textarea {
    padding: 0.75rem;
    border: 2px solid var(--border-color);
    border-radius: 5px;
    font-size: 1rem;
    font-family: inherit;
    background-color: var(--bg-secondary);
    color: var(--text-primary);
}

input:focus, select:focus, textarea:focus {
    outline: none;
    border-color: var(--accent-color);
}

/* États et statuts */
.status {
    padding: 0.25rem 0.75rem;
    border-radius: 15px;
    font-size: 0.875rem;
    font-weight: bold;
}

.status.validated, .status.active {
    background: #d4edda;
    color: #155724;
}

.status.pending {
    background: #fff3cd;
    color: #856404;
}

.status.inactive {
    background: #f8d7da;
    color: #721c24;
}

/* État vide */
.empty-state {
    text-align: center;
    padding: 3rem;
    color: var(--text-secondary);
}

/* Responsive */
@media (max-width: 768px) {
    .container {
        padding: 1rem;
    }
    
    .navbar {
        padding: 1rem;
    }
    
    .nav-user {
        flex-direction: column;
        gap: 0.5rem;
    }
    
    .page-header {
        text-align: center;
    }
    
    .page-header h1 {
        font-size: 2rem;
    }
    
    .stats-grid, .menu-grid {
        grid-template-columns: 1fr;
    }
    
    .data-table {
        font-size: 0.875rem;
    }
    
    .data-table th, .data-table td {
        padding: 0.5rem;
    }
}
`;
border - radius: 10px;
overflow: hidden;
box - shadow: 0 5px 15px rgba(0, 0, 0, 0.08);
}

.data - table {
  width: 100 %;
  border - collapse: collapse;
}

.data - table th {
  background: #f8f9fa;
  padding: 1rem;
  text - align: left;
  font - weight: bold;
  border - bottom: 2px solid #dee2e6;
}

.data - table td {
  padding: 1rem;
  border - bottom: 1px solid #dee2e6;
  vertical - align: top;
}

.data - table tr:hover {
  background: #f8f9fa;
}

/* Formulaires */
.form - container {
  background: white;
  padding: 2rem;
  border - radius: 10px;
  box - shadow: 0 5px 15px rgba(0, 0, 0, 0.08);
}

.form - grid {
  display: grid;
  grid - template - columns: repeat(auto - fit, minmax(300px, 1fr));
  gap: 1.5rem;
  margin - bottom: 2rem;
}

.form - group {
  display: flex;
  flex - direction: column;
}

.form - group.full - width {
  grid - column: 1 / -1;
}

label {
  margin - bottom: 0.5rem;
  font - weight: bold;
  color: #333;
}

input, select, textarea {
  padding: 0.75rem;
  border: 2px solid #ddd;
  border - radius: 5px;
  font - size: 1rem;
  font - family: inherit;
}

input: focus, select: focus, textarea:focus {
  outline: none;
  border - color: #667eea;
}

/* États et statuts */
.status {
  padding: 0.25rem 0.75rem;
  border - radius: 15px;
  font - size: 0.875rem;
  font - weight: bold;
}

.status.validated, .status.active {
  background: #d4edda;
  color: #155724;
}

.status.pending {
  background: #fff3cd;
  color: #856404;
}

.status.inactive {
  background: #f8d7da;
  color: #721c24;
}

/* État vide */
.empty - state {
  text - align: center;
  padding: 3rem;
  color: #666;
}

/* Responsive */
@media(max - width: 768px) {
    .container {
    padding: 1rem;
  }
    
    .navbar {
    padding: 1rem;
  }
    
    .nav - user {
    flex - direction: column;
    gap: 0.5rem;
  }
    
    .page - header {
    text - align: center;
  }
    
    .page - header h1 {
    font - size: 2rem;
  }
    
    .stats - grid, .menu - grid {
    grid - template - columns: 1fr;
  }
    
    .data - table {
    font - size: 0.875rem;
  }
    
    .data - table th, .data - table td {
    padding: 0.5rem;
  }
} `;

const cssPath = path.join('public', 'css', 'style.css');
fs.writeFileSync(cssPath, cssContent);
console.log('✅ Fichier CSS créé: public/css/style.css');

// Créer le fichier README
const readmeContent = `# Application Soakoja

Application web de gestion d'eau potable pour Soakoja Madagascar.

## Installation

1. ** Installer Node.js ** (version 16 ou supérieure)
- Télécharger depuis https://nodejs.org/

2. ** Cloner ou télécharger le projet **

  3. ** Installation des dépendances **
\`\`\`bash
   npm install
   \`\`\`

4. **Démarrer l'application**
   \`\`\`bash
   npm start
   \`\`\`

5. **Ouvrir dans le navigateur**
   - http://localhost:3000

## Comptes de test

- **Administrateur**: admin / admin123 (niveau 4)
- **Caissière**: marie / marie123 (niveau 2) 
- **Agent terrain**: jean / jean123 (niveau 1)

## Structure

- \`server.js\` - Serveur principal
- \`views/\` - Templates EJS
- \`public/\` - Fichiers statiques (CSS, JS)
- \`database/\` - Base de données SQLite

## Fonctionnalités

- ✅ Authentification multi-niveaux
- ✅ Gestion des plannings d'activités
- ✅ Suivi des ouvrages d'eau
- ✅ Gestion des points d'eau
- ✅ Cartes sociales (tarifs préférentiels)
- ✅ Interface responsive
- 🔄 Intégration DiameX (en cours)

## Développement

Pour le mode développement avec rechargement automatique:
\`\`\`bash
npm run dev
\`\`\`
`;

fs.writeFileSync('README.md', readmeContent);
console.log('✅ Fichier README créé');

console.log('\n🎉 Configuration terminée!');
console.log('\n📋 Prochaines étapes:');
console.log('1. npm install');
console.log('2. npm start');
console.log('3. Ouvrir http://localhost:3000');
console.log('4. Se connecter avec admin/admin123');