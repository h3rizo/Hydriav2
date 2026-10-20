# Workflow Encaissement Groupé - Paiements Forfaitaires

## Vue d'ensemble

Le système d'encaissement groupé permet de traiter plusieurs factures forfaitaires en une seule transaction DiameX, optimisant ainsi le processus comptable tout en maintenant la traçabilité complète.

## Architecture

### Modèle de données

**PaiementForfaitaire** (billing.models)
```python
class PaiementForfaitaire(models.Model):
    point_eau = ForeignKey(PointEau)
    date_facture = DateField()
    montant = DecimalField()
    paye = BooleanField(default=False)
    date_paiement = DateField(null=True)
    numeroDiameX = CharField(max_length=50, null=True)
    baseDiameX = CharField(max_length=50, null=True)
```

**DiameXTemporaire** (accounting.models)
```python
class DiameXTemporaire(models.Model):
    # Lien vers le premier paiement (pour traçabilité)
    paiement_forfaitaire = ForeignKey(PaiementForfaitaire, null=True)

    # NOUVEAU : Liste complète des IDs des paiements groupés
    paiements_forfaitaires_ids = JSONField(
        null=True,
        help_text="Pour encaissement groupé : liste des UUIDs des paiements inclus"
    )

    type_transaction = CharField(max_length=20)  # 'recette'
    date_m = DateField()
    description = TextField()
    montant_in = FloatField()  # Montant total groupé
    montant_out = FloatField()  # 0 pour les recettes
    compte_code = CharField(max_length=20)  # '748411' pour vente eau forfait
    info = CharField(max_length=255)
    activ = CharField(max_length=50, null=True)  # Volet de l'ouvrage
    statut = CharField(max_length=20)  # 'en_attente'
```

### Workflow complet

```
1. SÉLECTION (Interface Web)
   ├─ Filtrer par organisation/ouvrage
   ├─ Rechercher dans noms de points d'eau
   ├─ Sélectionner plusieurs factures (checkboxes)
   └─ Validation : Toutes du même ouvrage

2. ENCAISSEMENT (API Backend)
   ├─ Marquer tous les paiements comme payés
   ├─ Définir date_paiement = aujourd'hui
   ├─ Calculer montant total
   └─ Créer UNE ligne DiameXTemporaire

3. COMPTABILITÉ (DiameX)
   ├─ Validation de la ligne temporaire
   ├─ Export vers DiameX (Access)
   ├─ DiameX génère numeroDiameX
   └─ Retour du numeroDiameX vers Hydria

4. PROPAGATION (Mise à jour)
   ├─ Récupérer paiements_forfaitaires_ids
   ├─ Pour chaque ID dans la liste :
   │  └─ Mettre à jour numeroDiameX
   └─ TOUS les paiements groupés ont le même numéro
```

## Interface utilisateur

### Page d'encaissement groupé

**URL** : `/billing/paiements-forfaitaires/encaissement-groupe/`

**Accès** : Facturation > Suivi des Paiements Forfaitaires > Bouton "Encaissement Groupé"

**Fonctionnalités** :

1. **Filtres avancés**
   - Organisation (dropdown)
   - Ouvrage (dropdown)
   - Recherche textuelle dans noms de points d'eau

2. **Sélection multiple**
   - Checkbox "Tout sélectionner"
   - Checkboxes individuelles par facture
   - Compteurs en temps réel :
     - Nombre de factures sélectionnées
     - Montant total à encaisser

3. **Validation automatique**
   - Vérification que toutes les factures sélectionnées proviennent du **même ouvrage**
   - Alert si différents ouvrages détectés
   - Bouton "Encaisser" désactivé si validation échoue

4. **Actions**
   - "Tout sélectionner" : Sélectionne toutes les factures visibles
   - "Tout désélectionner" : Vide la sélection
   - "Encaisser la sélection" : Lance l'encaissement groupé

### Template : `encaissement_groupe.html`

**Sections principales** :

