"""
Modèles pour le système de recrutement et tests de candidats
"""
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.utils import timezone


class CandidatPreconfigure(models.Model):
    """
    Modèle pour les candidats préconfigurés par l'administrateur.
    L'admin crée un enregistrement avec email et poste, puis envoie le lien au candidat.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, verbose_name="Email du candidat")
    poste = models.ForeignKey(
        'employees.Poste',
        on_delete=models.CASCADE,
        verbose_name="Poste souhaité"
    )
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de préconfiguration")
    test_complete = models.BooleanField(default=False, verbose_name="Test complété")
    candidat = models.OneToOneField(
        'Candidat',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Lien vers le candidat créé après inscription"
    )
    nom = models.CharField(max_length=100, blank=True, default='', verbose_name="Nom")
    prenom = models.CharField(max_length=100, blank=True, default='', verbose_name="Prénom")
    domicile = models.TextField(blank=True, default='', verbose_name="Domicile")
    date_naissance = models.DateField(null=True, blank=True, verbose_name="Date de naissance")
    formation = models.TextField(blank=True, default='', verbose_name="Formation")
    experience_poste = models.TextField(blank=True, default='', verbose_name="Expérience sur le poste")
    autre_experience = models.TextField(blank=True, default='', verbose_name="Autre expérience")
    pretention_salariale = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Prétention salariale",
    )
    permis_conduire = models.BooleanField(default=False, verbose_name="Permis de conduire")
    photo_candidat = models.ImageField(
        upload_to='recrutement/photos/%Y/%m/',
        null=True,
        blank=True,
        verbose_name="Photo du candidat",
        help_text="Format accepté: JPG, JPEG, PNG, WEBP",
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])],
    )
    cv = models.FileField(
        upload_to='recrutement/preconfig/cv/%Y/%m/',
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx'])],
        verbose_name="CV",
        help_text="Format accepté: PDF, DOC, DOCX",
    )
    lettre_motivation = models.FileField(
        upload_to='recrutement/preconfig/lettres/%Y/%m/',
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx'])],
        verbose_name="Lettre de motivation",
        help_text="Format accepté: PDF, DOC, DOCX",
    )
    screening_statut = models.CharField(
        max_length=20,
        choices=[
            ('a_analyser', 'A analyser'),
            ('invite_test', 'Invité au test'),
            ('test_complete', 'Test complete'),
            ('invite_entretien', 'Invité à l\'entretien'),
            ('entretien_complete', 'Entretien complete'),
            ('elimine', 'Éliminé'),
        ],
        default='a_analyser',
        verbose_name="Statut screening",
    )
    invite_test_envoyee = models.BooleanField(default=False, verbose_name="Invitation test envoyée")
    commentaire_analyse = models.TextField(blank=True, default='', verbose_name="Commentaire d'analyse")
    note_domicile = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="Note domicile")
    note_age = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="Note âge")
    note_formation = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="Note formation")
    note_experience = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="Note expérience")
    note_pretention = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="Note prétention")
    note_permis = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="Note permis")

    class Meta:
        db_table = 'candidats_preconfigures'
        verbose_name = "Candidat Préconfiguré"
        verbose_name_plural = "Candidats Préconfigurés"
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.email} - {self.poste.nom_poste}"

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}".strip() or self.email

    @property
    def age(self):
        if not self.date_naissance:
            return None
        today = timezone.localdate()
        years = today.year - self.date_naissance.year
        if (today.month, today.day) < (self.date_naissance.month, self.date_naissance.day):
            years -= 1
        return years

    @property
    def note_globale(self):
        notes = [
            self.note_domicile,
            self.note_age,
            self.note_formation,
            self.note_experience,
            self.note_pretention,
            self.note_permis,
        ]
        values = [float(note) for note in notes if note is not None]
        if not values:
            return None
        max_total = len(values) * 2
        if max_total <= 0:
            return None
        return round((sum(values) / max_total) * 100, 2)


class Candidat(models.Model):
    """Modèle pour les candidats qui postulent"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Compte utilisateur du candidat (créé automatiquement)"
    )

    # Informations personnelles
    nom = models.CharField(max_length=100, verbose_name="Nom")
    prenom = models.CharField(max_length=100, verbose_name="Prénom")
    email = models.EmailField(unique=True, verbose_name="Email")
    telephone = models.CharField(max_length=20, verbose_name="Téléphone")

    # Informations de candidature
    poste_souhaite = models.ForeignKey(
        'employees.Poste',
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Poste souhaité"
    )
    experience = models.TextField(
        verbose_name="Expérience professionnelle",
        help_text="Décrivez votre expérience professionnelle"
    )
    formation = models.TextField(
        verbose_name="Formation",
        help_text="Décrivez votre parcours de formation"
    )

    date_naissance = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de naissance"
    )
    adresse = models.TextField(
        blank=True,
        verbose_name="Adresse"
    )
    base = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name="Base"
    )

    # Documents
    cv = models.FileField(
        upload_to='recrutement/cv/%Y/%m/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx'])],
        verbose_name="CV",
        help_text="Format accepté: PDF, DOC, DOCX"
    )
    lettre_motivation = models.FileField(
        upload_to='recrutement/lettres/%Y/%m/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx'])],
        verbose_name="Lettre de motivation",
        help_text="Format accepté: PDF, DOC, DOCX"
    )

    # Statut
    date_candidature = models.DateTimeField(auto_now_add=True, verbose_name="Date de candidature")
    statut = models.CharField(
        max_length=20,
        choices=[
            ('en_attente', 'En attente'),
            ('test_en_cours', 'Test en cours'),
            ('test_termine', 'Test terminé'),
            ('retenu', 'Retenu'),
            ('rejete', 'Rejeté'),
        ],
        default='en_attente',
        verbose_name="Statut"
    )

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    convocation_entretien = models.BooleanField(
        default=False,
        verbose_name="Convocation entretien",
        help_text="Indique si le candidat est sélectionné pour un entretien"
    )

    class Meta:
        db_table = 'candidats'
        verbose_name = "Candidat"
        verbose_name_plural = "Candidats"
        ordering = ['-date_candidature']

    def __str__(self):
        return f"{self.prenom} {self.nom} - {self.poste_souhaite}"

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}"


