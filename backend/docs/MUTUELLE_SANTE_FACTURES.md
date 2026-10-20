# Génération Factures Mutuelle Santé (AMIT/OSIEFSoVa)

## Vue d'ensemble
Module permettant de générer automatiquement les factures Excel pour les paiements de mutuelle santé en utilisant des modèles prédéfinis pour AMIT et OSIEFSoVa.

## Fonctionnalités

### 1. Génération automatique de factures
- **Entrée** : Paiement de mutuelle santé validé
- **Sortie** : 1 ou 2 fichiers Excel selon les mutuelles concernées
  - `Facture_AMIT_{Organisation}_T{Trimestre}_{Année}.xlsx`
  - `Facture_OSIEFSoVa_{Organisation}_T{Trimestre}_{Année}.xlsx`

### 2. Modèles Excel utilisés
- **AMIT** : `backend/Modele facture AMIT.xlsx`
  - Onglet 1 : BORDEREAU TRIMESTRIELLE (informations organisation)
  - Onglet 2 : DNS 3T FANAINGA (liste des employés)

- **OSIEFSoVa** : `backend/Modèle facture OSIEFSoVa.xlsx`
  - Onglet BORDEREAU SKJ (informations organisation)
  - Onglets mensuels : MAI, JUIN, JUILLET (données employés par mois)

### 3. Workflow utilisateur

**Étape 1 : Créer un paiement mutuelle**
- Aller sur `/paiements-mutuelle-sante/`
- Cliquer "Générer Paiement Mutuelle"
- Sélectionner trimestre, année, organisation
- Le système calcule automatiquement les montants AMIT et OSIEFSoVa

**Étape 2 : Valider le paiement**
- Cliquer "Valider" dans le menu Actions
- Le statut passe de "Brouillon" à "Validé"

**Étape 3 : Générer les factures Excel**
- Cliquer "Générer facture" dans le menu Actions
- Le système crée les fichiers Excel avec les données des employés
- Le champ `facture_generee` est marqué à `True`

**Étape 4 : Télécharger les factures**
- Cliquer "Télécharger AMIT" ou "Télécharger OSIEFSoVa"
- Les fichiers Excel s'ouvrent dans un nouvel onglet

## Structure des données AMIT

### Onglet BORDEREAU TRIMESTRIELLE
| Cellule | Contenu |
|---------|---------|
| B10 | Nom de l'organisation |
| B12 | Adresse |
| B13 | Email |
| B14 | Téléphone |
| B17 | Effectif total |
| B19 | Total des salaires |

### Onglet DNS 3T FANAINGA (à partir de la ligne 15)
| Colonne | Contenu |
|---------|---------|
| A | NOM |
| B | PRENOMS |
| C | N° CHEZ L'AMIT (vide) |
| D | Date de naissance (DD/MM/YYYY) |
| E | CIN |
| F | SEXE |
| G | DATE (embauche - DD/MM/YYYY) |
| J | Temps de travail (vide) |
| K | REMUNERATION |
| N | TOTAL SALAIRE NON PLAFONNE |

## Structure des données OSIEFSoVa

### Onglet BORDEREAU SKJ
| Cellule | Contenu |
|---------|---------|
| B10 | Nom de l'organisation |
| B12 | Adresse |
| B13 | Email |
| B14 | Téléphone |
| B17 | Effectif total |
| B19 | Total des salaires |

### Onglets mensuels (MAI, JUIN, JUILLET)
| Cellule | Contenu |
|---------|---------|
| C1 | "NOM OU RAISON SOCIALE : {Organisation}" |

#### Données employés (à partir de la ligne 15)
| Colonne | Contenu |
|---------|---------|
| A | NOM ET PRENOMS |
| B | Date de naissance (DD/MM/YYYY) |
| C | CIN |
| D | SEXE |
| E | DATE (embauche - DD/MM/YYYY) |
| G | REMUNERATION |
| I | Temps de travail (vide) |
| J | TOTAL SALAIRE NON PLAFONNE |
| K | Cotisations 6% (montant × 0.06) |
| L | Nombre Enfants CNaPS |

## Code Backend

### Fichiers créés
1. **`backend/apps/employees/views_mutuelle_facture.py`**
   - `generer_facture_mutuelle_sante()` : API principale de génération
   - `generer_facture_amit()` : Logique spécifique AMIT
   - `generer_facture_osiefsova()` : Logique spécifique OSIEFSoVa
   - `telecharger_facture_mutuelle()` : Téléchargement des fichiers générés

### URLs ajoutées
```python
path('api/paiement-mutuelle-sante/<uuid:paiement_id>/generer-facture/',
     views_mutuelle_facture.generer_facture_mutuelle_sante,
     name='api_generer_facture_mutuelle_sante'),

path('api/paiement-mutuelle-sante/<uuid:paiement_id>/telecharger/<str:mutuelle_type>/',
     views_mutuelle_facture.telecharger_facture_mutuelle,
     name='telecharger_facture_mutuelle'),
```

### Gestion des cellules fusionnées
Le code utilise la fonction `safe_write()` qui vérifie si une cellule est fusionnée avant d'écrire :