```html
<!-- Header avec titre et actions -->
<div class="flex justify-between items-center">
    <h1>Encaissement Groupé - Paiements Forfaitaires</h1>
    <a href="suivi_paiements_forfaitaires">Retour au suivi</a>
</div>

<!-- Filtres -->
<div class="card">
    <select id="filter-organisation">
    <select id="filter-ouvrage">
    <input id="filter-search">
    <button onclick="applyFilters()">Filtrer</button>
</div>

<!-- Actions groupées avec compteurs -->
<div class="card">
    <span id="selection-count">0</span> facture(s) sélectionnée(s)
    <span id="selection-total">0 Ar</span> Montant total

    <button onclick="selectAll()">Tout sélectionner</button>
    <button onclick="deselectAll()">Tout désélectionner</button>
    <button onclick="encaisserSelection()" id="btn-encaisser">Encaisser</button>
</div>

<!-- Tableau des factures -->
<table>
    <thead>
        <th><input type="checkbox" id="checkbox-all"></th>
        <th>Ouvrage</th>
        <th>Point d'eau</th>
        <th>Date facture</th>
        <th>Montant</th>
        ...
    </thead>
    <tbody id="tbody-factures">
        <!-- Lignes chargées dynamiquement via API -->
    </tbody>
</table>
```

**JavaScript critique** :

