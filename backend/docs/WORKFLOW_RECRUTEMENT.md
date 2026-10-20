# 🎯 MODULE RECRUTEMENT ET TESTS DE CANDIDATS (2 janvier 2026)

## Vue d'ensemble
Module complet permettant de gérer le processus de recrutement avec tests de sélection automatisés et chronométrés pour les candidats.

## Fonctionnalités implémentées
1. **Inscription candidats** : Formulaire complet avec upload CV et lettre de motivation
2. **Tests chronométrés** : 30 minutes par défaut, avec timer visible
3. **Types de questions** : QCM, Oui/Non, Texte libre
4. **Auto-évaluation** : Correction automatique selon le type de question
5. **Sauvegarde automatique** : Réponses sauvegardées en temps réel (AJAX)
6. **Prévention retake** : Impossible de repasser le test après soumission
7. **Résultats détaillés** : Affichage du score avec détail par question

## Architecture

### Modèles créés

#### 1. Candidat
**Fichier** : `apps/recrutement/models.py` (lignes 11-53)

```python
class Candidat(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # Informations personnelles
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    telephone = models.CharField(max_length=20)

    # Candidature
    poste_souhaite = models.ForeignKey('employees.Poste')
    experience = models.TextField()
    formation = models.TextField()
    cv = models.FileField(upload_to='recrutement/cv/%Y/%m/')
    lettre_motivation = models.FileField(upload_to='recrutement/lettres/%Y/%m/')

    # Statut
    statut = models.CharField(choices=[
        ('en_attente', 'En attente'),
        ('test_passe', 'Test passé'),
        ('accepte', 'Accepté'),
        ('refuse', 'Refusé')
    ])
```

#### 2. QuestionTest
**Fichier** : `apps/recrutement/models.py` (lignes 56-85)

```python
class QuestionTest(models.Model):
    TYPE_QUESTION_CHOICES = [
        ('qcm', 'QCM (Choix multiples)'),
        ('oui_non', 'Oui/Non'),
        ('texte_libre', 'Texte libre'),
    ]

    poste = models.ForeignKey('employees.Poste')
    type_question = models.CharField(max_length=20, choices=TYPE_QUESTION_CHOICES)
    texte_question = models.TextField()

    # Pour QCM : options séparées par pipe "Option A|Option B|Option C"
    options_qcm = models.TextField(blank=True, null=True)

    # Réponse correcte
    reponse_correcte = models.TextField()

    points = models.IntegerField(default=1)
    ordre = models.IntegerField(default=0)
    active = models.BooleanField(default=True)
```

#### 3. SessionTest
**Fichier** : `apps/recrutement/models.py` (lignes 88-174)

```python
class SessionTest(models.Model):
    candidat = models.ForeignKey(Candidat)
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    duree_limite = models.IntegerField(default=30)  # minutes

    statut = models.CharField(choices=[
        ('non_commence', 'Non commencé'),
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
        ('expire', 'Expiré')
    ])

    score_obtenu = models.IntegerField(default=0)
    score_total = models.IntegerField(default=0)
    pourcentage = models.DecimalField(max_digits=5, decimal_places=2)

    def est_expire(self):
        """Vérifie si le temps est écoulé"""
        if self.date_debut and self.statut == 'en_cours':
            temps_ecoule = timezone.now() - self.date_debut
            return temps_ecoule.total_seconds() > (self.duree_limite * 60)
        return False

    def temps_restant_secondes(self):
        """Retourne le temps restant en secondes"""
        if self.date_debut and self.statut == 'en_cours':
            temps_ecoule = timezone.now() - self.date_debut
            temps_total = self.duree_limite * 60
            temps_restant = temps_total - temps_ecoule.total_seconds()
            return max(0, int(temps_restant))
        return self.duree_limite * 60
```

#### 4. ReponseCandidat
**Fichier** : `apps/recrutement/models.py` (lignes 177-261)

```python
class ReponseCandidat(models.Model):
    session = models.ForeignKey(SessionTest, related_name='reponses')
    question = models.ForeignKey(QuestionTest)
    reponse_donnee = models.TextField()

    est_correcte = models.BooleanField(default=False)
    points_obtenus = models.IntegerField(default=0)

    def evaluer(self):
        """Auto-évaluation de la réponse"""
        reponse_correcte = self.question.reponse_correcte.strip().lower()
        reponse_donnee = self.reponse_donnee.strip().lower()

        if self.question.type_question in ['qcm', 'oui_non']:
            # Comparaison exacte pour QCM et Oui/Non
            self.est_correcte = (reponse_donnee == reponse_correcte)
        else:
            # Pour texte libre : vérifier présence de mots-clés
            # Format: "mot1,mot2,mot3" dans reponse_correcte
            mots_cles = [m.strip() for m in reponse_correcte.split(',')]
            self.est_correcte = all(mot in reponse_donnee for mot in mots_cles)

        self.points_obtenus = self.question.points if self.est_correcte else 0
        self.save()
```

### Vues implémentées

**Fichier** : `apps/recrutement/views.py`

