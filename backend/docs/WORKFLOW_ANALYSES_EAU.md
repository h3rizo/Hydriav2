# 💧 MODULE ANALYSES D'EAU - WORKFLOW COMPLET

**Date de création** : 23 décembre 2025

## Vue d'ensemble

Module complet pour gérer les analyses de qualité de l'eau (coliformes fécaux, pH) avec import/export Excel et tableau de bord avec filtres.

## Fonctionnalités implémentées

1. ✅ **Modèle AnalyseEau** - Table complète avec tous les champs requis
2. ✅ **CRUD complet** - Création, lecture, modification, suppression via APIs REST
3. ✅ **Import Excel** - Validation des données avec gestion d'erreurs détaillée
4. ✅ **Export Excel** - Fichier avec styles et filtres appliqués
5. ✅ **Template Excel** - Fichier pré-formaté pour faciliter l'import
6. ✅ **Tableau de bord** - Vue synthétique avec filtres avancés
7. ✅ **URLs configurées** - Routes API et pages accessibles

## Architecture

### Modèle : AnalyseEau

**Fichier** : `apps/inspections/models_analyse_eau.py`

**Champs principaux** :
- `type_prelevement` : equipement, point_eau, point_eau_traditionnel, bouteille, autre
- `equipement` : FK optionnelle vers EquipementConstitutif
- `point_eau` : FK optionnelle vers PointEau
- `description_lieu` : Texte libre pour autres types
- `date_prelevement`, `date_analyse`, `date_resultat` : DateTimeField
- `volume_analyse` : 10, 20, 25, 50, 60 ou 100 mL
- `nombre_coliformes` : Entier (null si TNC)
- `tnc` : Boolean (Trop Nombreux pour être Compté)
- `ph` : Decimal 0-14
- `observation` : TextField

**Propriétés calculées** :
- `nombre_pour_100ml` : `(100 * nombre_coliformes) / volume_analyse`
- `est_positif` : `tnc == True OR nombre_coliformes > 0`
- `lieu_affichage` : Retourne le nom du lieu de prélèvement
- `commune_nom`, `village_nom` : Remontent la chaîne géographique

### Vues et APIs

**Fichier principal** : `apps/inspections/views_analyse_eau.py`

**Pages** :
- `analyses_eau_list(request)` : Page de gestion des analyses
- `analyses_eau_dashboard(request)` : Tableau de bord avec filtres

**APIs REST** :
- `GET /inspections/analyses-eau/api/list/` : Liste avec filtres
- `POST /inspections/analyses-eau/api/create/` : Créer nouvelle analyse
- `GET /inspections/analyses-eau/api/<uuid>/` : Détails d'une analyse
- `POST /inspections/analyses-eau/api/<uuid>/update/` : Modifier
- `POST /inspections/analyses-eau/api/<uuid>/delete/` : Supprimer
- `GET /inspections/analyses-eau/api/dashboard/` : Données pour dashboard

**Fichier Excel** : `apps/inspections/views_analyse_eau_excel.py`

- `GET /inspections/analyses-eau/export/` : Export Excel avec filtres
- `GET /inspections/analyses-eau/template-import/` : Télécharger template
- `POST /inspections/analyses-eau/import/` : Import depuis Excel

### Structure de la base de données

**Table** : `analyses_eau`

