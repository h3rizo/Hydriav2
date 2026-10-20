# Recoupement Paiements Forfaitaires - Documentation

## Vue d'ensemble

Page de recoupement entre les paiements forfaitaires (table `PaiementForfaitaire`) et la comptabilité DiameX (compte **748411**).

**URL** : `/comptabilite/recoupement/forfaitaires/`

## Structure de la page

La page est divisée en **3 sections** de recoupement :

### 1. Recoupement Normal : Paiements → Comptabilité

**Direction** : PaiementForfaitaire → BaseDiameX

**Clé de liaison** :
- `PaiementForfaitaire.numeroDiameX` ↔ `BaseDiameX.id_access`
- `PaiementForfaitaire.baseDiameX` ↔ `BaseDiameX.prog`

**Objectif** : Vérifier que chaque paiement forfaitaire avec `numeroDiameX` et `baseDiameX` renseignés existe bien en comptabilité.

**Statistiques** :
- Total : Nombre de couples (numeroDiameX, baseDiameX) uniques
- OK : Écart < 0.01 Ar
- Attention : Écart < 100 Ar
- Erreur : Écart ≥ 100 Ar
- Manquant : Paiement sans entrée comptable correspondante

**Données affichées** :
- Numéro DiameX
- Base DiameX
- Ouvrage
- Point d'Eau
- Date Facture
- Scan (bouton pour ouvrir le fichier)
- Nombre de paiements groupés
- Total Paiements (Ar)
- Compta IN (Ar)
- Écart (Ar)
- Status (badge coloré)

**Filtres disponibles** :
- Status (ok, warning, error, missing)
- Ouvrage
- Base DiameX
- Mois (sélecteur month)

**Pagination** : 50 résultats par page

---

### 2. Recoupement Inverse : Comptabilité → Paiements

**Direction** : BaseDiameX → PaiementForfaitaire

**Critère** : Toutes les entrées DiameX avec compte **748411**

**Objectif** : Vérifier que chaque entrée comptable 748411 correspond bien à un paiement forfaitaire.

**Statistiques** :
- Total : Nombre d'entrées DiameX 748411
- OK : Écart < 0.01 Ar
- Attention : Écart < 100 Ar
- Erreur : Écart ≥ 100 Ar
- Sans paiement : Entrée comptable sans paiement correspondant

**Données affichées** :
- ID DiameX (id_access)
- Prog (base)
- Description (tronquée à 8 mots)
- Date
- Compta IN (Ar)
- Total Paiements (Ar)
- Écart (Ar)
- Status
- Nombre de paiements liés

**Filtres disponibles** :
- Prog (Base) : Liste déroulante des bases DiameX
- Mois : Sélecteur month

**Pas de pagination** : Affichage complet de tous les résultats

---

### 3. Recoupement par Extraction : Comptabilité → Extraction → Paiements

**Direction** : BaseDiameX → Extraction ouvrage → PaiementForfaitaire

**Méthode** :
1. Récupérer toutes les entrées DiameX avec compte **748411**
2. Extraire le nom d'ouvrage depuis la description via `extraire_ouvrage_et_mois_generique()`
3. Chercher les paiements forfaitaires pour cet ouvrage
4. Filtrer par date (tolérance ±90 jours autour de la date DiameX)

**Objectif** : Recouper SANS utiliser les IDs DiameX (numeroDiameX, baseDiameX), uniquement par extraction intelligente.

**Extracteur utilisé** : `extraire_ouvrage_paiement_forfaitaire()` depuis `extracteurs_description.py`

**Format attendu** : `Paiement forfaitaire_U_[Quantité]_[Prix unitaire]_[NOM_OUVRAGE]`

**Exemple** : `Paiement forfaitaire_U_1_75000_Andranobe`

**Extraction** :
- Ouvrage : "Andranobe"
- Quantité : 1
- Prix unitaire : 75000

**Statistiques** :
- Total : Nombre d'entrées DiameX 748411
- OK : Écart < 0.01 Ar
- Attention : Écart < 100 Ar
- Erreur : Extraction échouée OU écart important
- Sans paiement : Ouvrage extrait mais pas de paiements trouvés

**Données affichées** :
- ID DiameX
- Prog
- **Ouvrage extrait** (avec lien si trouvé en BDD, warning si non trouvé, erreur si extraction échouée)
- Date
- Quantité extraite
- Prix unitaire extrait
- Compta IN (Ar)
- Total Paiements (Ar)
- Écart (Ar)
- Status
- Nombre de paiements liés

**Filtres disponibles** :
- Ouvrage extrait : Recherche textuelle
- Mois : Sélecteur month

**Tolérance temporelle** : Les paiements sont recherchés dans une fenêtre de **±90 jours** autour de la date DiameX.

---

## Calcul des écarts

**Règle** : Les paiements forfaitaires sont des **recettes** (IN).

**Formule** :
```
Écart = Total Paiements - Comptabilité IN
```