```javascript
// État de la sélection
let selectedPaiements = [];
let allFactures = [];

// Chargement des factures
async function loadFactures() {
    const params = new URLSearchParams();
    params.append('paye', 'false');  // Seulement non payées

    if (organisation !== 'all') params.append('organisation_id', organisation);
    if (ouvrage !== 'all') params.append('ouvrage_id', ouvrage);
    if (search) params.append('search', search);

    const response = await fetch('/billing/paiements-forfaitaires/api/list/?' + params);
    const data = await response.json();

    allFactures = data.paiements || [];
    displayFactures(allFactures);
}

// Toggle sélection
function toggleSelection(paiementId, montant, ouvrageId) {
    const index = selectedPaiements.findIndex(p => p.id === paiementId);

    if (index > -1) {
        selectedPaiements.splice(index, 1);
    } else {
        selectedPaiements.push({
            id: paiementId,
            montant: montant,
            ouvrage_id: ouvrageId
        });
    }

    updateSelectionSummary();
    checkOuvrageUnique();
}

// Validation ouvrage unique
function checkOuvrageUnique() {
    if (selectedPaiements.length === 0) return true;

    const premierOuvrage = selectedPaiements[0].ouvrage_id;
    const tousMemOuvrage = selectedPaiements.every(p => p.ouvrage_id === premierOuvrage);

    const btnEncaisser = document.getElementById('btn-encaisser');

    if (!tousMemOuvrage) {
        btnEncaisser.disabled = true;
        btnEncaisser.title = "Vous devez sélectionner des factures du même ouvrage";
        alert("⚠️ Attention : Vous avez sélectionné des factures de différents ouvrages.");
        return false;
    } else {
        btnEncaisser.title = "Encaisser les factures sélectionnées";
    }

    return true;
}

// Encaissement groupé
async function encaisserSelection() {
    if (selectedPaiements.length === 0) {
        alert('Veuillez sélectionner au moins une facture');
        return;
    }

    if (!checkOuvrageUnique()) return;

    const count = selectedPaiements.length;
    const total = selectedPaiements.reduce((sum, p) => sum + p.montant, 0);

    const confirmation = confirm(
        `Confirmer l'encaissement groupé de ${count} facture(s) ?\n\n` +
        `Montant total : ${total.toLocaleString('fr-FR')} Ar\n\n` +
        `Cela créera UNE SEULE ligne dans DiameX pour toutes ces factures.`
    );

    if (!confirmation) return;

    const response = await fetch('/billing/paiements-forfaitaires/api/encaisser/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({
            paiement_ids: selectedPaiements.map(p => p.id),
            groupe: true  // CLEF : Active le mode groupé
        })
    });

    const result = await response.json();

    if (result.success) {
        alert(`✅ ${result.message}`);
        deselectAll();
        loadFactures();
    } else {
        alert('❌ Erreur: ' + result.error);
    }
}
```

## API Backend

### 1. Liste des paiements forfaitaires

**Endpoint** : `GET /billing/paiements-forfaitaires/api/list/`

**Paramètres** :
- `organisation_id` : UUID de l'organisation (optionnel)
- `ouvrage_id` : UUID de l'ouvrage (optionnel)
- `paye` : `true` ou `false` pour filtrer par statut (optionnel)
- `search` : Recherche textuelle dans noms de points d'eau (optionnel)

**Réponse** :
```json
{
    "success": true,
    "paiements": [
        {
            "id": "uuid-paiement-1",
            "point_eau_nom": "Fontaine publique Nord",
            "point_eau_id": "uuid-point-eau",
            "ouvrage_nom": "AEPG Ambato",
            "ouvrage_id": "uuid-ouvrage",
            "date_facture": "2025-12-01",
            "quantite": 1,
            "prix_unitaire": 5000.0,
            "montant": 5000.0,
            "duree_mois": 1,
            "date_fin_validite": "2025-12-31",
            "paye": false,
            "date_paiement": null,
            "numeroDiameX": ""
        },
        // ... autres paiements
    ],
    "total": 42
}
```

**Implémentation** (`views_encaissement_forfaitaire.py`) :
```python
@csrf_exempt
@require_http_methods(["GET"])
def api_liste_paiements_forfaitaires(request):
    """API pour lister les paiements forfaitaires avec filtres"""

    organisation_id = request.GET.get('organisation_id')
    ouvrage_id = request.GET.get('ouvrage_id')
    paye_str = request.GET.get('paye')
    search = request.GET.get('search', '').strip()

    queryset = PaiementForfaitaire.objects.select_related(
        'point_eau',
        'point_eau__ouvrage',
        'point_eau__ouvrage__organisation'
    ).all()

    # Filtre organisation
    if organisation_id and organisation_id != 'all':
        queryset = queryset.filter(point_eau__ouvrage__organisation_id=organisation_id)

    # Filtre ouvrage
    if ouvrage_id and ouvrage_id != 'all':
        queryset = queryset.filter(point_eau__ouvrage_id=ouvrage_id)

    # Filtre payé/non payé
    if paye_str:
        paye_bool = paye_str.lower() == 'true'
        queryset = queryset.filter(paye=paye_bool)

    # Recherche
    if search:
        from django.db.models import Q
        queryset = queryset.filter(
            Q(point_eau__nomabonne__icontains=search) |
            Q(point_eau__numeroabonne__icontains=search)
        )

    queryset = queryset.order_by('-date_facture')

    paiements = []
    for p in queryset:
        paiements.append({
            'id': str(p.id),
            'ouvrage_id': str(p.point_eau.ouvrage.id),
            'montant': float(p.montant) if p.montant else 0.0,
            # ... autres champs
        })

    return JsonResponse({
        'success': True,
        'paiements': paiements,
        'total': len(paiements)
    })
