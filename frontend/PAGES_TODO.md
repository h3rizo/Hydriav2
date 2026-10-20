# Pages à créer - Frontend Hydria

## ✅ INFRASTRUCTURE COMPLÉTÉE (2 novembre 2025)

### Composables créés :
- [x] **useApi.ts** - Gestion des appels API avec CSRF token Django
- [x] **useTimezone.ts** - Gestion timezone Madagascar (UTC+3) avec parsing manuel dates

### Layout mis à jour (default.vue) :
- [x] **Menu mobile** - Complet et aligné avec backend Django
- [x] **Menu desktop** - Complet et aligné avec backend Django
- [x] Fil d'actualité ajouté (lien direct)
- [x] Section Chantiers complète (Demandes Villages, Validation Sources, Kanban, Tâcherons, WASH)
- [x] Section Comptabilité ajoutée (Dashboard, DiameX, Import, Recoupement, Transactions)
- [x] Section Usagers ajoutée (Représentantes & Avis)
- [x] Section Administration complète (39 liens : Géographie, Organisations, Ouvrages, Employés, Inspections, Planning, Système)
- [x] Demandes BP ajoutées dans menu Paiements

## ✅ Pages existantes

### Dashboard
- [x] `/dashboard` - Vue d'ensemble
- [x] `/dashboard/payments-flat` - Paiements forfaitaires
- [x] `/dashboard/payments-volume` - Paiements au volume
- [x] `/dashboard/expenses` - Dépenses
- [x] `/dashboard/infrastructure` - État des ouvrages
- [x] `/dashboard/map` - Carte interactive

### Autres
- [x] `/` (index.vue) - Page d'accueil
- [x] `/connexion` - Page de connexion
- [x] `/login` - Page login alternative
- [x] `/facturation` - Vue facturation
- [x] `/plannings` - Vue planning
- [x] `/stocks` - Vue stocks

## 🚀 Pages prioritaires à créer

### 1. Fil d'actualité (PRIORITÉ 1)
- [ ] `/feed` - Page principale du fil
  - Affichage posts (auteur surnom ou "Système")
  - Commentaires, likes, dislikes
  - Filtres (commune, ouvrage, employé, type, priorité)
  - Création de posts manuels
  - Upload d'images

### 2. Module Caissière - Retours (PRIORITÉ 1)
- [ ] `/billing/retours-caissiere` - Scanner et traiter les retours
  - Scanner QR code (ZXing)
  - Saisie manuelle de numéro ticket
  - Validation des retours
  - Impact stock automatique
  - Modal table temporaire DiameX

### 3. Demandes BP (PRIORITÉ 2)
- [ ] `/billing/demandes-bp` - Gestion branchements privés
  - Liste demandes avec stats
  - Filtres (recherche, ouvrage, statut)
  - Modal création/édition avec GPS
  - Export vers table temporaire DiameX
  - Modal visualisation lignes DiameX

### 4. Validation Sources (PRIORITÉ 2)
- [ ] `/chantiers/validations` - Validation sources d'eau
  - Formulaire avec proposition (Construction/Réhabilitation/Réparation)
  - Nombre de sources visitées
  - GPS capture haute précision (mobile)
  - Scanner documents (mobile camera)
  - Upload photo source et doc validation
  - Import/Export Excel
  - Bouton "Vider table" avec confirmation

### 5. Relevés (PRIORITÉ 2)
- [ ] `/billing/releves` - Workflow relevés complet
  - Tableau points d'eau (lignes cliquables)
  - Filtres géographiques
  - Modal saisie relevés par compteur
  - Sauvegarde et validation

### 6. Comptabilité (PRIORITÉ 3)
- [ ] `/accounting/entries` - Vérification comptabilité
  - Liste avec filtres avancés
  - Modal édition entrée
  - Bouton ouverture fichier scanné (via API)
  - Mise à jour Django + Access
  - Feedback multi-niveaux

### 7. Planning (PRIORITÉ 3)
- [ ] `/planning/calendar` - Vue calendrier
  - Grille mensuelle avec activités
  - Filtres par employé, base, activité
  - Drag & drop (optionnel)
  - Modal détails planning

- [ ] `/planning/livraisons` - Gestion livraisons
  - Liste bons de livraison
  - Création/édition
  - Suivi statut
  - Impact stock

- [ ] `/planning/avances` - Gestion avances
  - Liste avances
  - Création/édition
  - Suivi retours
  - Validation comptabilité

### 8. Chantiers (PRIORITÉ 3)
- [ ] `/chantiers/demandes` - Demandes villages
  - Liste demandes
  - Filtres géographiques
  - Modal création/édition
  - Workflow validation

- [ ] `/chantiers/list` - Liste chantiers
  - Tableau avec filtres
  - Stats par statut
  - Actions (éditer, valider, clôturer)