```python
def safe_write(ws, row, col, value):
    """Écrire dans une cellule en ignorant les cellules fusionnées"""
    cell = ws.cell(row=row, column=col)
    if not isinstance(cell, MergedCell):
        cell.value = value
```

## Frontend

### Template modifié
**`backend/templates/employees/paiements_mutuelle_liste.html`**

#### Boutons dans le menu Actions
```html
${p.statut === 'validé' && !p.facture_generee ? `
    <li><a onclick="genererFacture('${p.id}')">
        <i class="fas fa-file-excel mr-2"></i>Générer facture
    </a></li>
` : ''}

${p.facture_generee ? `
    <li><a onclick="telechargerFacture('${p.id}', 'amit')">
        <i class="fas fa-download mr-2 text-info"></i>Télécharger AMIT
    </a></li>
    <li><a onclick="telechargerFacture('${p.id}', 'osiefsova')">
        <i class="fas fa-download mr-2 text-success"></i>Télécharger OSIEFSoVa
    </a></li>
` : ''}
```

#### Fonctions JavaScript
```javascript
// Génération
async function genererFacture(paiementId) {
    const response = await fetch(
        `/employes/api/paiement-mutuelle-sante/${paiementId}/generer-facture/`,
        {method: 'POST', headers: {'X-CSRFToken': getCookie('csrftoken')}}
    );
    const data = await response.json();
    // Affiche message de succès et recharge la liste
}

// Téléchargement
function telechargerFacture(paiementId, mutuelleType) {
    window.open(
        `/employes/api/paiement-mutuelle-sante/${paiementId}/telecharger/${mutuelleType}/`,
        '_blank'
    );
}
```

## Répertoire de stockage

**Chemin** : `backend/media/factures_mutuelle/`

Les fichiers générés sont stockés dans ce répertoire avec la nomenclature :
- `Facture_AMIT_{Organisation}_T{Trimestre}_{Année}.xlsx`
- `Facture_OSIEFSoVa_{Organisation}_T{Trimestre}_{Année}.xlsx`

## Validation et sécurité

### Vérifications avant génération
1. Le paiement doit avoir le statut `'valide'`
2. Les montants AMIT et/ou OSIEFSoVa doivent être > 0
3. Au moins un détail de paiement doit exister

### Gestion d'erreurs
- Si une mutuelle échoue, l'autre peut quand même être générée
- Les erreurs sont retournées dans un tableau `erreurs[]`
- Le champ `facture_generee` est marqué même si une mutuelle échoue

### Réponse JSON de génération
```json
{
    "success": true,
    "message": "2 facture(s) générée(s) avec succès",
    "fichiers": [
        {"mutuelle": "AMIT", "path": "..."},
        {"mutuelle": "OSIEFSoVa", "path": "..."}
    ],
    "erreurs": []
}
```

## Points d'attention CRITICAL

1. **Modèles Excel à ne pas modifier** : Les fichiers `Modele facture AMIT.xlsx` et `Modèle facture OSIEFSoVa.xlsx` doivent être conservés dans le dossier `backend/`

2. **Cellules fusionnées** : Toujours utiliser `safe_write()` pour éviter les erreurs lors de l'écriture dans des cellules fusionnées

3. **Format des dates** : Les dates sont formatées en DD/MM/YYYY (format français)

4. **Calcul des cotisations OSIEFSoVa** : 6% du montant mutuelle (colonne K)

5. **Nombre d'enfants** : Provient de `employe.personnes_charge`

6. **Temps de travail** : Laissé vide car non disponible dans les données

## Améliorations futures possibles

1. **Sélection des mois** : Actuellement, les 3 premiers mois disponibles sont utilisés. À adapter selon le trimestre réel.

2. **N° CHEZ L'AMIT** : Champ laissé vide, pourrait être ajouté au modèle Employe

3. **Temps de travail** : Pourrait être calculé à partir des données de planning

4. **Feuilles FNG** : L'onglet BORDEREAU FNG existe mais n'est pas rempli (similaire à SKJ)

5. **Export vers DiameX** : Déjà implémenté dans `views_mutuelle_export.py` (séparé)

## Tests à effectuer

- [ ] Créer un paiement mutuelle avec employés AMIT uniquement
- [ ] Créer un paiement mutuelle avec employés OSIEFSoVa uniquement
- [ ] Créer un paiement mutuelle avec employés des deux mutuelles
- [ ] Vérifier que le bouton "Générer facture" n'apparaît que pour les paiements validés
- [ ] Vérifier que les boutons de téléchargement n'apparaissent qu'après génération
- [ ] Télécharger et ouvrir les fichiers Excel générés
- [ ] Vérifier que les données des employés sont correctes
- [ ] Vérifier que les totaux correspondent aux montants du paiement

## Accessible via
**URL** : http://localhost:8000/paiements-mutuelle-sante/
**Menu** : Plannings > Paie > Paiements Mutuelle Santé

---

**Date de création** : 20 décembre 2025
**Dernière modification** : 20 décembre 2025
