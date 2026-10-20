# Guide de génération de facture IRI

## 📋 Vue d'ensemble

Ce module permet de générer automatiquement des factures Excel IRI (Impôt sur les Revenus Intermittents) à partir des paiements validés, en utilisant le modèle Excel fourni.

## 🏗️ Architecture

### Fichiers créés/modifiés

1. **Backend**
   - `apps/employees/views_iri_facture.py` - Logique de génération et téléchargement
   - `apps/employees/urls.py` - Routes API ajoutées
   - `apps/employees/views_iri.py` - Champ `facture_generee` ajouté à l'API

2. **Frontend**
   - `templates/employees/paiements_iri_liste.html` - Boutons et fonctions JavaScript ajoutés

3. **Modèle**
   - `backend/Modèle Facture IRI.xlsx` - Template Excel à remplir
   - `backend/media/factures_iri/` - Répertoire de stockage des factures générées

### Modèle de données

Le modèle `PaiementIRI` possède déjà les champs nécessaires :
- `facture_generee` (Boolean) - Indique si la facture a été générée
- `date_generation_facture` (DateTime) - Date de génération

## 🚀 Workflow utilisateur

### Étape 1 : Générer le paiement IRI

1. Accéder à **Plannings > Paie > Paiements IRI**
2. Cliquer sur "Générer Paiement IRI"
3. Sélectionner le mois, l'année et l'organisation
4. Le système récupère automatiquement toutes les transactions DiameX avec :
   - Description commençant par "ISI"
   - Cat (compte_code) étant un nombre
5. Statut initial : **Brouillon**

### Étape 2 : Valider le paiement

1. Cliquer sur **Actions > Voir détails**
2. Vérifier les données groupées par ACTIV avec sous-totaux
3. Vérifier les colonnes :
   - ID (id_access), Rec, Prog, ACTIV
   - Fournisseur, Numéro CIN, Adresse
   - Date, Libellé, Unité, Prix unitaire
   - Montant, IRI 5%
4. Cliquer sur **Actions > Valider**
5. Statut passe à : **Validé**

### Étape 3 : Générer la facture Excel

**Conditions requises** :
- ✅ Paiement au statut "Validé"
- ✅ Au moins un détail existe

**Processus** :
1. Cliquer sur **Actions > Générer facture**
2. Confirmation : "Générer la facture Excel pour ce paiement IRI ?"
3. Le système :
   - Charge le modèle `Modèle Facture IRI.xlsx`
   - Remplit l'onglet **Annexe IRI** :
     - E4 : Nom organisation
     - E5 : Numéro NIF
     - E6 : Adresse organisation
     - E7 : Mois au format MMMM-YY (ex: Janvier-25)
     - Tableau des détails groupés par ACTIV (ligne 12+)
   - Remplit l'onglet **Déclaration IRI** :
     - E19 : Nom organisation
     - E23 : Adresse organisation
     - E25 : Numéro NIF
     - E27 : Mois au format MMM-YY (ex: Jan-25)
     - G31 : Total des montants achats
     - G33 : Formule `=G31*G32` (total IRI)
   - Sauvegarde dans `media/factures_iri/`
   - Marque `facture_generee = True`

**Nomenclature fichier** :
```
Facture_IRI_{Organisation}_{Mois:02d}_{Année}.xlsx
Exemple : Facture_IRI_Soakoja_01_2025.xlsx
```

### Étape 4 : Télécharger la facture

1. Le bouton **Télécharger facture** apparaît dans le menu Actions
2. Cliquer pour télécharger le fichier Excel généré

## 📊 Structure du fichier Excel

### Onglet "Annexe IRI"

**En-tête (lignes 4-7)** :
- E4 : Nom de l'organisation
- E5 : Numéro NIF
- E6 : Adresse
- E7 : Mois au format "MMMM-YY"

**Tableau des détails (ligne 12+)** :
| Col | Contenu |
|--------|---------|
| A | N° reçu (numero_diamex_source) |
| B | Fournisseur (fournisseur_nom) |
| C | N° CIN (fournisseur_cin) |
| D | Adresse (fournisseur_adresse) |
| E | Date (date_achat au format DD/MM/YYYY) |
| F | Libellé (libelle) |
| G | Unité (unite) |
| H | Prix unitaire (prix_unitaire) |
| I | Montant (montant_achat) |
| J | IRI 5% (montant_iri) |

**Format** :
- En-tête du tableau : Ligne 11
- Données : À partir de la ligne 12
- Bordures : Fine (thin) sur toutes les cellules
- Groupement : Par ACTIV avec :
  - Ligne d'en-tête de groupe : "ACTIV: {nom}" (fusionnée sur colonnes A-J, texte en gras)
  - Détails du groupe
  - Ligne de sous-total : "Sous-total {nom}" (fusionnée sur colonnes A-H, montants en gras)

### Onglet "Déclaration IRI"

**Informations organisation** :
- E19 : Nom organisation
- E23 : Adresse
- E25 : Numéro NIF
- E27 : Mois au format "MMM-YY" (ex: Jan-25)

**Montants** :
- G31 : Total des montants achats (valeur)
- G33 : Formule `=G31*G32` (calcul IRI basé sur G32)

## 🔧 APIs REST

### 1. Générer facture

**Endpoint** : `POST /api/paiement-iri/<uuid:paiement_id>/generer-facture/`

**Headers** :
```
X-CSRFToken: {csrf_token}
```

**Validation** :
- Paiement existe
- Statut = 'valide'
- Au moins 1 détail existe