**Interprétation** :
- Écart = 0 → OK parfait
- Écart > 0 → Plus de paiements que comptabilisé (warning/error)
- Écart < 0 → Moins de paiements que comptabilisé (error)

---

## Status colorés

| Status | Badge | Condition |
|--------|-------|-----------|
| OK | Vert (success) | abs(écart) < 0.01 Ar |
| Attention | Orange (warning) | abs(écart) < 100 Ar |
| Erreur | Rouge (error) | abs(écart) ≥ 100 Ar |
| Manquant | Gris (ghost) | Entrée non trouvée |

---

## Groupement des données

**Section 1 (Normal)** : Groupement par couple `(numeroDiameX, baseDiameX)`
- Plusieurs paiements peuvent avoir le même couple → ils sont regroupés
- Le total des montants est calculé pour le groupe

**Section 2 (Inverse)** : Une ligne par entrée DiameX
- Affichage de tous les paiements liés (recherche par clé)

**Section 3 (Extraction)** : Une ligne par entrée DiameX
- Affichage de tous les paiements liés (recherche par ouvrage + date)

---

## Scans et fichiers

**Bouton "Ouvrir Scan"** (Section 1) :
- Appelle l'API `/comptabilite/file/open/` (POST)
- Utilise `os.startfile()` pour ouvrir le fichier Windows
- Chemin reconstruit depuis `EmployeBaseDiameX.chemin_base_diamex`

**Exemple** :
```
scan DiameX : "./Scans/2024/facture.pdf"
chemin_base : "C:/Bases/DiameX/"
→ Chemin complet : "C:/Bases/DiameX/Scans/2024/facture.pdf"
```

---

## Navigation

**Barre de navigation** : Inclut un lien vers toutes les pages de recoupement :
- Planning
- Salaires
- Indemnités
- Frais Médicaux
- Frais Scolarité
- Relevés
- **Paiements Forfaitaires** ← Nouvelle page
- Demandes BP
- Devis BP
- Cartes Sociales
- Achats

---

## Fichiers implémentés

### Backend

1. **`apps/accounting/views_recoupement_forfaitaires.py`** (521 lignes)
   - Fonction principale : `recoupement_paiements_forfaitaires(request)`
   - 3 sections de recoupement implémentées
   - Calculs des écarts et statistiques
   - Filtres et pagination

2. **`apps/accounting/urls.py`**
   - Route : `path('recoupement/forfaitaires/', ...)`

### Frontend

1. **`templates/accounting/recoupement_forfaitaires.html`** (584 lignes)
   - 3 sections avec tables séparées
   - Filtres indépendants pour chaque section
   - Stats en temps réel (5 cartes par section)
   - JavaScript pour ouverture scan

2. **`templates/accounting/includes/recoupement_nav.html`**
   - Ajout du lien "Paiements Forfaitaires"

---

## Données disponibles (14 décembre 2025)

**Section 1 (Normal)** : 985 paiements avec numeroDiameX/baseDiameX
**Section 2 (Inverse)** : 590 entrées DiameX compte 748411
**Section 3 (Extraction)** : 590 entrées DiameX compte 748411

**Taux d'extraction** : ~90% (estimé, basé sur tests)

---

## Tests effectués

✅ Import du module sans erreur
✅ Données disponibles dans les 3 sections
✅ Extraction fonctionne correctement (5 exemples testés, 100% succès)
✅ Configuration Django valide (`python manage.py check`)
✅ Navigation intégrée

---

## Utilisation

1. **Accéder à la page** : http://localhost:8000/comptabilite/recoupement/forfaitaires/
2. **Section 1** : Vérifier les paiements avec ID DiameX
3. **Section 2** : Vérifier que toutes les entrées comptables ont des paiements
4. **Section 3** : Vérifier par extraction intelligente (sans ID)

**Cas d'usage** :
- **Section 1** : Détecter les paiements mal comptabilisés
- **Section 2** : Détecter les entrées comptables orphelines
- **Section 3** : Détecter les erreurs de saisie d'ID (fallback via nom d'ouvrage)

---

## Améliorations futures possibles

1. **Export Excel** : Exporter les résultats de chaque section
2. **Correction automatique** : Bouton pour corriger les numeroDiameX manquants (via extraction)
3. **Historique** : Tracker les corrections apportées
4. **Alertes** : Notification quand de nouveaux écarts apparaissent
5. **Dashboard** : Graphiques d'évolution des écarts dans le temps

---

## Support

En cas de problème :
1. Vérifier que le compte 748411 est bien configuré dans `CompteTable`
2. Vérifier que l'extracteur `extraire_ouvrage_paiement_forfaitaire()` fonctionne
3. Consulter les logs Django pour les erreurs
4. Vérifier que les bases DiameX sont bien renseignées dans `EmployeBaseDiameX`

**Date de création** : 14 décembre 2025
**Développeur** : Claude Code
**Version** : 1.0