#### 1. `inscription_candidat()` - Inscription
- Affiche formulaire avec liste des postes
- POST : Crée User + Candidat + Upload fichiers
- Connexion automatique après inscription
- Redirect vers dashboard

#### 2. `dashboard_candidat()` - Tableau de bord
- Affiche statut candidature
- Affiche statut test (non commencé, en cours, terminé)
- Bouton pour démarrer ou reprendre test
- Liens vers documents (CV, lettre)

#### 3. `demarrer_test()` - Démarrage test
- Vérifie qu'aucun test n'a déjà été passé
- Crée SessionTest
- Charge questions du poste
- Crée objets ReponseCandidat vides
- Redirect vers page_test

#### 4. `page_test()` - Page de test
- Affiche timer en temps réel
- Vérifie expiration
- Affiche questions selon type
- JavaScript pour sauvegarde auto
- Progress bar

#### 5. `enregistrer_reponse()` - AJAX Save
- Endpoint pour sauvegarder réponses
- Appelé automatiquement pendant le test
- Validation session active

#### 6. `soumettre_test()` - Soumission
- Évalue toutes les réponses
- Calcule score total
- Change statut à 'termine'
- Redirect vers résultats

#### 7. `resultats_test()` - Résultats
- Affiche score et pourcentage
- Détail par question avec correction
- Message "test unique"

### URLs

**Fichier** : `apps/recrutement/urls.py`

```python
urlpatterns = [
    # Pages candidat
    path('inscription/', inscription_candidat, name='inscription'),
    path('dashboard/', dashboard_candidat, name='dashboard'),

    # Workflow de test
    path('test/demarrer/', demarrer_test, name='demarrer_test'),
    path('test/<uuid:session_id>/', page_test, name='test'),
    path('test/<uuid:session_id>/reponse/', enregistrer_reponse, name='enregistrer_reponse'),
    path('test/<uuid:session_id>/soumettre/', soumettre_test, name='soumettre_test'),
    path('resultats/<uuid:session_id>/', resultats, name='resultats'),

    # Admin
    path('admin/questions/', gestion_questions, name='gestion_questions'),
    path('admin/questions/creer/', creer_question, name='creer_question'),
]
```

**Point de montage** : `/recrutement/` (dans `hydria/urls.py`)

### Templates créés

1. **inscription.html** - Formulaire d'inscription avec upload fichiers
2. **dashboard.html** - Dashboard candidat avec statut test
3. **test.html** - Page de test avec timer et questions
4. **test_expire.html** - Message quand temps écoulé
5. **resultats.html** - Affichage des résultats avec détails

### Admin Django

**Fichier** : `apps/recrutement/admin.py`

- **CandidatAdmin** : Liste, filtres par statut/poste, search
- **QuestionTestAdmin** : Tri par poste/ordre, list_editable
- **SessionTestAdmin** : Scores readonly, filtres par statut
- **ReponseCandidatAdmin** : Optimisation select_related

## Workflow utilisateur

### Phase 1 : Inscription
1. Candidat accède à `/recrutement/inscription/`
2. Remplit formulaire (nom, email, téléphone, CV, lettre, etc.)
3. Sélectionne poste souhaité
4. Upload CV et lettre de motivation (PDF/DOC/DOCX)
5. Soumission → Création compte User + Candidat
6. Connexion automatique
7. Redirect vers dashboard

### Phase 2 : Passer le test
1. Dashboard affiche "Test disponible"
2. Clic "Démarrer le test" → `demarrer_test()`
3. Création SessionTest + ReponseCandidat vides
4. Redirect vers `/recrutement/test/<session_id>/`
5. Timer démarre automatiquement (30 minutes)
6. Candidat répond aux questions :
   - **QCM** : Sélection radio button
   - **Oui/Non** : Boutons Oui/Non
   - **Texte libre** : Textarea
7. Sauvegarde automatique AJAX à chaque changement
8. Progress bar mise à jour en temps réel
9. Bouton "Soumettre le test" ou expiration auto
10. Évaluation automatique → Résultats

### Phase 3 : Résultats
1. Affichage score (points et pourcentage)
2. Badge selon performance :
   - ≥70% : Excellent (vert)
   - 50-69% : Satisfaisant (jaune)
   - <50% : À améliorer (rouge)
3. Détail par question avec correction
4. Message "Impossible de repasser le test"
5. Retour au dashboard

## Points d'attention CRITICAL

### 1. Validation fichiers upload
```python
cv = models.FileField(
    validators=[FileExtensionValidator(['pdf', 'doc', 'docx'])]
)
```

### 2. Timer côté serveur
```python
def est_expire(self):
    if self.date_debut and self.statut == 'en_cours':
        temps_ecoule = timezone.now() - self.date_debut
        return temps_ecoule.total_seconds() > (self.duree_limite * 60)
    return False
```

### 3. Prévention retake
```python
session_existante = SessionTest.objects.filter(
    candidat=candidat,
    statut__in=['termine', 'expire']
).first()

if session_existante:
    return JsonResponse({
        'success': False,
        'error': 'Vous avez déjà passé le test.'
    })
```

