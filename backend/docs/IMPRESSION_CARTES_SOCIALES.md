# Vue Impression - Paiements Cartes Sociales

## Date : 16 décembre 2025

## Modifications apportées

### Objectif
Modifier la vue d'impression pour afficher **carte par carte** au lieu de point d'eau par point d'eau, tout en conservant le regroupement par point d'eau, et supprimer toutes les colonnes liées aux montants.

### Changements Backend

**Fichier** : `backend/apps/planning/views_conso_cartes_sociales.py`

**Fonction** : `impression_conso_cartes_sociales()` (lignes 575-767)

#### Structure de données modifiée

**AVANT** : `commune → ouvrage → point d'eau → mois`
```python
data_par_commune[commune_nom]['ouvrages'][ouvrage_nom]['points_eau'][point_eau_nom] = {
    'point_eau': pe,
    'mois': {1: {'payes': 0, 'non_payes': 0}, ...},
    'total_payes': 0,
    'total_non_payes': 0,
    'montant_total': Decimal('0')  # ❌ SUPPRIMÉ
}
```

**APRÈS** : `commune → ouvrage → point d'eau → carte → mois`
```python
data_par_commune[commune_nom]['ouvrages'][ouvrage_nom]['points_eau'][point_eau_nom]['cartes'][carte_numero] = {
    'carte': carte,
    'numero': carte_numero,
    'beneficiaire': carte.nom_beneficiaire,
    'habitants': carte.nombre_habitants or 0,
    'mois': {1: {'paye': False}, 2: {'paye': False}, ...},
    'total_payes': 0,
    'total_non_payes': 0
}
```

#### Logique de traitement

1. **Récupération des points d'eau avec cartes actives** :
```python
points_eau_avec_cartes = PointEau.objects.filter(
    ouvrage_id__in=modalites_ids,
    cartes_sociales__statut='active'
).distinct()
```

2. **Pour chaque point d'eau, récupérer les cartes actives** :
```python
cartes_actives = pe.cartes_sociales.filter(statut='active')
for carte in cartes_actives:
    carte_numero = carte.numero_carte or f"CS-{str(carte.id)[:8]}"
```

3. **Pour chaque carte, tracker les paiements mensuels** :
```python
for releve in releves_filtres:
    if releve.point_eau_id != pe.id:
        continue
    # Conversion timezone pour obtenir le mois
    date_madagascar = date_aware.astimezone(tz_madagascar)
    mois = date_madagascar.month

    # Vérifier si payé
    est_paye = releve.numeroDiameX is not None and releve.numeroDiameX.strip() != ''
    carte_data['mois'][mois] = {'paye': est_paye}
```

4. **Compter les totaux par carte** :
```python
carte_data['total_payes'] = sum(1 for m in carte_data['mois'].values() if m['paye'])
carte_data['total_non_payes'] = 12 - carte_data['total_payes']
```

5. **Agréger vers les niveaux supérieurs** :
- Point d'eau : Somme des cartes de ce point d'eau
- Ouvrage : Somme des points d'eau de cet ouvrage
- Commune : Somme des ouvrages de cette commune
- **Total général** : Somme de toutes les communes

#### Suppressions

- ❌ **Tous les `montant_total`** supprimés de la structure de données
- ❌ **Calculs de montant** supprimés
- ❌ **Contexte `montant_total`** supprimé (non passé au template)

### Changements Template

**Fichier** : `backend/templates/planning/conso_cartes_sociales_impression.html`

#### 1. Statistiques globales (lignes 220-233)

**AVANT** :
```html
<div class="stat-item">
    <div class="label">Montant Total</div>
    <div class="value">{{ montant_total|floatformat:0 }} Ar</div>
</div>
```

**APRÈS** : Supprimé, seulement 3 stats :
- Factures Payées
- Factures Non Payées
- Communes

#### 2. En-tête commune (lignes 239-245)

