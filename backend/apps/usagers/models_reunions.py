"""
Modeles pour la gestion des reunions avec les usagers/representants et le suivi
de leurs decisions, participants, pieces jointes et depenses associees (DiameX).
"""

import uuid

from django.db import models
from django.utils import timezone


class TypeAutorite(models.Model):
    """
    Referentiel editable des types d'autorite (Maire, Chef Fokontany, ...), utilise pour
    peupler les choix du champ Autorite.type_autorite. Remplace l'ancienne liste TYPE_CHOICES
    figee dans le code : les valeurs de depart (voir migration de creation) reprennent les
    memes slugs que l'ancienne liste, pour ne rien casser sur les fiches Autorite existantes
    (le champ Autorite.type_autorite reste un simple CharField/slug, pas une FK, afin de ne
    pas changer le contrat JSON des APIs qui le lisent/ecrivent).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=30, unique=True, verbose_name="Code (slug)")
    nom = models.CharField(max_length=100, verbose_name="Nom")
    ordre = models.PositiveIntegerField(default=0, verbose_name="Ordre d'affichage")
    actif = models.BooleanField(default=True, verbose_name="Actif")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'types_autorite'
        verbose_name = "Type d'autorite"
        verbose_name_plural = "Types d'autorite"
        ordering = ['ordre', 'nom']
        indexes = [
            models.Index(fields=['actif']),
        ]

    def __str__(self):
        return self.nom


class Autorite(models.Model):
    """Referentiel des autorites locales (chef fokontany, maire, etc.) pouvant participer a des reunions."""

    # Slugs de depart (seed de la migration de creation de TypeAutorite), conserves ici comme
    # reference pour le code qui devrait exceptionnellement s'appuyer sur une valeur connue
    # (aucun usage de ce type actuellement, mais evite de "perdre" ces constantes).
    TYPE_MAIRE = 'maire'
    TYPE_CHEF_FOKONTANY = 'chef_fokontany'
    TYPE_CHEF_DISTRICT = 'chef_district'
    TYPE_CHEF_REGION = 'chef_region'
    TYPE_PREFET = 'prefet'
    TYPE_AUTRE = 'autre'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, verbose_name="Nom complet")
    type_autorite = models.CharField(
        max_length=30,
        blank=True,
        default='',
        db_index=True,
        verbose_name="Type d'autorite",
        help_text="Laisse vide pour les fiches existantes non encore qualifiees. Valeurs geree via le referentiel TypeAutorite (cf. Autorite.get_type_choices()).",
    )
    fonction = models.CharField(max_length=255, blank=True, null=True, verbose_name="Fonction")
    fokontany = models.ForeignKey(
        'geography.Fokontany',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='autorites',
        verbose_name="Fokontany de rattachement",
        help_text="Pour les autorites de niveau fokontany (chef fokontany) rattachees precisement a ce fokontany."
    )
    commune = models.ForeignKey(
        'geography.Commune',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='autorites',
        verbose_name="Commune de rattachement"
    )
    district = models.ForeignKey(
        'geography.District',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='autorites',
        verbose_name="District de rattachement",
        help_text="Pour les autorites de niveau district (chef district, prefet) sans commune precise."
    )
    region = models.ForeignKey(
        'geography.Region',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='autorites',
        verbose_name="Region de rattachement",
        help_text="Pour les autorites de niveau regional (chef region) sans district/commune precis."
    )
    email = models.EmailField(blank=True, null=True, verbose_name="Email")
    contact = models.CharField(max_length=50, blank=True, null=True, verbose_name="Contact (telephone)")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    observation = models.TextField(blank=True, null=True, verbose_name="Observations")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'autorites'
        verbose_name = "Autorite"
        verbose_name_plural = "Autorites"
        ordering = ['nom']
        indexes = [
            models.Index(fields=['fokontany']),
            models.Index(fields=['commune']),
            models.Index(fields=['district']),
            models.Index(fields=['region']),
            models.Index(fields=['actif']),
            models.Index(fields=['type_autorite']),
        ]

    def __str__(self):
        commune_nom = self.commune.nom_commune if self.commune else ''
        fonction = self.fonction or ''
        suffix = ' - '.join(part for part in [fonction, commune_nom] if part)
        return f"{self.nom} ({suffix})" if suffix else self.nom

    @classmethod
    def get_type_choices(cls):
        """
        Choix de type_autorite (slug, nom) a jour, lus depuis le referentiel TypeAutorite
        (types actifs uniquement). Remplace l'ancienne liste TYPE_CHOICES figee : tout le
        code qui peuplait un select ou validait une valeur avec Autorite.TYPE_CHOICES doit
        desormais appeler Autorite.get_type_choices() pour refleter les types geres depuis
        la page dediee (usagers:types_autorite_list).
        """
        return list(TypeAutorite.objects.filter(actif=True).order_by('ordre', 'nom').values_list('slug', 'nom'))

    def get_type_autorite_display(self):
        """
        Equivalent du get_FOO_display() genere automatiquement par Django pour un champ avec
        choices= : necessaire ici car type_autorite n'a plus de choices= statique (les choix
        viennent de TypeAutorite, cf. get_type_choices). Retombe sur le slug brut si le type
        a ete supprime du referentiel entre-temps (fiche existante orpheline).
        """
        if not self.type_autorite:
            return ''
        type_obj = TypeAutorite.objects.filter(slug=self.type_autorite).first()
        return type_obj.nom if type_obj else self.type_autorite

    @property
    def zone_affichee(self):
        """Zone geographique la plus precise disponible (fokontany > commune > district > region)."""
        if self.fokontany_id and self.fokontany:
            return f"{self.fokontany.nom_fokontany} ({self.fokontany.commune.nom_commune})"
        if self.commune_id and self.commune:
            return self.commune.nom_commune
        if self.district_id and self.district:
            return f"District {self.district.nom_district}"
        if self.region_id and self.region:
            return f"Region {self.region.nom_region}"
        return ''


class TiersParticipant(models.Model):
    """
    Referentiel des tiers (ONG, bailleurs, institutions, prestataires, personnes sans fiche
    employe/representant/autorite) pouvant participer a des reunions de facon recurrente.
    """

    TYPE_ONG = 'ong'
    TYPE_BAILLEUR = 'bailleur'
    TYPE_INSTITUTION = 'institution'
    TYPE_PRESTATAIRE = 'prestataire'
    TYPE_AUTRE = 'autre'
    TYPE_CHOICES = [
        (TYPE_ONG, 'ONG'),
        (TYPE_BAILLEUR, 'Bailleur'),
        (TYPE_INSTITUTION, 'Institution'),
        (TYPE_PRESTATAIRE, 'Prestataire'),
        (TYPE_AUTRE, 'Autre'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, verbose_name="Nom complet")
    type_tiers = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
        blank=True,
        default='',
        db_index=True,
        verbose_name="Type de tiers",
        help_text="Laisse vide pour les fiches existantes non encore qualifiees.",
    )
    organisme = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Organisme / structure",
        help_text="Nom de la structure ou organisation, distinct du nom de la personne physique."
    )
    fonction = models.CharField(max_length=255, blank=True, null=True, verbose_name="Fonction / qualite")
    email = models.EmailField(blank=True, null=True, verbose_name="Email")
    contact = models.CharField(max_length=50, blank=True, null=True, verbose_name="Contact (telephone)")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    observation = models.TextField(blank=True, null=True, verbose_name="Observations")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reunion_tiers_participants'
        verbose_name = "Tiers participant"
        verbose_name_plural = "Tiers participants"
        ordering = ['nom']
        indexes = [
            models.Index(fields=['actif']),
            models.Index(fields=['type_tiers']),
        ]

    def __str__(self):
        return f"{self.nom} ({self.fonction})" if self.fonction else self.nom


class Reunion(models.Model):
    """Reunion tenue avec les usagers d'une commune : objet, compte-rendu, recommandations, decisions."""
    TYPE_RESTITUTION_COMMUNALE = 'restitution_communale'
    TYPE_RESTITUTION_REGIONALE = 'restitution_regionale'
    TYPE_REUNION_EQUIPE = 'reunion_equipe'
    TYPE_CHOICES = [
        (TYPE_RESTITUTION_COMMUNALE, 'Restitution communale'),
        (TYPE_RESTITUTION_REGIONALE, 'Restitution regionale'),
        (TYPE_REUNION_EQUIPE, "Reunion d'equipe"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    type_reunion = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Type de reunion"
    )
    date_reunion = models.DateField(default=timezone.now, verbose_name="Date de la reunion", db_index=True)
    commune = models.ForeignKey(
        'geography.Commune',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reunions',
        verbose_name="Commune"
    )
    district = models.ForeignKey(
        'geography.District',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reunions',
        verbose_name="District",
        help_text="Renseigne pour les reunions/ateliers tenus au niveau district (sans commune precise)."
    )
    region = models.ForeignKey(
        'geography.Region',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reunions',
        verbose_name="Region",
        help_text="Renseigne pour les reunions/ateliers tenus au niveau regional (sans commune ni district precis)."
    )
    lieu = models.CharField(max_length=255, blank=True, null=True, verbose_name="Lieu")

    objet = models.CharField(max_length=255, verbose_name="Objet de la reunion")
    compte_rendu = models.TextField(blank=True, null=True, verbose_name="Compte-rendu")
    recommandations = models.TextField(blank=True, null=True, verbose_name="Recommandations")

    organise_par = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reunions_organisees',
        verbose_name="Organise par"
    )

    created_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reunions_creees',
        verbose_name="Cree par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reunions'
        verbose_name = "Reunion"
        verbose_name_plural = "Reunions"
        ordering = ['-date_reunion']
        indexes = [
            models.Index(fields=['commune']),
            models.Index(fields=['district']),
            models.Index(fields=['region']),
            models.Index(fields=['date_reunion']),
            models.Index(fields=['commune', 'date_reunion']),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(commune__isnull=False)
                    | models.Q(district__isnull=False)
                    | models.Q(region__isnull=False)
                ),
                name='reunion_commune_district_ou_region_requise',
            ),
        ]

    def __str__(self):
        return f"{self.objet} - {self.lieu_affiche} ({self.date_reunion})"

    @property
    def lieu_affiche(self):
        if self.commune_id and self.commune:
            return self.commune.nom_commune
        if self.district_id and self.district:
            return f"District {self.district.nom_district}"
        if self.region_id and self.region:
            return f"Region {self.region.nom_region}"
        return 'Lieu non precise'

    @property
    def nb_participants(self):
        return self.participants.count()

    @property
    def nb_decisions_en_cours(self):
        return self.decisions.exclude(statut=DecisionReunion.STATUT_REALISEE).count()

    @property
    def montant_depense_total(self):
        total = self.pointages_diamex.aggregate(
            total=models.Sum('montant')
        )['total']
        return total or 0