```sql
CREATE TABLE analyses_eau (
    id UUID PRIMARY KEY,
    type_prelevement VARCHAR(50),  -- equipement, point_eau, point_eau_traditionnel, bouteille, autre
    equipement_id UUID REFERENCES equipements_constitutifs(id),  -- Nullable
    point_eau_id UUID REFERENCES points_eau(id),  -- Nullable
    description_lieu VARCHAR(500),
    date_prelevement TIMESTAMP WITH TIME ZONE,
    date_analyse TIMESTAMP WITH TIME ZONE,
    date_resultat TIMESTAMP WITH TIME ZONE,
    volume_analyse INTEGER,  -- 10, 20, 25, 50, 60, 100 mL
    nombre_coliformes INTEGER,  -- Nullable si TNC
    tnc BOOLEAN DEFAULT FALSE,
    ph DECIMAL(3,1),  -- 0.0 à 14.0
    observation TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    created_by_id INTEGER REFERENCES auth_user(id)
);

CREATE INDEX idx_analyses_eau_type ON analyses_eau(type_prelevement);
CREATE INDEX idx_analyses_eau_date_prel ON analyses_eau(date_prelevement);
CREATE INDEX idx_analyses_eau_date_analyse ON analyses_eau(date_analyse);
```

## Workflow utilisateur

### 1. Créer une nouvelle analyse

**Via interface** :
1. Accéder à **Inspections > Analyses d'eau**
2. Clic "Nouvelle Analyse"
3. Remplir formulaire :
   - Type de prélèvement* (dropdown)
   - Si "Équipement" : Sélectionner équipement
   - Si "Point d'eau" : Sélectionner point d'eau
   - Si "Autre" : Saisir description
   - Date et heure de prélèvement*
   - Date et heure d'analyse*
   - Date et heure du résultat*
   - Volume analysé (mL)* (dropdown)
   - Nombre de coliformes comptés (si pas TNC)
   - Checkbox TNC
   - pH (optionnel)
   - Observation (texte libre)
4. Enregistrer → Analyse créée

**Via API** :
```javascript
fetch('/inspections/analyses-eau/api/create/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify({
        type_prelevement: 'point_eau',
        point_eau_id: 'uuid-du-point-eau',
        date_prelevement: '2025-12-23T10:30',
        date_analyse: '2025-12-23T14:00',
        date_resultat: '2025-12-24T09:00',
        volume_analyse: 100,
        nombre_coliformes: 5,
        tnc: false,
        ph: '7.2',
        observation: 'Eau claire'
    })
})
```

### 2. Import Excel

**Préparer le fichier** :
1. Télécharger template : `/inspections/analyses-eau/template-import/`
2. Remplir les colonnes (voir format ci-dessous)
3. Supprimer les lignes d'exemple (grisées)

**Format des colonnes** :

| Colonne | Obligatoire | Format | Exemple |
|---------|-------------|--------|---------|
| Type prélèvement | ✅ | equipement, point_eau, point_eau_traditionnel, bouteille, autre | equipement |
| ID Équipement | ⚠️ | UUID (si type=equipement) | uuid-equipement |
| ID Point d'eau | ⚠️ | UUID (si type=point_eau) | uuid-point-eau |
| Description lieu | | Texte libre | Puits village Ambanja |
| Date prélèvement | ✅ | DD/MM/YYYY | 15/12/2025 |
| Heure prélèvement | ✅ | HH:MM | 10:30 |
| Date analyse | ✅ | DD/MM/YYYY | 15/12/2025 |
| Heure analyse | ✅ | HH:MM | 14:00 |
| Date résultat | ✅ | DD/MM/YYYY | 16/12/2025 |
| Heure résultat | ✅ | HH:MM | 09:00 |
| Volume (mL) | ✅ | 10, 20, 25, 50, 60, 100 | 100 |
| Nb coliformes | | Entier (vide si TNC) | 5 |
| TNC | | Oui/Non | Non |
| pH | | Décimal 0-14 | 7.2 |
| Observation | | Texte libre | Eau claire |

**Importer** :
1. Accéder à **Inspections > Analyses d'eau**
2. Clic "Importer Excel"
3. Sélectionner fichier
4. Valider
5. Résultat : "X analyse(s) importée(s), Y erreur(s)"
6. Si erreurs : Liste détaillée des lignes en erreur

### 3. Export Excel

**Filtrer puis exporter** :
1. Appliquer filtres souhaités (année, commune, résultat)
2. Clic "Exporter Excel"
3. Téléchargement automatique du fichier

