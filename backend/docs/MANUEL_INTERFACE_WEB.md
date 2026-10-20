# Manuel d'Utilisateur - Interface Web

## 📖 Vue d'ensemble

Le manuel d'utilisateur Hydria est maintenant accessible directement depuis l'interface web de l'application, offrant une expérience de consultation interactive et moderne.

## 🌐 Accès au Manuel

### Depuis l'interface web

**URL directe** : `http://localhost:8000/systeme/manuel/`

**Accès via le menu** :
- **Desktop** : Menu principal > Référentiel > Système > Manuel d'utilisateur
- **Mobile** : Menu hamburger > Système > Manuel d'utilisateur

### Icône

🔵 Icône bleue avec livre (`fa-book text-info`)

## 📸 Captures d'écran

### Interface principale

L'interface se compose de deux zones principales :

**Zone gauche (Sidebar)** :
- Table des matières interactive avec les 6 sections principales
- Badges numérotés pour faciliter la navigation
- Boutons d'action (Imprimer, Télécharger)

**Zone droite (Contenu)** :
- Barre de recherche en temps réel
- Contenu du manuel avec mise en forme riche (tableaux, code, citations)
- Navigation par ancres (scroll automatique)

### Aperçu Desktop

```
┌─────────────────────────────────────────────────────────────────┐
│ 📚 MANUEL D'UTILISATEUR - HYDRIA                                │
│ Guide complet d'utilisation - Tous modules et workflows         │
├──────────────┬──────────────────────────────────────────────────┤
│ Table des    │ 🔍 Rechercher dans le manuel...         [🔎]     │
│ matières     ├──────────────────────────────────────────────────┤
│              │                                                  │
│ 1️⃣ Introduction│ ## 1. Introduction                             │
│ 2️⃣ Connexion  │                                                  │
│ 3️⃣ Modules    │ Hydria est une application web de gestion...  │
│ 4️⃣ Workflows  │                                                  │
│ 5️⃣ Rôles      │ ### 1.1 Objectif                               │
│ 6️⃣ FAQ        │ [Contenu de la section...]                     │
│              │                                                  │
│ ──────────   │ ## 2. Connexion et Navigation                   │
│              │                                                  │
│ 🖨️ Imprimer   │ ### 2.1 Se connecter                           │
│ 💾 Télécharger│ [Contenu de la section...]                     │
└──────────────┴──────────────────────────────────────────────────┘
```

### Mode impression

Lors de l'impression (Ctrl+P ou bouton Imprimer) :
- ✅ Sidebar masquée automatiquement
- ✅ Boutons d'action masqués
- ✅ Barre de recherche masquée
- ✅ Navigation masquée
- ✅ Contenu uniquement (pleine largeur)
- ✅ Optimisation des sauts de page (pas de coupure de tableaux/titres)

```
┌─────────────────────────────────────────────────────────────────┐
│ PAGE 1                                                           │
│                                                                  │
│ ## 1. Introduction                                              │
│                                                                  │
│ Hydria est une application web de gestion opérationnelle...     │
│                                                                  │
│ ### 1.1 Objectif                                                │
│ [Contenu...]                                                    │
│                                                                  │
│ ### 1.2 Public cible                                            │
│ [Contenu...]                                                    │
│                                                                  │
│ ## 2. Connexion et Navigation                                   │
│                                                                  │
│ ### 2.1 Se connecter                                            │
│ [Contenu...]                                                    │
├─────────────────────────────────────────────────────────────────┤
│ PAGE 2                                                           │
│                                                                  │
│ ### 2.2 Interface principale                                    │
│ [Contenu...]                                                    │
└─────────────────────────────────────────────────────────────────┘
```

### Responsive Mobile

Sur mobile et tablette :
- Sidebar se transforme en menu dépliable (accordion)
- Barre de recherche pleine largeur
- Contenu adapté à la taille de l'écran
- Boutons d'action empilés verticalement

```
┌──────────────────────┐
│ 📱 MANUEL HYDRIA     │
├──────────────────────┤
│ [≡] Table matières ▼ │
├──────────────────────┤
│ 🔍 Rechercher...  🔎 │
├──────────────────────┤
│                      │
│ ## 1. Introduction   │
│                      │
│ [Contenu adapté à    │
│  la largeur mobile]  │
│                      │
├──────────────────────┤
│ [🖨️] Imprimer        │
│ [💾] Télécharger     │
└──────────────────────┘
```

