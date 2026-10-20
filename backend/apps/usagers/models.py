"""
Modèles pour la gestion des représentants des usagers et leurs avis
"""

from django.db import models
from django.utils import timezone
import uuid


class RepresentantUsager(models.Model):
    """Représentant des usagers d'un village"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    village = models.ForeignKey(
        'geography.Village',
        on_delete=models.CASCADE,
        related_name='representants_usagers',
        verbose_name="Village"
    )
    nom = models.CharField(max_length=255, blank=True, null=True, verbose_name="Nom complet")
    contact = models.CharField(max_length=50, blank=True, null=True, verbose_name="Contact (téléphone)")
    observation = models.TextField(blank=True, null=True, verbose_name="Observations")
    date_debut = models.DateField(blank=True, null=True, db_index=True, verbose_name="Date début")
    date_fin = models.DateField(blank=True, null=True, db_index=True, verbose_name="Date fin")
    actif = models.BooleanField(default=True, verbose_name="Actif")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'representants_usagers'
        verbose_name = "Représentante des usagers"
        verbose_name_plural = "Représentantes des usagers"
        ordering = ['village__nom_village', 'nom']
        indexes = [
            models.Index(fields=['village']),
            models.Index(fields=['actif']),
        ]

    def __str__(self):
        return f"{self.nom} ({self.village.nom_village})"

    @property
    def est_actif(self):
        today = timezone.localdate()
        if self.date_debut is not None or self.date_fin is not None:
            debut_ok = self.date_debut is None or self.date_debut <= today
            fin_ok = self.date_fin is None or self.date_fin >= today
            return debut_ok and fin_ok
        return self.actif


class AvisRepresentant(models.Model):
    """Avis recueilli auprès d'un représentant des usagers"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    representant = models.ForeignKey(
        RepresentantUsager,
        on_delete=models.CASCADE,
        related_name='avis',
        verbose_name="Représentant"
    )
    date_avis = models.DateField(default=timezone.now, verbose_name="Date de l'avis")
    employe = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='avis_recueillis',
        verbose_name="Employé ayant recueilli l'avis"
    )
    reunion = models.ForeignKey(
        'usagers.Reunion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='avis_recueillis',
        verbose_name="Réunion associée"
    )

    # Critères d'évaluation (Oui/Non)
    quantite_ok = models.BooleanField(default=False, verbose_name="Quantité d'eau suffisante")
    qualite_ok = models.BooleanField(default=False, verbose_name="Qualité de l'eau satisfaisante")
    delai_reparation_ok = models.BooleanField(default=False, verbose_name="Délai de réparation correct")
    relation_gestionnaire_ok = models.BooleanField(default=False, verbose_name="Bonne relation avec gestionnaire")

    # Champs problèmes (texte libre) - chaque champ renseigné compte comme point négatif
    probleme_technique = models.TextField(blank=True, null=True, verbose_name="Problème technique")
    probleme_recouvrement = models.TextField(blank=True, null=True, verbose_name="Problème de recouvrement")
    probleme_regles_utilisation = models.TextField(blank=True, null=True, verbose_name="Problème sur les règles d'utilisation")

    remarque = models.TextField(blank=True, null=True, verbose_name="Remarques")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'avis_representants'
        verbose_name = "Avis de représentante"
        verbose_name_plural = "Avis de représentantes"
        ordering = ['-date_avis', 'representant']
        indexes = [
            models.Index(fields=['representant']),
            models.Index(fields=['date_avis']),
            models.Index(fields=['employe']),
            models.Index(fields=['reunion']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['representant', 'date_avis'],
                name='uniq_avis_representant_date',
            ),
        ]

    def __str__(self):
        return f"Avis du {self.date_avis} - {self.representant.nom}"

    @property
    def score_satisfaction(self):
        """
        Calcule un score de satisfaction sur 4.
        Chaque problème renseigné retire 1 point (minimum 0).
        """
        score_positif = sum([
            self.quantite_ok,
            self.qualite_ok,
            self.delai_reparation_ok,
            self.relation_gestionnaire_ok
        ])
        penalites = sum([
            bool((self.probleme_technique or '').strip()),
            bool((self.probleme_recouvrement or '').strip()),
            bool((self.probleme_regles_utilisation or '').strip()),
        ])
        return max(0, score_positif - penalites)

    @property
    def pourcentage_satisfaction(self):
        """Pourcentage de satisfaction"""
        return (self.score_satisfaction / 4) * 100

    @property
    def est_negatif(self):
        """
        Un avis est negatif si au moins un probleme texte est renseigne, ou si les 4
        criteres sont tous a False. Meme regle que le dashboard des representants
        (apps.usagers.views.representants_list), pour rester coherent dans tout le projet.
        """
        if any([
            (self.probleme_technique or '').strip(),
            (self.probleme_recouvrement or '').strip(),
            (self.probleme_regles_utilisation or '').strip(),
        ]):
            return True
        return not any([
            self.quantite_ok,
            self.qualite_ok,
            self.delai_reparation_ok,
            self.relation_gestionnaire_ok,
        ])

    # Nombre total de criteres evalues par avis, utilise pour le taux "criteres negatifs /
    # total criteres" de la page reunions (cf. reunions_list). Different de est_negatif
    # (tout ou rien par avis) : ici chaque critere pese individuellement dans le taux.
    NB_CRITERES_TOTAL = 7  # 4 criteres booleens + 3 champs probleme (texte)

    @property
    def nb_criteres_negatifs(self):
        """
        Nombre de criteres negatifs sur les 7 evalues : un critere booleen est negatif si sa
        valeur est False, un champ probleme (texte libre) est negatif si renseigne (non vide).
        """
        criteres_booleens_negatifs = sum([
            not self.quantite_ok,
            not self.qualite_ok,
            not self.delai_reparation_ok,
            not self.relation_gestionnaire_ok,
        ])
        problemes_renseignes = sum([
            bool((self.probleme_technique or '').strip()),
            bool((self.probleme_recouvrement or '').strip()),
            bool((self.probleme_regles_utilisation or '').strip()),
        ])
        return criteres_booleens_negatifs + problemes_renseignes