**Colonnes exportées** :
- Type de prélèvement
- Équipement ou Point d'eau
- Description lieu
- Commune
- Village
- Date et heure prélèvement
- Date et heure analyse
- Date et heure résultat
- Volume analysé (mL)
- Nombre de coliformes
- TNC
- Nombre pour 100mL (calculé)
- pH
- Observation

### 4. Tableau de bord

**Accès** : **Inspections > Analyses d'eau > Dashboard**

**Colonnes affichées** :
- Commune
- Village
- Lieu de prélèvement
- Date d'analyse (DD/MM/YYYY)
- Nombre pour 100 mL (ou "TNC" ou "N/A")
- Observation

**Filtres disponibles** :
- **Année** : Dropdown avec années disponibles
- **Commune** : Dropdown avec toutes les communes
- **Résultat** :
  - Tous
  - Positif (coliformes > 0 ou TNC)
  - Zéro (coliformes = 0 et pas TNC)

**Indicateurs** : Badges colorés selon résultat
- 🔴 **Positif** : Badge rouge si `est_positif == True`
- 🟢 **Conforme** : Badge vert si `nombre_pour_100ml == 0`

## Templates HTML à créer

### 1. analyses_eau_list.html

**Fichier** : `templates/inspections/analyses_eau_list.html`

**Structure** :
```html
{% extends 'base.html' %}
{% block title %}Analyses d'eau{% endblock %}

{% block content %}
<div class="container mx-auto px-4 py-6">
    <!-- Header avec boutons -->
    <div class="flex justify-between items-center mb-6">
        <h1 class="text-3xl font-bold">Analyses d'eau</h1>
        <div class="flex gap-2">
            <button onclick="openImportModal()" class="btn btn-info">
                <i class="fas fa-upload mr-2"></i>Importer Excel
            </button>
            <a href="{% url 'inspections:template_import_analyses_eau' %}" class="btn btn-secondary">
                <i class="fas fa-download mr-2"></i>Template Excel
            </a>
            <button onclick="exportExcel()" class="btn btn-success">
                <i class="fas fa-file-excel mr-2"></i>Exporter
            </button>
            <button onclick="openCreateModal()" class="btn btn-primary">
                <i class="fas fa-plus mr-2"></i>Nouvelle Analyse
            </button>
        </div>
    </div>

    <!-- Filtres -->
    <div class="card bg-base-100 shadow mb-4">
        <div class="card-body">
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div class="form-control">
                    <label class="label">Année</label>
                    <select id="filter-annee" class="select select-bordered">
                        {% for annee in annees %}
                        <option value="{{ annee }}" {% if annee == annee_actuelle %}selected{% endif %}>{{ annee }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-control">
                    <label class="label">Commune</label>
                    <select id="filter-commune" class="select select-bordered">
                        <option value="all">Toutes</option>
                        {% for commune in communes %}
                        <option value="{{ commune.id }}">{{ commune.nom_commune }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-control">
                    <label class="label">Type</label>
                    <select id="filter-type" class="select select-bordered">
                        <option value="">Tous</option>
                        <option value="equipement">Équipement</option>
                        <option value="point_eau">Point d'eau</option>
                        <option value="point_eau_traditionnel">Point d'eau traditionnel</option>
                        <option value="bouteille">Bouteille cachetée</option>
                        <option value="autre">Autre</option>
                    </select>
                </div>
                <div class="form-control">
                    <label class="label">Résultat</label>
                    <select id="filter-resultat" class="select select-bordered">
                        <option value="">Tous</option>
                        <option value="positif">Positif</option>
                        <option value="negatif">Négatif</option>
                    </select>
                </div>
            </div>
            <div class="flex gap-2 mt-4">
                <button onclick="loadAnalyses()" class="btn btn-primary">Filtrer</button>
                <button onclick="resetFilters()" class="btn btn-ghost">Réinitialiser</button>
            </div>
        </div>
    </div>

    <!-- Tableau -->
    <div class="card bg-base-100 shadow">
        <div class="card-body">
            <div class="overflow-x-auto">
                <table class="table table-zebra w-full">
                    <thead>
                        <tr>
                            <th>Type</th>
                            <th>Lieu</th>
                            <th>Commune</th>
                            <th>Village</th>
                            <th>Date prélèvement</th>
                            <th>Volume (mL)</th>
                            <th>Coliformes</th>
                            <th>100mL</th>
                            <th>pH</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="analyses-tbody">
                        <!-- Rempli via JavaScript -->
                    </tbody>
                </table>
            </div>
            <div id="no-data" class="text-center py-8 hidden">
                <p class="text-gray-500">Aucune analyse trouvée</p>
            </div>
        </div>
    </div>
</div>

<!-- Modal Création/Modification -->
<!-- Modal Import -->
{% endblock %}

{% block extra_js %}
<script>
// Fonctions JavaScript : loadAnalyses(), exportExcel(), openCreateModal(), etc.
</script>
{% endblock %}
```