- [ ] `/chantiers/kanban` - Kanban chantiers
  - Colonnes par statut
  - Drag & drop entre colonnes
  - Cartes chantiers avec détails

- [ ] `/chantiers/tacherons` - Gestion tâcherons
  - Liste tâcherons
  - CRUD complet
  - Affectations chantiers

### 9. Ressources Humaines & Évaluation (PRIORITÉ 3)
- [ ] `/employees/fiches-poste` - Fiches de poste
  - Sélection poste
  - Liste tâches avec CRUD
  - Modal création/édition (tâche, description, outils, ordre)
  - Suppression avec validation

- [ ] `/employees/evaluations` - Évaluations employés
  - Liste évaluations avec filtres (employé, statut, année)
  - Création évaluation (employé, évaluateur, périodes)
  - Détail évaluation avec notation (0-2 par tâche)
  - Historique évaluations dans sidebar
  - Modal visualisation anciennes évaluations
  - Calcul score automatique (total, pourcentage)
  - Workflow : brouillon → terminée → validée

### 10. Administration (PRIORITÉ 4)
- [ ] `/geography` - Gestion géographie
  - Régions, Districts, Communes, Fokontanys, Villages, Parcelles
  - CRUD avec arborescence
  - Import/Export Excel

- [ ] `/geography/consolidated` - Géographie consolidée
  - Vue tableau complète
  - Filtres et recherche
  - Export global

- [ ] `/organization` - Gestion organisations
  - Organisations, Bases, Comptes, Postes, Magasins, Journaux
  - CRUD complet
  - Hiérarchie

- [ ] `/organization/ouvrages` - Gestion ouvrages
  - Ouvrages, Points d'Eau, Équipements, Compteurs
  - Tarifs, Modalités, Adresses, Fournisseurs, Cartes Sociales
  - CRUD complet avec relations

- [ ] `/planning/activites` - Gestion activités
  - Types d'activités
  - Activités
  - Activités/Postes

- [ ] `/planning/designations` - Gestion désignations
  - Types de désignations
  - Désignations
  - Comptes liés
  - Prix unitaires avec historique

- [ ] `/planning/deplacements` - Gestion déplacements
  - Liste trajets
  - CRUD complet
  - Moyens de transport (taxi-brousse, pirogue, bac)
  - Prix par trajet avec dates
  - Import/Export Excel

- [ ] `/employees` - Gestion employés
  - Liste employés
  - CRUD complet
  - Postes et affectations
  - Bases DiameX

- [ ] `/employees/positions-gps` - Positions GPS
  - Carte avec positions temps réel
  - Historique positions
  - Filtres par employé/date

### 10. Inventaire (PRIORITÉ 4)
- [ ] `/inventory/dashboard` - Vue d'ensemble stocks
  - Stats globales
  - Alertes stock faible
  - Graphiques

- [ ] `/inventory/purchases` - Saisie achats
  - Formulaire achat
  - Multi-lignes
  - Calcul totaux
  - Impact stock

- [ ] `/inventory/stocks` - Inventaires
  - Liste produits avec stock
  - Filtres (magasin, catégorie)
  - Ajustements stock

- [ ] `/inventory/fiche-stock` - Fiches de stock
  - Mouvements par produit
  - Historique complet
  - Export

- [ ] `/inventory/summary` - Résumé stocks
  - Tableau consolidé
  - Stats par magasin
  - Export global

### 11. Messaging (PRIORITÉ 5)
- [ ] `/messaging/conversations` - Liste conversations
  - Conversations directes et groupes
  - Recherche
  - Statuts non-lus

- [ ] `/messaging/chat/:id` - Chat conversation
  - Interface messagerie temps réel
  - Upload fichiers/images
  - Réactions
  - Mentions

### 12. Autres pages
- [ ] `/search` - Recherche globale
  - Recherche multi-entités
  - Filtres avancés
  - Résultats paginés

- [ ] `/accounting/import` - Import DiameX
  - Upload fichier
  - Mapping colonnes
  - Validation données
  - Import batch

- [ ] `/accounting/recoupement` - Recoupement planning
  - Comparaison planning vs comptabilité
  - Tableau écarts
  - Corrections

- [ ] `/accounting/transactions` - Transactions temporaires
  - Liste lignes en attente
  - Filtres par type
  - Export vers DiameX
  - Gestion erreurs

- [ ] `/usagers/representants` - Représentantes & Avis
  - Liste représentantes
  - CRUD avis/feedback
  - Stats satisfaction

- [ ] `/filemanager` - Gestion fichiers
  - Arborescence fichiers
  - Upload/Download
  - Prévisualisation
  - Partage

## 🎨 Composants à créer

### Composants de base
- [ ] `Navbar.vue` - Barre de navigation (déjà dans layout)
- [ ] `Sidebar.vue` - Menu latéral
- [ ] `Card.vue` - Carte de contenu
- [ ] `Table.vue` - Tableau de données
- [ ] `Modal.vue` - Dialogue modal
- [ ] `Toast.vue` - Notifications
- [ ] `Badge.vue` - Labels/Tags
- [ ] `Button.vue` - Boutons personnalisés
- [ ] `Tabs.vue` - Onglets

