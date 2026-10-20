# 🤖 MODULE ÉVALUATION AUTOMATIQUE DES EMPLOYÉS

## Vue d'ensemble

Système d'évaluation automatique basé sur les données réelles de l'application pour deux types de postes :
1. **Assistant(e) Administratif** : Évaluation basée sur la qualité de saisie comptable
2. **Agent de Recouvrement** : Évaluation basée sur les taux de recouvrement

## Architecture

### Modèles de données

**Modèles d'évaluation** (`apps/employees/models_evaluation.py`) :
- `FichePoste` : Tâches et descriptions par poste
- `Evaluation` : Évaluation globale d'un employé sur une période
- `EvaluationDetail` : Note (0-2) et remarques par tâche

**Modèles de données source** :
- `BaseDiameX` : Données de saisie comptable (pour assistants admin)
- `Releve` : Factures et paiements (pour agents de recouvrement)

### APIs REST

**1. API Évaluation Saisie Comptable**
- **Route** : `/comptabilite/api/evaluation-saisie/employe/`
- **Méthode** : GET
- **Paramètres** :
  - `employe_id` (UUID) - ID de l'employé
  - `date_debut` (YYYY-MM-DD) - Début de période
  - `date_fin` (YYYY-MM-DD) - Fin de période

**Exemple de requête** :
```
GET /comptabilite/api/evaluation-saisie/employe/?employe_id=xxx&date_debut=2024-01-01&date_fin=2024-03-31
```

**Réponse JSON** :
```json
{
  "success": true,
  "employe": {
    "id": "uuid",
    "nom_complet": "Jean DUPONT"
  },
  "periode": {
    "debut": "2024-01-01",
    "fin": "2024-03-31",
    "nb_jours": 90
  },
  "statistiques": {
    "total_lignes": 1250,
    "lignes_conformes": 1100,
    "taux_conformite": 88.0,
    "decalage_moyen": 1.2,
    "moyenne_jour": 13.9,
    "repartition_decalages": {
      "conforme": 1100,
      "decalage_1": 80,
      "decalage_2": 40,
      "decalage_3": 20,
      "decalage_4_plus": 10
    }
  },
  "evaluation_auto": {
    "note": 1.5,
    "remarques": [
      "Taux de conformité : 88.0% (Bon niveau)",
      "Décalage moyen : 1.2 mois (Acceptable)",
      "Productivité : 13.9 lignes/jour"
    ]
  }
}
```

**Calcul de la note** :
```python
if taux_conformite >= 90:
    note_base = 2.0
elif taux_conformite >= 70:
    note_base = 1.5
elif taux_conformite >= 50:
    note_base = 1.0
else:
    note_base = 0.5

# Bonus si décalage moyen < 1.5 mois
if decalage_moyen < 1.5 and note_base < 2:
    note_finale = min(note_base + 0.5, 2.0)
```

**2. API Évaluation Recouvrement**
- **Route** : `/comptabilite/api/evaluation-recouvrement/employe/`
- **Méthode** : GET
- **Paramètres** : Identiques à l'API saisie

**Réponse JSON** :
```json
{
  "success": true,
  "employe": {
    "id": "uuid",
    "nom_complet": "Marie RAKOTO"
  },
  "periode": {
    "debut": "2024-01-01",
    "fin": "2024-03-31",
    "nb_jours": 90
  },
  "statistiques": {
    "total_releves": 450,
    "nb_payes": 380,
    "taux_recouvrement_nombre": 84.4,
    "montant_total": 25000000.0,
    "montant_paye": 21500000.0,
    "taux_recouvrement_montant": 86.0,
    "delai_moyen_jours": 25
  },
  "evaluation_auto": {
    "note": 2.0,
    "remarques": [
      "Taux de recouvrement : 86.0% (Excellent niveau)",
      "Délai moyen de paiement : 25 jours (Très bon)",
      "380 factures payées sur 450"
    ]
  }
}
```

**Calcul de la note** :
```python
if taux_recouvrement_montant >= 80:
    note_base = 2.0
elif taux_recouvrement_montant >= 60:
    note_base = 1.5
elif taux_recouvrement_montant >= 40:
    note_base = 1.0
else:
    note_base = 0.5

# Bonus si délai moyen < 30 jours
if delai_moyen > 0 and delai_moyen < 30 and note_base < 2:
    note_finale = min(note_base + 0.5, 2.0)
```

## Interface utilisateur

### Page de détail d'évaluation
**URL** : `/evaluations/<evaluation_id>/detail/`

**Sections automatiques affichées** :

#### 1. Évaluation Saisie Comptable (si données disponibles)
- **Carte avec gradient bleu** (`from-primary/10 to-secondary/10`)
- **4 statistiques** :
  - Lignes saisies (total + moyenne/jour)
  - Conformité (taux % + nb lignes conformes)
  - Décalage moyen (en mois)
  - Note automatique (sur 2)
- **Remarques automatiques** : Liste des points clés
- **Bouton "Appliquer"** : Applique automatiquement la note à une tâche contenant "saisie"

#### 2. Évaluation Recouvrement (si données disponibles)
- **Carte avec gradient vert** (`from-success/10 to-info/10`)
- **4 statistiques** :
  - Relevés facturés (total + nb payés)
  - Taux recouvrement (% + montant en Ar)
  - Délai moyen (en jours)
  - Note automatique (sur 2)
