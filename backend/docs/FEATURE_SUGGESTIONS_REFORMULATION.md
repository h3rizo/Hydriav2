# Système de suggestions de reformulation - Documentation

## Vue d'ensemble

Le système de suggestions de reformulation aide les utilisateurs à formater correctement les descriptions DiameX pour qu'elles soient compatibles avec l'algorithme d'extraction automatique.

## Date d'implémentation

**17 décembre 2025**

## Fichiers modifiés/créés

### 1. `apps/accounting/extracteurs_description.py` (lignes 1465-1568)

**Fonction ajoutée** : `generer_suggestions_reformulation(description)`

**Objectif** : Analyser une description et proposer 1 à 3 formats compatibles avec l'algorithme.

**Logique** :
- Détecte les mots-clés présents dans la description (rbf, bf, pmh, savon, nettoyage, indemnité, etc.)
- Détecte la présence de chiffres (potentiellement IDXLS)
- Détecte les formats spécifiques (U, pour gestion, etc.)
- Génère des suggestions pertinentes ordonnées par spécificité
- Limite le résultat à 3 suggestions maximum

**Exemples de détection** :

| Description | Suggestions générées |
|-------------|---------------------|
| `Indemnité RBF_U_5_20000_Ambinanisalohy` | Format: `Indemnité RBF_U_[numéro]_[montant]_[Ouvrage]`<br>Exemple: `Indemnité RBF_U_5_20000_Ambinanisalohy` |
| `_VELONDIZY_Indemnité de Savon BF1_Fft_20000_pour gestion Ambalatenina Nord` | Format: `Indemnité de Savon BF[num]_[code]_[montant]_pour gestion [Ouvrage]`<br>Exemple: `Indemnité de Savon BF1_Fft_20000_pour gestion Ambalatenina Nord` |
| `_TOMILAHY_Nettoyage BF_Ambalafary Mahambo` | Format: `Nettoyage BF_[Ouvrage]`<br>Exemple: `Nettoyage BF_Ambalafary Mahambo` |
| `Indemnité RBF1_Ambalahady` | Format: `Indemnité RBF[numéro]_[Ouvrage]`<br>Exemple: `Indemnité RBF1_Ambalahady` |
| `Indemnité savon_Ambinanisakoana` | Format: `Indemnité savon_[Ouvrage]`<br>Exemple: `Indemnité savon_Ambinanisakoana` |

### 2. `apps/accounting/views.py` (lignes 2042-2044)

**Modification** : Appel de `generer_suggestions_reformulation()` lors de l'enrichissement des entrées.

**Code ajouté** :
```python
# Générer des suggestions de reformulation pour la description
from apps.accounting.extracteurs_description import generer_suggestions_reformulation
suggestions = generer_suggestions_reformulation(entry.description)

entries_enriched.append({
    'entry': entry,
    'has_scan': has_scan,
    'full_scan_path': full_scan_path,
    'scan_status': scan_status,
    'base_info': bases_dict.get(entry.prog),
    'suggestions': suggestions,  # ← Ajouté
})
```

**Impact** : Chaque entrée de la liste enrichie contient maintenant une clé `suggestions` avec une liste de 0 à 3 suggestions.

### 3. `templates/accounting/verification_comptabilite.html` (lignes 219-236)

**Modification** : Affichage des suggestions sous la description dans un élément `<details>` collapsible.

**Structure HTML** :
```html
<td class="max-w-xs text-xs">
    <!-- Description tronquée avec tooltip -->
    <div class="truncate" title="{{ entry.description }}">
        {{ entry.description|default:"-" }}
    </div>

    <!-- Suggestions (si disponibles) -->
    {% if item.suggestions %}
        <details class="mt-1">
            <summary class="cursor-pointer text-info text-xs hover:underline">
                💡 {{ item.suggestions|length }} suggestion(s) de format
            </summary>
            <div class="mt-2 p-2 bg-info/10 rounded text-xs space-y-1">
                {% for suggestion in item.suggestions %}
                    <div class="border-l-2 border-info pl-2">
                        <div class="font-semibold text-info-content">
                            Format: {{ suggestion.format }}
                        </div>
                        <div class="text-gray-600 italic">
                            Exemple: {{ suggestion.exemple }}
                        </div>
                    </div>
                {% endfor %}
            </div>
        </details>
    {% endif %}
</td>
```

**Design** :
- **Collapsible** : Les suggestions sont masquées par défaut, clic sur le résumé pour les afficher
- **Badge info** : Icône 💡 + nombre de suggestions en bleu
- **Zone de fond** : Fond bleu clair (`bg-info/10`) avec bordures arrondies
- **Bordure gauche** : Chaque suggestion a une bordure bleue à gauche pour la séparation visuelle
- **Format en gras** : Le format proposé est en caractères gras
- **Exemple en italique** : L'exemple est en italique et gris

## Utilisation

### Côté utilisateur

1. **Accéder à la page de vérification comptabilité** :
   - URL : `/comptabilite/verification/`
   - Menu : Comptabilité → Vérification comptabilité

2. **Consulter les suggestions** :
   - Pour chaque ligne, si des suggestions sont disponibles, un lien "💡 X suggestion(s) de format" apparaît sous la description
   - Clic sur le lien pour dérouler les suggestions
   - Chaque suggestion montre :
     - **Format** : Structure générale avec placeholders entre crochets
     - **Exemple** : Exemple concret de description formatée correctement