class ReseauMeetingSession(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_OPEN = 'open'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Brouillon'),
        (STATUS_OPEN, 'Ouverte'),
        (STATUS_CONFIRMED, 'Confirmee'),
        (STATUS_CLOSED, 'Cloturee'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    titre = models.CharField(max_length=255, verbose_name="Titre")
    slug = models.SlugField(max_length=120, unique=True, verbose_name="Slug")
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    lieu = models.CharField(max_length=255, blank=True, null=True, verbose_name="Lieu")
    duree_minutes = models.PositiveIntegerField(default=60, verbose_name="Duree (minutes)")
    fuseau_horaire = models.CharField(max_length=64, default='Indian/Antananarivo', verbose_name="Fuseau horaire")
    seuil_confirmation = models.PositiveIntegerField(default=2, verbose_name="Seuil minimum")
    statut = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT, verbose_name="Statut")
    date_debut = models.DateField(blank=True, null=True, verbose_name="Date debut")
    date_fin = models.DateField(blank=True, null=True, verbose_name="Date fin")
    confirmed_slot = models.ForeignKey(
        'ReseauAvailabilitySlot',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='confirmed_for_sessions',
        verbose_name="Creneau confirme"
    )
    confirmation_envoyee_at = models.DateTimeField(blank=True, null=True, verbose_name="Confirmation envoyee le")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reseau_meeting_sessions'
        verbose_name = "Session reseau"
        verbose_name_plural = "Sessions reseau"
        ordering = ['-created_at']

    def __str__(self):
        return self.titre


class ReseauParticipant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ReseauMeetingSession,
        on_delete=models.CASCADE,
        related_name='participants',
        verbose_name="Session"
    )
    nom = models.CharField(max_length=255, verbose_name="Nom")
    email = models.EmailField(verbose_name="Email")
    telephone = models.CharField(max_length=50, blank=True, default='', verbose_name="Telephone")
    organisation = models.CharField(max_length=255, blank=True, default='', verbose_name="Organisation")
    google_calendar_email = models.EmailField(blank=True, null=True, verbose_name="Email Google Agenda")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    last_login_at = models.DateTimeField(blank=True, null=True, verbose_name="Dernier acces")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reseau_participants'
        verbose_name = "Participant reseau"
        verbose_name_plural = "Participants reseau"
        ordering = ['nom', 'email']
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'email'],
                name='uniq_reseau_participant_session_email',
            ),
        ]

    def __str__(self):
        return f"{self.nom} <{self.email}>"

    @property
    def calendar_email(self):
        return self.google_calendar_email or self.email


class ReseauAvailabilitySlot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ReseauMeetingSession,
        on_delete=models.CASCADE,
        related_name='slots',
        verbose_name="Session"
    )
    start_at = models.DateTimeField(verbose_name="Debut")
    end_at = models.DateTimeField(verbose_name="Fin")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reseau_availability_slots'
        verbose_name = "Creneau reseau"
        verbose_name_plural = "Creneaux reseau"
        ordering = ['start_at']
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'start_at', 'end_at'],
                name='uniq_reseau_slot_session_start_end',
            ),
        ]

    def __str__(self):
        return f"{self.session.titre} - {self.start_at:%d/%m/%Y %H:%M}"