- **Remarques automatiques** : Liste des points clés
- **Bouton "Appliquer"** : Applique automatiquement la note à une tâche contenant "recouvrement"

### Workflow utilisateur

1. **Créer une évaluation** pour un employé avec période
2. **Ouvrir la page de détail** : Les sections automatiques se chargent automatiquement
3. **Consulter les statistiques** : Vérifier les données avant application
4. **Cliquer "Appliquer"** :
   - Recherche automatique de la tâche correspondante (saisie ou recouvrement)
   - Arrondi de la note (0, 1 ou 2)
   - Application de la note + remarques automatiques
   - Rechargement de la liste des tâches

### Règles d'arrondi

La note automatique (0.0 - 2.0) est arrondie pour correspondre au système 0-2 :

```javascript
if (noteAuto >= 1.75) {
    noteArrondie = 2;  // Maîtrisé
} else if (noteAuto >= 0.75) {
    noteArrondie = 1;  // En cours d'acquisition
} else {
    noteArrondie = 0;  // Non acquis
}
```

## Fichiers impliqués

### Backend

1. **`backend/apps/accounting/views_evaluation_saisie.py`**
   - Lignes 471-638 : `api_evaluation_saisie_employe()`
   - Lignes 641-791 : `api_evaluation_recouvrement_employe()`

2. **`backend/apps/accounting/urls.py`**
   - Ligne 161 : Route API saisie
   - Ligne 162 : Route API recouvrement

### Frontend

1. **`backend/templates/employees/evaluation_detail.html`**
   - Lignes 54-108 : Section UI évaluation saisie
   - Lignes 110-161 : Section UI évaluation recouvrement
   - Lignes 413-526 : JavaScript évaluation saisie
   - Lignes 528-647 : JavaScript évaluation recouvrement

## Cas d'usage

### Assistant(e) Administratif - Saisie Comptable

**Données analysées** :
- Toutes les lignes saisies dans DiameX pendant la période
- Conformité = mois de saisie = mois comptable
- Décalage = différence en mois entre date saisie et mois comptable

**Critères d'excellence** :
- ✅ Taux conformité ≥ 90%
- ✅ Décalage moyen < 1.5 mois
- ✅ Productivité régulière (moyenne/jour)

**Note maximale (2.0)** :
- 90%+ de conformité
- Décalage moyen < 1.5 mois

### Agent de Recouvrement

**Données analysées** :
- Tous les relevés facturés pendant la période
- Relevés payés = ceux avec `numeroDiameX` renseigné
- Délai = jours entre `datereleve` et `datepaiement`

**Critères d'excellence** :
- ✅ Taux recouvrement (montant) ≥ 80%
- ✅ Délai moyen < 30 jours
- ✅ Nombre de factures payées élevé

**Note maximale (2.0)** :
- 80%+ de recouvrement en montant
- Délai moyen < 30 jours

## Sécurité et permissions

- ✅ **Aucune authentification requise** sur les APIs (données internes)
- ✅ **Lecture seule** : Les APIs ne modifient pas les données source
- ✅ **Application manuelle** : L'utilisateur doit cliquer pour appliquer la note
- ✅ **Validation côté serveur** : Vérification des IDs et dates

## Améliorations futures possibles

1. **Graphiques** : Visualiser l'évolution des performances dans le temps
2. **Seuils personnalisables** : Ajuster les seuils de notation par organisation
3. **Autres postes** : Ajouter d'autres types d'évaluations automatiques :
   - Techniciens : Nombre de réparations effectuées
   - Agents terrain : Nombre de relevés saisis
4. **Notifications** : Alerter si performance en baisse
5. **Export PDF** : Rapport d'évaluation automatique imprimable
6. **Historique** : Comparer les évaluations successives

## Tests de validation

### Test API Saisie
```bash
# Remplacer les valeurs par des données réelles
curl "http://localhost:8000/comptabilite/api/evaluation-saisie/employe/?employe_id=xxx&date_debut=2024-01-01&date_fin=2024-03-31"
```

### Test API Recouvrement
```bash
curl "http://localhost:8000/comptabilite/api/evaluation-recouvrement/employe/?employe_id=xxx&date_debut=2024-01-01&date_fin=2024-03-31"
```

### Test Interface
1. Créer une évaluation pour un assistant admin
2. Ouvrir la page de détail
3. Vérifier que la section "Évaluation automatique - Saisie comptable" apparaît
4. Cliquer "Appliquer à une tâche Saisie comptable"
5. Vérifier que la note et les remarques sont ajoutées

## ✅ Statut : COMPLET ET OPÉRATIONNEL

Le système d'évaluation automatique est maintenant entièrement fonctionnel avec :
- ✅ API Saisie Comptable créée et testée
- ✅ API Recouvrement créée et testée
- ✅ Interface UI intégrée pour les deux types
- ✅ Chargement automatique au démarrage de la page
- ✅ Application manuelle avec confirmation
- ✅ Remarques contextuelles générées automatiquement
- ✅ Calcul de notes cohérent (0-2 scale)

**Accessible via** : Évaluations > Détail d'une évaluation
