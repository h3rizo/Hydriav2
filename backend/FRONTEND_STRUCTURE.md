# Structure Frontend - Application Hydria

## 📋 Vue d'ensemble

Application Nuxt.js 3 + Vue 3 + TypeScript + Tailwind CSS + DaisyUI pour la gestion des activités d'approvisionnement en eau à Madagascar.

## 🗂️ Structure des menus (depuis base.html)

### 1. 🔍 Recherche Globale
- URL : `/search`
- Icône : `fa-search`

### 2. 📰 Fil d'actualité
- URL : `/feed`
- Icône : `fa-rss`
- **Pages importantes créées :**
  - Page principale avec posts automatiques et manuels
  - Affichage auteur (surnom ou "Système")
  - Commentaires, likes, dislikes
  - Filtres : commune, ouvrage, employé, type, priorité

### 3. 📊 Tableaux de bord
- **Vue d'ensemble** : `/dashboard`
- **Paiements forfaitaires** : `/dashboard/payments-flat`
- **Paiements au volume** : `/dashboard/payments-volume`
- **Dépenses** : `/dashboard/expenses`
- **État des ouvrages** : `/dashboard/infrastructure`
- **Comptabilité** : `/dashboard/comptabilite`
- **Carte interactive** : `/dashboard/map`

### 4. 📅 Plannings

#### Vue d'ensemble et calendrier
- **Vue d'ensemble** : `/planning/dashboard`
- **Vue calendrier** : `/planning/calendar`
- **Saisie planning** : `/planning/dashboard`

#### Opérations terrain
- **Livraison** : `/planning/livraisons`
  - Gestion des bons de livraison
  - Tracking des livraisons
- **Avance** : `/planning/avances`
  - Gestion des avances financières
- **Retour (Caissière)** : `/billing/retours-caissiere`
  - **Page importante créée :**
    - Scanner QR code
    - Validation retours tickets
    - Impact stock automatique
    - Table temporaire DiameX

#### Suivi & Contrôle
- **Inspections & Maintenance** : `/inspections`
- **Positions GPS Employés** : `/employees/positions-gps`
- **Suivi avance** : `/planning/suivi-avance`

#### Chantiers
- **Demandes Villages** : `/chantiers/demandes`
  - **Page créée :** Liste demandes avec filtres
- **Validation Sources** : `/chantiers/validations`
  - **Page importante créée :**
    - Proposition (Construction/Réhabilitation/Réparation)
    - Nombre de sources visitées
    - GPS capture (mobile)
    - Scanner documents
    - Import/Export Excel
    - Bouton "Vider table" pour reimport
- **Chantiers** : `/chantiers/list`
- **Kanban Chantiers** : `/chantiers/kanban`
- **Tâcherons** : `/chantiers/tacherons`

#### WASH & Enquêtes
- **Ménages & Enquêtes** : `/chantiers/list?enquetes=1`
- **Animations WASH** : `/chantiers/list?animations=1`

### 5. 📈 Rapports
- **Tableau de bord** : `/rapports`
- **Activités par employé** : `/rapports/activites-employe`
- **Performance bases** : `/rapports/performance-bases`
- **Indicateurs DiameX** : `/rapports/diamex`

### 6. 💳 Paiements
- **Vue d'ensemble** : `/billing/dashboard`
- **Factures** : `/billing/factures`
- **Paiements** : `/billing/paiements`
- **Gestion forfaitaire** : `/billing/forfaitaire`
- **Gestion volumétrique** : `/billing/volumetrique`
- **Demandes BP (Branchements Privés)** : `/billing/demandes-bp`
  - **Page importante créée :**
    - Workflow BP complet
    - Stats (en attente, branchés, exportés, montant total)
    - Filtres (recherche, ouvrage, statut)
    - Actions : créer, modifier, exporter vers DiameX
    - Modal table temporaire DiameX

### 7. 📋 Relevés
- **Liste des relevés** : `/billing/releves`
  - **Page créée :**
    - Workflow relevés complet
    - Sélection points d'eau (lignes cliquables)
    - Saisie relevés par compteur
- **Compteurs** : `/billing/compteurs`
- **Suivi consommation** : `/billing/suivi-consommation`

### 8. 🧾 Comptabilité
- **Tableau de bord** : `/accounting/dashboard`
- **Comptabilité DiameX** : `/accounting/entries`
  - **Page importante créée :**
    - Vérification comptabilité avec édition
    - Ouverture fichiers scannés (via serveur)
    - Filtres avancés
- **Import DiameX** : `/accounting/import`
- **Recoupement Planning** : `/accounting/recoupement`
- **Transactions Temporaires** : `/accounting/transactions`

