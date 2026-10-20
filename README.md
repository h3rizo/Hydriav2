# 🌊 Hydria - Système de gestion de l'eau Madagascar

Application web complète pour la gestion opérationnelle, financière et administrative des activités d'approvisionnement en eau à Madagascar.

## 🚀 Démarrage rapide

### Prérequis
- Python 3.13+
- Node.js 18+
- PostgreSQL (via Supabase)

### Installation

1. **Backend Django**
```powershell
cd backend
# PowerShell
.\venv\Scripts\Activate.ps1
# ou Command Prompt: venv\Scripts\activate.bat
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

2. **Frontend (Tailwind CSS)**
```bash
cd frontend
npm install
npm run dev  # Mode watch pour développement
# ou
npm run build  # Build production
```

### Accès
- **Application**: http://localhost:8000
- **Admin Django**: http://localhost:8000/admin

## 📋 Fonctionnalités

### ✅ Implémentées
- [x] Architecture Django + PostgreSQL/Supabase
- [x] Interface moderne Tailwind CSS + DaisyUI  
- [x] Mode sombre/clair avec switch
- [x] Navbar responsive multi-niveaux
- [x] Système d'authentification de base
- [x] Structure backend/frontend séparée

### 🔄 En développement
- [ ] Modèles Django basés sur schéma Supabase
- [ ] Système d'authentification avec niveaux d'accès
- [ ] Gestion des plannings et indemnités
- [ ] Facturation et relevés compteurs
- [ ] Cartes sociales
- [ ] Achats et gestion des stocks

### 🎯 Prévues
- [ ] Rapports et exports PDF/Excel
- [ ] API REST complète
- [ ] Intégration DiameX
- [ ] Mode hors-ligne partiel

## 🏗️ Architecture

```
hydria-nuxt-django/
├── backend/           # Django API + Templates
│   ├── hydria/        # Configuration Django
│   ├── apps/          # Applications modulaires
│   ├── templates/     # Templates Django
│   ├── static/        # Fichiers statiques
│   └── venv/          # Environnement Python
├── frontend/          # Interface utilisateur
│   ├── src/css/       # Sources Tailwind
│   ├── dist/          # CSS compilé
│   └── node_modules/  # Dépendances NPM
└── CLAUDE.md         # Documentation développement
```

## 🎨 Technologies

### Backend
- **Django 5.2.6** - Framework web Python
- **PostgreSQL** - Base de données (Supabase)
- **Django REST Framework** - API REST
- **Python-decouple** - Configuration

### Frontend
- **Tailwind CSS 3.4** - Framework CSS utilitaire
- **DaisyUI 5.1** - Composants UI pré-construits
- **PostCSS** - Traitement CSS
- **Autoprefixer** - Compatibilité navigateurs

### Base de données
- **Supabase** - PostgreSQL hébergé
- **Modèles métier** - Employés, Plannings, Facturation, Stocks

## 🔧 Configuration

### Variables d'environnement (.env)
```env
DATABASE_URL=postgresql://...
SUPABASE_URL=https://...
SUPABASE_SERVICE_KEY=...
SECRET_KEY=...
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

### Thèmes DaisyUI disponibles
- **cupcake** - Thème clair (défaut)
- **night** - Thème sombre
- **hydria** - Thème personnalisé bleu/vert

## 👥 Contexte métier

### Utilisateurs cibles
- **Employés** - Accès selon poste et niveau menu (0-4)
- **Gestionnaires** - Validation plannings (niveau ≥3)
- **Administrateurs** - Accès complet système

### Modules fonctionnels
1. **Plannings** - Activités, indemnités, validation
2. **Facturation** - Forfaitaire/volumétrique, relevés
3. **Cartes sociales** - Gestion consommations 
4. **Achats/Stocks** - Fournisseurs, inventaires
5. **Rapports** - Exports, tableaux de bord

## 📖 Documentation

Voir `CLAUDE.md` pour le journal détaillé du développement et les commandes exécutées.