class ReseauParticipantAvailability(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(
        ReseauParticipant,
        on_delete=models.CASCADE,
        related_name='availabilities',
        verbose_name="Participant"
    )
    slot = models.ForeignKey(
        ReseauAvailabilitySlot,
        on_delete=models.CASCADE,
        related_name='participant_availabilities',
        verbose_name="Creneau"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reseau_participant_availabilities'
        verbose_name = "Disponibilite participant reseau"
        verbose_name_plural = "Disponibilites participants reseau"
        constraints = [
            models.UniqueConstraint(
                fields=['participant', 'slot'],
                name='uniq_reseau_participant_slot',
            ),
        ]


class ReseauParticipantUnavailability(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(
        ReseauParticipant,
        on_delete=models.CASCADE,
        related_name='unavailabilities',
        verbose_name="Participant"
    )
    start_at = models.DateTimeField(verbose_name="Debut indisponibilite")
    end_at = models.DateTimeField(verbose_name="Fin indisponibilite")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reseau_participant_unavailabilities'
        verbose_name = "Indisponibilite participant reseau"
        verbose_name_plural = "Indisponibilites participants reseau"
        ordering = ['start_at']


class ReseauMeeting(models.Model):
    STATUS_PROPOSED = 'proposed'
    STATUS_PLANNED = 'planned'
    STATUS_COMPLETED = 'completed'
    STATUS_CHOICES = [
        (STATUS_PROPOSED, 'Propose'),
        (STATUS_PLANNED, 'Planifie'),
        (STATUS_COMPLETED, 'Termine'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ReseauMeetingSession,
        on_delete=models.CASCADE,
        related_name='meetings',
        verbose_name="Session"
    )
    slot = models.ForeignKey(
        ReseauAvailabilitySlot,
        on_delete=models.CASCADE,
        related_name='meetings',
        verbose_name="Creneau"
    )
    participants = models.ManyToManyField(
        ReseauParticipant,
        related_name='meetings',
        verbose_name="Participants au rendez-vous"
    )
    created_by = models.ForeignKey(
        ReseauParticipant,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='meetings_created',
        verbose_name="Propose par"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PROPOSED, verbose_name="Statut")
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name="Date de fin")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reseau_meetings'
        verbose_name = "Rendez-vous reseau"
        verbose_name_plural = "Rendez-vous reseau"
        ordering = ['-created_at']

    def __str__(self):
        return f"Rendez-vous le {self.slot.start_at:%d/%m/%Y %H:%M}"


class ReseauMeetingConfirmation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    meeting = models.ForeignKey(
        ReseauMeeting,
        on_delete=models.CASCADE,
        related_name='confirmations',
        verbose_name="Rendez-vous"
    )
    participant = models.ForeignKey(
        ReseauParticipant,
        on_delete=models.CASCADE,
        related_name='meeting_confirmations',
        verbose_name="Participant"
    )
    confirmed_at = models.DateTimeField(blank=True, null=True, verbose_name="Confirme le")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reseau_meeting_confirmations'
        verbose_name = "Confirmation rendez-vous reseau"
        verbose_name_plural = "Confirmations rendez-vous reseau"
        constraints = [
            models.UniqueConstraint(
                fields=['meeting', 'participant'],
                name='uniq_reseau_meeting_confirmation_participant',
            ),
        ]



class ReseauMagicLink(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(
        ReseauParticipant,
        on_delete=models.CASCADE,
        related_name='magic_links',
        verbose_name="Participant"
    )
    token = models.CharField(max_length=64, unique=True, verbose_name="Token")
    expires_at = models.DateTimeField(verbose_name="Expire le")
    used_at = models.DateTimeField(blank=True, null=True, verbose_name="Utilise le")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reseau_magic_links'
        verbose_name = "Lien magique reseau"
        verbose_name_plural = "Liens magiques reseau"
        ordering = ['-created_at']

    @property
    def is_valid(self):
        return self.used_at is None and self.expires_at >= timezone.now()


from .models_reunions import (  # noqa: E402
    Autorite,
    TypeAutorite,
    TiersParticipant,
    Reunion,
    ParticipantReunion,
    ParticipantAttendu,
    DecisionReunion,
    PieceJointeReunion,
    PointageReunionDiameX,
    LigneDiameXIgnoreeReunion,
)