### 2. analyses_eau_dashboard.html

**Structure similaire** avec focus sur le tableau de bord (voir template liste pour référence).

## Validation et gestion d'erreurs

### Import Excel

**Validations** :
1. Champs obligatoires présents
2. Format dates valide (DD/MM/YYYY)
3. Format heures valide (HH:MM)
4. Volume dans liste autorisée (10, 20, 25, 50, 60, 100)
5. Si TNC = Oui, nombre_coliformes doit être vide
6. pH entre 0 et 14
7. UUID équipement/point_eau existe en base

**Retour JSON** :
```json
{
    "success": true,
    "message": "150 analyse(s) importée(s), 3 erreur(s)",
    "nb_imported": 150,
    "nb_errors": 3,
    "errors": [
        "Ligne 12: Format de date invalide",
        "Ligne 45: Équipement uuid-xxx introuvable",
        "Ligne 78: pH invalide (doit être 0-14)"
    ]
}
```

### Création manuelle

**Validations côté serveur** :
- Type de prélèvement obligatoire
- Dates obligatoires et cohérentes
- Volume obligatoire
- Si type=equipement, equipement_id requis
- Si type=point_eau, point_eau_id requis

## Tests à effectuer

- [ ] Créer analyse via formulaire
- [ ] Créer analyse via API
- [ ] Modifier une analyse
- [ ] Supprimer une analyse
- [ ] Télécharger template Excel
- [ ] Importer fichier Excel valide
- [ ] Importer fichier avec erreurs (vérifier messages)
- [ ] Exporter avec filtres
- [ ] Filtrer par année
- [ ] Filtrer par commune
- [ ] Filtrer par résultat (positif/négatif)
- [ ] Vérifier calcul nombre_pour_100ml
- [ ] Vérifier affichage commune/village
- [ ] Dashboard avec filtres

## Prochaines améliorations possibles

1. **Graphiques** : Évolution des résultats dans le temps
2. **Alertes** : Notification si analyse positive
3. **Photos** : Upload photos des prélèvements
4. **Géolocalisation** : Coordonnées GPS des prélèvements
5. **Laboratoire** : Lien vers laboratoire d'analyse
6. **Conformité** : Seuils de conformité paramétrables
7. **Rapports PDF** : Génération de rapports d'analyse
8. **Historique** : Suivi des analyses d'un même lieu

## Accès et permissions

**URL principale** : `http://localhost:8000/inspections/analyses-eau/`

**Menu navigation** : **Inspections > Analyses d'eau**

**Permissions** : À définir selon les besoins (actuellement accessible à tous les utilisateurs authentifiés)

---

**Documentation créée le** : 23 décembre 2025
**Dernière mise à jour** : 23 décembre 2025
**Auteur** : Claude (Assistant IA)
