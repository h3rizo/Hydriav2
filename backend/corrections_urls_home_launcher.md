# Corrections des URLs dans home_launcher.html

## URLs corrigées (27 décembre 2025)

### 1. Ligne 460 - Demande BP
- ❌ AVANT: `href="/billing/demande-bp/"`
- ✅ APRÈS: `href="{% url 'billing:demandes_bp' %}"`
- 🔗 URL générée: `/facturation/demandes-bp/`

### 2. Ligne 492 - Représentantes
- ❌ AVANT: `href="/facturation/representantes/"`
- ✅ APRÈS: `href="{% url 'usagers:representants_list' %}"`
- 🔗 URL générée: `/usagers/representants/`

### 3. Ligne 534 - Postes
- ❌ AVANT: `href="/employes/postes/"`
- ✅ APRÈS: `href="{% url 'employees:poste_list' %}"`
- 🔗 URL générée: `/postes/`

### 4. Ligne 550 - CNaPS/FMFP
- ❌ AVANT: `href="/employes/paiements-cnaps-fmfp/"`
- ✅ APRÈS: `href="{% url 'employees:paiements_cnaps_fmfp_list' %}"`
- 🔗 URL générée: `/paiements-cnaps-fmfp/`

## URLs déjà corrigées dans la session précédente

### Facturation volumétrique (3 occurrences)
- Lignes 54, 208, 436, 468: `{% url 'billing:workflow_facturation' %}`

### Points d'eau
- Ligne 444: `{% url 'organization:points_eau_list' %}`

### Modalités de gestion
- Ligne 452: `{% url 'organization:modalites_gestion_list' %}`

### Autres URLs facturation
- Ligne 476: `{% url 'billing:suivi_paiements_forfaitaires' %}`
- Ligne 484: `{% url 'billing:encaissement_factures' %}`
- Ligne 500: `{% url 'billing:cartes_sociales_workflow' %}`
- Ligne 508: `{% url 'billing:cartes_sociales_encaissement' %}`

## URLs encore hardcodées (à corriger si nécessaire)

Les URLs suivantes sont encore hardcodées mais peuvent fonctionner :
- `/plannings/` (plusieurs occurrences)
- `/inspections/` (plusieurs occurrences)
- `/employes/list/` (plusieurs occurrences)
- `/comptabilite/verification/` (plusieurs occurrences)
- `/recherche/`
- Et autres URLs `/accounting/*`

**Note**: Ces URLs seront corrigées au fur et à mesure des besoins utilisateur.

## Comment corriger une nouvelle URL

1. Identifier le message d'erreur 404
2. Noter l'URL incorrecte et l'URL correcte
3. Trouver la route Django correspondante:
   ```bash
   cd backend
   grep -r "nom-de-la-route" apps/*/urls.py
   ```
4. Vérifier le nom de la route:
   ```bash
   python manage.py shell -c "from django.urls import reverse; print(reverse('app:route_name'))"
   ```
5. Remplacer dans home_launcher.html:
   - AVANT: `href="/url/hardcodee/"`
   - APRÈS: `href="{% url 'app:route_name' %}"`

## Principe CRITICAL

**❌ NE JAMAIS utiliser d'URLs hardcodées**
```html
<a href="/facturation/demandes-bp/">  <!-- INCORRECT -->
```

**✅ TOUJOURS utiliser les tags Django url**
```html
<a href="{% url 'billing:demandes_bp' %}">  <!-- CORRECT -->
```

**Raisons:**
- Les URLs peuvent changer dans urls.py sans casser les liens
- Django vérifie au démarrage que les routes existent
- Facilite la maintenance et les refactorisations


### 5. Ligne 78 - Comptabilité (bouton principal)
- ❌ AVANT: `href="/comptabilite/verification/"`
- ✅ APRÈS: `href="{% url 'accounting:dashboard_comptabilite' %}"`
- 🔗 URL générée: `/comptabilite/dashboard/`

### 6. Ligne 234 - Comptabilité (section 2)
- ❌ AVANT: `href="/comptabilite/verification/"`
- ✅ APRÈS: `href="{% url 'accounting:dashboard_comptabilite' %}"`
- 🔗 URL générée: `/comptabilite/dashboard/`

### 7. Ligne 568 - Vérification (bouton spécifique)
- ❌ AVANT: `href="/comptabilite/verification/"`
- ✅ APRÈS: `href="{% url 'accounting:verification_scans_recap' %}"`
- 🔗 URL générée: `/comptabilite/verification-scans/`

**Note**: L'ancienne route `/comptabilite/verification/` a été supprimée et remplacée par 5 pages spécialisées:
- `/verification-paiements/`
- `/comptabilite/verification-fournisseurs/`
- `/comptabilite/verification-avec-ouvrage/`
- `/comptabilite/verification-sans-ouvrage/`
- `/comptabilite/verification-scans/` (utilisée ici)

### 8. Ligne 576 - Import DiameX
- ❌ AVANT: `href="/comptabilite/import-diamex/"`
- ✅ APRÈS: `href="{% url 'accounting:import_home' %}"`
- 🔗 URL générée: `/comptabilite/import/`

### 9. Ligne 592 - Comptes
- ❌ AVANT: `href="/comptabilite/comptes/"`
- ✅ APRÈS: `href="{% url 'organization:list' %}"`
- 🔗 URL générée: `/organisations/`

**Note**: Il n'existe pas de page dédiée aux comptes. Les comptes sont gérés en cascade dans la page Organisations (`/organisations/`).

### 10. Ligne 600 - Écritures comptables
- ❌ AVANT: `href="/accounting/ecritures/"`
- ✅ APRÈS: `href="{% url 'accounting:entries_list' %}"`
- 🔗 URL générée: `/comptabilite/entries/`