3. **Appliquer les suggestions** :
   - Copier le format proposé
   - Modifier la description dans DiameX ou Access selon le format
   - Réimporter les données

### Côté développeur

**Ajouter de nouveaux formats** :

Modifier la fonction `generer_suggestions_reformulation()` dans `extracteurs_description.py` :

```python
# Exemple : Ajouter support pour format "Collecte"
if 'collecte' in desc_lower:
    if has_digits:
        suggestions.append({
            'format': 'Collecte [Type][num]_[Ouvrage]',
            'exemple': 'Collecte RBF1_NomOuvrage'
        })
    else:
        suggestions.append({
            'format': 'Collecte [Type]_[Ouvrage]',
            'exemple': 'Collecte RBF_NomOuvrage'
        })
```

**Tester les suggestions** :

```bash
cd backend
python manage.py shell -c "
from apps.accounting.extracteurs_description import generer_suggestions_reformulation
suggestions = generer_suggestions_reformulation('Votre description ici')
for s in suggestions:
    print(f'Format: {s[\"format\"]}')
    print(f'Exemple: {s[\"exemple\"]}')
"
```

## Formats actuellement détectés

### RBF (Robinet à Borne Fontaine)
- `Indemnité RBF_U_[num]_[montant]_[Ouvrage]` (avec U et numéro)
- `Indemnité RBF[num]_[Ouvrage]` (simple avec numéro)
- `Indemnité RBF_[Ouvrage]` (sans numéro)

### BF (Borne Fontaine) - Savon
- `Indemnité de Savon BF[num]_[code]_[montant]_pour gestion [Ouvrage]` (avec "pour gestion")
- `Indemnité savon_U_[num]_[Ouvrage]` (avec U)
- `Indemnité de savon BF[num]_[montant]_[Ouvrage]` (simple avec montant)
- `Indemnité savon_[Ouvrage]` (très simple)

### BF - Nettoyage
- `Nettoyage BF_[Ouvrage]`

### PMH (Pompe à Motricité Humaine)
- `Indemnité PMH[num]_[Ouvrage]` (avec numéro)
- `Indemnité PMH_[Ouvrage]` (sans numéro)

### Générique
- `Indemnité [Type][num]_[Ouvrage]` (quand le type n'est pas reconnu)

## Logique de priorité

Les suggestions sont générées dans l'ordre suivant :

1. **RBF spécifique** : RBF_U avec chiffres → RBF avec chiffres → RBF sans chiffres
2. **BF savon spécifique** : Avec "pour gestion" → savon_U → savon avec BF et chiffres → savon simple
3. **Nettoyage BF** : Si "nettoyage" + "bf"
4. **PMH** : Avec ou sans numéro
5. **Générique** : Format par défaut si "indemnité" détecté

## Performance

- **Temps d'exécution** : < 1ms par description
- **Impact page** : Négligeable (calcul côté serveur avant rendu)
- **Pagination** : Suggestions calculées uniquement pour les 50 entrées affichées (pagination 50 par page)

## Compatibilité

- **Django** : 5.2.6+
- **Python** : 3.13+
- **Tailwind CSS / DaisyUI** : Classes utilisées (`text-info`, `bg-info/10`, etc.)
- **Navigateurs** : Support natif `<details>` (tous navigateurs modernes)

## Tests

**Résultats des tests (17 décembre 2025)** :

| Description testée | Nombre suggestions | Format principal |
|-------------------|-------------------|------------------|
| `Indemnité RBF_U_5_20000_Ambinanisalohy` | 1 | `Indemnité RBF_U_[numéro]_[montant]_[Ouvrage]` ✅ |
| `_VELONDIZY Florine_Indemnité de Savon BF1_Fft_20000_pour gestion Ambalatenina Nord` | 1 | `Indemnité de Savon BF[num]_[code]_[montant]_pour gestion [Ouvrage]` ✅ |
| `_TOMILAHY_Nettoyage BF_Ambalafary Mahambo` | 1 | `Nettoyage BF_[Ouvrage]` ✅ |

**Tous les tests passent correctement.**

## Prochaines améliorations possibles

1. **Machine Learning** : Utiliser les patterns réussis pour apprendre de nouvelles structures
2. **Historique** : Proposer les formats qui ont déjà fonctionné pour cet utilisateur
3. **Édition inline** : Permettre de modifier la description directement depuis la page
4. **Prévisualisation** : Afficher le résultat de l'extraction en temps réel
5. **Statistiques** : Tracker quels formats sont les plus utilisés
6. **Export** : Générer un guide PDF avec tous les formats supportés

## Support

En cas de problème avec les suggestions :
1. Vérifier que la fonction `generer_suggestions_reformulation()` est bien importée dans `views.py`
2. Vérifier que les suggestions sont bien passées au template (`'suggestions': suggestions` dans `entries_enriched`)
3. Vérifier que le template utilise `item.suggestions` et non `entry.suggestions`
4. Consulter les logs Django pour les erreurs d'exécution

## Notes de version

**v1.0 (17 décembre 2025)** :
- Implémentation initiale
- Support RBF, BF, PMH, Nettoyage
- Interface collapsible avec DaisyUI
- Maximum 3 suggestions par description
- Détection basée sur mots-clés et patterns regex