```

### 2. Encaissement des paiements

**Endpoint** : `POST /billing/paiements-forfaitaires/api/encaisser/`

**Body (JSON)** :
```json
{
    "paiement_ids": ["uuid1", "uuid2", "uuid3"],
    "numero_diamex": "",  // Optionnel
    "base_diamex": "",    // Optionnel
    "groupe": true        // CLEF : Active encaissement groupé
}
```

**Réponse** :
```json
{
    "success": true,
    "message": "3 paiement(s) encaissé(s) en un seul groupe (montant total: 15,000.00 Ar)",
    "nb_encaisses": 3,
    "erreurs": []
}
```

**Implémentation** (`views_encaissement_forfaitaire.py`) :
```python
@csrf_exempt
@require_http_methods(["POST"])
def api_encaisser_paiements(request):
    """API pour encaisser des paiements forfaitaires"""

    data = json.loads(request.body)
    paiement_ids = data.get('paiement_ids', [])
    numero_diamex = data.get('numero_diamex', '')
    base_diamex = data.get('base_diamex', '')
    encaissement_groupe = data.get('groupe', False)  # NOUVEAU

    if not paiement_ids:
        return JsonResponse({
            'success': False,
            'error': 'Aucun paiement à encaisser'
        }, status=400)

    nb_encaisses = 0
    erreurs = []
    montant_total = Decimal('0')
    premier_point_eau = None
    ouvrage_commun = None
    paiements_encaisses = []

    # 1. Marquer tous les paiements comme payés
    for paiement_id in paiement_ids:
        try:
            paiement = PaiementForfaitaire.objects.get(id=paiement_id)

            paiement.paye = True

            if not paiement.date_paiement:
                paiement.date_paiement = datetime.now().date()

            if numero_diamex:
                paiement.numeroDiameX = str(numero_diamex)
            if base_diamex:
                paiement.baseDiameX = str(base_diamex)

            paiement.save()

            # Accumuler pour encaissement groupé
            if encaissement_groupe:
                montant_total += paiement.montant if paiement.montant else Decimal('0')
                if premier_point_eau is None:
                    premier_point_eau = paiement.point_eau
                    ouvrage_commun = paiement.point_eau.ouvrage if paiement.point_eau else None
                paiements_encaisses.append(paiement)

            nb_encaisses += 1

        except PaiementForfaitaire.DoesNotExist:
            erreurs.append(f"Paiement {paiement_id} introuvable")
        except Exception as e:
            erreurs.append(f"Erreur paiement {paiement_id}: {str(e)}")

    # 2. Créer ligne(s) DiameXTemporaire
    try:
        if encaissement_groupe and len(paiements_encaisses) > 0:
            # ENCAISSEMENT GROUPÉ : UNE SEULE ligne pour tous

            description = f"Paiement forfaitaire groupé - {ouvrage_commun.nom_ouvrage}"
            description += f" ({len(paiements_encaisses)} factures)"

            DiameXTemporaire.objects.create(
                paiement_forfaitaire=paiements_encaisses[0],  # Lien vers le premier
                paiements_forfaitaires_ids=[str(p.id) for p in paiements_encaisses],  # Liste complète
                type_transaction='recette',
                date_m=paiements_encaisses[0].date_paiement or datetime.now().date(),
                description=description,
                montant_in=float(montant_total),
                montant_out=0.0,
                compte_code='748411',  # Code compte vente eau forfait
                info=f'Hydria - Paiement forfaitaire groupé - {len(paiements_encaisses)} factures',
                activ=ouvrage_commun.volet if ouvrage_commun else None,
                statut='en_attente'
            )

        elif not encaissement_groupe:
            # ENCAISSEMENT INDIVIDUEL : Une ligne par paiement
            for paiement_id in paiement_ids:
                try:
                    paiement = PaiementForfaitaire.objects.get(id=paiement_id)
                    point_eau = paiement.point_eau

                    description = f"Paiement forfaitaire - {point_eau.nomabonne or point_eau.numeroabonne}"
                    if point_eau.ouvrage:
                        description += f" ({point_eau.ouvrage.nom_ouvrage})"

                    montant = float(paiement.montant) if paiement.montant else 0.0

                    DiameXTemporaire.objects.create(
                        paiement_forfaitaire=paiement,
                        type_transaction='recette',
                        date_m=paiement.date_paiement or datetime.now().date(),
                        description=description,
                        montant_in=montant,
                        montant_out=0.0,
                        compte_code='748411',
                        info='Hydria - Paiement forfaitaire',
                        activ=point_eau.ouvrage.volet if point_eau.ouvrage else None,
                        statut='en_attente'
                    )
                except Exception as e_diamex:
                    erreurs.append(f"Paiement {paiement_id} encaissé mais erreur DiameX: {str(e_diamex)}")

    except Exception as e_diamex_global:
        erreurs.append(f"Erreur lors de la création de la ligne DiameX: {str(e_diamex_global)}")

    # 3. Message de retour
    message = f'{nb_encaisses} paiement(s) encaissé(s)'
    if encaissement_groupe and nb_encaisses > 1:
        message += f' en un seul groupe (montant total: {float(montant_total):,.2f} Ar)'
    if erreurs:
        message += f' - {len(erreurs)} erreur(s)'

    return JsonResponse({
        'success': True,
        'message': message,
        'nb_encaisses': nb_encaisses,
        'erreurs': erreurs
    })