### 9. 👥 Usagers
- **Représentantes & Avis** : `/usagers/representants`

### 10. 💳 Cartes sociales
- **Gestion cartes** : `/cartes-sociales`
- **Encaissement** : `/cartes-sociales/encaissement`
- **Suivi usage** : `/cartes-sociales/suivi`
- **Reporting social** : `/cartes-sociales/reporting`

### 11. 📦 Achats/Stocks
- **Vue d'ensemble** : `/inventory/dashboard`
- **Saisie achats** : `/inventory/purchases`
- **Inventaires** : `/inventory/stocks`
- **Fiches de Stock** : `/inventory/fiche-stock`
- **Résumé Stocks** : `/inventory/summary`
- **Bons de commande** : `/inventory/commandes`
- **Transferts** : `/inventory/transferts`

### 12. 💬 Conversations
- **Mes conversations** : `/messaging/conversations`
- **Nouveau chat** : Modal `newDirectModal`
- **Nouveau groupe** : Modal `newGroupModal`
- **Assistant IA** : Floating chat
- **Requête rapide** : Modal quick query

### 13. ⚙️ Administration

#### Système
- **Interface Django** : `/admin`
- **Intégration DiameX** : `/accounting/import`
- **Transactions Temporaires** : `/accounting/transactions`
- **Gestion Fichiers** : `/filemanager`

#### Géographie
- **Géographie** : `/geography`
  - Régions, Districts, Communes, Fokontanys, Villages, Parcelles
- **Géographie Consolidée** : `/geography/consolidated`

#### Organisations
- **Organisations** : `/organization`
  - Organisations, Bases, Comptes, Postes, Magasins, Journaux, Employés

#### Ouvrages
- **Ouvrages** : `/organization/ouvrages`
  - Ouvrages, Points d'Eau, Équipements, Compteurs, Tarifs, Modalités, Adresses, Fournisseurs, Cartes Sociales

#### Planning & Activités
- **Activités** : `/planning/activites`
- **Désignations** : `/planning/designations`
- **Déplacements** : `/planning/deplacements`
  - **Page créée :**
    - CRUD complet
    - Prix par trajet (taxi-brousse, pirogue, bac)
    - Import/Export Excel

#### Employés
- **Employés** : `/employees`
- **Postes** : `/employees/postes`
- **Positions GPS** : `/employees/positions-gps`

## 🎨 Design System

### Thèmes
- **Light** : `winter` (DaisyUI)
- **Dark** : `dark` (DaisyUI)
- Switcher dans la navbar

### Couleurs principales (DaisyUI)
- **Primary** : Bleu (actions principales)
- **Secondary** : Violet (actions secondaires)
- **Accent** : Vert-bleu (mise en évidence)
- **Info** : Bleu clair (informations)
- **Success** : Vert (succès, validations)
- **Warning** : Orange (avertissements)
- **Error** : Rouge (erreurs)

### Icônes
- **Font Awesome 6.x** (free)
- Classes : `fa-solid`, `fa-regular`, `fa-light`, `fa-duotone`

### Composants DaisyUI utilisés
- **Navbar** : Menu principal responsive
- **Drawer** : Menu latéral mobile
- **Card** : Conteneurs de contenu
- **Badge** : Labels et tags
- **Button** : Boutons avec variantes
- **Modal** : Dialogues et pop-ups
- **Dropdown** : Menus déroulants
- **Table** : Tableaux de données
- **Form Controls** : Inputs, selects, checkboxes
- **Alert** : Messages d'information
- **Toast** : Notifications temporaires
- **Tabs** : Onglets de navigation
- **Collapse** : Accordéons
- **Stats** : Cartes de statistiques

## 🔑 Fonctionnalités importantes implémentées

### 1. Fil d'actualité (Feed)
- Posts automatiques : "Système" comme auteur
- Posts manuels : Surnom de l'employé
- Commentaires avec réponses
- Likes/Dislikes
- Filtres avancés
- Images attachées

### 2. Module Caissière - Retours
- Scanner QR code (ZXing)
- Saisie manuelle fallback
- Validation tickets (livraison, avance, recette)
- Impact stock automatique
- Table temporaire DiameX
- Mise à jour prix unitaires (désignations "Avance")

### 3. Demandes BP (Branchements Privés)
- Workflow complet
- Export vers table temporaire DiameX
- Stats en temps réel
- Filtres par statut (en attente, branchés)

### 4. Validation Sources
- Proposition travaux (Construction/Réhabilitation/Réparation)
- Nombre de sources visitées
- GPS haute précision (mobile)
- Scanner documents
- Import/Export Excel avec UUID fix
- Bouton "Vider table" avec double confirmation