class ParticipantReunion(models.Model):
    """Participant a une reunion : peut etre un representant, un abonne, un employe, une autorite ou un tiers."""
    TYPE_REPRESENTANT = 'representant'
    TYPE_ABONNE = 'abonne'
    TYPE_EMPLOYE = 'employe'
    TYPE_AUTORITE = 'autorite'
    TYPE_TIERS = 'tiers'
    TYPE_CHOICES = [
        (TYPE_REPRESENTANT, 'Representant des usagers'),
        (TYPE_ABONNE, 'Abonne'),
        (TYPE_EMPLOYE, 'Employe'),
        (TYPE_AUTORITE, 'Autorite'),
        (TYPE_TIERS, 'Tiers'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reunion = models.ForeignKey(
        Reunion,
        on_delete=models.CASCADE,
        related_name='participants',
        verbose_name="Reunion"
    )
    type_participant = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name="Type de participant")

    # Liens vers un referentiel existant selon le type (un seul rempli a la fois)
    representant = models.ForeignKey(
        'usagers.RepresentantUsager',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='participations_reunions',
        verbose_name="Representant"
    )
    point_eau = models.ForeignKey(
        'billing.PointEau',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='participations_reunions',
        verbose_name="Point d'eau (abonne)"
    )
    employe = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='participations_reunions',
        verbose_name="Employe"
    )
    autorite = models.ForeignKey(
        Autorite,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='participations_reunions',
        verbose_name="Autorite"
    )
    tiers = models.ForeignKey(
        TiersParticipant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='participations_reunions',
        verbose_name="Tiers"
    )

    # Nom libre : conserve pour compatibilite avec les anciens participants "tiers" crees
    # avant l'ajout du referentiel TiersParticipant (aucune nouvelle creation ne doit s'appuyer
    # dessus, cf. participant_create qui exige desormais une fiche pour tous les types).
    nom_libre = models.CharField(max_length=255, blank=True, null=True, verbose_name="Nom (si pas de fiche liee)")
    fonction_libre = models.CharField(max_length=255, blank=True, null=True, verbose_name="Fonction / qualite")
    contact_libre = models.CharField(max_length=50, blank=True, null=True, verbose_name="Contact")

    present = models.BooleanField(default=True, verbose_name="Present")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reunion_participants'
        verbose_name = "Participant a une reunion"
        verbose_name_plural = "Participants aux reunions"
        ordering = ['type_participant', 'nom_libre']
        indexes = [
            models.Index(fields=['reunion']),
            models.Index(fields=['type_participant']),
        ]

    def __str__(self):
        return f"{self.nom_affiche} ({self.get_type_participant_display()})"

    @property
    def nom_affiche(self):
        if self.representant_id and self.representant:
            return self.representant.nom or 'Representant'
        if self.employe_id and self.employe:
            return self.employe.surnom or self.employe.nom or 'Employe'
        if self.autorite_id and self.autorite:
            return self.autorite.nom
        if self.tiers_id and self.tiers:
            return self.tiers.nom
        if self.point_eau_id and self.point_eau:
            return self.point_eau.nomabonne or 'Abonne'
        return self.nom_libre or 'Participant'


