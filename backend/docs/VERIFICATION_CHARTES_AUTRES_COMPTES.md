# Système de Vérification des Chartes Comptables - Autres Comptes

**Date de création** : 27 novembre 2025
**Module** : Comptabilité > Vérification Autres Comptes
**URL** : http://localhost:8000/comptabilite/verification-autres/

## Vue d'ensemble

Ce module permet de vérifier automatiquement la conformité des descriptions des transactions DiameX par rapport à des chartes comptables spécifiques définies pour chaque compte.

## Chartes implémentées

### 1. Allocation familiale employés (648200)
**Format** : `__Allocation familiale employés__[Année] [Numéro du mois]`

**Exemple** : `__Allocation familiale employés__2025 11`

**Validations** :
- Préfixe double underscore exact : `__Allocation familiale employés__`
- Année sur 4 chiffres
- Mois entre 1 et 12

### 2. BAF - Budget Activités Fonctionnement (748100)
**Format** : `__BAF__[Année] [Numéro du mois]`

**Exemple** : `__BAF__2025 11`

**Validations** :
- Préfixe double underscore : `__BAF__`
- Année sur 4 chiffres
- Mois entre 1 et 12

**Note importante** : Les comptes 648200 et 748100 doivent s'équilibrer mensuellement :
- Entrée sur 748100 = Sortie sur 648200

### 3. Installation Branchement Privé (748201)
**Format** : `_[Nom de personne]_[Type paiement]_[Nom de l'ouvrage]_[IDxls point d'eau]`

**Exemple** : `_Jean DUPONT_Paiement pour installation BP_Ambanja Centre_12345`

**Types de paiement valides** :
- `Paiement demande devis installation BP`
- `Paiement pour installation BP`

**Validations** :
- Format en 5 parties séparées par underscore
- Type de paiement doit être l'un des deux types valides
- Tous les champs obligatoires

### 4. Taxe communale (635201)
**Format** : `Taxe communale_[Nom de commune]`

**Exemple** : `Taxe communale_Ambanja`

**Validations** :
- Commence par "Taxe communale_"
- Nom de commune non vide

### 5. Cartes sociales (748415)
**Format** : `Cartes sociales [Nom de l'ouvrage] [Mois en format 01/MM/YYYY]`

**Exemple** : `Cartes sociales Ambanja Centre 01/11/2025`

**Validations** :
- Commence par "Cartes sociales "
- Date au format DD/MM/YYYY
- Le jour doit être "01" (premier du mois)
- Date valide

### 6. Paiement au volume (707401)
**Format** : `Paiement au volume [Nom de l'ouvrage] [Mois en format 01/MM/YYYY]`

**Exemple** : `Paiement au volume Ambanja Centre 01/11/2025`

**Validations** :
- Commence par "Paiement au volume "
- Date au format DD/MM/YYYY
- Le jour doit être "01" (premier du mois)
- Date valide

### 7. Paiement forfaitaire (748411)
**Format** : `Paiement forfaitaire_U_[Quantité]_[Tarifforfaitaire]_[Nom de l'ouvrage]`

**Exemple** : `Paiement forfaitaire_U_150_2500_Ambanja Centre`

**Validations** :
- Format en exactement 5 parties séparées par underscore
- Commence par "Paiement forfaitaire"
- Unité doit être "U"
- Quantité doit être un nombre
- Tarif doit être un nombre
- Nom de l'ouvrage non vide
- **STRICTEMENT RIEN APRÈS** le nom de l'ouvrage

## Configuration

### Modèle Compte
Chaque compte dans le modèle `Compte` (apps/organization/models.py) possède maintenant un champ :

```python
charte_verification = models.CharField(
    max_length=50,
    choices=CHARTE_CHOICES,
    blank=True,
    default='',
    verbose_name="Charte de vérification",
    help_text="Format de description attendu pour ce compte"
)
```

### Comptes configurés

Les 7 comptes suivants ont été automatiquement configurés avec leurs chartes respectives :

| Code compte | Nom du compte | Charte |
|-------------|---------------|--------|
| 648200 | Allocation familiale employés | allocation_familiale |
| 748100 | BAF - Budget Activités Fonctionnement | baf |
| 748201 | Installation Branchement Privé | installation_bp |
| 635201 | Taxe communale | taxe_communale |
| 748415 | Cartes sociales | cartes_sociales |
| 707401 | Paiement au volume | paiement_volume |
| 748411 | Paiement forfaitaire | paiement_forfaitaire |