**AVANT** :
```html
Montant: <span class="montant">{{ commune_data.montant_total|floatformat:0 }} Ar</span>
```

**APRÈS** : Supprimé

#### 3. En-tête ouvrage (lignes 251-256)

**Montant supprimé** également.

#### 4. Nouvelle en-tête point d'eau (lignes 261-267)

**AJOUTÉ** :
```html
<tr class="point-eau-header">
    <td colspan="17">
        Point d'Eau: {{ point_eau_nom }} -
        Payés: <span class="paye">{{ pe_data.total_payes }}</span> /
        Non payés: <span class="non-paye">{{ pe_data.total_non_payes }}</span>
    </td>
</tr>
```

Style CSS :
```css
.point-eau-header {
    background: #f0f9ff !important;
    font-weight: bold;
    color: #0284c7;
    padding: 6px 8px !important;
    font-size: 8.5pt;
}
```

#### 5. En-têtes de colonnes (lignes 270-282)

**AVANT** : Point d'Eau + 12 mois (Payés/Non payés) + Totaux

**APRÈS** : Numéro Carte + Bénéficiaire + Habitants + 12 mois + Totaux
```html
<tr>
    <th rowspan="2" style="width: 120px;">Numéro Carte</th>
    <th rowspan="2" style="width: 150px;">Bénéficiaire</th>
    <th rowspan="2" style="width: 60px;" class="text-center">Habitants</th>
    <th colspan="12" class="text-center">Paiements par Mois</th>
    <th rowspan="2" class="text-center" style="width: 70px;">Total Payés</th>
    <th rowspan="2" class="text-center" style="width: 70px;">Total Non Payés</th>
</tr>
<tr>
    {% for mois in mois_labels %}
        <th class="month-header">{{ mois }}</th>
    {% endfor %}
</tr>
```

#### 6. Lignes de données (lignes 285-380)

**AVANT** : Boucle sur les points d'eau
```html
{% for point_eau_nom, pe_data in ouvrage_data.points_eau.items %}
<tr>
    <td>{{ point_eau_nom }}</td>
    <!-- Mois avec Payés/Non payés -->
</tr>
{% endfor %}
```

**APRÈS** : Double boucle - points d'eau puis cartes
```html
{% for point_eau_nom, pe_data in ouvrage_data.points_eau.items %}
    <!-- En-tête point d'eau -->
    <tr class="point-eau-header">...</tr>

    <!-- En-têtes colonnes -->
    <tr>...</tr>

    <!-- Boucle sur les cartes -->
    {% for carte_numero, carte_data in pe_data.cartes.items %}
    <tr class="carte-row">
        <td>{{ carte_numero }}</td>
        <td>{{ carte_data.beneficiaire|default:"—" }}</td>
        <td class="text-center">{{ carte_data.habitants|default:0 }}</td>

        <!-- 12 colonnes mensuelles avec icônes -->
        <td class="month-cell">
            {% if carte_data.mois.1.paye %}
                <span class="paye">✓</span>
            {% else %}
                <span class="non-paye">✗</span>
            {% endif %}
        </td>
        <!-- ... répéter pour mois 2 à 12 ... -->

        <td class="paye text-center">{{ carte_data.total_payes }}</td>
        <td class="non-paye text-center">{{ carte_data.total_non_payes }}</td>
    </tr>
    {% endfor %}

    <!-- Sous-total point d'eau -->
    <tr style="background: #dbeafe; font-weight: bold;">
        <td colspan="15" class="text-right">Sous-total {{ point_eau_nom }}</td>
        <td class="paye text-center">{{ pe_data.total_payes }}</td>
        <td class="non-paye text-center">{{ pe_data.total_non_payes }}</td>
    </tr>
{% endfor %}
```

#### 7. Affichage mensuel

**AVANT** : Format `X / Y` (payés / non payés)
```html
<span class="paye">{{ mois_data.1.payes|default:0 }}</span> /
<span class="non-paye">{{ mois_data.1.non_payes|default:0 }}</span>
```

