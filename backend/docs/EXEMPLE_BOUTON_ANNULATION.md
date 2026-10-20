# Exemple d'intégration du bouton "Annuler" dans les interfaces Planning

## ✅ INTÉGRATION COMPLÈTE - 8 décembre 2025

**Le bouton "Annuler" a été intégré dans les 3 interfaces de planning :**
1. ✅ **Liste des plannings** (`/plannings/`) - Bouton dans la colonne Actions
2. ✅ **Calendrier** (`/plannings/calendrier/`) - Bouton dans les actions rapides des cartes
3. ✅ **Vue consolidée** (`/plannings/consolide/`) - Bouton dans l'en-tête de chaque planning

Le JavaScript `static/js/planning_annulation.js` est inclus dans les 3 templates.

---

## 📋 Vue d'ensemble

Le bouton "Annuler" permet aux utilisateurs de supprimer un Planning de type **Repos** ou **Jour férié**, avec création automatique d'une récupération si nécessaire.

---

## 🔧 Fichiers créés

1. **`static/js/planning_annulation.js`** - JavaScript réutilisable avec fonction `annulerReposFerie()`
2. **Ce document** - Exemples d'intégration dans les templates

---

## 📝 Intégration dans les templates

### Étape 1 : Inclure le JavaScript

Ajouter dans le `<head>` ou avant `</body>` :

```html
{% load static %}
<script src="{% static 'js/planning_annulation.js' %}"></script>
```

---

### Étape 2 : Ajouter le bouton dans la liste

#### Option A : Dans `planning_list.html` (Colonne Actions)

**Emplacement** : Ligne 164 (dans la colonne Actions)

**Code à ajouter** :

```html
<td>
    <div class="flex gap-1 items-center">
        <!-- Boutons existants (photos, etc.) -->

        <!-- Bouton Annuler (seulement pour Repos/Jour férié) -->
        {% if planning.activite.nom == 'Repos' or planning.activite.nom == 'Jour férié' %}
        <button
            onclick="annulerReposFerie('{{ planning.id }}', '{{ planning.activite.nom }}')"
            class="btn btn-xs btn-error gap-1"
            title="Annuler ce {{ planning.activite.nom }}">
            <i class="fas fa-times"></i>
            Annuler
        </button>
        {% endif %}
    </div>
</td>
```

#### Option B : Dropdown avec icône

```html
<div class="dropdown dropdown-end">
    <label tabindex="0" class="btn btn-sm btn-ghost">
        <i class="fas fa-ellipsis-v"></i>
    </label>
    <ul tabindex="0" class="dropdown-content menu p-2 shadow bg-base-100 rounded-box w-52">
        <!-- Autres actions -->
        <li><a href="/plannings/{{ planning.id }}/modifier/">
            <i class="fas fa-edit"></i> Modifier
        </a></li>

        <!-- Annuler (seulement Repos/Jour férié) -->
        {% if planning.activite.nom == 'Repos' or planning.activite.nom == 'Jour férié' %}
        <li><a onclick="annulerReposFerie('{{ planning.id }}', '{{ planning.activite.nom }}')">
            <i class="fas fa-times text-error"></i> Annuler
        </a></li>
        {% endif %}
    </ul>
</div>
```

---

### Étape 3 : Intégration dans le Calendrier

#### Dans `planning_calendar.html`

**Emplacement** : Modal de détails du planning (quand on clique sur un événement)

**Code à ajouter** :

```html
<!-- Dans le modal de détails -->
<div class="modal-body">
    <!-- Infos du planning -->
    <p><strong>Activité:</strong> {{ planning.activite.nom }}</p>
    <p><strong>Employé:</strong> {{ planning.employe.nom_complet }}</p>

    <!-- Bouton Annuler -->
    {% if planning.activite.nom == 'Repos' or planning.activite.nom == 'Jour férié' %}
    <div class="alert alert-warning mt-4">
        <i class="fas fa-exclamation-triangle"></i>
        <div>
            <p class="font-bold">Ce {{ planning.activite.nom }} peut être annulé</p>
            <p class="text-sm">Une récupération sera créée automatiquement (sauf Samedi)</p>
        </div>
    </div>

    <button
        onclick="annulerReposFerie('{{ planning.id }}', '{{ planning.activite.nom }}')"
        class="btn btn-error btn-block mt-4">
        <i class="fas fa-times"></i>
        Annuler ce {{ planning.activite.nom }}
    </button>
    {% endif %}
</div>
```

---

### Étape 4 : Intégration dans le Planning Consolidé

#### Dans `planning_consolide.html`

**Emplacement** : Cellule du tableau pour chaque jour

**Code à ajouter** :