## Fonctionnalités de l'interface

### 1. Filtrage des comptes
- La liste déroulante "Compte Cat" affiche **uniquement les comptes de l'organisation de l'utilisateur**
- Exclut automatiquement les comptes employés et fournisseurs

### 2. Colonne Conformité
- **Badge vert ✓ OK** : Description conforme à la charte
- **Badge rouge ✗ Non conforme** : Clic pour voir les erreurs détaillées
- **"-"** : Pas de charte définie pour ce compte

### 3. Modal de détails
Lorsque vous cliquez sur une entrée non conforme, le modal affiche :
- Toutes les informations de la transaction
- **Section "Charte comptable"** avec :
  - Type de charte appliquée
  - Alerte rouge avec la liste détaillée des erreurs de format

### 4. Statistiques
Les statistiques en haut de la page comptent le nombre de transactions conformes/non conformes.

## Architecture technique

### Fichiers modifiés/créés

**Backend :**
- `apps/organization/models.py` : Ajout champ `charte_verification` au modèle Compte
- `apps/accounting/charte_verification.py` : Fonction `verifier_charte_compte()` (196 lignes)
- `apps/accounting/views_verification_autres.py` : Intégration de la vérification dans l'API
- `apps/organization/migrations/0021_add_charte_verification.py` : Migration

**Frontend :**
- `templates/accounting/verification_autres.html` :
  - Colonne "Conformité" ajoutée
  - Badge cliquable pour erreurs
  - Section charte dans le modal de détails

**Scripts utilitaires :**
- `scripts/configure_chartes_comptes.py` : Configuration automatique des 7 comptes

### Fonction de vérification

```python
from apps.accounting.charte_verification import verifier_charte_compte

# Utilisation
result = verifier_charte_compte(
    description="__BAF__2025 11",
    charte_type="baf",
    compte_code="748100"
)

# result = {
#     'conforme': True,
#     'erreurs': [],
#     'details': {'type_charte': 'baf', 'annee': '2025', 'mois': '11'}
# }
```

### Workflow de vérification

1. L'API `api_verification_autres_comptes()` récupère les entrées DiameX
2. Pour chaque entrée :
   - Recherche le compte correspondant
   - Si le compte a une `charte_verification` définie :
     - Appelle `verifier_charte_compte()`
     - Retourne résultat de conformité
3. Le frontend affiche les badges selon le résultat

## Tests

### Tester une charte

1. Accéder à http://localhost:8000/comptabilite/verification-autres/
2. Filtrer par compte (ex: 748100)
3. Vérifier que les badges de conformité s'affichent
4. Cliquer sur un badge "Non conforme" pour voir les détails

### Ajouter une nouvelle charte

1. Modifier `apps/organization/models.py` :
   - Ajouter le choix dans `CHARTE_CHOICES`

2. Modifier `apps/accounting/charte_verification.py` :
   - Ajouter le cas `elif charte_type == 'nouveau_type':`
   - Implémenter la logique de validation

3. Créer une migration :
   ```bash
   python manage.py makemigrations organization
   python manage.py migrate
   ```

4. Configurer le compte :
   ```python
   compte = Compte.objects.get(compte='XXXXX')
   compte.charte_verification = 'nouveau_type'
   compte.save()
   ```

## Points d'attention CRITICAL

1. **Validation stricte** : Les chartes appliquent des règles strictes. Toute déviation génère une erreur.

2. **Pas d'auto-correction** : Le système ne corrige pas automatiquement les descriptions. Il faut modifier manuellement via l'interface.

3. **Balance 648200/748100** : La vérification de l'équilibre mensuel entre ces deux comptes n'est pas encore implémentée. C'est une amélioration future.

4. **Performance** : La vérification se fait en Python (pas en SQL). Pour de gros volumes, envisager une mise en cache.

## Améliorations futures

1. **Validation de balance** : Vérifier automatiquement que Entrée 748100 = Sortie 648200 chaque mois

2. **Correction automatique** : Proposer une correction intelligente des descriptions non conformes

3. **Import en masse** : Ajouter une validation lors de l'import Excel pour rejeter les lignes non conformes

4. **Rapport d'audit** : Export Excel avec toutes les non-conformités pour reporting

5. **Notifications** : Alerter l'utilisateur quand une nouvelle transaction non conforme est créée

## Historique

- **27 novembre 2025** : Implémentation complète du système de vérification des chartes pour 7 comptes