class ParticipantAttendu(models.Model):
    """
    Nombre de participants attendus pour une reunion, par type (representant, autorite,
    employe, tiers, abonne), permettant d'afficher un ratio "presents / attendus".

    Pre-rempli automatiquement a la creation de la reunion selon son type (cf.
    calculer_attendus_par_defaut dans views_reunions.py) : restitution communale
    (representantes = nb villages desservis par un ouvrage gere, maire = 1, employes = 2),
    restitution regionale (maires = nb communes avec ouvrage gere dans la region), reunion
    d'equipe (rien de pre-rempli). Reste editable manuellement dans tous les cas.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reunion = models.ForeignKey(
        Reunion,
        on_delete=models.CASCADE,
        related_name='attendus',
        verbose_name="Reunion"
    )
    type_participant = models.CharField(
        max_length=20,
        choices=ParticipantReunion.TYPE_CHOICES,
        verbose_name="Type de participant"
    )
    nombre_attendu = models.PositiveIntegerField(default=0, verbose_name="Nombre attendu")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reunion_participants_attendus'
        verbose_name = "Participants attendus (par type)"
        verbose_name_plural = "Participants attendus (par type)"
        ordering = ['type_participant']
        indexes = [
            models.Index(fields=['reunion']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['reunion', 'type_participant'],
                name='uniq_attendu_par_reunion_et_type',
            ),
        ]

    def __str__(self):
        return f"{self.reunion.objet} - {self.get_type_participant_display()}: {self.nombre_attendu} attendu(s)"


class DecisionReunion(models.Model):
    """Decision prise lors d'une reunion, avec suivi de sa realisation."""
    STATUT_A_FAIRE = 'a_faire'
    STATUT_EN_COURS = 'en_cours'
    STATUT_REALISEE = 'realisee'
    STATUT_ABANDONNEE = 'abandonnee'
    STATUT_CHOICES = [
        (STATUT_A_FAIRE, 'A faire'),
        (STATUT_EN_COURS, 'En cours'),
        (STATUT_REALISEE, 'Realisee'),
        (STATUT_ABANDONNEE, 'Abandonnee'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reunion = models.ForeignKey(
        Reunion,
        on_delete=models.CASCADE,
        related_name='decisions',
        verbose_name="Reunion"
    )
    description = models.TextField(verbose_name="Decision")
    responsable = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='decisions_reunions_a_suivre',
        verbose_name="Responsable du suivi"
    )
    date_echeance = models.DateField(blank=True, null=True, verbose_name="Date d'echeance")
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default=STATUT_A_FAIRE, verbose_name="Statut")
    date_realisation = models.DateField(blank=True, null=True, verbose_name="Date de realisation")
    commentaire_suivi = models.TextField(blank=True, null=True, verbose_name="Commentaire de suivi")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reunion_decisions'
        verbose_name = "Decision de reunion"
        verbose_name_plural = "Decisions de reunions"
        ordering = ['date_echeance', '-created_at']
        indexes = [
            models.Index(fields=['reunion']),
            models.Index(fields=['statut']),
            models.Index(fields=['date_echeance']),
        ]

    def __str__(self):
        return f"{self.description[:60]} ({self.get_statut_display()})"

    @property
    def est_en_retard(self):
        if self.statut in (self.STATUT_REALISEE, self.STATUT_ABANDONNEE):
            return False
        return bool(self.date_echeance and self.date_echeance < timezone.localdate())