**APRÈS** : Icône simple ✓ ou ✗
```html
{% if carte_data.mois.1.paye %}
    <span class="paye">✓</span>
{% else %}
    <span class="non-paye">✗</span>
{% endif %}
```

#### 8. Sous-totaux et totaux

**Modification des colspan** pour correspondre aux nouvelles colonnes :
- `colspan="17"` pour les en-têtes (commune, ouvrage, point d'eau)
- `colspan="15"` pour les sous-totaux (avant les 2 colonnes de totaux)

### Nouveaux styles CSS

```css
.point-eau-header {
    background: #f0f9ff !important;
    font-weight: bold;
    color: #0284c7;
    padding: 6px 8px !important;
    font-size: 8.5pt;
}

.carte-row {
    font-size: 8.5pt;
}
```

## Structure finale du tableau

```
COMMUNE: AMBANJA - Payés: 120 / Non payés: 30

  Ouvrage: Ambanja BP - Payés: 80 / Non payés: 20

    Point d'Eau: PE Ambanja BP - Payés: 80 / Non payés: 20

    ┌──────────────┬─────────────┬──────────┬─────────────────────────┬────────┬────────┐
    │ Numéro Carte │ Bénéficiaire│ Habitants│ Jan Fév Mar ... Déc     │ Payés  │ Non P. │
    ├──────────────┼─────────────┼──────────┼─────────────────────────┼────────┼────────┤
    │ CS-0001      │ RAKOTO Jean │ 5        │ ✓   ✓   ✓  ... ✗       │ 10     │ 2      │
    │ CS-0002      │ RABE Marie  │ 4        │ ✗   ✓   ✓  ... ✓       │ 8      │ 4      │
    │ CS-0003      │ RASOA Paul  │ 6        │ ✓   ✓   ✓  ... ✓       │ 12     │ 0      │
    ├──────────────┴─────────────┴──────────┴─────────────────────────┼────────┼────────┤
    │ Sous-total PE Ambanja BP                                         │ 30     │ 6      │
    └──────────────────────────────────────────────────────────────────┴────────┴────────┘

    Sous-total Ambanja BP                                              80       20

TOTAL COMMUNE AMBANJA                                                  120      30

TOTAL GÉNÉRAL                                                          120      30
```

## Informations affichées

### Par carte sociale
- **Numéro de carte** : `carte.numero_carte` ou ID généré
- **Bénéficiaire** : `carte.nom_beneficiaire` (ou "—" si vide)
- **Habitants** : `carte.nombre_habitants` (ou 0 si NULL)
- **12 colonnes mensuelles** : ✓ (payé) ou ✗ (non payé)
- **Total Payés** : Nombre de mois payés sur 12
- **Total Non Payés** : 12 - Total Payés

### Agrégations
- **Sous-total Point d'Eau** : Somme des totaux de toutes les cartes du PE
- **Sous-total Ouvrage** : Somme des totaux de tous les PE de l'ouvrage
- **Total Commune** : Somme des totaux de tous les ouvrages de la commune
- **Total Général** : Somme des totaux de toutes les communes

## Validation

✅ Django check : Aucune erreur
✅ Structure de données correcte
✅ Pas de colonnes au-delà des totaux
✅ Montants totalement supprimés
✅ Affichage carte par carte avec regroupement par PE
✅ Hiérarchie complète maintenue

## Accès

**URL** : `/plannings/conso-cartes-sociales/impression/?annee=2025`

**Navigation** : Depuis la vue globale → Bouton "Imprimer" dans l'en-tête

## Format d'impression

- **Orientation** : Paysage (landscape)
- **Marges** : 1cm
- **Taille police** : 9pt (corps), 8pt (en-têtes)
- **Couleurs préservées** : Oui (`print-color-adjust: exact`)
- **Saut de page** : Entre chaque commune