### 5. Relevés
- Points d'eau cliquables (rows entiers)
- Workflow par compteur
- Prévention conflits avec boutons/radio

### 6. Vérification Comptabilité
- Édition in-app
- Ouverture fichiers via serveur (bypass navigateur)
- Mise à jour Django + Access
- Feedback multi-niveaux (success/warning/error)

### 7. Déplacements
- CRUD complet
- Trajet entre villages
- Moyens de transport (taxi-brousse, pirogue, bac)
- Prix par trajet avec historique dates
- Import/Export Excel

### 8. Gestion Timezone (CRITICAL)
- Timezone : `Indian/Antananarivo` (UTC+3)
- Import : `tz_madagascar.localize()` (PAS `make_aware`)
- Affichage : `.astimezone(tz_madagascar)` avant `.date()`
- Filtres : En Python APRÈS conversion (JAMAIS en SQL)
- JavaScript : Parser manuel avec `split()` (PAS `new Date(string)`)
- Guide complet : `backend/TIMEZONE_GUIDE.md`

### 9. Filtrage Modalités de Paiement (CRITICAL)
- Chemin : Région > District > Commune > Fokontany > Village > Parcelle > PointEau > Ouvrage > ModaliteGestion
- Inclure modalités `forfaitaire` ET `mixte`
- Filtrer points d'eau par géographie → récupérer IDs ouvrages → filtrer modalités
- Mise à jour dynamique des compteurs dashboard/feed
- Guide : CLAUDE.md section "RÈGLES FILTRAGE MODALITÉS"

## 📱 Mobile-First

### Fonctionnalités mobiles spécifiques
- **GPS capture** : `navigator.geolocation` avec haute précision
- **Camera access** : `<input capture="environment">`
- **Scanner QR** : ZXing library
- **Touch-friendly** : Boutons larges, zones cliquables étendues
- **Responsive** : Drawer menu sur mobile, navbar sur desktop

## 🔄 Intégrations

### DiameX (Système comptable externe)
- Table temporaire : `TemporaireDiameX`
- Types tickets : demande_bp, paiement_forfaitaire, livraison, avance, recette
- Workflow : Django → Table temporaire → Export DiameX
- Statuts : en_attente, envoye, erreur

### Access Database (Legacy)
- Vérification comptabilité
- Mise à jour via pyodbc
- Ouverture fichiers scannés

## 🚀 Prochaines étapes Frontend

### Phase 1 : Setup (Prioritaire)
1. ✅ Analyser structure menus/pages
2. Créer projet Nuxt 3 avec TypeScript
3. Configurer Tailwind CSS + DaisyUI
4. Setup Font Awesome
5. Créer layout de base avec navbar/drawer

### Phase 2 : Pages essentielles
1. Page d'accueil (dashboard principal)
2. Fil d'actualité
3. Planning dashboard + calendrier
4. Demandes BP
5. Validation Sources
6. Relevés workflow

### Phase 3 : Pages secondaires
1. Tous les dashboards
2. Gestion forfaitaire/volumétrique
3. Livraisons/Avances
4. Comptabilité
5. Chantiers (liste + kanban)
6. Inventaire

### Phase 4 : Administration
1. Géographie (CRUD)
2. Organisations (CRUD)
3. Ouvrages (CRUD)
4. Employés (CRUD)
5. Activités/Désignations
6. Déplacements

### Phase 5 : Fonctionnalités avancées
1. Scanner QR code
2. GPS capture
3. Camera access
4. Conversations/Messaging
5. Assistant IA
6. Cartes interactives

## 🔧 Configuration API

### Base URL
- **Production** : À définir
- **Development** : `http://localhost:8000/api/`

### Authentification
- Django Session + CSRF token
- Cookie-based authentication
- OAuth2 Google (optionnel)

### Endpoints clés
- `/feed/` : Fil d'actualité
- `/billing/demandes-bp/api/` : Demandes BP
- `/chantiers/validations/api/` : Validation sources
- `/billing/releves/api/` : Relevés
- `/accounting/entries/api/` : Comptabilité
- `/planning/deplacements/api/` : Déplacements

## 📝 Notes importantes

1. **UUID Export Excel** : Toujours convertir en string (`str(uuid)`) avant export
2. **Timezone** : Suivre strictement `TIMEZONE_GUIDE.md`
3. **Filtrage modalités** : Inclure `forfaitaire` ET `mixte`
4. **Auteur posts** : Surnom prioritaire, sinon nom complet
5. **Mobile** : Tester GPS/Camera sur appareils réels
6. **DiameX** : Utiliser table temporaire pour tous exports
7. **Permissions** : Respecter hiérarchie géographique et organisationnelle