def piece_jointe_reunion_upload_path(instance, filename):
    date_str = instance.reunion.date_reunion.strftime('%Y/%m') if instance.reunion_id and instance.reunion.date_reunion else 'sans-date'
    return f"reunions/{date_str}/{instance.reunion_id}/{filename}"


class PieceJointeReunion(models.Model):
    """Photo, video ou rapport joint a une reunion (fichier stocke localement sur le VPS)."""
    TYPE_PHOTO = 'photo'
    TYPE_VIDEO = 'video'
    TYPE_RAPPORT = 'rapport'
    TYPE_AUTRE = 'autre'
    TYPE_CHOICES = [
        (TYPE_PHOTO, 'Photo'),
        (TYPE_VIDEO, 'Video'),
        (TYPE_RAPPORT, 'Rapport'),
        (TYPE_AUTRE, 'Autre'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reunion = models.ForeignKey(
        Reunion,
        on_delete=models.CASCADE,
        related_name='pieces_jointes',
        verbose_name="Reunion"
    )
    type_piece = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_PHOTO, verbose_name="Type")
    fichier = models.FileField(upload_to=piece_jointe_reunion_upload_path, max_length=500, verbose_name="Fichier")
    legende = models.CharField(max_length=255, blank=True, null=True, verbose_name="Legende")

    uploaded_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pieces_jointes_reunions',
        verbose_name="Ajoute par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reunion_pieces_jointes'
        verbose_name = "Piece jointe de reunion"
        verbose_name_plural = "Pieces jointes de reunions"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['reunion']),
            models.Index(fields=['type_piece']),
        ]

    def __str__(self):
        return f"{self.get_type_piece_display()} - {self.reunion.objet}"


