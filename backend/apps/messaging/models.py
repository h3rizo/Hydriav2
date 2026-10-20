from django.db import models
from django.contrib.auth.models import User
from apps.employees.models import Employe

class Conversation(models.Model):
    """Conversation individuelle ou de groupe"""
    TYPE_CHOICES = [
        ('direct', 'Conversation directe'),
        ('group', 'Groupe'),
    ]

    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='direct')
    nom_groupe = models.CharField(max_length=200, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    photo_groupe = models.ImageField(upload_to='conversations/', blank=True, null=True)
    createur = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='conversations_creees')
    date_creation = models.DateTimeField(auto_now_add=True)
    derniere_activite = models.DateTimeField(auto_now=True)
    archivee = models.BooleanField(default=False)

    class Meta:
        db_table = 'messaging_conversations'
        ordering = ['-derniere_activite']

    def __str__(self):
        if self.type == 'group':
            return self.nom_groupe or f"Groupe {self.id}"
        else:
            participants = self.participants.exclude(employe=self.createur)
            if participants.exists():
                emp = participants.first().employe
                nom = emp.surnom or emp.nom_employe
                return f"Chat avec {nom}"
            return f"Conversation {self.id}"

    @property
    def nombre_participants(self):
        return self.participants.count()

    @property
    def dernier_message(self):
        return self.messages.order_by('-date_envoi').first()

class Participant(models.Model):
    """Participant à une conversation"""
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='participants')
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='participations')
    date_ajout = models.DateTimeField(auto_now_add=True)
    date_derniere_lecture = models.DateTimeField(auto_now_add=True)
    notifications_activees = models.BooleanField(default=True)
    est_admin = models.BooleanField(default=False)  # Pour les groupes

    class Meta:
        db_table = 'messaging_participants'
        unique_together = ['conversation', 'employe']

    def __str__(self):
        nom = self.employe.surnom or self.employe.nom_employe
        return f"{nom} dans {self.conversation}"

    @property
    def messages_non_lus(self):
        return self.conversation.messages.filter(
            date_envoi__gt=self.date_derniere_lecture
        ).exclude(expediteur=self.employe).count()

class Message(models.Model):
    """Message dans une conversation"""
    TYPE_CHOICES = [
        ('text', 'Texte'),
        ('image', 'Image'),
        ('file', 'Fichier'),
        ('system', 'Message système'),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    expediteur = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='messages_envoyes', null=True, blank=True)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='text')
    contenu = models.TextField()
    fichier = models.FileField(upload_to='messages/', blank=True, null=True)
    date_envoi = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(null=True, blank=True)
    supprime = models.BooleanField(default=False)
    message_repondu = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='reponses')

    class Meta:
        db_table = 'messaging_messages'
        ordering = ['date_envoi']

    def __str__(self):
        if self.type == 'system':
            return f"[Système] {self.contenu[:50]}"
        nom = self.expediteur.surnom or self.expediteur.nom_employe if self.expediteur else "Inconnu"
        return f"{nom}: {self.contenu[:50]}"

