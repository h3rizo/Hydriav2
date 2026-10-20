# WORKFLOW GARDIENS - SYSTÈME DE ROTATION ET CONGÉS SPÉCIAUX

## 📋 Vue d'ensemble

Module complet pour gérer les rotations des 3 gardiens de la base Soakoja avec leurs particularités :
- Rotation 24h : Jour (8h-18h) → Nuit (18h-8h) → Congé → Répète
- Extension automatique des shifts lors des congés (8h-8h = 24h pour les 2 restants)
- Calcul automatique des heures supplémentaires (> 243h/mois)
- Majorations pour dimanches et jours fériés

## 🎯 Gardiens identifiés

| ID | Nom | Base |
|----|-----|------|
| 64a11eeb-0dfc-4d6b-92ea-73175edc3642 | RAOUL | Soakoja |
| cde49c47-0e00-4ba1-8631-a0b0ed150849 | RENE | Soakoja |
| b866a66c-93fb-42b4-81ef-08caaa25c272 | VELONASY | Soakoja |

## 🏗️ Architecture

### Modèles Django

#### RotationGardien (`apps/employees/models_gardiens.py`)

**Champs principaux** :
- `employe` : ForeignKey vers Employe
- `date` : Date du shift
- `shift_type` : Choix (jour, nuit, conge, etendu)
- `heure_debut` / `heure_fin` : Horaires du shift
- `heures_travaillees` : Calculé automatiquement
- `est_dimanche` : Boolean (détection automatique)
- `est_jour_ferie` : Boolean
- `est_extension` : Boolean (si remplacement d'un collègue)
- `remplace_employe` : ForeignKey optionnelle vers Employe remplacé

**Types de shifts** :
- **jour** : 8h-18h (10 heures)
- **nuit** : 18h-8h lendemain (14 heures)
- **conge** : Pas de shift
- **etendu** : 8h-8h lendemain (24 heures) - Remplacement d'un collègue

**Unique constraint** : `(employe, date)`

#### HeuresSupplementairesGardien (`apps/employees/models_gardiens.py`)

**Champs principaux** :
- `employe` : ForeignKey vers Employe
- `mois` / `annee` : Période
- `heures_normales` : Jusqu'à 243h
- `heures_supplementaires` : Au-delà de 243h
- `heures_dimanche` : Heures travaillées le dimanche
- `heures_jours_feries` : Heures travaillées les jours fériés
- `heures_extensions` : Heures d'extension (remplacement)
- `montant_heures_supplementaires` : À calculer lors de la paie
- `montant_majoration_dimanche` : À calculer lors de la paie
- `montant_majoration_jours_feries` : À calculer lors de la paie

**Unique constraint** : `(employe, mois, annee)`

**Méthode clé** :
```python
HeuresSupplementairesGardien.calculer_pour_mois(employe_id, mois, annee)
```
Calcule automatiquement toutes les heures pour un mois donné.

### APIs REST

#### 1. Générer rotations standard

**Endpoint** : `POST /api/gardiens/generer-rotations/`

**Body** :
```json
{
  "date_debut": "2025-12-30",
  "nb_jours": 30
}
```

**Réponse** :
```json
{
  "success": true,
  "message": "14 rotation(s) créée(s)",
  "rotations_creees": ["2025-12-30", "2025-12-31", ...],
  "total_genere": 21
}
```

**Workflow** :
1. Génère rotations selon pattern Jour → Nuit → Congé
2. Décale chaque gardien dans le pattern
3. Détecte automatiquement dimanches et jours fériés
4. Évite doublons avec `get_or_create`

#### 2. Créer congé avec extension automatique ⭐

**Endpoint** : `POST /api/gardiens/creer-conge/`

**Body** :
```json
{
  "employe_id": "64a11eeb-0dfc-4d6b-92ea-73175edc3642",
  "date_debut": "2025-12-30",
  "date_fin": "2026-01-02",
  "motif": "Congé annuel"
}
```

**Réponse** :
```json
{
  "success": true,
  "message": "Congé créé pour 4 jour(s). 8 shift(s) étendu(s).",
  "jours_traites": ["2025-12-30", "2025-12-31", "2026-01-01", "2026-01-02"],
  "shifts_etendus": [
    {"gardien_id": "cde49c47...", "date": "2025-12-30"},
    {"gardien_id": "b866a66c...", "date": "2025-12-30"},
    ...
  ]
}
```

**Workflow CRITICAL** :
1. Valide que l'employé est bien un gardien (check dans `GARDIENS_IDS`)
2. Pour chaque jour de congé :
   - **Supprime** les rotations existantes du gardien en congé
   - **Crée** entrée Planning avec activité "Congé"
   - **Trouve** les 2 autres gardiens
   - **Supprime** leurs shifts normaux
   - **Crée** shifts étendus (8h-8h = 24h) avec `est_extension=True`
   - **Lie** le shift étendu au gardien remplacé (`remplace_employe`)

#### 3. Lister les rotations

**Endpoint** : `GET /api/gardiens/rotations/`

**Paramètres** :
- `date_debut` : Date de début (format YYYY-MM-DD)
- `date_fin` : Date de fin
- `employe_id` : UUID du gardien (optionnel)

**Réponse** :
```json
{
  "success": true,
  "rotations": [
    {
      "id": "uuid",
      "employe_id": "uuid",
      "employe_nom": "RAOUL",
      "date": "2025-12-30",
      "shift_type": "jour",
      "shift_type_display": "Jour (8h-18h)",
      "heure_debut": "08:00:00",
      "heure_fin": "18:00:00",
      "heures_travaillees": 10.0,
      "est_dimanche": false,
      "est_jour_ferie": false,
      "est_extension": false,
      "remplace_employe_nom": null
    },
    ...
  ],
  "count": 14
}
```

#### 4. Heures supplémentaires

**Endpoint** : `GET /api/gardiens/heures-supplementaires/`

**Paramètres** :
- `employe_id` : UUID du gardien (obligatoire)
- `mois` : Mois (1-12)
- `annee` : Année (ex: 2025)

**Réponse** :
```json
{
  "success": true,
  "heures_supplementaires": {
    "employe_id": "uuid",
    "employe_nom": "RAOUL",
    "mois": 12,
    "annee": 2025,
    "heures_normales": 243.0,
    "heures_supplementaires": 25.0,
    "heures_dimanche": 48.0,
    "heures_jours_feries": 24.0,
    "heures_extensions": 72.0
  }
}
```

**Constante** : `HEURES_NORMALES_MOIS = 243`

## 🔄 Workflow complet

### Scénario 1 : Génération mensuelle des rotations

```python
# Via API
POST /api/gardiens/generer-rotations/
{
  "date_debut": "2026-01-01",
  "nb_jours": 31
}

# Via Python
from apps.employees.views_gardiens import generer_rotation_standard
from apps.employees.models_gardiens import RotationGardien

rotations = generer_rotation_standard(date(2026, 1, 1), 31)
for rot in rotations:
    RotationGardien.objects.get_or_create(
        employe_id=rot['employe_id'],
        date=rot['date'],
        defaults=rot
    )
```

### Scénario 2 : Congé avec extension automatique

**Avant** :
```
Date         | RAOUL    | RENE     | VELONASY
-------------|----------|----------|----------
2025-12-30   | Jour     | Nuit     | -
2025-12-31   | Nuit     | -        | Jour
2026-01-01   | -        | Jour     | Nuit
```

**Action** :
```bash
POST /api/gardiens/creer-conge/
{
  "employe_id": "64a11eeb-0dfc-4d6b-92ea-73175edc3642",  # RAOUL
  "date_debut": "2025-12-30",
  "date_fin": "2026-01-01",
  "motif": "Congé annuel"
}
```

**Après** :
```
Date         | RAOUL    | RENE        | VELONASY
-------------|----------|-------------|-------------
2025-12-30   | CONGÉ    | Étendu 24h  | Étendu 24h
2025-12-31   | CONGÉ    | Étendu 24h  | Étendu 24h
2026-01-01   | CONGÉ    | Étendu 24h  | Étendu 24h
```

**Résultat** :
- RAOUL : 3 jours de congé inscrits au Planning
- RENE : 3 shifts étendus (8h-8h) = 72h
- VELONASY : 3 shifts étendus (8h-8h) = 72h

### Scénario 3 : Calcul des heures supplémentaires

```python
# Fin du mois : calculer les heures de chaque gardien
from apps.employees.models_gardiens import HeuresSupplementairesGardien

for gardien_id in GARDIENS_IDS:
    heures = HeuresSupplementairesGardien.calculer_pour_mois(
        gardien_id, 12, 2025
    )

    print(f"Heures normales: {heures.heures_normales}")
    print(f"Heures supp: {heures.heures_supplementaires}")
    print(f"Heures dimanche: {heures.heures_dimanche}")
    print(f"Heures fériés: {heures.heures_jours_feries}")
    print(f"Heures extensions: {heures.heures_extensions}")
```

**Calcul** :
- Total heures du mois : Somme de toutes les `RotationGardien.heures_travaillees`
- Si total > 243h : `heures_supplementaires = total - 243`
- Heures dimanche : Somme des shifts où `est_dimanche=True`
- Heures fériés : Somme des shifts où `est_jour_ferie=True`
- Heures extensions : Somme des shifts où `est_extension=True`

## 💰 Calcul de la paie (à implémenter)

### Formule proposée

**Salaire mensuel gardien** :
```
Salaire_base = (heures_normales × taux_horaire)

Heures_supp = heures_supplementaires × taux_horaire × 1.3  (30% majoration)

Majoration_dimanche = heures_dimanche × taux_horaire × 0.5  (50% bonus)

Majoration_feries = heures_jours_feries × taux_horaire × 1.0  (100% bonus)

Total = Salaire_base + Heures_supp + Majoration_dimanche + Majoration_feries
```

**Exemple concret** :
- Taux horaire : 2,057 Ar/h (500,000 Ar / 243h)
- Heures normales : 243h → 500,000 Ar
- Heures supplémentaires : 72h (3 shifts étendus) → 72 × 2,057 × 1.3 = 192,757 Ar
- Heures dimanche : 24h → 24 × 2,057 × 0.5 = 24,684 Ar
- **Total** : 717,441 Ar

### Intégration dans le système de paie

**Modèle à modifier** : `apps/employees/models.py` - `Salaire`

**Champs à ajouter** :
```python
# Ajout pour gardiens
heures_supplementaires_gardien = models.DecimalField(
    max_digits=6, decimal_places=2, default=Decimal('0')
)
montant_heures_supplementaires = models.DecimalField(
    max_digits=10, decimal_places=2, default=Decimal('0')
)
montant_majoration_dimanche = models.DecimalField(
    max_digits=10, decimal_places=2, default=Decimal('0')
)
montant_majoration_jours_feries = models.DecimalField(
    max_digits=10, decimal_places=2, default=Decimal('0')
)
```

**Logique de calcul** :
```python
# Dans la fonction de calcul de paie
if employe.id in GARDIENS_IDS:
    # Récupérer les heures du mois
    heures_supp = HeuresSupplementairesGardien.objects.get(
        employe=employe,
        mois=mois,
        annee=annee
    )

    # Calculer taux horaire
    taux_horaire = salaire.salaire_base / Decimal('243')

    # Calculer majorations
    montant_hs = heures_supp.heures_supplementaires * taux_horaire * Decimal('1.3')
    montant_dim = heures_supp.heures_dimanche * taux_horaire * Decimal('0.5')
    montant_fer = heures_supp.heures_jours_feries * taux_horaire * Decimal('1.0')

    # Ajouter au salaire
    salaire.montant_heures_supplementaires = montant_hs
    salaire.montant_majoration_dimanche = montant_dim
    salaire.montant_majoration_jours_feries = montant_fer
    salaire.salaire_brut += montant_hs + montant_dim + montant_fer
```

## 📅 Jours fériés 2025

Liste hardcodée dans `views_gardiens.py` (fonction `est_jour_ferie()`) :
- 01/01/2025 : Jour de l'an
- 29/03/2025 : Commémoration des martyrs
- 31/03/2025 : Lundi de Pâques
- 01/05/2025 : Fête du travail
- 08/05/2025 : Jeudi de l'Ascension
- 19/05/2025 : Lundi de Pentecôte
- 26/06/2025 : Fête de l'indépendance
- 15/08/2025 : Assomption
- 01/11/2025 : Toussaint
- 25/12/2025 : Noël

**⚠️ À mettre à jour chaque année**

## 🧪 Tests

### Script de test complet

`backend/test_workflow_gardiens.py` :
1. Vérifie les 3 gardiens
2. Génère 7 jours de rotations
3. Affiche rotations par gardien
4. Calcule heures supplémentaires
5. Affiche statistiques globales

**Exécution** :
```bash
cd backend
python test_workflow_gardiens.py
```

### Tests unitaires recommandés

1. **Test génération rotation** :
   - Vérifier pattern Jour → Nuit → Congé
   - Vérifier que chaque gardien a un shift différent
   - Vérifier calcul automatique des heures

2. **Test congé avec extension** :
   - Créer congé pour RAOUL
   - Vérifier suppression shifts RAOUL
   - Vérifier création shifts étendus RENE et VELONASY
   - Vérifier `est_extension=True` et `remplace_employe` correct

3. **Test calcul heures supplémentaires** :
   - Créer rotations totalisant 250h
   - Calculer : heures_normales = 243h, heures_supp = 7h
   - Vérifier heures_dimanche correct
   - Vérifier heures_feries correct

## 📊 Statistiques et rapports

### Requêtes utiles

**Heures par gardien sur le mois** :
```python
from django.db.models import Sum
from datetime import date
from calendar import monthrange

mois = 12
annee = 2025
premier_jour = date(annee, mois, 1)
dernier_jour = date(annee, mois, monthrange(annee, mois)[1])

heures_par_gardien = RotationGardien.objects.filter(
    date__gte=premier_jour,
    date__lte=dernier_jour
).values('employe__surnom').annotate(
    total_heures=Sum('heures_travaillees')
).order_by('-total_heures')
```

**Extensions de shifts par période** :
```python
extensions = RotationGardien.objects.filter(
    est_extension=True,
    date__gte=premier_jour,
    date__lte=dernier_jour
).select_related('employe', 'remplace_employe')

for ext in extensions:
    print(f"{ext.employe.surnom} remplace {ext.remplace_employe.surnom} le {ext.date}")
```

## ⚠️ Points d'attention CRITICAL

1. **IDs hardcodés** : Les 3 UUIDs des gardiens sont hardcodés dans `GARDIENS_IDS`. Si changement de gardien, mettre à jour.

2. **Jours fériés annuels** : Liste hardcodée dans `est_jour_ferie()`. Mettre à jour chaque année.

3. **Unique constraint** : Un gardien = 1 rotation par jour maximum. Vérifier avant création.

4. **Calcul heures** : Méthode `calculer_heures()` appelée automatiquement au save. Shift de nuit (heure_fin < heure_debut) gère automatiquement le passage minuit.

5. **Timezone** : Toutes les dates Planning utilisent `tz_madagascar` (Indian/Antananarivo).

6. **Activité "Congé"** : Doit exister dans la table `Activite` pour créer les plannings de congé.

## 📈 Améliorations futures

1. **Interface web** : Page dédiée pour visualiser et gérer les rotations (calendrier)
2. **Notifications** : Alerter les gardiens de leur shift du lendemain (SMS/email)
3. **Validation** : Workflow de validation des congés avant extension automatique
4. **Échange de shifts** : Permettre aux gardiens d'échanger leurs shifts
5. **Historique** : Conserver historique des modifications de rotation
6. **Export** : Exporter planning gardiens vers Excel/PDF
7. **Dashboard** : Graphiques des heures par gardien, évolution mensuelle
8. **Intégration paie** : Automatiser calcul majorations dans le module Salaire

## 🔗 Fichiers créés

1. `backend/apps/employees/models_gardiens.py` - Modèles RotationGardien et HeuresSupplementairesGardien
2. `backend/apps/employees/views_gardiens.py` - APIs de gestion des rotations et congés
3. `backend/apps/employees/migrations/0040_add_gardiens_workflow.py` - Migration
4. `backend/test_workflow_gardiens.py` - Script de test
5. `backend/docs/WORKFLOW_GARDIENS.md` - Cette documentation

## ✅ Checklist de validation

- [x] Modèles créés et migrés
- [x] APIs REST créées et testées
- [x] URLs enregistrées
- [x] Script de test fonctionnel
- [x] Django check sans erreur
- [x] Génération rotation standard OK
- [x] Calcul heures supplémentaires OK
- [x] Documentation complète
- [ ] Interface web (à faire)
- [ ] Intégration module paie (à faire)
- [ ] Tests unitaires (à faire)