class QuestionTest(models.Model):
    """Modèle pour les questions de test par poste"""
    TYPE_QUESTION_CHOICES = [
        ('qcm', 'QCM (Choix multiples)'),
        ('oui_non', 'Oui/Non'),
        ('chiffres', 'Chiffres'),
        ('texte_libre', 'Texte libre'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    poste = models.ForeignKey(
        'employees.Poste',
        on_delete=models.CASCADE,
        related_name='questions_test',
        verbose_name="Poste"
    )

    # Contenu de la question
    type_question = models.CharField(
        max_length=20,
        choices=TYPE_QUESTION_CHOICES,
        verbose_name="Type de question"
    )
    texte_question = models.TextField(verbose_name="Texte de la question")

    # Pour QCM : options séparées par des pipes |
    # Ex: "Option A|Option B|Option C|Option D"
    options_qcm = models.TextField(
        blank=True,
        null=True,
        verbose_name="Options QCM",
        help_text="Séparez les options par des pipes | (ex: Option A|Option B|Option C)"
    )

    # Réponse correcte
    reponse_correcte = models.TextField(
        verbose_name="Réponse correcte",
        help_text="Pour QCM: la lettre de l'option (A, B, C, etc.). Pour Oui/Non: 'oui' ou 'non'. Pour texte libre: mots-clés attendus"
    )

    # Points
    points = models.IntegerField(
        default=1,
        verbose_name="Points",
        help_text="Nombre de points pour cette question"
    )

    # Ordre d'affichage
    ordre = models.IntegerField(
        default=0,
        verbose_name="Ordre d'affichage"
    )

    # Statut
    active = models.BooleanField(
        default=True,
        verbose_name="Active",
        help_text="Décocher pour désactiver la question"
    )

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'questions_test'
        verbose_name = "Question de test"
        verbose_name_plural = "Questions de test"
        ordering = ['poste', 'ordre']

    def __str__(self):
        return f"{self.poste} - {self.get_type_question_display()} - Q{self.ordre}"

    def get_options_list(self):
        """Retourne la liste des options QCM"""
        if self.options_qcm:
            return self.options_qcm.split('|')
        return []


class SessionTest(models.Model):
    """Modèle pour une session de test d'un candidat"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidat = models.ForeignKey(
        Candidat,
        on_delete=models.CASCADE,
        related_name='sessions_test',
        verbose_name="Candidat"
    )

    # Timing
    date_debut = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de début"
    )
    date_fin = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de fin"
    )
    duree_limite = models.IntegerField(
        default=30,
        verbose_name="Durée limite (minutes)",
        help_text="Durée maximale du test en minutes"
    )

    # Statut
    statut = models.CharField(
        max_length=20,
        choices=[
            ('non_commence', 'Non commencé'),
            ('en_cours', 'En cours'),
            ('termine', 'Terminé'),
            ('expire', 'Expiré'),
        ],
        default='non_commence',
        verbose_name="Statut"
    )

    # Résultats
    score_obtenu = models.IntegerField(
        default=0,
        verbose_name="Score obtenu"
    )
    score_total = models.IntegerField(
        default=0,
        verbose_name="Score total possible"
    )
    pourcentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Pourcentage de réussite"
    )

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sessions_test'
        verbose_name = "Session de test"
        verbose_name_plural = "Sessions de test"
        ordering = ['-date_debut']

    def __str__(self):
        return f"Test de {self.candidat.nom_complet} - {self.statut}"

    def demarrer(self):
        """Démarre la session de test"""
        self.date_debut = timezone.now()
        self.statut = 'en_cours'
        self.save()

    def terminer(self):
        """Termine la session de test"""
        self.date_fin = timezone.now()
        self.statut = 'termine'
        self.save()

        # Calculer le score
        self.calculer_score()

        # Mettre à jour le statut du candidat
        self.candidat.statut = 'test_termine'
        self.candidat.save()

    def calculer_score(self):
        """Calcule le score final"""
        reponses = self.reponses.all()
        self.score_obtenu = sum(r.points_obtenus for r in reponses)
        self.score_total = sum(r.question.points for r in reponses)

        if self.score_total > 0:
            self.pourcentage = (self.score_obtenu / self.score_total) * 100
        else:
            self.pourcentage = 0

        self.save()

    def est_expire(self):
        """Vérifie si le test est expiré"""
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


class ReponseCandidat(models.Model):
    """Modèle pour les réponses d'un candidat"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        SessionTest,
        on_delete=models.CASCADE,
        related_name='reponses',
        verbose_name="Session de test"
    )
    question = models.ForeignKey(
        QuestionTest,
        on_delete=models.CASCADE,
        verbose_name="Question"
    )

    # Réponse du candidat
    reponse_donnee = models.TextField(verbose_name="Réponse donnée")

    # Évaluation
    est_correcte = models.BooleanField(
        default=False,
        verbose_name="Réponse correcte"
    )
    points_obtenus = models.IntegerField(
        default=0,
        verbose_name="Points obtenus"
    )

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reponses_candidat'
        verbose_name = "Réponse de candidat"
        verbose_name_plural = "Réponses de candidats"
        unique_together = ('session', 'question')

    def __str__(self):
        return f"Réponse de {self.session.candidat.nom_complet} - Q{self.question.ordre}"

    def evaluer(self):
        """Évalue automatiquement la réponse"""
        reponse_correcte = self.question.reponse_correcte.strip().lower()
        reponse_donnee = self.reponse_donnee.strip().lower()

        if self.question.type_question in ['qcm', 'oui_non', 'chiffres']:
            # Comparaison exacte pour QCM et Oui/Non
            self.est_correcte = (reponse_donnee == reponse_correcte)
        else:
            # Pour texte libre, vérifier si les mots-clés sont présents
            mots_cles = [m.strip() for m in reponse_correcte.split(',')]
            self.est_correcte = all(mot in reponse_donnee for mot in mots_cles)

        # Attribution des points
        if self.est_correcte:
            self.points_obtenus = self.question.points
        else:
            self.points_obtenus = 0

        self.save()


class EntretienQuestion(models.Model):
    # Questions d'entretien par poste
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    poste = models.ForeignKey(
        'employees.Poste',
        on_delete=models.CASCADE,
        related_name='questions_entretien',
        verbose_name="Poste"
    )
    texte_question = models.TextField(verbose_name="Question d'entretien")
    ordre = models.IntegerField(default=0, verbose_name="Ordre")
    active = models.BooleanField(default=True, verbose_name="Active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'questions_entretien'
        verbose_name = "Question d'entretien"
        verbose_name_plural = "Questions d'entretien"
        ordering = ['poste', 'ordre']

    def __str__(self):
        return f"{self.poste} - Q{self.ordre}"


class Entretien(models.Model):
    # Evaluation d'entretien d'un candidat
    DECISION_CHOICES = [
        ('retenu', 'Retenu'),
        ('rejete', 'Rejete'),
        ('autre', 'Autre'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidat = models.OneToOneField(
        Candidat,
        on_delete=models.CASCADE,
        related_name='entretien',
        verbose_name="Candidat"
    )
    poste = models.ForeignKey(
        'employees.Poste',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Poste"
    )
    date_entretien = models.DateField(null=True, blank=True, verbose_name="Date d'entretien")
    decision = models.CharField(
        max_length=20,
        choices=DECISION_CHOICES,
        blank=True,
        default='',
        verbose_name="Decision finale"
    )
    notes_generales = models.TextField(blank=True, default='', verbose_name="Notes generales")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'entretiens'
        verbose_name = "Entretien"
        verbose_name_plural = "Entretiens"

    def __str__(self):
        return f"Entretien - {self.candidat.nom_complet}"


class EntretienReponse(models.Model):
    # Reponses et remarques par question d'entretien
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entretien = models.ForeignKey(
        Entretien,
        on_delete=models.CASCADE,
        related_name='reponses',
        verbose_name="Entretien"
    )
    question = models.ForeignKey(
        EntretienQuestion,
        on_delete=models.CASCADE,
        related_name='reponses',
        verbose_name="Question"
    )
    reponse_candidat = models.TextField(blank=True, default='', verbose_name="Reponse du candidat")
    remarque = models.TextField(blank=True, default='', verbose_name="Remarque")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'entretiens_reponses'
        verbose_name = "Reponse d'entretien"
        verbose_name_plural = "Reponses d'entretien"
        unique_together = ('entretien', 'question')

    def __str__(self):
        return f"{self.entretien} - {self.question}"