**Réponse succès** :
```json
{
  "success": true,
  "message": "Facture IRI générée avec succès",
  "filename": "Facture_IRI_Soakoja_01_2025.xlsx",
  "path": "/path/to/media/factures_iri/Facture_IRI_Soakoja_01_2025.xlsx",
  "erreurs": []
}
```

**Réponse erreur** :
```json
{
  "success": false,
  "error": "Seuls les paiements validés peuvent générer une facture"
}
```

**Avertissements possibles** :
- "Onglet 'Annexe IRI' non trouvé dans le modèle"
- "Onglet 'Déclaration IRI' non trouvé dans le modèle"

### 2. Télécharger facture

**Endpoint** : `GET /api/paiement-iri/<uuid:paiement_id>/telecharger-facture/`

**Validation** :
- Paiement existe
- `facture_generee = True`
- Fichier existe sur le disque

**Réponse** :
- Content-Type: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Content-Disposition: `attachment; filename="Facture_IRI_Soakoja_01_2025.xlsx"`

## 🎨 Interface utilisateur

### Menu Actions (dropdown)

**Statut Brouillon** :
- ✅ Voir détails
- ✅ Valider
- ✅ Supprimer

**Statut Validé (facture non générée)** :
- ✅ Voir détails
- ✅ Générer facture (vert, icône Excel)

**Statut Validé (facture générée)** :
- ✅ Voir détails
- ✅ Télécharger facture (bleu, icône téléchargement)

### Fonctions JavaScript

**genererFacture(id)** :
```javascript
// Confirmation utilisateur
// Appel API POST /api/paiement-iri/{id}/generer-facture/
// Affichage message succès avec nom fichier
// Rechargement liste pour afficher bouton téléchargement
```

**telechargerFacture(id)** :
```javascript
// Redirection vers /api/paiement-iri/{id}/telecharger-facture/
// Téléchargement automatique du fichier
```

## 📁 Arborescence fichiers

```
backend/
├── Modèle Facture IRI.xlsx           # Template source
├── media/
│   └── factures_iri/                 # Factures générées
│       └── Facture_IRI_Soakoja_01_2025.xlsx
├── apps/employees/
│   ├── views_iri.py                  # API liste paiements
│   ├── views_iri_facture.py          # API génération facture
│   ├── urls.py                       # Routes
│   └── models.py                     # PaiementIRI, PaiementIRIDetail
└── templates/employees/
    └── paiements_iri_liste.html      # Interface utilisateur
```

## ⚙️ Configuration

### Répertoire de stockage

Le répertoire est créé automatiquement :
```python
media_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'media', 'factures_iri'
)
os.makedirs(media_dir, exist_ok=True)
```

### Modèle Excel

**Emplacement** : `backend/Modèle Facture IRI.xlsx`

**⚠️ Important** :
- Ne pas modifier la structure du modèle
- Les onglets doivent s'appeler exactement "Annexe IRI" et "Déclaration IRI"
- Les cellules d'en-tête sont à des positions fixes (E4, E5, etc.)

## 🐛 Gestion d'erreurs

### Erreurs possibles

1. **Modèle introuvable** :
   - Message : "Modèle non trouvé: {path}"
   - Solution : Vérifier que `Modèle Facture IRI.xlsx` existe

2. **Paiement non validé** :
   - Message : "Seuls les paiements validés peuvent générer une facture"
   - Solution : Valider le paiement d'abord

3. **Aucun détail** :
   - Message : "Aucun détail trouvé pour ce paiement"
   - Solution : Régénérer le paiement avec les bonnes transactions

4. **Onglet manquant** :
   - Warning : "Onglet 'Annexe IRI' non trouvé dans le modèle"
   - Solution : Vérifier le nom des onglets dans le modèle

5. **Fichier non trouvé (téléchargement)** :
   - Message : "Fichier de facture introuvable"
   - Solution : Régénérer la facture

### Fonction safe_write()

```python
def safe_write(ws, row, col, value, border_style=None, font_style=None, alignment_style=None):
    """
    Écrit une valeur dans une cellule en ignorant les cellules fusionnées
    Évite l'erreur "Cells are merged" lors de l'écriture
    """
    cell = ws.cell(row=row, column=col)
    if not isinstance(cell, MergedCell):
        cell.value = value
        if border_style:
            cell.border = border_style
        # ...
```

## 📈 Améliorations futures possibles

1. **Groupement ACTIV** : Activer les lignes de groupement et sous-totaux
2. **Export PDF** : Convertir le fichier Excel en PDF
3. **Envoi email** : Envoyer la facture par email automatiquement
4. **Historique** : Table dédiée pour tracker les générations de factures
5. **Modèles multiples** : Support de plusieurs modèles Excel selon l'organisation
6. **Validation avancée** : Vérifier la structure du modèle avant génération

## ✅ Checklist de validation

Avant de mettre en production :

- [ ] Le modèle `Modèle Facture IRI.xlsx` existe
- [ ] Les onglets "Annexe IRI" et "Déclaration IRI" existent
- [ ] Le répertoire `media/factures_iri/` est accessible en écriture
- [ ] L'organisation a un NIF et une adresse renseignés
- [ ] Les transactions DiameX ont des données fournisseur complètes
- [ ] Le filtre ISI fonctionne correctement (Description + Cat numérique)
- [ ] Les boutons apparaissent selon le statut du paiement
- [ ] Le téléchargement fonctionne sur tous les navigateurs

## 📞 Support

Pour toute question ou problème :
1. Consulter ce guide
2. Vérifier les logs Django
3. Vérifier que le modèle Excel est intact
4. Tester avec un petit paiement d'abord

---

**Date de création** : 20 décembre 2025
**Dernière mise à jour** : 20 décembre 2025
**Version** : 1.0