```html
<!-- Pour chaque cellule de planning -->
<td>
    {% if planning %}
        <div class="tooltip" data-tip="{{ planning.activite.nom }}">
            <span class="badge {{ badge_class }}">
                {{ planning.activite.nom|truncatechars:10 }}
            </span>

            <!-- Bouton Annuler (icône) -->
            {% if planning.activite.nom == 'Repos' or planning.activite.nom == 'Jour férié' %}
            <button
                onclick="event.stopPropagation(); annulerReposFerie('{{ planning.id }}', '{{ planning.activite.nom }}')"
                class="btn btn-xs btn-ghost btn-circle ml-1"
                title="Annuler">
                <i class="fas fa-times text-error"></i>
            </button>
            {% endif %}
        </div>
    {% endif %}
</td>
```

---

## 🎨 Styles CSS (optionnel)

Si vous voulez personnaliser l'apparence :

```css
/* Bouton Annuler avec animation hover */
.btn-annuler-repos {
    transition: all 0.2s;
}

.btn-annuler-repos:hover {
    transform: scale(1.05);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

/* Badge pour Repos annulable */
.badge-annulable {
    position: relative;
}

.badge-annulable::after {
    content: '✕';
    position: absolute;
    top: -5px;
    right: -5px;
    background: red;
    color: white;
    border-radius: 50%;
    width: 16px;
    height: 16px;
    font-size: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: opacity 0.2s;
}

.badge-annulable:hover::after {
    opacity: 1;
}
```

---

## 🔄 Comportement de l'API

### Règles d'annulation

| Jour | Crée Récupération | Motif |
|------|-------------------|-------|
| **Dimanche** (Repos) | ✅ OUI | `dimanche` |
| **Samedi** (Repos) | ❌ NON | Non récupérable |
| **Jour férié** | ✅ OUI | `jour_ferie` |

### Messages affichés

**Si Dimanche ou Jour férié** :
```
✅ Planning annulé. Une récupération a été créée automatiquement (dimanche)

Une récupération a été ajoutée à votre solde.
```

**Si Samedi** :
```
✅ Planning annulé (Samedi non récupérable)
```

**Si erreur** :
```
❌ Erreur: Ce planning n'est pas un Repos/Jour férié (activité: Congé)
```

---

## 🧪 Test de l'intégration

### 1. Vérifier que le JavaScript est chargé

Ouvrir la console navigateur (F12) et taper :
```javascript
typeof annulerReposFerie
// Devrait afficher: "function"
```

### 2. Tester l'annulation

1. Créer un Repos Dimanche via :
   ```bash
   python manage.py populate_repos_weekly --weeks 1
   ```

2. Aller sur la page Planning → Liste
3. Trouver un Repos Dimanche
4. Cliquer "Annuler"
5. Vérifier le message de confirmation
6. Valider
7. Vérifier qu'une récupération a été créée :
   ```bash
   python manage.py shell -c "
   from apps.employees.models_recuperations import Recuperation
   print(f'{Recuperation.objects.filter(statut=\"acquise\").count()} récupérations acquises')
   "
   ```

---

## 📱 Version mobile

Pour une meilleure UX mobile, utiliser un bouton plus grand :

```html
<!-- Version mobile -->
<div class="sm:hidden">
    {% if planning.activite.nom == 'Repos' or planning.activite.nom == 'Jour férié' %}
    <button
        onclick="annulerReposFerie('{{ planning.id }}', '{{ planning.activite.nom }}')"
        class="btn btn-error btn-block btn-sm mt-2">
        <i class="fas fa-times"></i>
        Annuler ce {{ planning.activite.nom }}
    </button>
    {% endif %}
</div>

<!-- Version desktop -->
<div class="hidden sm:block">
    {% if planning.activite.nom == 'Repos' or planning.activite.nom == 'Jour férié' %}
    <button
        onclick="annulerReposFerie('{{ planning.id }}', '{{ planning.activite.nom }}')"
        class="btn btn-xs btn-error gap-1">
        <i class="fas fa-times"></i>
        Annuler
    </button>
    {% endif %}
</div>
```

---

## 🔒 Sécurité

### Vérifications côté serveur

L'API vérifie automatiquement :
- ✅ Le planning existe
- ✅ C'est bien un Repos ou Jour férié
- ✅ L'utilisateur a les permissions (si implémenté)

### Vérifications côté client

Le JavaScript vérifie :
- ✅ Confirmation utilisateur
- ✅ Gestion des erreurs réseau
- ✅ Affichage des messages appropriés

---

## 📚 Fichiers de référence

- **API** : `apps/planning/views_annulation_repos.py`
- **Route** : `apps/planning/urls.py` (ligne 170)
- **JavaScript** : `static/js/planning_annulation.js`
- **Documentation** : `docs/WORKFLOW_PLANNING_AUTOMATIQUE.md`

---

## ✅ Checklist d'intégration

- [ ] Inclure `planning_annulation.js` dans le template
- [ ] Ajouter bouton dans colonne Actions
- [ ] Tester sur un Repos Dimanche
- [ ] Tester sur un Repos Samedi (pas de récupération)
- [ ] Tester sur un Jour férié
- [ ] Vérifier messages de confirmation
- [ ] Vérifier création récupération
- [ ] Tester sur mobile

---

*Dernière mise à jour : 8 décembre 2025*