### Composants spécialisés
- [ ] `QRScanner.vue` - Scanner QR code (ZXing)
- [ ] `GPSCapture.vue` - Capture GPS mobile
- [ ] `CameraCapture.vue` - Capture photo mobile
- [ ] `MapView.vue` - Carte interactive (Leaflet/MapboxGL)
- [ ] `Calendar.vue` - Calendrier mensuel
- [ ] `KanbanBoard.vue` - Tableau Kanban
- [ ] `FileUpload.vue` - Upload fichiers
- [ ] `DatePicker.vue` - Sélecteur de date
- [ ] `TimePicker.vue` - Sélecteur d'heure
- [ ] `Select.vue` - Select personnalisé
- [ ] `Autocomplete.vue` - Champ avec suggestions
- [ ] `StatCard.vue` - Carte de statistique
- [ ] `Chart.vue` - Graphiques (Chart.js)
- [ ] `TreeView.vue` - Vue arborescente

### Composables à créer
- [ ] `useAPI.ts` - Appels API Django
- [ ] `useAuth.ts` - Authentification
- [ ] `useToast.ts` - Notifications
- [ ] `usePermissions.ts` - Gestion permissions
- [ ] `useGeography.ts` - Hiérarchie géographique
- [ ] `useTimezone.ts` - Gestion timezone Madagascar
- [ ] `useLocalStorage.ts` - Stockage local
- [ ] `useGPS.ts` - Géolocalisation
- [ ] `useCamera.ts` - Accès caméra
- [ ] `useQRScanner.ts` - Scan QR codes

## 📱 Fonctionnalités mobiles

### PWA
- [x] Configuration de base
- [ ] Service Worker optimisé
- [ ] Cache offline
- [ ] Installation progressive
- [ ] Notifications push

### Mobile-specific
- [ ] GPS haute précision
- [ ] Accès caméra (rear/front)
- [ ] Scanner QR code
- [ ] Upload photos
- [ ] Touch gestures
- [ ] Mode hors ligne complet

## 🔐 Authentification

- [ ] Login avec Django session
- [ ] OAuth2 Google
- [ ] Gestion tokens
- [ ] Refresh automatique
- [ ] Logout
- [ ] Middleware auth
- [ ] Guards de routes

## 🌐 API Configuration

- [ ] Créer `~/composables/useAPI.ts`
- [ ] Base URL configuration
- [ ] CSRF token handling
- [ ] Interceptors
- [ ] Error handling global
- [ ] Loading states
- [ ] Retry logic

## 📊 État (Pinia Stores)

- [ ] `auth.ts` - Authentification
- [ ] `user.ts` - Utilisateur connecté
- [ ] `feed.ts` - Fil d'actualité
- [ ] `planning.ts` - Plannings
- [ ] `billing.ts` - Facturation
- [ ] `inventory.ts` - Stocks
- [ ] `geography.ts` - Géographie
- [ ] `organization.ts` - Organisations
- [ ] `notifications.ts` - Notifications
- [ ] `theme.ts` - Thème dark/light

## 🎯 Ordre de développement suggéré

### Phase 1 : Infrastructure (Semaine 1)
1. Composables de base (useAPI, useAuth, useToast)
2. Stores essentiels (auth, user, theme)
3. Composants UI de base (Modal, Table, Card, Button)
4. Middleware auth et guards
5. Configuration API backend

### Phase 2 : Pages essentielles (Semaine 2-3)
1. Fil d'actualité (`/feed`)
2. Module caissière (`/billing/retours-caissiere`)
3. Demandes BP (`/billing/demandes-bp`)
4. Validation sources (`/chantiers/validations`)
5. Relevés (`/billing/releves`)

### Phase 3 : Planning (Semaine 4)
1. Calendrier (`/planning/calendar`)
2. Livraisons (`/planning/livraisons`)
3. Avances (`/planning/avances`)
4. Dashboard planning

### Phase 4 : Chantiers (Semaine 5)
1. Liste chantiers (`/chantiers/list`)
2. Kanban (`/chantiers/kanban`)
3. Demandes villages (`/chantiers/demandes`)
4. Tâcherons (`/chantiers/tacherons`)

### Phase 5 : Administration (Semaine 6-7)
1. Géographie (`/geography`)
2. Organisations (`/organization`)
3. Ouvrages (`/organization/ouvrages`)
4. Employés (`/employees`)
5. Activités/Désignations/Déplacements

### Phase 6 : Fonctionnalités avancées (Semaine 8+)
1. Inventaire complet
2. Comptabilité avancée
3. Messaging/Conversations
4. Carte interactive avancée
5. Mobile features (GPS, Camera, QR)
6. PWA optimisé