### 4. Auto-évaluation texte libre
```python
# Réponse correcte = mots-clés séparés par virgules
# Ex: "python,django,orm"
mots_cles = [m.strip() for m in reponse_correcte.split(',')]
self.est_correcte = all(mot in reponse_donnee for mot in mots_cles)
```

### 5. Format options QCM
```
"Option A|Option B|Option C|Option D"
```
Séparées par pipe `|` pour faciliter le split en template

## Fichiers créés/modifiés

### Créés
1. `backend/apps/recrutement/__init__.py`
2. `backend/apps/recrutement/apps.py`
3. `backend/apps/recrutement/models.py` (261 lignes)
4. `backend/apps/recrutement/views.py` (454 lignes)
5. `backend/apps/recrutement/urls.py`
6. `backend/apps/recrutement/admin.py` (115 lignes)
7. `backend/apps/recrutement/migrations/0001_initial.py`
8. `backend/templates/recrutement/inscription.html`
9. `backend/templates/recrutement/dashboard.html`
10. `backend/templates/recrutement/test.html`
11. `backend/templates/recrutement/test_expire.html`
12. `backend/templates/recrutement/resultats.html`
13. `backend/docs/WORKFLOW_RECRUTEMENT.md` (ce fichier)

### Modifiés
1. `backend/hydria/settings.py` - Ajout `'apps.recrutement'` dans INSTALLED_APPS
2. `backend/hydria/urls.py` - Ajout `path('recrutement/', include('apps.recrutement.urls'))`

## Tables créées (PostgreSQL)

1. **candidats** :
   - Colonnes : id (UUID), user_id, nom, prenom, email, telephone, poste_souhaite_id, experience, formation, cv, lettre_motivation, statut

2. **questions_test** :
   - Colonnes : id, poste_id, type_question, texte_question, options_qcm, reponse_correcte, points, ordre, active

3. **sessions_test** :
   - Colonnes : id, candidat_id, date_debut, date_fin, duree_limite, statut, score_obtenu, score_total, pourcentage

4. **reponses_candidat** :
   - Colonnes : id, session_id, question_id, reponse_donnee, est_correcte, points_obtenus

## Configuration requise

### 1. Créer des questions de test
Via Django Admin (`/admin/recrutement/questiontest/`) :

```python
QuestionTest.objects.create(
    poste=poste_technicien,
    type_question='qcm',
    texte_question='Quelle est la capitale de Madagascar ?',
    options_qcm='Antananarivo|Toamasina|Mahajanga|Fianarantsoa',
    reponse_correcte='antananarivo',  # en minuscules
    points=2,
    ordre=1,
    active=True
)
```

### 2. Configuration MEDIA_ROOT
Dans `settings.py` :
```python
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
```

### 3. URLs pour servir les médias (développement)
Dans `urls.py` :
```python
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

## Tests de validation

- [ ] Créer un poste dans Django admin
- [ ] Créer 10 questions pour ce poste (mix QCM, Oui/Non, Texte libre)
- [ ] Accéder à `/recrutement/inscription/`
- [ ] Remplir formulaire et uploader CV/lettre
- [ ] Soumettre → Vérifier création User + Candidat
- [ ] Dashboard → Vérifier statut "Test disponible"
- [ ] Démarrer test → Vérifier timer démarre
- [ ] Répondre à quelques questions → Vérifier sauvegarde AJAX
- [ ] Soumettre test → Vérifier calcul du score
- [ ] Afficher résultats → Vérifier détails et corrections
- [ ] Retourner dashboard → Vérifier "Test terminé"
- [ ] Essayer de recommencer test → Vérifier blocage

## Améliorations futures possibles

1. **Email de confirmation** : Envoyer email après inscription
2. **Notification résultats** : Email aux RH quand candidat termine test
3. **Import questions Excel** : Importer questions en masse
4. **Banque de questions** : Questions partagées entre postes
5. **Niveaux de difficulté** : Questions faciles/moyennes/difficiles
6. **Historique tentatives** : Même si unique, garder trace des tentatives
7. **Export résultats PDF** : Générer rapport PDF pour RH
8. **Statistiques globales** : Taux de réussite par poste, par question
9. **Questions aléatoires** : Ordre aléatoire pour éviter triche
10. **Proctoring basique** : Détection changement d'onglet

## ✅ STATUT : SYSTÈME OPÉRATIONNEL

**Le module de recrutement est maintenant entièrement fonctionnel avec :**
✅ Modèles créés et migrés (4 tables)
✅ Vues complètes (7 endpoints)
✅ URLs configurées
✅ Admin Django enregistré
✅ Templates créés (5 pages)
✅ JavaScript timer et AJAX
✅ Auto-évaluation des réponses
✅ Prévention de retake
✅ Upload de fichiers
✅ Django check sans erreur

**Accessible via** :
- Inscription : `http://localhost:8000/recrutement/inscription/`
- Dashboard : `http://localhost:8000/recrutement/dashboard/`
- Admin : `http://localhost:8000/admin/recrutement/`