class PointageReunionDiameX(models.Model):
    """
    Pointage (lien) entre une reunion et une ligne comptable DiameX (comptes 608004/625300/625302),
    permettant de rattacher plusieurs lignes de depense a une meme reunion sans verifier de montant.

    Suit le meme principe de matching que le pointage forfaitaire/volumetrique : on stocke le couple
    (numero_diamex, base_diamex) qui identifie la ligne BaseDiameX (id_access, prog), plutot qu'une FK
    directe, car BaseDiameX est alimente par import Access et n'a pas de cle stable exploitable en FK.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reunion = models.ForeignKey(
        Reunion,
        on_delete=models.CASCADE,
        related_name='pointages_diamex',
        verbose_name="Reunion"
    )
    numero_diamex = models.CharField(max_length=50, verbose_name="Numero DiameX (ID Access)")
    base_diamex = models.CharField(max_length=50, verbose_name="Base DiameX (Prog)")
    entry_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="ID interne BaseDiameX",
        help_text="Cle primaire (AutoField) de la ligne BaseDiameX au moment du pointage, utilisee pour retrouver le scan associe."
    )

    # Copie des infos de la ligne au moment du pointage, pour affichage sans re-requeter Access/BaseDiameX
    date_transaction = models.DateField(blank=True, null=True, verbose_name="Date de la transaction")
    description = models.CharField(max_length=500, blank=True, null=True, verbose_name="Description (copie)")
    compte_code = models.CharField(max_length=20, blank=True, null=True, verbose_name="Code compte")
    montant = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Montant (copie)")

    pointe_par = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pointages_reunions_diamex',
        verbose_name="Pointe par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reunion_pointages_diamex'
        verbose_name = "Pointage reunion / DiameX"
        verbose_name_plural = "Pointages reunions / DiameX"
        ordering = ['-date_transaction']
        indexes = [
            models.Index(fields=['reunion']),
            models.Index(fields=['numero_diamex', 'base_diamex']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['numero_diamex', 'base_diamex'],
                name='uniq_pointage_reunion_diamex_ligne',
            ),
        ]

    def __str__(self):
        return f"{self.reunion.objet} <- {self.numero_diamex}/{self.base_diamex}"


class LigneDiameXIgnoreeReunion(models.Model):
    """
    Marque une ligne BaseDiameX des comptes de reunion comme "ne correspondant a aucune
    reunion" (ex: depense mal categorisee sur ce compte), pour la retirer de la liste de
    pointage sans creer de faux rattachement a une reunion existante.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero_diamex = models.CharField(max_length=50, verbose_name="Numero DiameX (ID Access)")
    base_diamex = models.CharField(max_length=50, verbose_name="Base DiameX (Prog)")
    entry_id = models.IntegerField(null=True, blank=True, verbose_name="ID interne BaseDiameX")
    motif = models.CharField(max_length=255, blank=True, null=True, verbose_name="Motif")
    ignore_par = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lignes_diamex_reunion_ignorees',
        verbose_name="Ignore par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reunion_lignes_diamex_ignorees'
        verbose_name = "Ligne DiameX ignoree (reunion)"
        verbose_name_plural = "Lignes DiameX ignorees (reunion)"
        indexes = [
            models.Index(fields=['numero_diamex', 'base_diamex']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['numero_diamex', 'base_diamex'],
                name='uniq_ligne_diamex_ignoree_reunion',
            ),
        ]

    def __str__(self):
        return f"Ignoree: {self.numero_diamex}/{self.base_diamex}"