## ✨ Fonctionnalités de l'interface

### 1. Navigation intelligente

**Sidebar fixe (gauche)** :
- Table des matières interactive avec 6 sections principales
- Badges numérotés pour chaque section
- Scroll automatique vers la section cliquée
- Highlight de la section active pendant le scroll

**Sections disponibles** :
1. Introduction
2. Connexion et Navigation
3. Modules par Fonction
4. Workflows Détaillés
5. Rôles et Permissions
6. FAQ et Dépannage

### 2. Barre de recherche

**Fonctionnalités** :
- Recherche en temps réel dans tout le manuel
- Highlight automatique des termes trouvés (fond jaune)
- Recherche à partir de 3 caractères
- Compatible avec les accents

**Utilisation** :
1. Saisir au moins 3 caractères dans la barre de recherche
2. Les résultats sont surlignés automatiquement en jaune
3. Effacer la recherche pour retirer les highlights

### 3. Actions disponibles

**Bouton Imprimer** :
- Ouvre la boîte de dialogue d'impression du navigateur
- Version imprimable optimisée (sans navigation, boutons, etc.)
- Préserve les tableaux et diagrammes
- Page breaks intelligents pour éviter de couper les sections

**Bouton Télécharger** :
- Télécharge le manuel au format Markdown (`.md`)
- Nom du fichier : `Manuel_Utilisateur_Hydria.md`
- Format original pour édition ou consultation hors-ligne

**Bouton Retour en haut** :
- Flèche vers le haut (bouton circulaire primaire)
- Scroll animé vers le haut de la page
- Toujours visible en bas de page

### 4. Mise en forme du contenu

**Styles appliqués** :
- **Titres H1** : Couleur primaire avec bordure inférieure
- **Titres H2** : Couleur secondaire avec ligne de séparation
- **Titres H3** : Couleur accent
- **Titres H4** : Couleur info
- **Tableaux** : Bordures, en-têtes avec fond, lignes alternées
- **Code inline** : Fond gris clair avec bordure arrondie
- **Blocs de code** : Fond gris avec bordure
- **Listes** : Indentation et puces claires
- **Citations** : Bordure gauche colorée, texte italique
- **Séparateurs** : Lignes horizontales épaisses

### 5. Responsive design

**Desktop (> 1024px)** :
- Layout 2 colonnes : Sidebar (25%) + Contenu (75%)
- Sidebar fixe qui suit le scroll
- Largeur maximale optimale pour la lecture

**Tablette (768px - 1024px)** :
- Layout ajusté avec sidebar réductible
- Contenu prend plus d'espace

**Mobile (< 768px)** :
- Layout 1 colonne
- Sidebar en haut ou dépliable
- Barre de recherche pleine largeur

## 📂 Architecture technique

### Fichiers créés

1. **Backend - Vue** : `backend/apps/system/views_manuel.py`
   - `manuel_utilisateur()` : Affiche le manuel avec navigation
   - `telecharger_manuel()` : Télécharge le fichier Markdown

2. **Backend - Template** : `backend/templates/system/manuel_utilisateur.html`
   - Interface complète avec sidebar, recherche, actions
   - Styles CSS pour le rendu Markdown
   - JavaScript pour recherche et navigation

3. **Backend - URLs** : `backend/apps/system/urls.py`
   - `/systeme/manuel/` : Page principale
   - `/systeme/manuel/telecharger/` : Téléchargement

4. **Backend - Source** : `backend/docs/MANUEL_UTILISATEUR.md`
   - Fichier Markdown source (1374 lignes)
   - Contenu complet du manuel

### Dépendances

**Librairie Python** :
- `markdown>=3.9` : Convertisseur Markdown → HTML
- Extensions activées :
  - `tables` : Support des tableaux
  - `fenced_code` : Blocs de code avec ` ``` `
  - `toc` : Table des matières
  - `attr_list` : Attributs HTML personnalisés

### Processus de rendu

```
MANUEL_UTILISATEUR.md (Markdown)
        ↓
    Python (views_manuel.py)
        ↓
    markdown.markdown() avec extensions
        ↓
    HTML généré
        ↓
    Template (manuel_utilisateur.html)
        ↓
    Styles CSS + JavaScript interactif
        ↓
    Page web finale