```

## Workflow DiameX complet

### 1. Encaissement (Hydria)

```python
# Action : Encaisser 3 factures groupées
paiement_ids = ['uuid1', 'uuid2', 'uuid3']

# Résultat :
# - 3 PaiementForfaitaire : paye=True, date_paiement=2025-12-27
# - 1 DiameXTemporaire créée :
DiameXTemporaire(
    paiement_forfaitaire=PaiementForfaitaire(uuid1),  # Premier
    paiements_forfaitaires_ids=['uuid1', 'uuid2', 'uuid3'],  # TOUS
    montant_in=15000.0,  # Somme des 3 factures
    description="Paiement forfaitaire groupé - AEPG Ambato (3 factures)",
    statut='en_attente'
)
```

### 2. Validation (Hydria)

L'utilisateur valide la ligne temporaire dans l'interface Hydria.

```python
# Action manuelle dans l'interface
transaction.statut = 'validee'
transaction.save()
```

### 3. Export vers DiameX (Hydria → Access)

Un script d'export récupère les lignes validées et les exporte vers DiameX (base Access).

```python
# Pseudo-code export
transactions_a_exporter = DiameXTemporaire.objects.filter(statut='validee')

for transaction in transactions_a_exporter:
    # Écriture dans Access DiameX
    access_connection.execute(
        "INSERT INTO DATA (Description, Montant_In, ...) VALUES (?, ?, ...)",
        transaction.description,
        transaction.montant_in,
        ...
    )

    transaction.statut = 'exportee'
    transaction.save()
```

### 4. DiameX génère numeroDiameX (Access)

DiameX (Access) génère un numéro unique pour chaque transaction.

```sql
-- Dans DiameX (Access)
UPDATE DATA SET NumeroPiece = 'D2025120001' WHERE ID = 123;
```

### 5. Import du numeroDiameX (Access → Hydria)

**⚠️ CRITICAL** : Le script d'import doit utiliser `paiements_forfaitaires_ids` pour mettre à jour TOUS les paiements.

```python
# Pseudo-code import numeroDiameX
transactions_exportees = DiameXTemporaire.objects.filter(statut='exportee')

for transaction in transactions_exportees:
    # Récupérer le numeroDiameX depuis Access
    numero_diamex = access_connection.query(
        "SELECT NumeroPiece FROM DATA WHERE Description = ?",
        transaction.description
    )[0]

    # CRITICAL : Mettre à jour TOUS les paiements du groupe
    if transaction.paiements_forfaitaires_ids:
        # ENCAISSEMENT GROUPÉ : Mise à jour de tous les paiements
        PaiementForfaitaire.objects.filter(
            id__in=transaction.paiements_forfaitaires_ids
        ).update(
            numeroDiameX=numero_diamex,
            baseDiameX=transaction.base_diamex
        )
    else:
        # ENCAISSEMENT INDIVIDUEL : Mise à jour du paiement lié
        if transaction.paiement_forfaitaire:
            transaction.paiement_forfaitaire.numeroDiameX = numero_diamex
            transaction.paiement_forfaitaire.baseDiameX = transaction.base_diamex
            transaction.paiement_forfaitaire.save()

    transaction.statut = 'termine'
    transaction.save()
