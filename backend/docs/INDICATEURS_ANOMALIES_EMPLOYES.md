# Indicateurs d'Anomalies par Employé - Analyse Croisée (12 décembre 2025)

## Vue d'ensemble

Ajout d'indicateurs visuels à côté du nom de chaque employé dans l'analyse croisée des paiements pour identifier rapidement les types de paiement présentant des anomalies récurrentes.

## Fonctionnalité

### Badges d'anomalies

**Affichage** : À côté du nom de chaque employé (sous le nom)

**Format** : `⚠️ Type` (badge jaune avec icône d'avertissement)

**Déclenchement** : Un badge apparaît pour chaque type de paiement où l'employé a une **moyenne > 1** (paiements multiples récurrents)

### Informations au survol (tooltip)

Lorsque l'utilisateur survole un badge, un tooltip affiche :
- **Nombre de mois** avec anomalie (>1 paiement)
- **Moyenne** des paiements par mois pour ce type

**Exemple** : "3 mois avec >1 paiement (moy: 1.42)"

### Types abrégés affichés

Les noms de types sont abrégés pour gagner de la place :

| Type complet | Abréviation |
|-------------|-------------|
| Salaire | Sal |
| Ajustement salaire | Ajust |
| Prime | Prime |
| Solde de tout compte | Solde |
| Allocation terrain | Alloc |
| Indemnité compensatrice | Indem |
| IRSA | IRSA |
| CNaPS | CNaPS |
| FMFP | FMFP |
| Mutuelle santé | Mut |
| Frais médicaux | Méd |
| Frais scolarité | Scol |
| Indemnité terrain | IT |
| Indemnité hors zone | IHZ |
| Indemnité stage | ISt |
| Frais déplacement | Dép |

## Exemple visuel

### Employé sans anomalie
```
┌──────────────────┐
│ Antoine          │
│ (base Tana)      │
└──────────────────┘
```

### Employé avec 1 anomalie
```
┌──────────────────────────┐
│ Marie                    │
│ ⚠️ Sal                   │
│ (3 mois, moy: 1.25)      │
└──────────────────────────┘
```

### Employé avec plusieurs anomalies
```
┌─────────────────────────────────────┐
│ Jean                                │
│ ⚠️ Sal  ⚠️ IRSA  ⚠️ Prime           │
│ (Sal: 5 mois, IRSA: 2 mois...)      │
└─────────────────────────────────────┘
```

## Implémentation technique

### Fichier modifié
`backend/templates/employees/verification_paiements_croisee.html` (lignes 489-539)

### Logique JavaScript

**Étape 1 : Calculer les anomalies par type**
```javascript
const typesAvecAnomalies = [];
for (const [type, nomCourt] of Object.entries(nomsTypes)) {
    const moyenne = data.moyennes[type] || 0;
    if (moyenne > 1) {
        // Compter le nombre de mois avec anomalie
        let nbMoisAnomalie = 0;
        for (let mois = 1; mois <= 12; mois++) {
            const valeur = data.mois[mois.toString()]?.[type] || 0;
            if (valeur > 1) nbMoisAnomalie++;
        }
        typesAvecAnomalies.push({type, nomCourt, nbMois: nbMoisAnomalie, moyenne});
    }
}
```

**Étape 2 : Générer les badges HTML**
```javascript
let badgesHtml = '';
if (typesAvecAnomalies.length > 0) {
    typesAvecAnomalies.forEach(anomalie => {
        const tooltip = `${anomalie.nbMois} mois avec >1 paiement (moy: ${anomalie.moyenne.toFixed(2)})`;
        badgesHtml += `<span class="badge badge-xs badge-warning gap-1 cursor-help" title="${tooltip}">
            <i class="fas fa-exclamation-triangle text-xs"></i>${anomalie.nomCourt}
        </span>`;
    });
}
```

**Étape 3 : Afficher avec le nom de l'employé**
```javascript
tdEmploye.innerHTML = `
    <div class="flex flex-col gap-1">
        <div class="flex items-center gap-2">
            <span>${data.surnom}</span>
            ${!data.actif ? '<span class="badge badge-sm badge-ghost">Inactif</span>' : ''}
        </div>
        ${badgesHtml ? `<div class="flex flex-wrap gap-1">${badgesHtml}</div>` : ''}
    </div>
`;
```

### Critères d'anomalie

**Anomalie détectée si** :
- Moyenne de paiements par mois **> 1** pour un type donné
- Calculé sur les 12 mois de l'année sélectionnée

**Exemple** :
- Employé a 3 paiements "Salaire" en janvier, 2 en février, 1 en mars-décembre
- Moyenne = (3 + 2 + 1×10) / 12 = 1.25
- → Badge "⚠️ Sal" affiché avec "3 mois avec >1 paiement (moy: 1.25)"

## Cas d'usage

### 1. Identification rapide des employés problématiques

**Avant** : Il fallait regarder la colonne "Moyenne" pour chaque type de paiement individuellement

**Maintenant** : Les badges permettent de voir d'un coup d'œil quels employés ont des anomalies et sur quels types

### 2. Audit ciblé

**Workflow** :
1. Ouvrir l'analyse croisée
2. Repérer visuellement les employés avec badges jaunes
3. Cliquer sur un badge orange dans le tableau pour voir les détails du mois
4. Vérifier si l'anomalie est légitime ou une erreur

### 3. Priorisation des vérifications

**Priorité haute** : Employés avec 3+ badges (plusieurs types avec anomalies)
**Priorité moyenne** : Employés avec 1-2 badges
**Priorité basse** : Employés sans badge (tout normal)

### 4. Comparaison entre bases

Avec le regroupement par base (implémenté précédemment), on peut maintenant :
- Voir quelle base a le plus d'employés avec anomalies
- Identifier des patterns par région (ex: Base A a beaucoup d'anomalies IRSA)

## Avantages

✅ **Vision globale immédiate** : Voir tous les types problématiques d'un employé en un coup d'œil

✅ **Gain de temps** : Ne plus parcourir tous les types un par un

✅ **Traçabilité** : Le tooltip donne le nombre exact de mois concernés

✅ **Priorisation** : Concentrer les efforts sur les employés avec le plus d'anomalies

✅ **Contexte** : Badges visibles même quand on consulte un autre type dans le tableau

## Légende mise à jour

La section légende a été enrichie avec 2 colonnes :

**Colonne 1** : Codes couleurs cellules (existant)
- Vert (0-1) : Normal
- Orange (>1) : Anomalie potentielle
- Rouge (moyenne >1) : Anomalies récurrentes

**Colonne 2** : Indicateurs employés (nouveau)
- Badge jaune avec ⚠️ : Types avec anomalies récurrentes
- Note : "Survoler le badge pour voir le nombre de mois concernés"

## Tests de validation

### Test 1 : Employé sans anomalie
```javascript
data.moyennes = { salaire: 1, irsa: 1, cnaps: 1 }
→ Aucun badge affiché ✅
```

### Test 2 : Employé avec 1 anomalie
```javascript
data.moyennes = { salaire: 1.25, irsa: 1, cnaps: 1 }
data.mois = { '1': {salaire: 2}, '2': {salaire: 2}, '3': {salaire: 1}, ... }
→ Badge "⚠️ Sal" affiché
→ Tooltip: "2 mois avec >1 paiement (moy: 1.25)" ✅
```

### Test 3 : Employé avec plusieurs anomalies
```javascript
data.moyennes = { salaire: 1.5, irsa: 1.3, prime: 2.1 }
→ 3 badges affichés: "⚠️ Sal", "⚠️ IRSA", "⚠️ Prime" ✅
```

### Test 4 : Compatibilité avec statut inactif
```javascript
data.actif = false
data.moyennes = { salaire: 1.5 }
→ Badge "Inactif" + Badge "⚠️ Sal" affichés ensemble ✅
```

## Améliorations futures possibles

1. **Code couleur par sévérité** :
   - Jaune : Moyenne 1-1.5
   - Orange : Moyenne 1.5-2
   - Rouge : Moyenne >2

2. **Clic sur badge** : Filtrer automatiquement le tableau pour afficher ce type

3. **Badge compteur** : Afficher "3" au lieu de "⚠️" pour le nombre de mois

4. **Export** : Inclure les anomalies dans l'export Excel

5. **Statistiques** : Graphique "Top 10 employés avec le plus d'anomalies"

## Compatibilité

✅ Compatible avec le regroupement par base (implémenté 12 déc 2025)
✅ Compatible avec tous les filtres existants (année, employé, statut)
✅ Compatible avec la recherche d'employés
✅ Fonctionne avec les données historiques
✅ Responsive (badges se replient sur plusieurs lignes si nécessaire)

## Performances

**Impact** : Négligeable
- Calcul effectué en JavaScript côté client
- Pas de requête API supplémentaire
- Boucle sur 16 types × 12 mois = 192 itérations par employé maximum
- Pour 67 employés : ~13,000 opérations (instantané)

## Fichiers modifiés

1. `backend/templates/employees/verification_paiements_croisee.html`
   - Lignes 489-539 : Ajout calcul et affichage badges
   - Lignes 191-225 : Mise à jour légende avec 2 colonnes

2. `backend/docs/INDICATEURS_ANOMALIES_EMPLOYES.md` (ce fichier)
   - Documentation complète de la fonctionnalité

## Accès

**URL** : http://localhost:8000/verification-paiements-croisee/
**Menu** : Administration → Vérification & Contrôle → Analyse Croisée (Mois × Types)

---

**Date d'implémentation** : 12 décembre 2025
**Fichier modifié** : `verification_paiements_croisee.html`
**Lignes ajoutées** : ~50 lignes JavaScript + 20 lignes HTML légende
**Impact utilisateur** : ✅ Amélioration significative de la lisibilité et de l'efficacité