class Call(models.Model):
    """Appel audio ou vidéo"""
    TYPE_CHOICES = [
        ('audio', 'Appel audio'),
        ('video', 'Appel vidéo'),
    ]

    STATUT_CHOICES = [
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
        ('manque', 'Manqué'),
        ('refuse', 'Refusé'),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='appels')
    initiateur = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='appels_inities')
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='audio')
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_cours')
    date_debut = models.DateTimeField(auto_now_add=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    duree_secondes = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'messaging_calls'
        ordering = ['-date_debut']

    def __str__(self):
        nom = self.initiateur.surnom or self.initiateur.nom_employe
        return f"{self.get_type_display()} - {nom} ({self.get_statut_display()})"

    @property
    def duree_formatee(self):
        if not self.duree_secondes:
            return "0:00"
        minutes = self.duree_secondes // 60
        secondes = self.duree_secondes % 60
        return f"{minutes}:{secondes:02d}"


class RelanceFacturesNonPointees(models.Model):
    """Trace l'envoi (ou tentative d'envoi) du rappel mensuel des factures
    non pointées à un responsable d'ouvrage, ou du rappel consolidé pour
    information envoyé à un supérieur hiérarchique."""

    STATUT_CHOICES = [
        ('envoye', 'Envoyé'),
        ('echec', 'Échec'),
        ('email_manquant', 'Email destinataire manquant'),
    ]

    TYPE_DESTINATAIRE_CHOICES = [
        ('responsable', 'Responsable direct d\'ouvrage'),
        ('superieur', 'Supérieur hiérarchique (pour information)'),
    ]

    employe = models.ForeignKey(
        Employe,
        on_delete=models.CASCADE,
        related_name='relances_factures_non_pointees',
        verbose_name="Employé destinataire",
    )
    type_destinataire = models.CharField(
        max_length=20,
        choices=TYPE_DESTINATAIRE_CHOICES,
        default='responsable',
        verbose_name="Type de destinataire",
        help_text="Distingue le responsable direct d'un ouvrage du supérieur hiérarchique notifié pour information.",
    )
    annee = models.PositiveIntegerField(verbose_name="Année de la période cible")
    mois = models.PositiveSmallIntegerField(verbose_name="Mois de la période cible (1-12)")

    email_destinataire = models.EmailField(
        null=True,
        blank=True,
        verbose_name="Email utilisé",
        help_text="Snapshot de l'email au moment de l'envoi",
    )
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, verbose_name="Statut")
    message_erreur = models.TextField(blank=True, verbose_name="Message d'erreur")

    nb_points_eau = models.PositiveIntegerField(default=0, verbose_name="Nombre de points d'eau inclus")
    nb_factures = models.PositiveIntegerField(default=0, verbose_name="Nombre de factures incluses")
    montant_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    est_test = models.BooleanField(default=False, verbose_name="Envoi de test")

    date_envoi = models.DateTimeField(null=True, blank=True, verbose_name="Date d'envoi effectif")
    created_at = models.DateTimeField(auto_now_add=True)

    email_message_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Identifiant message du service d'email",
        help_text=(
            "Identifiant retourné par le service d'envoi d'email, si disponible. "
            "Le backend SMTP standard Django (EmailMultiAlternatives.send()) ne "
            "retourne qu'un compteur de messages envoyés, jamais un identifiant "
            "exploitable — ce champ reste donc vide avec ce backend."
        ),
    )
    date_premiere_reponse = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de première réponse du responsable",
        help_text="Renseignée une seule fois, lors de la première soumission de commentaire liée à cette relance. Jamais écrasée ensuite.",
    )

    class Meta:
        db_table = 'messaging_relances_factures_non_pointees'
        verbose_name = 'Relance factures non pointées'
        verbose_name_plural = 'Relances factures non pointées'
        ordering = ['-annee', '-mois', 'employe']
        constraints = [
            models.UniqueConstraint(
                fields=['employe', 'annee', 'mois', 'type_destinataire'],
                condition=models.Q(est_test=False),
                name='uniq_relance_employe_periode_type_hors_test',
            ),
        ]
        indexes = [
            models.Index(fields=['annee', 'mois']),
            models.Index(fields=['statut']),
        ]

    def __str__(self):
        nom = self.employe.surnom or self.employe.nom_employe
        suffixe = ' (hiérarchie)' if self.type_destinataire == 'superieur' else ''
        return f"{nom} — {self.mois:02d}/{self.annee} ({self.get_statut_display()}){suffixe}"

    @property
    def date_generation(self):
        """Alias sémantique de created_at : moment où le contenu de la relance
        a été généré (quasi simultané à la création de la trace)."""
        return self.created_at


class CommentaireRelance(models.Model):
    """Commentaire libre d'un responsable sur un point d'eau, dans le cadre
    d'une relance de factures non pointées. N'a JAMAIS d'effet sur le
    pointage des factures (numeroDiameX/baseDiameX) : c'est une note
    d'information uniquement, jamais une action de pointage. Journal
    append-only : pas d'édition en place, chaque soumission ajoute une
    nouvelle entrée."""

    relance = models.ForeignKey(
        RelanceFacturesNonPointees,
        on_delete=models.CASCADE,
        related_name='commentaires',
        verbose_name="Relance d'origine",
    )
    employe_auteur = models.ForeignKey(
        Employe,
        on_delete=models.CASCADE,
        related_name='commentaires_relances_factures',
        verbose_name="Auteur du commentaire",
    )
    # Pattern entity_type/entity_id repris de notes/models.py (NoteLink/NoteTask/
    # NoteDecision), pas le ContentType framework — cohérence avec la convention
    # déjà établie dans le projet.
    entity_type = models.CharField(max_length=80, default='point_eau', verbose_name="Type d'entité visée")
    entity_id = models.CharField(max_length=120, verbose_name="Identifiant de l'entité visée (UUID en texte)")

    contenu = models.TextField(verbose_name="Commentaire")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'messaging_commentaires_relances_factures'
        verbose_name = 'Commentaire de relance factures non pointées'
        verbose_name_plural = 'Commentaires de relances factures non pointées'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['relance', 'entity_type', 'entity_id']),
            models.Index(fields=['employe_auteur']),
        ]

    def __str__(self):
        return f"Commentaire {self.employe_auteur} sur {self.entity_type}={self.entity_id} ({self.relance})"