```

**Résultat** : Les 3 paiements ont maintenant le même `numeroDiameX='D2025120001'`.

## Points critiques

### 1. Champ `paiements_forfaitaires_ids`

**Rôle** : Stocker la liste complète des UUIDs des paiements groupés.

**Format** : JSONField contenant une liste de strings
```python
paiements_forfaitaires_ids = ['uuid1', 'uuid2', 'uuid3']
```

**Utilisation** :
- Création : Rempli lors de l'encaissement groupé
- Export : Utilisé pour mettre à jour TOUS les paiements avec le même numeroDiameX
- Traçabilité : Permet de retrouver tous les paiements d'une transaction groupée

### 2. Validation ouvrage unique

**Pourquoi** : Une transaction DiameX correspond à un seul ouvrage (volet).

**Implémentation** :
```javascript
function checkOuvrageUnique() {
    if (selectedPaiements.length === 0) return true;

    const premierOuvrage = selectedPaiements[0].ouvrage_id;
    const tousMemOuvrage = selectedPaiements.every(p => p.ouvrage_id === premierOuvrage);

    if (!tousMemOuvrage) {
        alert("⚠️ Attention : Toutes les factures doivent provenir du même ouvrage.");
        return false;
    }

    return true;
}
```

### 3. Gestion des erreurs

Le système gère les erreurs à plusieurs niveaux :

1. **Validation côté client** : Avant l'envoi de la requête
   - Aucune facture sélectionnée
   - Factures de différents ouvrages

2. **Validation côté serveur** : Dans l'API
   - Liste vide de paiement_ids
   - Paiements introuvables
   - Erreurs lors de la création DiameX

3. **Retour détaillé** :
   ```json
   {
       "success": true,
       "message": "3 paiement(s) encaissé(s)",
       "nb_encaisses": 3,
       "erreurs": [
           "Paiement uuid4 introuvable",
           "Erreur DiameX pour uuid5: ..."
       ]
   }
   ```

## Exemples d'utilisation

### Exemple 1 : Encaissement groupé de 5 factures

**Contexte** :
- Organisation : SOAKOJA
- Ouvrage : AEPG Ambato
- 5 factures non payées de 5,000 Ar chacune

**Actions** :
1. Accéder à : Facturation > Suivi > Encaissement Groupé
2. Filtrer par Organisation "SOAKOJA" et Ouvrage "AEPG Ambato"
3. Cliquer "Tout sélectionner" → 5 factures cochées
4. Vérifier compteurs : "5 facture(s) sélectionnée(s)" + "25,000 Ar"
5. Cliquer "Encaisser la sélection"
6. Confirmer : "Oui" dans la popup

**Résultat** :
- 5 PaiementForfaitaire : `paye=True`, `date_paiement=2025-12-27`
- 1 DiameXTemporaire :
  ```python
  {
      'description': 'Paiement forfaitaire groupé - AEPG Ambato (5 factures)',
      'montant_in': 25000.0,
      'paiements_forfaitaires_ids': ['uuid1', 'uuid2', 'uuid3', 'uuid4', 'uuid5'],
      'statut': 'en_attente'
  }
  ```

### Exemple 2 : Erreur - Factures de différents ouvrages

**Contexte** :
- Sélectionner 2 factures de "AEPG Ambato"
- Sélectionner 1 facture de "AEPG Ankazomanga"

**Actions** :
1. Sélectionner les 3 factures
2. Le système détecte automatiquement les différents ouvrages
3. Bouton "Encaisser" désactivé
4. Alert : "⚠️ Attention : Vous avez sélectionné des factures de différents ouvrages."

**Résultat** : Encaissement bloqué, l'utilisateur doit désélectionner les factures d'un des ouvrages.

## Migration de données

### Migration 0021 : Ajout `paiements_forfaitaires_ids`

**Fichier** : `apps/accounting/migrations/0021_add_paiements_forfaitaires_ids_to_diamex.py`

```python
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('accounting', '0020_previous_migration'),
    ]

    operations = [
        migrations.AddField(
            model_name='diamextemporaire',
            name='paiements_forfaitaires_ids',
            field=models.JSONField(
                blank=True,
                help_text='Pour encaissement groupé : liste des UUIDs des paiements inclus dans cette transaction',
                null=True,
                verbose_name='IDs des paiements forfaitaires groupés'
            ),
        ),
    ]