```

## 🎨 Personnalisation

### Modifier le contenu

Pour mettre à jour le manuel :

1. Éditer le fichier source : `backend/docs/MANUEL_UTILISATEUR.md`
2. Utiliser la syntaxe Markdown standard
3. Les changements sont visibles immédiatement (rafraîchir la page)
4. Pas besoin de redémarrer Django

### Ajouter une section

```markdown
## X. Nouvelle Section

### X.1 Sous-section

Contenu de la sous-section avec :
- Listes à puces
- **Texte en gras**
- *Texte en italique*
- `Code inline`

#### Exemple de tableau

| Colonne 1 | Colonne 2 |
|-----------|-----------|
| Valeur A  | Valeur B  |

#### Exemple de code

\`\`\`python
def exemple():
    print("Bonjour Hydria")
\`\`\`
```

La nouvelle section apparaîtra automatiquement dans la table des matières.

### Modifier les couleurs

Les couleurs utilisent les variables DaisyUI définies dans le thème actif :

```css
/* Dans manuel_utilisateur.html <style> */
.prose h1 { color: hsl(var(--p)); }  /* Primaire */
.prose h2 { color: hsl(var(--s)); }  /* Secondaire */
.prose h3 { color: hsl(var(--a)); }  /* Accent */
.prose h4 { color: hsl(var(--in)); } /* Info */
```

## 🔒 Permissions

**Accès requis** : Utilisateur authentifié (`@login_required`)

Tous les utilisateurs connectés peuvent consulter le manuel, quel que soit leur rôle (Directeur, Chef, Agent, Comptable, Client, etc.).

## 📱 Cas d'usage

### Formation nouveaux utilisateurs

1. Partager le lien `/systeme/manuel/`
2. Guider l'utilisateur vers la section "2. Connexion et Navigation"
3. Lui montrer comment utiliser la table des matières
4. L'inviter à rechercher des termes spécifiques

### Résolution de problèmes

1. Utilisateur bloqué sur une fonctionnalité
2. Accéder au manuel via le menu Système
3. Utiliser la recherche pour trouver le workflow concerné
4. Section "6. FAQ et Dépannage" pour problèmes courants

### Documentation pour administrateurs

1. Imprimer le manuel (bouton Imprimer)
2. Ou télécharger le Markdown pour édition locale
3. Créer une version personnalisée avec notes internes
4. Partager aux équipes

## 🚀 Améliorations futures possibles

### Version PDF native

Ajouter la librairie `weasyprint` ou `reportlab` pour générer des PDF :

```python
pip install weasyprint

# Dans views_manuel.py
from weasyprint import HTML

def telecharger_manuel_pdf(request):
    # Convertir HTML en PDF
    html = HTML(string=html_content)
    pdf = html.write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="Manuel_Hydria.pdf"'
    return response
```

### Versions multilingues

Créer des fichiers Markdown pour chaque langue :
- `MANUEL_UTILISATEUR_fr.md` (français)
- `MANUEL_UTILISATEUR_mg.md` (malgache)
- Détection automatique de la langue utilisateur

### Feedback utilisateurs

Ajouter un bouton "Cette page vous a-t-elle été utile ?" :
- Oui/Non avec commentaire optionnel
- Stockage dans une table `ManuelFeedback`
- Permet d'identifier les sections à améliorer

### Historique de versions

Tracker les modifications du manuel :
- Date de modification
- Auteur des changements
- Diff entre versions
- Permet de savoir quand le manuel a été mis à jour

## ✅ Checklist de déploiement

Avant de déployer en production :

- [x] Vérifier que `markdown` est installé : `pip install markdown`
- [x] Ajouter `markdown` dans `requirements.txt`
- [x] Vérifier les permissions (uniquement utilisateurs authentifiés)
- [x] Tester sur mobile, tablette, desktop
- [x] Vérifier que l'impression fonctionne correctement
- [x] Tester la recherche avec accents et caractères spéciaux
- [x] Vérifier que la navigation par ancres fonctionne
- [x] Tester le téléchargement du fichier Markdown
- [x] Vérifier le highlight de la section active

## 📞 Support

En cas de problème avec le manuel d'utilisateur :

1. Vérifier les logs Django pour les erreurs
2. S'assurer que le fichier `MANUEL_UTILISATEUR.md` existe et est lisible
3. Vérifier que la librairie `markdown` est installée
4. Consulter la console navigateur pour erreurs JavaScript

---

**Dernière mise à jour** : 26 décembre 2025
**Version** : 1.0
**Auteur** : Équipe Hydria