class RelanceReparations(models.Model):
    """Trace l'envoi (ou tentative d'envoi) d'une relance de reparation
    echue a un responsable d'ouvrage ou un superieur hierarchique, dans le
    cadre du moteur de relance combine (voir apps.messaging.relance_engine).

    Contrairement a RelanceFacturesNonPointees, une reparation n'a pas de
    periode mensuelle intrinseque (elle est evaluee en continu, echue ou
    pas, independamment du mois). L'idempotence "ne pas re-notifier deux
    fois dans le meme cycle d'envoi" repose donc sur batch_id (UUID genere
    une fois par execution complete du moteur combine) plutot que sur
    annee/mois."""

    STATUT_CHOICES = [
        ('envoye', 'Envoyé'),
        ('echec', 'Échec'),
        ('email_manquant', 'Email destinataire manquant'),
    ]

    TYPE_DESTINATAIRE_CHOICES = [
        ('responsable', 'Responsable direct d\'ouvrage'),
        ('superieur', 'Supérieur hiérarchique (pour information)'),
    ]

    # FK vers Planning (pas apps.planning.models_reparations.Reparation) :
    # le vrai systeme de suivi des reparations en production repose sur
    # Planning classifie via repair_classification.get_repair_fiche_ids(),
    # pas sur le modele Reparation (vide, deconnecte de la production).
    reparation = models.ForeignKey(
        'planning.Planning',
        on_delete=models.CASCADE,
        related_name='relances',
        verbose_name="Réparation concernée",
    )
    employe = models.ForeignKey(
        Employe,
        on_delete=models.CASCADE,
        related_name='relances_reparations',
        verbose_name="Employé destinataire",
    )
    type_destinataire = models.CharField(
        max_length=20,
        choices=TYPE_DESTINATAIRE_CHOICES,
        default='responsable',
        verbose_name="Type de destinataire",
    )
    batch_id = models.UUIDField(verbose_name="Identifiant du cycle d'envoi")

    email_destinataire = models.EmailField(null=True, blank=True, verbose_name="Email utilisé")
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, verbose_name="Statut")
    message_erreur = models.TextField(blank=True, verbose_name="Message d'erreur")

    est_test = models.BooleanField(default=False, verbose_name="Envoi de test")

    nb_relances = models.PositiveIntegerField(
        default=1,
        verbose_name="Nombre de cycles ayant notifié ce destinataire pour cette réparation",
        help_text="Calculé à l'écriture par agrégation sur les cycles antérieurs (hors test) pour ce triplet réparation/employé/type.",
    )
    date_premiere_relance = models.DateTimeField(null=True, blank=True, verbose_name="Date de la première relance")
    date_derniere_relance = models.DateTimeField(null=True, blank=True, verbose_name="Date de la dernière relance")

    date_envoi = models.DateTimeField(null=True, blank=True, verbose_name="Date d'envoi effectif")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'messaging_relances_reparations'
        verbose_name = 'Relance réparation'
        verbose_name_plural = 'Relances réparations'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['reparation', 'employe', 'type_destinataire', 'batch_id'],
                condition=models.Q(est_test=False),
                name='uniq_relance_reparation_employe_type_batch_hors_test',
            ),
        ]
        indexes = [
            models.Index(fields=['batch_id']),
            models.Index(fields=['reparation', 'employe']),
            models.Index(fields=['statut']),
        ]

    def __str__(self):
        nom = self.employe.surnom or self.employe.nom_employe
        suffixe = ' (hiérarchie)' if self.type_destinataire == 'superieur' else ''
        return f"{nom} — {self.reparation_id} ({self.get_statut_display()}){suffixe}"


class DeviceToken(models.Model):
    """Jeton FCM (Firebase Cloud Messaging) d'un appareil, pour les notifications push
    de messagerie quand le destinataire n'a pas de connexion WebSocket active
    (app fermee ou en arriere-plan). Reste inerte tant que Firebase n'est pas
    configure cote serveur (cf. apps.messaging.push)."""
    PLATFORM_ANDROID = 'android'
    PLATFORM_CHOICES = [
        (PLATFORM_ANDROID, 'Android'),
    ]

    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='device_tokens')
    token = models.CharField(max_length=255, unique=True, verbose_name="Jeton FCM")
    plateforme = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default=PLATFORM_ANDROID)
    device_label = models.CharField(max_length=120, blank=True, null=True)
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'messaging_device_tokens'
        verbose_name = 'Jeton push (appareil)'
        verbose_name_plural = 'Jetons push (appareils)'
        indexes = [
            models.Index(fields=['employe', 'actif']),
        ]

    def __str__(self):
        nom = self.employe.surnom or self.employe.nom_employe
        return f"{nom} — {self.get_plateforme_display()} ({'actif' if self.actif else 'inactif'})"
