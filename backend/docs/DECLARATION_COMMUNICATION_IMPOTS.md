# Déclaration de Communication aux Impôts

## Vue d'ensemble

Ce module permet de générer automatiquement la déclaration de communication annuelle aux services des impôts, en regroupant toutes les transactions qui commencent par **NIF** ou **ISI** dans leur description.

## Architecture

### Tables créées

#### 1. `config_declaration_communication`

Table de configuration des natures de déclaration.

**Champs** :
- `id` : UUID (primary key)
- `nom` : Nom de la nature (ex: Fournitures, Matériaux, Services, Travaux)
- `ordre` : Ordre d'affichage dans les listes déroulantes
- `actif` : Boolean (si désactivé, n'apparaît plus dans les choix)
- `created_at` : Date de création
- `updated_at` : Date de modification

**Exemples de natures** :
- Fournitures
- Matériaux
- Services
- Travaux
- Équipements
- Carburant
- Loyer
- Honoraires
- etc.

#### 2. Champ `nature_declaration` dans la table `comptes`

**Type** : ForeignKey vers `ConfigDeclarationCommunication`
**Optionnel** : `null=True, blank=True`
**Utilité** : Permet de lier un compte comptable à une nature de déclaration

## Workflow

### 1. Configuration initiale

**Créer les natures de déclaration :**
1. Accéder à l'interface de gestion : `/comptabilite/natures-declaration/`
2. Cliquer sur "Nouvelle Nature"
3. Remplir le formulaire :
   - Nom : Ex: Fournitures, Matériaux, Services, Travaux
   - Ordre : Définir l'ordre d'affichage (0 = début)
   - Actif : Cocher pour rendre la nature disponible
4. Enregistrer

**Lier les comptes aux natures :**
1. Accéder à l'admin des comptes : `/admin/organization/compte/`
2. Pour chaque compte concerné par la déclaration (ex: compte 6011 "Matériaux"), sélectionner la nature correspondante
3. Sauvegarder

### 2. Génération de la déclaration

**URL** : `/comptabilite/declaration-communication/`

**Paramètres** :
- **Année** : Sélectionner l'année de la déclaration (liste déroulante)

**Critères de sélection automatique** :
- Transactions de l'année sélectionnée
- Description commence par **NIF** ou **ISI**
- Regroupement par : **Fournisseur ID** + **Nature de déclaration**

**Exemple** :
Si le fournisseur "STE ANTSINANANA" (ID: 123) a :
- 5 lignes de nature "Fournitures" → 1 ligne dans la déclaration
- 5 lignes de nature "Matériaux" → 1 ligne dans la déclaration

Total : 2 lignes dans la déclaration pour ce fournisseur.

### 3. Colonnes de la déclaration

| Colonne | Source | Règle |
|---------|--------|-------|
| **Numéro NIF** | `Fournisseur.numero_nif` | Depuis la table Fournisseur |
| **Numéro STAT** | `Fournisseur.numero_stat` | Depuis la table Fournisseur |
| **Numéro CIN** | `Fournisseur.cin` | Depuis la table Fournisseur |
| **Date CIN** | `Fournisseur.date_cin` | Format : DD/MM/YYYY |
| **Lieu de délivrance CIN** | - | À ajouter au modèle Fournisseur si nécessaire |
| **Nom fournisseur** | `Fournisseur.nom_fournisseur` | Nom complet |
| **Adresse** | `Fournisseur.adresse_fournisseur` | Adresse complète |
| **Ville** | - | À extraire de l'adresse si nécessaire |
| **Ex-province** | - | À ajouter au modèle Fournisseur si nécessaire |
| **Pays** | - | Par défaut : "Madagascar" |
| **Nature** | `Compte.nature_declaration.nom` | Ex: Fournitures, Matériaux |
| **Montant comptabilisé (Ar)** | `SUM(BaseDiameX.montant_out)` | Total des sorties groupées |
| **Montant versé (Ar)** | = Montant comptabilisé | Identique |
| **Achat ou Prestation** | Logique automatique | Si description contient "PREST" → "Prestation", sinon "Achat" |
| **ISI ou NIF** | Logique automatique | Si NIF renseigné → "NIF", sinon "ISI" |

### 4. Export Excel

**Fonctionnalité** : Génère un fichier Excel formaté avec toutes les colonnes

**Format** :
- En-têtes colorés (bleu foncé, texte blanc)
- Bordures sur toutes les cellules
- Largeurs de colonnes optimisées
- Montants avec format numérique : `#,##0.00`
- Première ligne figée (freeze panes)

**Nom du fichier** : `Declaration_Communication_{annee}_{timestamp}.xlsx`

**Exemple** : `Declaration_Communication_2025_20251222_143045.xlsx`

## APIs REST

### 1. Génération de la déclaration

**Endpoint** : `GET /comptabilite/declaration-communication/api/generer/`

**Paramètres** :
- `annee` : Année (ex: 2025)

**Réponse** :
```json
{
    "success": true,
    "annee": 2025,
    "total_lignes": 42,
    "data": [
        {
            "fournisseur_id": "123",
            "nif": "1234567890",
            "stat": "12345678912345",
            "cin": "101234567890",
            "date_cin": "15/03/2020",
            "lieu_cin": "",
            "nom": "STE ANTSINANANA",
            "adresse": "LOT ABC, Antananarivo",
            "ville": "",
            "province": "",
            "pays": "Madagascar",
            "nature": "Fournitures",
            "montant_comptabilise": "5500000.00",
            "montant_verse": "5500000.00",
            "type_operation": "Achat",
            "type_numero": "NIF"
        },
        ...
    ]
}
```

### 2. Export Excel

**Endpoint** : `GET /comptabilite/declaration-communication/api/export-excel/`

**Paramètres** :
- `annee` : Année (ex: 2025)

**Réponse** : Fichier Excel (Content-Type: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`)

## Règles métier

### Détermination du type d'opération

**Achats immobilisé** :
- Nature de déclaration = "Outillage" (insensible à la casse)
- Priorité la plus élevée (vérifié en premier)
- Exemple : Achat de perceuse, marteau-piqueur, etc.

**Prestation** :
- Description contient "PREST" (insensible à la casse)
- Exemple : `NIF PREST Consultation juridique`
- Exemple : `ISI PREST Services de nettoyage`

**Achat** :
- Description NE contient PAS "PREST" ET nature différente de "Outillage"
- Exemple : `NIF ABC Fournitures de bureau`

### Détermination du type de numéro

**NIF** :
- Si `Fournisseur.numero_nif` est renseigné (non vide)

**ISI** :
- Si `Fournisseur.numero_nif` est vide ou NULL

### Groupement des transactions

Les transactions sont groupées par **clé unique** :
```
fournisseur_id + "_" + nature_nom
```

**Exemple** :
- Fournisseur 123 + Nature "Fournitures" → Clé : `123_Fournitures`
- Fournisseur 123 + Nature "Matériaux" → Clé : `123_Matériaux`

Si 10 transactions correspondent à la clé `123_Fournitures`, elles seront agrégées en 1 seule ligne avec le total des montants.

## Améliorations futures possibles

### Champs manquants dans le modèle Fournisseur

Pour une déclaration complète, il serait utile d'ajouter :

1. **Lieu de délivrance CIN** : `CharField(max_length=100)`
2. **Ville** : `CharField(max_length=100)`
3. **Province** : `CharField(max_length=100)` avec choix :
   - Antananarivo
   - Fianarantsoa
   - Toamasina
   - Mahajanga
   - Toliara
   - Antsiranana

**Migration exemple** :
```python
python manage.py makemigrations billing --name add_fournisseur_declaration_fields
python manage.py migrate billing
```

### Interface de gestion des natures

Créer une interface web pour gérer les natures de déclaration sans passer par l'admin Django :
- Liste des natures avec recherche
- Création/Modification/Suppression
- Réorganisation de l'ordre d'affichage (drag & drop)

### Validation des données

Ajouter des alertes si :
- Un fournisseur n'a pas de NIF ni de STAT
- Une transaction n'a pas de nature de déclaration assignée
- Des montants semblent incohérents

### Export PDF

Générer un PDF formaté pour soumission officielle aux impôts.

## Fichiers créés/modifiés

**Modèles** :
- `apps/accounting/models.py` : Modèle `ConfigDeclarationCommunication`
- `apps/organization/models.py` : Champ `nature_declaration` dans `Compte`

**Migrations** :
- `apps/accounting/migrations/0020_declaration_communication.py`
- `apps/organization/migrations/0022_declaration_communication.py`

**Vues** :
- `apps/accounting/views_declaration_communication.py` (3 vues)

**URLs** :
- `apps/accounting/urls.py` : 3 routes ajoutées

**Templates** :
- `templates/accounting/declaration_communication.html`

**Documentation** :
- `docs/DECLARATION_COMMUNICATION_IMPOTS.md` (ce fichier)

## Utilisation

### Étape 1 : Configurer les natures

```bash
python manage.py shell
```

```python
from apps.accounting.models import ConfigDeclarationCommunication

# Créer les natures de base
natures = [
    'Fournitures',
    'Matériaux',
    'Services',
    'Travaux',
    'Équipements',
    'Carburant',
    'Loyer',
    'Honoraires'
]

for idx, nom in enumerate(natures, start=1):
    ConfigDeclarationCommunication.objects.get_or_create(
        nom=nom,
        defaults={'ordre': idx * 10}
    )
```

### Étape 2 : Lier les comptes aux natures

Via l'admin Django ou en script :

```python
from apps.organization.models import Compte
from apps.accounting.models import ConfigDeclarationCommunication

# Exemple : Lier le compte 6011 (Matériaux) à la nature "Matériaux"
nature_materiaux = ConfigDeclarationCommunication.objects.get(nom='Matériaux')
comptes_materiaux = Compte.objects.filter(compte__startswith='6011')
comptes_materiaux.update(nature_declaration=nature_materiaux)

# Exemple : Lier le compte 6021 (Fournitures) à la nature "Fournitures"
nature_fournitures = ConfigDeclarationCommunication.objects.get(nom='Fournitures')
comptes_fournitures = Compte.objects.filter(compte__startswith='6021')
comptes_fournitures.update(nature_declaration=nature_fournitures)
```

### Étape 3 : Générer la déclaration

1. Accéder à : `/comptabilite/declaration-communication/`
2. Sélectionner l'année
3. Cliquer sur "Générer la déclaration"
4. Vérifier les résultats
5. Cliquer sur "Exporter Excel"

## ✅ Fonctionnalités complètes

✅ Table `ConfigDeclarationCommunication` créée
✅ Champ `nature_declaration` ajouté au modèle Compte
✅ API de génération de la déclaration
✅ API d'export Excel
✅ Interface web complète avec statistiques
✅ Groupement par fournisseur et nature
✅ Détection automatique Achat/Prestation
✅ Détection automatique NIF/ISI
✅ Format Excel professionnel

**Le module de déclaration de communication aux impôts est maintenant entièrement opérationnel !**