```

**Application** :
```bash
python manage.py migrate accounting
```

## Tests recommandés

### Test 1 : Encaissement groupé basique
1. Créer 3 paiements forfaitaires pour le même ouvrage
2. Aller dans Encaissement Groupé
3. Filtrer par l'ouvrage
4. Sélectionner les 3 factures
5. Encaisser
6. Vérifier :
   - 3 PaiementForfaitaire : `paye=True`
   - 1 DiameXTemporaire créée
   - `paiements_forfaitaires_ids` contient les 3 UUIDs

### Test 2 : Validation ouvrage unique
1. Créer 2 paiements pour ouvrage A
2. Créer 1 paiement pour ouvrage B
3. Aller dans Encaissement Groupé
4. Sélectionner les 3 factures
5. Vérifier :
   - Alert affiché
   - Bouton "Encaisser" désactivé

### Test 3 : Filtres
1. Créer paiements pour plusieurs organisations/ouvrages
2. Tester filtre par organisation
3. Tester filtre par ouvrage
4. Tester recherche par nom de point d'eau

### Test 4 : Propagation numeroDiameX
1. Créer encaissement groupé de 3 factures
2. Simuler export DiameX et retour de numeroDiameX
3. Vérifier que les 3 PaiementForfaitaire ont le même numeroDiameX

## FAQ

**Q : Peut-on grouper des factures de différents ouvrages ?**
R : Non, le système bloque cela car une transaction DiameX correspond à un seul ouvrage (volet).

**Q : Que se passe-t-il si une facture échoue lors de l'encaissement ?**
R : Les autres factures sont quand même encaissées. L'erreur est retournée dans le champ `erreurs[]` de la réponse API.

**Q : Peut-on annuler un encaissement groupé ?**
R : Oui, mais il faut annuler chaque paiement individuellement (marquer `paye=False`) et supprimer la ligne DiameXTemporaire correspondante.

**Q : Comment retrouver tous les paiements d'une transaction groupée ?**
R : Via le champ `paiements_forfaitaires_ids` de DiameXTemporaire :
```python
transaction = DiameXTemporaire.objects.get(id=xxx)
paiements = PaiementForfaitaire.objects.filter(
    id__in=transaction.paiements_forfaitaires_ids
)
```

**Q : Pourquoi y a-t-il à la fois `paiement_forfaitaire` (FK) et `paiements_forfaitaires_ids` (JSON) ?**
R :
- `paiement_forfaitaire` : Lien vers le premier paiement, pour traçabilité et compatibilité avec encaissement individuel
- `paiements_forfaitaires_ids` : Liste complète pour la propagation du numeroDiameX sur TOUS les paiements groupés

## Maintenance

### Requêtes utiles

**Trouver toutes les transactions groupées** :
```python
transactions_groupees = DiameXTemporaire.objects.filter(
    paiements_forfaitaires_ids__isnull=False
)
```

**Statistiques d'encaissement** :
```python
from django.db.models import Count, Sum
stats = DiameXTemporaire.objects.filter(
    type_transaction='recette',
    paiements_forfaitaires_ids__isnull=False
).aggregate(
    nb_transactions=Count('id'),
    montant_total=Sum('montant_in')
)
```

**Vérifier cohérence** (tous les paiements du groupe sont payés) :
```python
for transaction in DiameXTemporaire.objects.filter(paiements_forfaitaires_ids__isnull=False):
    paiements = PaiementForfaitaire.objects.filter(
        id__in=transaction.paiements_forfaitaires_ids
    )
    non_payes = paiements.filter(paye=False)
    if non_payes.exists():
        print(f"⚠️ Transaction {transaction.id} : {non_payes.count()} paiements non marqués comme payés")
```

## Conclusion

Le système d'encaissement groupé optimise le workflow comptable en :
1. Réduisant le nombre de lignes DiameX (1 ligne au lieu de N)
2. Maintenant la traçabilité complète (via `paiements_forfaitaires_ids`)
3. Garantissant la cohérence (propagation du numeroDiameX sur TOUS les paiements)
4. Offrant une interface utilisateur intuitive avec validation automatique
