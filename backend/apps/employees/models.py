from django.db import models
from django.contrib.auth.models import User
from apps.organization.models import Organisation, Base, Compte
import uuid
from decimal import Decimal, ROUND_HALF_UP

# Import des modèles famille (frais médicaux et scolarité)
from .models_famille import FamilleEmploye, FraisMedicaux, FraisScolarite

# Import des modèles congés et permissions
from .models_conges import TypePermission, DemandeConge, SoldeConge

# Import des modèles récupérations
from .models_recuperations import Recuperation, SoldeRecuperation

# Import des modèles d'évaluation
from .models_evaluation import FichePoste, Evaluation, EvaluationDetail
from .models_evaluation_resultats import EvaluationResultats, EvaluationResultatsDetail

# Import des modèles gardiens
from .models_gardiens import RotationGardien, HeuresSupplementairesGardien

# Import des modèles de revalorisation salariale
from .models_revalorisation import GrilleSalariale, Revalorisation

# Import du modèle de template de grille salariale
from .models_grille_template import GrilleSalarialeTemplate

# Import des modèles de la grille salariale par stade d'autonomie
from .models_autonomie import (
    StadeAutonomie,
    GrilleAutonomie,
    HistoriqueStadeAutonomie,
    RegleDePrime,
    IndicateurPrime,
    PalierPrime,
    ResultatIndicateur,
    MajorationTerritoriale,
    SimulationRemuneration,
)


class HierarchieEmploye(models.Model):
    """Modèle pour gérer l'historique des relations hiérarchiques entre employés"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employe = models.ForeignKey(
        'Employe',
        on_delete=models.CASCADE,
        related_name='relations_hierarchiques',
        verbose_name="Employé"
    )
    superieur = models.ForeignKey(
        'Employe',
        on_delete=models.CASCADE,
        related_name='relations_subordonnes',
        verbose_name="Supérieur hiérarchique"
    )
    date_debut = models.DateField(verbose_name="Date de début")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Date de fin")
    commentaire = models.TextField(null=True, blank=True, verbose_name="Commentaire/Motif")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hierarchie_employes'
        verbose_name = 'Relation hiérarchique'
        verbose_name_plural = 'Relations hiérarchiques'
        ordering = ['-date_debut']

    def __str__(self):
        return f"{self.employe.nom_complet} -> {self.superieur.nom_complet} ({self.date_debut})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.employe_id == self.superieur_id:
            raise ValidationError("Un employé ne peut pas être son propre supérieur.")

        # Vérification des chevauchements de dates
        overlapping = HierarchieEmploye.objects.filter(
            employe=self.employe,
            date_debut__lte=self.date_fin if self.date_fin else '2099-12-31',
        ).exclude(pk=self.id)

        if self.date_fin:
            overlapping = overlapping.filter(
                models.Q(date_fin__gte=self.date_debut) | models.Q(date_fin__isnull=True)
            )
        else:
            overlapping = overlapping.filter(
                models.Q(date_fin__gte=self.date_debut) | models.Q(date_fin__isnull=True)
            )

        if overlapping.exists():
            pass # On laisse l'utilisateur gérer pour l'instant ou on l'alerte
            # raise ValidationError("Il existe déjà une relation hiérarchique pour cette période.")


class Poste(models.Model):
    """Modèle représentant les postes de travail dans les organisations"""

    MODE_REFERENCE_SALARIALE_CHOICES = [
        ('anciennete', "Ancienneté (grille classique)"),
        ('autonomie', "Stade d'autonomie"),
    ]

    # Mêmes catégories professionnelles que Contrat.categorie_professionnel,
    # réutilisées ici pour rattacher le poste à une classification standard.
    CATEGORIE_PROFESSIONNELLE_CHOICES = [
        ('3A', '3A'),
        ('M1', 'M1'),
        ('OP2B', 'OP2B'),
        ('OP3', 'OP3'),
        ('OS1', 'OS1'),
        ('HC', 'HC'),
    ]

    # Classification transversale du poste : "ce que fait le poste" (type) et
    # "son niveau de responsabilité" (niveau). Independant du stade d'autonomie
    # (qui mesure le degre de maitrise de la PERSONNE, pas du poste).
    TYPE_POSTE_CHOICES = [
        ('OPERATIONNEL', 'Opérationnel'),
        ('ADMINISTRATIF', 'Administratif'),
        ('SOUTIEN', 'Soutien'),
        ('TRANSVERSAL', 'Transversal'),
    ]

    NIVEAU_POSTE_CHOICES = [
        ('EXECUTION', 'Exécution'),
        ('MANAGEMENT', 'Management'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_poste = models.CharField(max_length=255, verbose_name="Nom du poste")
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='postes',
        db_column='organisation_id'
    )
    tarif_indemnite = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Tarif d'indemnité"
    )
    tarif_indemnite_demi_journee = models.DecimalField(
        max_digits=10, decimal_places=2, default=4000,
        verbose_name="Indemnité demi-journée",
        help_text="Montant par demi-journée pointée (matinée ou après-midi)."
    )
    tarif_indemnite_nuitee = models.DecimalField(
        max_digits=10, decimal_places=2, default=8000,
        verbose_name="Indemnité nuitée",
        help_text="Montant par nuitée pointée."
    )
    compte_salaire = models.ForeignKey(
        Compte,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='postes_salaire',
        db_column='compte_salaire_id',
        verbose_name="Compte salaire"
    )
    compte_irsa = models.ForeignKey(
        Compte,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='postes_irsa',
        db_column='compte_irsa_id',
        verbose_name="Compte IRSA"
    )
    compte_cnaps_fmfp_sante = models.ForeignKey(
        Compte,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='postes_cnaps_fmfp_sante',
        db_column='compte_cnaps_fmfp_sante_id',
        verbose_name="Compte CNAPS/FMFP/Santé"
    )
    compte_indemnite = models.ForeignKey(
        Compte,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='postes_indemnite',
        db_column='compte_indemnite_id',
        verbose_name="Compte Indemnité"
    )
    prefixe = models.CharField(max_length=10, null=True, blank=True, verbose_name="Préfixe")
    mode_reference_salariale = models.CharField(
        max_length=20,
        choices=MODE_REFERENCE_SALARIALE_CHOICES,
        default='anciennete',
        verbose_name="Mode de référence salariale",
        help_text="Détermine si ce poste utilise la grille par ancienneté (historique) ou par stade d'autonomie",
    )
    ordre_affichage = models.PositiveIntegerField(
        default=9999,
        verbose_name="Ordre d'affichage",
        help_text="Determine l'ordre de tri des postes dans les listes et grilles. Les postes sans ordre explicite (9999) sont tries apres ceux qui en ont un, par ordre alphabetique.",
    )
    categorie_professionnelle = models.CharField(
        max_length=10,
        choices=CATEGORIE_PROFESSIONNELLE_CHOICES,
        null=True,
        blank=True,
        verbose_name="Catégorie professionnelle",
    )
    competences_attributions = models.TextField(
        null=True,
        blank=True,
        verbose_name="Compétences et attributions",
        help_text="Description des compétences requises et des attributions du poste",
    )
    type_poste = models.CharField(
        max_length=20,
        choices=TYPE_POSTE_CHOICES,
        null=True,
        blank=True,
        verbose_name="Type de poste",
        help_text="Famille metier du poste (independant du niveau de responsabilite et du stade d'autonomie de la personne)",
    )
    niveau_poste = models.CharField(
        max_length=20,
        choices=NIVEAU_POSTE_CHOICES,
        null=True,
        blank=True,
        verbose_name="Niveau du poste",
        help_text="Niveau de responsabilite du poste (Execution ou Management)",
    )

    class Meta:
        db_table = 'postes'
        verbose_name = 'Poste'
        verbose_name_plural = 'Postes'
        ordering = ['organisation__nom_organisation', 'ordre_affichage', 'nom_poste']

    def __str__(self):
        return f"{self.nom_poste} ({self.organisation.nom_organisation})"


class Employe(models.Model):
    """Modèle représentant les employés des organisations"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Lien vers le compte utilisateur Django
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='employe',
        verbose_name="Compte utilisateur",
        help_text="Compte utilisateur Django lié à cet employé"
    )

    nom_employe = models.CharField(max_length=255, verbose_name="Nom complet de l'employé")
    nom = models.CharField(max_length=255, verbose_name="Nom de famille")
    prenom = models.CharField(max_length=255, null=True, blank=True, verbose_name="Prénom")
    surnom = models.CharField(max_length=255, null=True, blank=True, verbose_name="Surnom")
    poste = models.ForeignKey(
        Poste,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='employes',
        db_column='poste_id'
    )
    date_embauche = models.DateField(null=True, blank=True, verbose_name="Date d'embauche")
    date_sortie_junior = models.DateField(
        null=True, blank=True,
        verbose_name="Date de sortie du niveau Junior",
        help_text="Vide = encore Junior (non autonome). L'anciennete de la grille salariale "
                  "est comptee a partir de cette date.",
    )
    date_debauchage = models.DateField(null=True, blank=True, verbose_name="Date de débauche")
    base = models.ForeignKey(
        Base,
        on_delete=models.CASCADE,
        related_name='employes',
        db_column='base_id'
    )
    idxlsx = models.IntegerField(null=True, blank=True, verbose_name="IDxls")
    numero_cnaps = models.CharField(max_length=50, null=True, blank=True, verbose_name="Numéro CNAPS")
    numero_cin = models.CharField(max_length=50, null=True, blank=True, verbose_name="Numéro CIN")
    code_tiers = models.CharField(
        max_length=6,
        null=True,
        blank=True,
        unique=True,
        verbose_name="Code Tiers",
        help_text="Code tiers comptabilité (6 chiffres) - doit être unique"
    )
    telephone = models.CharField(max_length=20, null=True, blank=True, verbose_name="Téléphone")
    personnes_charge = models.IntegerField(default=0, verbose_name="Personnes à charge")
    salarie = models.BooleanField(default=True, verbose_name="Est salarié")
    mail = models.EmailField(null=True, blank=True, verbose_name="Email")
    volet = models.CharField(max_length=20, null=True, blank=True, verbose_name="Volet")
    signature = models.ImageField(
        upload_to='signatures/employes/', null=True, blank=True,
        verbose_name="Signature de l'employé"
    )

    # Nouveaux champs pour la mutuelle santé
    MUTUELLE_CHOICES = [
        ('AMIT', 'AMIT'),
        ('OSIEFSoVa', 'OSIEFSoVa'),
    ]
    mutuelle_sante = models.CharField(
        max_length=20,
        choices=MUTUELLE_CHOICES,
        null=True,
        blank=True,
        verbose_name="Mutuelle Santé",
        help_text="Organisme de mutuelle santé de l'employé"
    )

    GENRE_CHOICES = [
        ('M', 'Masculin'),
        ('F', 'Féminin'),
    ]
    genre = models.CharField(
        max_length=1,
        choices=GENRE_CHOICES,
        null=True,
        blank=True,
        verbose_name="Genre"
    )

    date_naissance = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de naissance"
    )
    adresse = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Adresse"
    )
    lieu_naissance = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Lieu de naissance"
    )
    lieu_delivrance_cin = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Lieu delivrance CIN"
    )
    date_delivrance_cin = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date delivrance CIN"
    )
    stade_autonomie_actuel = models.ForeignKey(
        'employees.StadeAutonomie',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employes_stade_actuel',
        verbose_name="Stade d'autonomie actuel",
        help_text="Stade d'autonomie actuel de l'employé, utilisé par la grille salariale par autonomie",
    )

    class Meta:
        db_table = 'employes'
        verbose_name = 'Employé'
        verbose_name_plural = 'Employés'
        ordering = ['base__organisation__nom_organisation', 'nom', 'prenom']

    def __str__(self):
        if self.prenom:
            return f"{self.prenom} {self.nom} ({self.base.nom_base})"
        return f"{self.nom} ({self.base.nom_base})"

    @property
    def nom_complet(self):
        """Retourne le nom complet de l'employé"""
        if self.prenom:
            return f"{self.prenom} {self.nom}"
        return self.nom

    @property
    def nom_affichage(self):
        """Retourne le nom d'affichage (surnom ou nom complet)"""
        return self.surnom or self.nom_complet

    @property
    def stade_autonomie_pivot(self):
        """
        Stade pivot (StadeAutonomie.declenche_anciennete) applicable a
        l'organisation de l'employe : le plus bas si plusieurs sont coches.
        A partir de ce stade, la remuneration ne plafonne plus (majoration
        d'anciennete). Retourne None si aucun stade pivot n'est configure.
        """
        organisation = self.base.organisation if self.base_id else None
        queryset = StadeAutonomie.objects.filter(declenche_anciennete=True)
        if organisation is not None:
            queryset = queryset.filter(
                models.Q(organisation=organisation) | models.Q(organisation__isnull=True)
            )
        return queryset.order_by('ordre').first()

    @property
    def date_debut_anciennete_autonomie(self):
        """
        Date a partir de laquelle l'anciennete "au sommet de grille" est comptee :
        premier acces a un stade dont l'ordre est >= a celui du stade pivot.
        Retourne None si pas de stade pivot ou pas d'historique.
        """
        pivot = self.stade_autonomie_pivot
        if pivot is None:
            return None
        entree = self.historique_stades_autonomie.filter(
            stade__ordre__gte=pivot.ordre
        ).order_by('date_effet').first()
        return entree.date_effet if entree else None

    def anciennete_autonomie_annees(self, date_reference=None):
        """
        Anciennete (en annees decimales, base 365.25) accumulee depuis le premier
        acces au stade pivot. Retourne Decimal('0') si non applicable.
        """
        import datetime as _dt
        debut = self.date_debut_anciennete_autonomie
        if debut is None:
            return Decimal('0')
        date_reference = date_reference or _dt.date.today()
        jours = (date_reference - debut).days
        if jours <= 0:
            return Decimal('0')
        return (Decimal(jours) / Decimal('365.25')).quantize(Decimal('0.01'))

    def est_junior(self, date_reference=None):
        """Junior tant qu'aucune date de sortie n'est saisie (ou qu'elle est future)."""
        import datetime as _dt
        date_reference = date_reference or _dt.date.today()
        return self.date_sortie_junior is None or self.date_sortie_junior > date_reference

    def anciennete_grille_annees(self, date_reference=None):
        """
        Anciennete (annees decimales, base 365.25) servant a la grille salariale :
        comptee depuis la sortie du niveau Junior. 0 pour un Junior.
        """
        import datetime as _dt
        date_reference = date_reference or _dt.date.today()
        if self.est_junior(date_reference):
            return Decimal('0')
        jours = (date_reference - self.date_sortie_junior).days
        return (Decimal(max(jours, 0)) / Decimal('365.25')).quantize(Decimal('0.01'))

    @property
    def superieur_hierarchique(self):
        """Retourne le supérieur hiérarchique actuel basé sur les dates"""
        from django.utils import timezone
        today = timezone.now().date()
        relation = self.relations_hierarchiques.filter(
            date_debut__lte=today
        ).filter(
            models.Q(date_fin__gte=today) | models.Q(date_fin__isnull=True)
        ).select_related('superieur').first()
        return relation.superieur if relation else None

    @property
    def ascendants(self):
        """Retourne la liste des supérieurs hiérarchiques actuels (du direct au plus haut)"""
        ascendants = []
        curr = self.superieur_hierarchique
        visited = {self.id}
        while curr and curr.id not in visited:
            ascendants.append(curr)
            visited.add(curr.id)
            curr = curr.superieur_hierarchique
        return ascendants

    @property
    def organisation(self):
        """Accès direct à l'organisation via la base"""
        return self.base.organisation

    @property
    def is_agent_recouvrement(self):
        """Vérifie si l'employé est un agent de recouvrement"""
        if self.poste:
            return 'recouvrement' in self.poste.nom_poste.lower() or 'agent' in self.poste.nom_poste.lower()
        return False

    @property
    def is_superviseur_technique(self):
        """Vérifie si l'employé est un superviseur technique"""
        if self.poste:
            return 'superviseur' in self.poste.nom_poste.lower() and 'technique' in self.poste.nom_poste.lower()
        return False

    @property
    def is_directeur(self):
        """Vérifie si l'employé est directeur ou a un poste de direction"""
        if self.poste:
            nom_poste_lower = self.poste.nom_poste.lower()
            return any(role in nom_poste_lower for role in ['directeur', 'direction', 'chef', 'responsable'])
        return False

    def get_accessible_ouvrages(self):
        """Retourne les ouvrages accessibles selon le rôle de l'employé"""
        from apps.organization.models import Ouvrage
        from apps.billing.models import ModaliteGestion

        if self.is_directeur:
            # Directeur : tous les ouvrages de l'organisation
            return Ouvrage.objects.filter(organisation=self.organisation)

        elif self.is_superviseur_technique:
            # Superviseur technique : ouvrages dont la modalité de gestion concerne les employés de sa base
            employes_meme_base = Employe.objects.filter(base=self.base)
            modalites = ModaliteGestion.objects.filter(employe__in=employes_meme_base)
            ouvrages_ids = modalites.values_list('ouvrage_id', flat=True)
            return Ouvrage.objects.filter(id__in=ouvrages_ids).distinct()

        elif self.is_agent_recouvrement:
            # Agent de recouvrement : uniquement les ouvrages avec modalité à son nom
            modalites = ModaliteGestion.objects.filter(employe=self)
            ouvrages_ids = modalites.values_list('ouvrage_id', flat=True)
            return Ouvrage.objects.filter(id__in=ouvrages_ids).distinct()

        else:
            # Par défaut : aucun ouvrage
            return Ouvrage.objects.none()

    def get_accessible_plannings(self):
        """Retourne les plannings accessibles selon le rôle de l'employé"""
        from apps.planning.models import Planning, PlanningEmploye

        if self.is_directeur:
            # Directeur : tous les plannings de l'organisation
            ouvrages = self.get_accessible_ouvrages()
            return Planning.objects.filter(ouvrage__in=ouvrages)

        elif self.is_superviseur_technique:
            # Superviseur technique : plannings des employés de sa base
            employes_meme_base = Employe.objects.filter(base=self.base)
            return Planning.objects.filter(
                planning_employees__employee__in=employes_meme_base
            ).distinct()

        elif self.is_agent_recouvrement:
            # Agent de recouvrement : uniquement ses propres plannings
            return Planning.objects.filter(
                planning_employees__employee=self
            ).distinct()

        else:
            # Par défaut : aucun planning
            return Planning.objects.none()


class ClientUser(models.Model):
    """Modèle représentant les clients/usagers reliés à des points d'eau"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Lien vers le compte utilisateur Django
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='client',
        verbose_name="Compte utilisateur",
        help_text="Compte utilisateur Django lié à ce client"
    )

    # Informations personnelles
    nom = models.CharField(max_length=255, verbose_name="Nom de famille")
    prenom = models.CharField(max_length=255, verbose_name="Prénom")
    telephone = models.CharField(max_length=20, null=True, blank=True, verbose_name="Téléphone")
    email = models.EmailField(null=True, blank=True, verbose_name="Email")

    # Relation avec le point d'eau
    point_eau = models.ForeignKey(
        'billing.PointEau',
        on_delete=models.CASCADE,
        related_name='clients',
        verbose_name="Point d'eau",
        help_text="Point d'eau auquel ce client est relié"
    )

    # Dates
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Date de modification")
    actif = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        db_table = 'clients_users'
        verbose_name = 'Client utilisateur'
        verbose_name_plural = 'Clients utilisateurs'
        ordering = ['nom', 'prenom']

    def __str__(self):
        return f"{self.prenom} {self.nom} ({self.point_eau.nom})"

    @property
    def nom_complet(self):
        """Retourne le nom complet du client"""
        return f"{self.prenom} {self.nom}"

    @property
    def ouvrage(self):
        """Retourne l'ouvrage lié au point d'eau"""
        return self.point_eau.ouvrage if self.point_eau else None

    def get_factures_impayees(self):
        """Retourne les factures impayées pour ce point d'eau"""
        from apps.billing.models import Releve
        return Releve.objects.filter(
            point_eau=self.point_eau,
            montant__isnull=False,
            facture_imprimee=True,
            numeroDiameX__isnull=True  # Non payé
        ).order_by('-datereleve')


class Contrat(models.Model):
    """Modèle représentant les contrats de travail des employés"""
    CATEGORIE_CHOICES = [
        ('3A', '3A'),
        ('M1', 'M1'),
        ('OP2B', 'OP2B'),
        ('OP3', 'OP3'),
        ('OS1', 'OS1'),
        ('HC', 'HC'),
    ]

    TYPE_CHOICES = [
        ('temps_plein', 'Temps plein'),
        ('temps_partiel', 'Temps partiel'),
        ('journalier', 'Journalier'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employe = models.ForeignKey(
        Employe,
        on_delete=models.CASCADE,
        related_name='contrats',
        db_column='employe_id'
    )
    debut_contrat = models.DateField(verbose_name="Début du contrat")
    fin_contrat = models.DateField(null=True, blank=True, verbose_name="Fin du contrat")
    poste = models.ForeignKey(
        Poste,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contrats',
        verbose_name="Poste occupé durant ce contrat",
        help_text="Permet de gérer l'historique des postes pour la vérification comptable"
    )
    categorie_professionnel = models.CharField(
        max_length=100, choices=CATEGORIE_CHOICES, null=True, blank=True,
        verbose_name="Catégorie professionnelle"
    )
    type_contrat = models.CharField(
        max_length=100, choices=TYPE_CHOICES, null=True, blank=True,
        verbose_name="Type de contrat"
    )
    quotite_temps_travail = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('100.00'),
        verbose_name="Quotite de temps de travail (%)",
        help_text="100 = temps plein, 50 = mi-temps, 25 = quart-temps. "
                  "Sert a proratiser les fourchettes de la grille salariale.",
    )
    salaire_brut_base = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        null=True,  # Permet NULL dans la base de données
        blank=True,  # Permet de laisser vide dans les formulaires, sera converti en 0
        verbose_name="Salaire brut de base (Ar)",
        help_text="Salaire brut de base mensuel défini dans le contrat"
    )

    class Meta:
        db_table = 'contrats'
        verbose_name = 'Contrat'
        verbose_name_plural = 'Contrats'
        ordering = ['employe__nom', 'employe__prenom', '-debut_contrat']

    def __str__(self):
        return f"Contrat {self.employe.nom_complet} ({self.debut_contrat})"

    @property
    def is_active(self):
        """Vérifie si le contrat est actuellement actif"""
        from django.utils import timezone
        today = timezone.now().date()
        return (self.debut_contrat <= today and
                (self.fin_contrat is None or self.fin_contrat >= today))


class ContratArticleModele(models.Model):
    """Modele d'article de contrat editable par organisation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='contrat_articles_modeles',
        db_column='organisation_id'
    )
    numero_article = models.PositiveIntegerField(verbose_name="Numero d'article")
    contenu_article = models.TextField(verbose_name="Contenu de l'article")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contrat_articles_modeles'
        verbose_name = "Modele d'article contrat"
        verbose_name_plural = "Modeles d'articles contrat"
        ordering = ['numero_article', 'date_creation']
        unique_together = ('organisation', 'numero_article')

    def __str__(self):
        return f"Article {self.numero_article} - {self.organisation.nom_organisation}"


class ContratTravail(models.Model):
    """Contrat de travail redige a partir d'un contrat RH et de modeles d'articles."""

    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('imprime', 'Imprime'),
        ('classe', 'Classe'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contrat = models.OneToOneField(
        Contrat,
        on_delete=models.CASCADE,
        related_name='contrat_travail'
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='contrats_travail',
        db_column='organisation_id'
    )
    nom_directeur = models.CharField(max_length=255, blank=True, verbose_name="Nom complet directeur")
    poste_directeur = models.CharField(max_length=255, blank=True, verbose_name="Poste directeur")
    districts_affectation = models.CharField(max_length=255, blank=True, verbose_name="Districts d'affectation")
    adresse_employe = models.CharField(max_length=255, blank=True, verbose_name="Adresse employe")
    lieu_naissance_employe = models.CharField(max_length=255, blank=True, verbose_name="Lieu de naissance employe")
    lieu_delivrance_cin = models.CharField(max_length=255, blank=True, verbose_name="Lieu delivrance CIN")
    date_delivrance_cin = models.DateField(null=True, blank=True, verbose_name="Date delivrance CIN")
    duree_contrat_texte = models.CharField(
        max_length=120,
        default='determinee',
        blank=True,
        verbose_name="Duree contrat (texte)"
    )
    lieu_contrat = models.CharField(max_length=255, blank=True, verbose_name="Lieu contrat")
    date_signature = models.DateField(null=True, blank=True, verbose_name="Date signature")
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='brouillon')
    date_impression = models.DateTimeField(null=True, blank=True)
    date_classement = models.DateTimeField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contrats_travail'
        verbose_name = "Contrat de travail"
        verbose_name_plural = "Contrats de travail"
        ordering = ['-date_creation']

    def __str__(self):
        return f"Contrat travail - {self.contrat.employe.nom_complet}"


class ContratTravailArticle(models.Model):
    """Article rattache a un contrat de travail avec contenu actuel et reference."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contrat_travail = models.ForeignKey(
        ContratTravail,
        on_delete=models.CASCADE,
        related_name='articles'
    )
    modele = models.ForeignKey(
        ContratArticleModele,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='articles_contrats'
    )
    numero_article = models.PositiveIntegerField(verbose_name="Numero d'article")
    contenu_article = models.TextField(verbose_name="Contenu article")
    contenu_reference = models.TextField(
        blank=True,
        default='',
        verbose_name="Contenu de reference (dernier contenu applique)"
    )
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contrats_travail_articles'
        verbose_name = "Article contrat de travail"
        verbose_name_plural = "Articles contrat de travail"
        ordering = ['numero_article']
        unique_together = ('contrat_travail', 'numero_article')

    def __str__(self):
        return f"Contrat {self.contrat_travail_id} - Article {self.numero_article}"


class AvenantContratTravail(models.Model):
    """Avenant de contrat construit uniquement avec les articles modifies."""

    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('imprime', 'Imprime'),
        ('classe', 'Classe'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contrat_travail = models.ForeignKey(
        ContratTravail,
        on_delete=models.CASCADE,
        related_name='avenants'
    )
    numero_avenant = models.PositiveIntegerField(verbose_name="Numero avenant")
    motif = models.TextField(blank=True, verbose_name="Motif")
    date_effet = models.DateField(null=True, blank=True, verbose_name="Date d'effet")
    date_signature = models.DateField(null=True, blank=True, verbose_name="Date signature")
    lieu_signature = models.CharField(max_length=255, blank=True, verbose_name="Lieu signature")
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='brouillon')
    est_applique = models.BooleanField(default=False, verbose_name="Applique au contrat")
    date_application = models.DateTimeField(null=True, blank=True)
    date_impression = models.DateTimeField(null=True, blank=True)
    date_classement = models.DateTimeField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'avenants_contrats_travail'
        verbose_name = "Avenant contrat de travail"
        verbose_name_plural = "Avenants contrats de travail"
        ordering = ['-date_creation']
        unique_together = ('contrat_travail', 'numero_avenant')

    def __str__(self):
        return f"Avenant {self.numero_avenant} - {self.contrat_travail.contrat.employe.nom_complet}"


class AvenantArticleModifie(models.Model):
    """Historique de modification d'article dans un avenant."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    avenant = models.ForeignKey(
        AvenantContratTravail,
        on_delete=models.CASCADE,
        related_name='articles_modifies'
    )
    article_contrat = models.ForeignKey(
        ContratTravailArticle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='historique_avenants'
    )
    numero_article = models.PositiveIntegerField(verbose_name="Numero d'article")
    ancien_contenu = models.TextField(blank=True, verbose_name="Ancien contenu")
    nouveau_contenu = models.TextField(blank=True, verbose_name="Nouveau contenu")

    class Meta:
        db_table = 'avenants_articles_modifies'
        verbose_name = "Article modifie avenant"
        verbose_name_plural = "Articles modifies avenant"
        ordering = ['numero_article']

    def __str__(self):
        return f"Avenant {self.avenant.numero_avenant} - Article {self.numero_article}"


class Salaire(models.Model):
    """Modèle représentant les paiements effectifs des salaires"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grille_salaire = models.ForeignKey(
        'GrilleSalaire',
        on_delete=models.CASCADE,
        related_name='salaires',
        db_column='grille_salaire_id'
    )
    date_paiement = models.DateField(verbose_name="Date de paiement")

    # Montants payés (calculés automatiquement depuis la grille)
    salaire_net_paye = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name="Salaire net payé",
        help_text="Calculé depuis salaire net arrondi de la grille"
    )
    irsa_paye = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name="IRSA payé",
        help_text="Calculé depuis la grille"
    )
    cnaps_paye = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name="CNAPS payé",
        help_text="Égal à 14 fois la charge CNaPS employé"
    )
    fmfp_paye = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name="FMFP payé",
        help_text="Égal à la charge CNaPS employé"
    )
    mutuelle_sante_paye = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name="Mutuelle santé payée",
        help_text="Calculé depuis la grille"
    )

    # Numéros DiameX (à remplir dans le workflow)
    numero_diamex_salaire = models.CharField(
        max_length=50, null=True, blank=True,
        verbose_name="Numéro DiameX Salaire"
    )
    numero_diamex_irsa = models.CharField(
        max_length=50, null=True, blank=True,
        verbose_name="Numéro DiameX IRSA"
    )
    numero_diamex_cnaps = models.CharField(
        max_length=50, null=True, blank=True,
        verbose_name="Numéro DiameX CNAPS"
    )
    numero_diamex_fmfp = models.CharField(
        max_length=50, null=True, blank=True,
        verbose_name="Numéro DiameX FMFP"
    )
    numero_diamex_mutuelle_sante = models.CharField(
        max_length=50, null=True, blank=True,
        verbose_name="Numéro DiameX Mutuelle Santé"
    )

    # Bases DiameX (à remplir dans le workflow)
    base_diamex_salaire = models.CharField(
        max_length=255, null=True, blank=True,
        verbose_name="Base DiameX Salaire"
    )
    base_diamex_irsa = models.CharField(
        max_length=255, null=True, blank=True,
        verbose_name="Base DiameX IRSA"
    )
    base_diamex_cnaps = models.CharField(
        max_length=255, null=True, blank=True,
        verbose_name="Base DiameX CNAPS"
    )
    base_diamex_fmfp = models.CharField(
        max_length=255, null=True, blank=True,
        verbose_name="Base DiameX FMFP"
    )
    base_diamex_mutuelle_sante = models.CharField(
        max_length=255, null=True, blank=True,
        verbose_name="Base DiameX Mutuelle Santé"
    )

    # Suivi de l'impression de la fiche de paie
    fiche_imprimee = models.BooleanField(
        default=False,
        verbose_name="Fiche de paie imprimée",
        help_text="Indique si la fiche de paie a été imprimée"
    )
    date_impression = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date d'impression",
        help_text="Date et heure de la première impression de la fiche de paie"
    )

    class Meta:
        db_table = 'salaires'
        verbose_name = 'Salaire'
        verbose_name_plural = 'Salaires'
        ordering = ['grille_salaire__contrat__employe__nom', 'grille_salaire__contrat__employe__prenom', '-date_paiement']

    def __str__(self):
        return f"Paiement {self.grille_salaire.contrat.employe.nom_complet} ({self.date_paiement})"


class PaiementIRSA(models.Model):
    """Modèle pour gérer les paiements IRSA mensuels par organisation"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    organisation = models.ForeignKey(
        'organization.Organisation',
        on_delete=models.CASCADE,
        related_name='paiements_irsa',
        verbose_name="Organisation"
    )
    mois = models.IntegerField(verbose_name="Mois (1-12)")
    annee = models.IntegerField(verbose_name="Année")
    date_paiement = models.DateField(verbose_name="Date de paiement", help_text="Date de paiement effectif de l'IRSA")

    # Montants globaux
    montant_total_brut = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Total salaires bruts")
    montant_total_base_imposable = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Total base imposable")
    montant_total_irsa = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Total IRSA")

    # Suivi de l'impression et validation
    facture_generee = models.BooleanField(default=False, verbose_name="Facture générée")
    date_generation = models.DateTimeField(null=True, blank=True, verbose_name="Date de génération de la facture")
    fichier_facture = models.CharField(max_length=500, null=True, blank=True, verbose_name="Chemin du fichier de facture")

    # Suivi de l'impression de la facture IRSA
    facture_imprimee = models.BooleanField(
        default=False,
        verbose_name="Facture imprimée",
        help_text="Indique si la facture IRSA a été imprimée - empêche le recalcul et déclenche l'export"
    )
    date_impression = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date d'impression",
        help_text="Date et heure de la première impression de la facture IRSA"
    )

    statut = models.CharField(
        max_length=20,
        choices=[
            ('brouillon', 'Brouillon'),
            ('valide', 'Validé'),
            ('paye', 'Payé'),
        ],
        default='brouillon',
        verbose_name="Statut"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='paiements_irsa_crees',
        verbose_name="Créé par"
    )

    class Meta:
        db_table = 'paiements_irsa'
        verbose_name = 'Paiement IRSA'
        verbose_name_plural = 'Paiements IRSA'
        unique_together = ('organisation', 'mois', 'annee')
        ordering = ['-annee', '-mois']

    def __str__(self):
        return f"IRSA {self.organisation.nom_organisation} - {self.mois:02d}/{self.annee}"


class PaiementIRSADetail(models.Model):
    """Détail des paiements IRSA par employé"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    paiement_irsa = models.ForeignKey(
        PaiementIRSA,
        on_delete=models.CASCADE,
        related_name='details',
        verbose_name="Paiement IRSA"
    )
    salaire = models.ForeignKey(
        Salaire,
        on_delete=models.CASCADE,
        related_name='paiements_irsa',
        verbose_name="Salaire"
    )

    # Informations employé (dénormalisées pour historique)
    employe_nom_complet = models.CharField(max_length=255, verbose_name="Nom complet")
    employe_fonction = models.CharField(max_length=255, null=True, blank=True, verbose_name="Fonction")

    # Montants IRSA
    salaire_brut = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Salaire brut")
    base_imposable = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Base imposable")
    montant_irsa = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Montant IRSA")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'paiements_irsa_details'
        verbose_name = 'Détail paiement IRSA'
        verbose_name_plural = 'Détails paiements IRSA'
        ordering = ['employe_fonction', 'employe_nom_complet']

    def __str__(self):
        return f"{self.employe_nom_complet} - {self.montant_irsa} Ar"


class PositionGPSEmploye(models.Model):
    """Modèle pour enregistrer les positions GPS des employés lors de leurs connexions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    employe = models.ForeignKey(
        Employe,
        on_delete=models.CASCADE,
        related_name='positions_gps',
        db_column='employe_id',
        verbose_name="Employé"
    )

    # Date et heure de la connexion/enregistrement
    date_enregistrement = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date d'enregistrement"
    )

    # Coordonnées GPS
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        verbose_name="Latitude",
        help_text="Latitude GPS (ex: -18.9332847)"
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        verbose_name="Longitude",
        help_text="Longitude GPS (ex: 47.5360256)"
    )
    altitude = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Altitude (m)",
        help_text="Altitude en mètres"
    )
    precision = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Précision (m)",
        help_text="Précision de la mesure GPS en mètres"
    )

    # Village le plus proche
    village_proche = models.ForeignKey(
        'geography.Village',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='positions_employes',
        verbose_name="Village le plus proche",
        help_text="Village le plus proche calculé automatiquement"
    )
    distance_village = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Distance au village (km)",
        help_text="Distance calculée jusqu'au village le plus proche"
    )

    # Informations supplémentaires
    type_connexion = models.CharField(
        max_length=20,
        choices=[
            ('login', 'Connexion'),
            ('manual', 'Manuel'),
            ('auto', 'Automatique')
        ],
        default='login',
        verbose_name="Type d'enregistrement"
    )
    adresse_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="Adresse IP"
    )
    user_agent = models.TextField(
        null=True,
        blank=True,
        verbose_name="User Agent",
        help_text="Informations du navigateur/appareil"
    )

    # Vérification de présence sur site
    est_sur_site = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="Est sur site",
        help_text="L'employé est-il proche d'un équipement de l'ouvrage planifié?"
    )
    est_hors_zone = models.BooleanField(
        default=False,
        verbose_name="Hors zone",
        help_text="L'employé est-il à plus de 10 km du village le plus proche?"
    )
    ouvrage_planifie = models.ForeignKey(
        'organization.Ouvrage',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='positions_employes',
        verbose_name="Ouvrage planifié",
        help_text="Ouvrage trouvé dans le planning du jour"
    )
    distance_equipement_proche = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Distance équipement (m)",
        help_text="Distance en mètres vers l'équipement le plus proche"
    )
    equipement_proche = models.ForeignKey(
        'infrastructure.EquipementConstitutif',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='positions_employes',
        verbose_name="Équipement proche",
        help_text="Équipement le plus proche détecté"
    )

    class Meta:
        db_table = 'positions_gps_employes'
        verbose_name = 'Position GPS Employé'
        verbose_name_plural = 'Positions GPS Employés'
        ordering = ['-date_enregistrement']
        indexes = [
            models.Index(fields=['employe', '-date_enregistrement']),
            models.Index(fields=['village_proche']),
            models.Index(fields=['-date_enregistrement']),
        ]

    def __str__(self):
        if self.village_proche:
            return f"{self.employe.nom_complet} - {self.date_enregistrement.strftime('%d/%m/%Y %H:%M')} - Près de {self.village_proche.nom_village}"
        return f"{self.employe.nom_complet} - {self.date_enregistrement.strftime('%d/%m/%Y %H:%M')}"

    def calculer_village_proche(self):
        """
        Calcule le village le plus proche en utilisant la formule de Haversine
        Retourne le village et la distance en km
        """
        if not self.latitude or not self.longitude:
            return None, None

        from apps.geography.models import Village
        from math import radians, cos, sin, asin, sqrt

        # Récupérer tous les villages avec coordonnées GPS
        villages_avec_gps = Village.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False
        )

        if not villages_avec_gps.exists():
            return None, None

        def haversine(lon1, lat1, lon2, lat2):
            """
            Calcule la distance entre deux points GPS en kilomètres
            en utilisant la formule de Haversine
            """
            # Convertir en radians
            lon1, lat1, lon2, lat2 = map(radians, [float(lon1), float(lat1), float(lon2), float(lat2)])

            # Formule de Haversine
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a))

            # Rayon de la Terre en kilomètres
            r = 6371

            return c * r

        # Trouver le village le plus proche
        village_proche = None
        distance_min = float('inf')

        for village in villages_avec_gps:
            distance = haversine(
                self.longitude, self.latitude,
                village.longitude, village.latitude
            )

            if distance < distance_min:
                distance_min = distance
                village_proche = village

        return village_proche, distance_min

    def verifier_presence_sur_site(self, rayon_metres=500):
        """
        Vérifie si l'employé est proche d'un équipement de l'ouvrage planifié.

        Args:
            rayon_metres: Rayon en mètres pour considérer l'employé "sur site" (défaut: 500m)

        Returns:
            tuple: (est_sur_site, ouvrage, distance_min, equipement_proche)
        """
        if not self.latitude or not self.longitude:
            return None, None, None, None

        from apps.planning.models import Planning, PlanningDetail
        from apps.infrastructure.models import EquipementConstitutif
        from datetime import date
        from math import radians, sin, cos, asin, sqrt

        def haversine_metres(lon1, lat1, lon2, lat2):
            """Calcule la distance en mètres entre deux points GPS"""
            lon1, lat1, lon2, lat2 = map(radians, [float(lon1), float(lat1), float(lon2), float(lat2)])
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a))
            return c * 6371 * 1000  # Retourne en mètres

        # Trouver le planning du jour pour cet employé
        if not self.date_enregistrement:
            from django.utils import timezone
            date_connexion = timezone.now().date()
        else:
            date_connexion = self.date_enregistrement.date()

        # Chercher dans Planning
        from apps.planning.models import Planning
        plannings_du_jour = Planning.objects.filter(
            employe=self.employe,
            date__date=date_connexion
        ).select_related('ouvrage')

        if not plannings_du_jour.exists():
            # Pas de planning trouvé
            return False, None, None, None

        # Pour chaque ouvrage planifié, chercher les équipements avec GPS
        equipement_le_plus_proche = None
        distance_min = float('inf')
        ouvrage_trouve = None

        for planning_detail in plannings_du_jour:
            ouvrage = planning_detail.ouvrage
            if not ouvrage:
                continue

            # Récupérer les équipements de cet ouvrage avec coordonnées GPS
            equipements = EquipementConstitutif.objects.filter(
                ouvrage=ouvrage,
                latitude__isnull=False,
                longitude__isnull=False
            )

            # Calculer la distance vers chaque équipement
            for equipement in equipements:
                distance = haversine_metres(
                    self.longitude, self.latitude,
                    equipement.longitude, equipement.latitude
                )

                if distance < distance_min:
                    distance_min = distance
                    equipement_le_plus_proche = equipement
                    ouvrage_trouve = ouvrage

        # Déterminer si l'employé est sur site (dans le rayon défini)
        if distance_min <= rayon_metres:
            est_sur_site = True
        else:
            est_sur_site = False if ouvrage_trouve else None

        return est_sur_site, ouvrage_trouve, distance_min if distance_min != float('inf') else None, equipement_le_plus_proche

    def save(self, *args, **kwargs):
        """Override save pour calculer automatiquement le village proche et vérifier la présence sur site"""
        # Si on a des coordonnées GPS
        if self.latitude and self.longitude:
            # Calculer le village proche si pas encore fait
            if not self.village_proche:
                village, distance = self.calculer_village_proche()
                if village:
                    self.village_proche = village
                    self.distance_village = round(distance, 2)

            # Marquer comme "hors zone" si distance au village > 10 km
            if self.distance_village is not None:
                self.est_hors_zone = (float(self.distance_village) > 10.0)

            # Vérifier la présence sur site si pas encore fait
            if self.est_sur_site is None:
                est_sur_site, ouvrage, distance, equipement = self.verifier_presence_sur_site()
                self.est_sur_site = est_sur_site
                self.ouvrage_planifie = ouvrage
                if distance is not None:
                    self.distance_equipement_proche = round(distance, 2)
                self.equipement_proche = equipement

        super().save(*args, **kwargs)


class EmployeBaseDiameX(models.Model):
    """Association entre un employé et ses bases DiameX pour l'import comptabilité"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employe = models.ForeignKey(
        'Employe',
        on_delete=models.CASCADE,
        related_name='bases_diamex',
        verbose_name="Employé"
    )
    chemin_base_diamex = models.CharField(
        max_length=500,
        verbose_name="Chemin dossier DiameX",
        help_text="Chemin du dossier pour prefixer les scans (ex: G:\\Mon Drive\\Compta\\)"
    )
    base_diamex = models.CharField(
        max_length=255,
        verbose_name="Nom fichier Base DiameX",
        help_text="Nom du fichier Access (ex: base.accdb, JIRAMA.mdb)"
    )

    @property
    def chemin_complet(self):
        """Retourne le chemin complet = chemin_base_diamex + base_diamex"""
        import os
        return os.path.join(self.chemin_base_diamex, self.base_diamex)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'employe_bases_diamex'
        verbose_name = 'Base DiameX Employé'
        verbose_name_plural = 'Bases DiameX Employés'
        unique_together = ('employe', 'base_diamex')
        ordering = ['employe__surnom', 'base_diamex']

    def __str__(self):
        return f"{self.employe.surnom or self.employe.nom_employe} - {self.base_diamex}"


class EmployeOuvrages(models.Model):
    """
    Table de liaison entre les employés et les ouvrages dont ils sont responsables.
    Utilisée pour le cloisonnement des données et les alertes.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employe = models.ForeignKey(
        'Employe',
        on_delete=models.CASCADE,
        related_name='ouvrages_responsable',
        verbose_name="Employé"
    )
    ouvrage = models.ForeignKey(
        'organization.Ouvrage',
        on_delete=models.CASCADE,
        related_name='employes_responsables',
        verbose_name="Ouvrage"
    )
    date_debut = models.DateField(
        verbose_name="Date de début",
        help_text="Date à partir de laquelle l'employé est responsable de cet ouvrage"
    )
    date_fin = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de fin",
        help_text="Date de fin de la responsabilité (null = responsabilité active)"
    )
    est_responsable_principal = models.BooleanField(
        default=False,
        verbose_name="Responsable principal",
        help_text="Indique si cet employé est le responsable principal de l'ouvrage"
    )
    recevoir_alertes = models.BooleanField(
        default=True,
        verbose_name="Recevoir les alertes",
        help_text="L'employé reçoit les alertes concernant cet ouvrage"
    )
    notes = models.TextField(
        null=True,
        blank=True,
        verbose_name="Notes",
        help_text="Notes sur la responsabilité de l'employé"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'employe_ouvrages'
        verbose_name = 'Responsabilité Ouvrage'
        verbose_name_plural = 'Responsabilités Ouvrages'
        unique_together = ('employe', 'ouvrage', 'date_debut')
        ordering = ['-date_debut', 'ouvrage__nom_ouvrage']
        indexes = [
            models.Index(fields=['employe', 'date_fin']),
            models.Index(fields=['ouvrage', 'date_fin']),
            models.Index(fields=['est_responsable_principal']),
        ]

    def __str__(self):
        status = "Responsable principal" if self.est_responsable_principal else "Responsable"
        active = "Actif" if self.date_fin is None else f"Jusqu'au {self.date_fin}"
        return f"{self.employe.surnom or self.employe.nom_employe} - {self.ouvrage.nom_ouvrage} ({status}, {active})"

    @property
    def est_actif(self):
        """Retourne True si la responsabilité est active (date_fin est None ou dans le futur)"""
        from datetime import date
        if self.date_fin is None:
            return True
        return self.date_fin >= date.today()


class ConfigSalaire(models.Model):
    """
    Configuration globale des paramètres de calcul des salaires.
    Cette table ne devrait contenir qu'une seule ligne (singleton).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    salaire_minimum = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Salaire minimum (Ar)",
        help_text="Salaire minimum légal en Ariary"
    )

    deduction_irsa = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Déduction IRSA (Ar)",
        help_text="Montant de la déduction IRSA forfaitaire en Ariary"
    )

    minimum_irsa = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Minimum IRSA (Ar)",
        help_text="Montant minimum d'IRSA à prélever en Ariary"
    )

    indemnite_hors_zone = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Indemnité hors zone (Ar)",
        help_text="Montant de l'indemnité hors zone"
    )

    indemnite_terrain = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Indemnité terrain (Ar)",
        help_text="Montant de l'indemnité terrain"
    )

    indemnite_herizo = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Indemnité Herizo (Ar)",
        help_text="Montant de l'indemnité Herizo"
    )

    remuneration_nette_min_autorisee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Rémunération nette minimum autorisée (Ar)",
        help_text="Borne basse pour le contrôle de cohérence de la grille par autonomie (laisser vide pour désactiver)",
    )

    remuneration_nette_max_autorisee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Rémunération nette maximum autorisée (Ar)",
        help_text="Borne haute pour le contrôle de cohérence de la grille par autonomie (laisser vide pour désactiver)",
    )

    seuil_alerte_progression_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal('50.00'),
        verbose_name="Seuil d'alerte progression entre stades (%)",
        help_text="Au-delà de ce pourcentage d'augmentation entre deux stades consécutifs, une alerte de cohérence est levée",
    )

    taux_anciennete_autonomie_defaut_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal('3.00'),
        verbose_name="Taux d'ancienneté annuel par défaut (%)",
        help_text="Grille par autonomie : majoration d'ancienneté appliquée à partir du stade « Autonome 100 % » "
                  "quand la grille ne précise pas son propre taux. Ex : 3.00 pour +3 %/an.",
    )

    plafond_anciennete_autonomie_annees = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal('15.00'),
        verbose_name="Plafond d'ancienneté comptée par défaut (années)",
        help_text="Grille par autonomie : nombre maximal d'années d'ancienneté prises en compte dans la majoration "
                  "quand la grille ne précise pas son propre plafond.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'config_salaire'
        verbose_name = 'Configuration Salaire'
        verbose_name_plural = 'Configuration Salaire'

    def __str__(self):
        return f"Config Salaire - Min: {self.salaire_minimum} Ar | Déduction IRSA: {self.deduction_irsa} Ar"

    def save(self, *args, **kwargs):
        """
        Override save pour assurer qu'il n'y a qu'une seule ligne dans la table (singleton).
        """
        # Si c'est une nouvelle instance et qu'une config existe déjà
        if not self.pk and ConfigSalaire.objects.exists():
            # Ne pas créer, mettre à jour l'existant
            existing = ConfigSalaire.objects.first()
            existing.salaire_minimum = self.salaire_minimum
            existing.deduction_irsa = self.deduction_irsa
            existing.minimum_irsa = self.minimum_irsa
            existing.indemnite_hors_zone = self.indemnite_hors_zone
            existing.indemnite_terrain = self.indemnite_terrain
            existing.indemnite_herizo = self.indemnite_herizo
            existing.remuneration_nette_min_autorisee = self.remuneration_nette_min_autorisee
            existing.remuneration_nette_max_autorisee = self.remuneration_nette_max_autorisee
            existing.seuil_alerte_progression_pct = self.seuil_alerte_progression_pct
            existing.taux_anciennete_autonomie_defaut_pct = self.taux_anciennete_autonomie_defaut_pct
            existing.plafond_anciennete_autonomie_annees = self.plafond_anciennete_autonomie_annees
            super(ConfigSalaire, existing).save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    @classmethod
    def get_config(cls):
        """
        Méthode helper pour récupérer la configuration (singleton).
        Crée une config par défaut si elle n'existe pas.
        """
        # Vérifier s'il existe déjà une config
        config = cls.objects.first()
        if config:
            return config

        # Sinon, créer une nouvelle config avec valeurs par défaut
        config = cls.objects.create(
            salaire_minimum=0,
            deduction_irsa=0,
            minimum_irsa=0,
            indemnite_hors_zone=0,
            indemnite_terrain=0,
            indemnite_herizo=0
        )
        return config


class ConfigTrancheIRSA(models.Model):
    """
    Configuration des tranches de calcul de l'IRSA.
    Chaque ligne représente une tranche avec sa borne supérieure et son pourcentage.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    tranche_superieure = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Tranche supérieure (Ar)",
        help_text="Montant maximum de cette tranche en Ariary (ex: 350000 pour 0-350000)"
    )

    pourcentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Pourcentage (%)",
        help_text="Pourcentage d'IRSA applicable à cette tranche (ex: 5 pour 5%)"
    )

    ordre = models.IntegerField(
        default=0,
        verbose_name="Ordre",
        help_text="Ordre d'application des tranches (1, 2, 3...)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'config_tranches_irsa'
        verbose_name = 'Tranche IRSA'
        verbose_name_plural = 'Tranches IRSA'
        ordering = ['ordre', 'tranche_superieure']
        indexes = [
            models.Index(fields=['ordre']),
            models.Index(fields=['tranche_superieure']),
        ]

    def __str__(self):
        return f"Tranche {self.ordre}: jusqu'à {self.tranche_superieure} Ar → {self.pourcentage}%"

    @classmethod
    def calculer_irsa(cls, base_imposable):
        """
        Calcule l'IRSA pour une base imposable donnée en appliquant les tranches.

        Args:
            base_imposable (Decimal): Montant de la base imposable

        Returns:
            Decimal: Montant de l'IRSA calculé
        """
        from decimal import Decimal, ROUND_HALF_UP

        tranches = cls.objects.all().order_by('ordre', 'tranche_superieure')
        irsa_total = Decimal('0')
        montant_restant = Decimal(str(base_imposable))
        tranche_precedente = Decimal('0')

        for tranche in tranches:
            # Montant de cette tranche
            montant_tranche = tranche.tranche_superieure - tranche_precedente

            # Montant à taxer dans cette tranche
            if montant_restant <= 0:
                break

            montant_taxable = min(montant_restant, montant_tranche)

            # Calcul de l'IRSA pour cette tranche
            irsa_tranche = montant_taxable * (tranche.pourcentage / Decimal('100'))
            irsa_total += irsa_tranche

            # Mise à jour pour la prochaine tranche
            montant_restant -= montant_taxable
            tranche_precedente = tranche.tranche_superieure

        return irsa_total


class GrilleSalaire(models.Model):
    """
    Modèle représentant la grille de salaire d'un employé pour un mois donné.
    Contient tous les calculs de salaire avec les majorations et déductions.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relations
    contrat = models.ForeignKey(
        Contrat,
        on_delete=models.CASCADE,
        related_name='grilles_salaire',
        verbose_name="Contrat"
    )

    # Date de référence
    date_salaire = models.DateField(
        verbose_name="Date du salaire",
        help_text="Date de référence pour ce salaire (généralement premier jour du mois)"
    )

    # Données saisies par l'utilisateur
    personnes_charge = models.IntegerField(
        default=0,
        verbose_name="Personnes à charge",
        help_text="Nombre de personnes à charge (récupéré depuis l'employé par défaut)"
    )
    nb_jours_presence = models.IntegerField(
        default=0,
        verbose_name="Nombre de jours de présence",
        help_text="Nombre de jours travaillés (journalier) ou de présence dans le mois (prorata temps plein/partiel)"
    )
    est_prorata = models.BooleanField(
        default=False,
        verbose_name="Calcul au prorata",
        help_text="Si True, le salaire brut total = salaire brut base × (nb_jours_presence / 30)"
    )
    nb_jours_feries_gardien = models.IntegerField(
        default=0,
        verbose_name="Jours fériés gardien",
        help_text="Nombre de jours fériés officiels travaillés (majoration 50%)"
    )
    nb_jours_chomes_payes = models.IntegerField(
        default=0,
        verbose_name="Jours chômés et payés travaillés",
        help_text="Nombre de jours chômés et payés (décret ponctuel) travaillés - majoration 30%"
    )
    nb_dimanches_travailles = models.IntegerField(
        default=0,
        verbose_name="Dimanches travailles",
        help_text="Nombre de dimanches travailles sur le mois de salaire"
    )
    a_travaille_1er_mai = models.BooleanField(
        default=False,
        verbose_name="Travaille le 1er Mai",
        help_text="Cocher si le gardien a travaille le 1er Mai (majore double d'un jour ferie normal)"
    )
    nb_heures_remplacement_gardien = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        verbose_name="Heures remplacement gardien",
        help_text="Nombre d'heures de remplacement (gardiens uniquement) - majoration 100% fixe"
    )
    nb_heures_remplacement_ordinaire_gardien = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        verbose_name="Heures remplacement (jour ordinaire) gardien",
        help_text="Part des heures de remplacement tombant un jour ordinaire - majoration 30% supplémentaire"
    )
    nb_heures_nuit_gardien = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        verbose_name="Heures de nuit gardien",
        help_text="Heures de nuit calculées depuis les rotations du gardien"
    )
    nb_heures_dimanche_gardien = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        verbose_name="Heures du dimanche gardien",
        help_text="Heures travaillées le dimanche calculées depuis les rotations"
    )
    nb_heures_feries_gardien = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        verbose_name="Heures fériées gardien",
        help_text="Heures travaillées les jours fériés officiels, hors 1er mai"
    )
    nb_heures_chomes_payes = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        verbose_name="Heures jours chômés et payés",
        help_text="Heures travaillées les jours chômés et payés (décret ponctuel)"
    )
    nb_heures_1er_mai_gardien = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        verbose_name="Heures du 1er mai gardien",
        help_text="Heures travaillées le 1er mai calculées depuis les rotations"
    )

    # Salaires - objectif à atteindre (valeur cible)
    salaire_net_cible = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Salaire net cible (Ar)",
        help_text="Salaire net souhaité - le salaire brut sera calculé automatiquement"
    )
    salaire_brut_base = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Salaire brut de base (Ar)",
        help_text="Salaire brut de base (calculé automatiquement si salaire net cible fourni)"
    )

    # Champs calculés automatiquement
    majoration_nuit_gardien = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Majoration nuit gardien (Ar)"
    )
    majoration_dimanche_gardien = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Majoration dimanche gardien (Ar)"
    )
    montant_jours_feries_gardien = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Montant jours f??ri??s gardien (Ar)"
    )
    montant_jours_chomes_payes = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Montant jours chômés et payés (Ar)"
    )
    montant_majoration_1er_mai = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Montant majoration 1er Mai (Ar)"
    )
    montant_remplacement_gardien = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Montant remplacement gardien (Ar)"
    )
    salaire_brut_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Salaire brut total (Ar)"
    )
    charge_cnaps_employe = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Charge CNaPS employé (Ar)"
    )
    base_imposable = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Base imposable (Ar)"
    )
    deduction_impots = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Déduction d'impôts (Ar)"
    )
    irsa = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="IRSA (Ar)"
    )
    mutuelle_sante = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Mutuelle Santé (Ar)",
        help_text="1% de (salaire_brut_total - charge_cnaps_employe)"
    )
    salaire_net = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Salaire net (Ar)"
    )

    # Métadonnées
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='grilles_salaire_creees',
        verbose_name="Créé par"
    )

    class Meta:
        db_table = 'grilles_salaire'
        verbose_name = 'Grille de salaire'
        verbose_name_plural = 'Grilles de salaire'
        ordering = ['-date_salaire', 'contrat__employe__nom']
        unique_together = ('contrat', 'date_salaire')
        indexes = [
            models.Index(fields=['contrat', '-date_salaire']),
            models.Index(fields=['date_salaire']),
        ]

    def __str__(self):
        employe = self.contrat.employe
        return f"Grille {employe.surnom or employe.nom} - {self.date_salaire.strftime('%m/%Y')}"

    @property
    def employe(self):
        """Retourne l'employé lié au contrat"""
        return self.contrat.employe

    @property
    def est_gardien(self):
        """Vérifie si le poste est Gardien"""
        poste_nom = self.contrat.employe.poste.nom_poste if self.contrat.employe.poste else ""
        return "gardien" in poste_nom.lower()

    @property
    def est_journalier(self):
        """Vérifie si le contrat est de type journalier"""
        return self.contrat.type_contrat == 'journalier'

    @property
    def poste_nom_normalise(self):
        poste_nom = self.contrat.employe.poste.nom_poste if self.contrat and self.contrat.employe and self.contrat.employe.poste else ""
        return poste_nom.lower().strip()

    @property
    def utilise_majorations_planning(self):
        poste_nom = self.poste_nom_normalise
        exclusions = [
            'gardien',
            'femme de menage',
            'mpikojakoja ifotony',
        ]
        return bool(poste_nom) and not any(exclusion in poste_nom for exclusion in exclusions)

    def _get_periode_salaire(self):
        from calendar import monthrange
        from datetime import date

        if not self.date_salaire:
            return None, None

        year = self.date_salaire.year
        month = self.date_salaire.month
        last_day = monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_day)

    def _compute_planning_majoration_counts(self):
        from apps.employees.models_conges import JourFerie
        from apps.planning.models import Planning

        period_start, period_end = self._get_periode_salaire()
        if not period_start or not period_end or not self.contrat_id or not self.contrat.employe_id:
            return {
                'dimanches': 0,
                'jours_feries': 0,
                'jours_chomes_payes': 0,
                'premier_mai': False,
            }

        employe_id = self.contrat.employe_id
        holiday_types = dict(
            JourFerie.objects.filter(
                actif=True,
                date__range=(period_start, period_end),
            ).values_list('date', 'type_jour')
        )

        worked_dates = set()
        direct_dates = Planning.objects.filter(
            date__date__range=(period_start, period_end),
            ouvrage__isnull=False,
            employe_id=employe_id,
        ).values_list('date__date', flat=True)
        worked_dates.update(direct_dates)

        participant_dates = Planning.objects.filter(
            date__date__range=(period_start, period_end),
            ouvrage__isnull=False,
            planning_employees__employee_id=employe_id,
            planning_employees__is_present=True,
        ).values_list('date__date', flat=True)
        worked_dates.update(participant_dates)

        sunday_count = 0
        holiday_count = 0
        chome_paye_count = 0
        worked_first_may = False
        for worked_date in worked_dates:
            if worked_date.month == 5 and worked_date.day == 1:
                worked_first_may = True
                continue
            if worked_date in holiday_types:
                if holiday_types[worked_date] == JourFerie.TYPE_DECRET:
                    chome_paye_count += 1
                else:
                    holiday_count += 1
                continue
            if worked_date.weekday() == 6:
                sunday_count += 1

        return {
            'dimanches': sunday_count,
            'jours_feries': holiday_count,
            'jours_chomes_payes': chome_paye_count,
            'premier_mai': worked_first_may,
        }

    @staticmethod
    def _gardien_shift_hours(shift_type):
        """Retourne les heures paie normalisées d'une rotation de gardien."""
        return {
            'jour': Decimal('10'),
            'nuit': Decimal('14'),
            'etendu': Decimal('24'),
        }.get(shift_type, Decimal('0'))

    @staticmethod
    def _gardien_night_majoration_hours(shift_type):
        """Heures réellement situées dans la plage de nuit 22h-05h.

        Une rotation de nuit 18h-08h contient 7 heures de nuit. Le shift
        étendu est rémunéré par la majoration de remplacement et n'est pas
        ajouté une seconde fois à la majoration de nuit.
        """
        return Decimal('7') if shift_type == 'nuit' else Decimal('0')

    @staticmethod
    def _calculate_gardien_majoration_amounts(salaire_brut, hours):
        """Applique les taux horaires de majoration propres aux gardiens.

        Les catégories calendaires (1er mai, férié, chômé/décret, dimanche,
        nuit) sont mutuellement exclusives : chaque heure de shift n'est
        comptée que dans une seule d'entre elles, selon la priorité
        1er mai > férié > chômé/décret > dimanche > nuit > ordinaire.

        Le remplacement est indépendant de cette cascade : chaque heure de
        remplacement reçoit toujours +100%, et reçoit en plus +30% si le
        jour où elle a été effectuée était "ordinaire" (aucune des
        catégories calendaires ci-dessus applicable). Si le remplacement
        tombe un jour ayant une catégorie calendaire, le +100% du
        remplacement se cumule avec le taux de cette catégorie (déjà
        compté dans les heures calendaires ci-dessus), sans le +30%
        supplémentaire "ordinaire".
        """
        salaire_brut = Decimal(str(salaire_brut or 0))
        taux_horaire = salaire_brut / Decimal('240')
        return {
            'taux_horaire': taux_horaire,
            'nuit': taux_horaire * Decimal(str(hours.get('nuit', 0))) * Decimal('0.30'),
            'dimanche': taux_horaire * Decimal(str(hours.get('dimanche', 0))) * Decimal('0.40'),
            'ferie': taux_horaire * Decimal(str(hours.get('ferie', 0))) * Decimal('0.50'),
            'chome_paye': taux_horaire * Decimal(str(hours.get('chome_paye', 0))) * Decimal('0.30'),
            'premier_mai': taux_horaire * Decimal(str(hours.get('premier_mai', 0))) * Decimal('1.00'),
            'remplacement': (
                taux_horaire * Decimal(str(hours.get('remplacement', 0))) * Decimal('1.00') +
                taux_horaire * Decimal(str(hours.get('remplacement_ordinaire', 0))) * Decimal('0.30')
            ),
        }

    @staticmethod
    def _calculate_employee_majoration_amounts(salaire_brut, hours):
        """Applique les majorations horaires des employés non-gardiens."""
        salaire_brut = Decimal(str(salaire_brut or 0))
        taux_horaire = salaire_brut / Decimal('173.33')
        return {
            'taux_horaire': taux_horaire,
            'dimanche': taux_horaire * Decimal(str(hours.get('dimanche', 0))) * Decimal('0.40'),
            'ferie': taux_horaire * Decimal(str(hours.get('ferie', 0))) * Decimal('0.50'),
            'chome_paye': taux_horaire * Decimal(str(hours.get('chome_paye', 0))) * Decimal('0.30'),
            'premier_mai': taux_horaire * Decimal(str(hours.get('premier_mai', 0))) * Decimal('1.00'),
        }

    def _compute_gardien_rotation_hours(self):
        """
        Calcule les heures majorées depuis les rotations du mois.

        Chaque heure de shift appartient à une seule catégorie calendaire
        exclusive, selon la priorité :
        1er mai > férié officiel > chômé/décret > dimanche > nuit > ordinaire.
        La catégorie est déterminée par le jour calendaire de DEBUT du
        shift et s'applique à toutes les heures de ce shift, sauf pour la
        nuit qui ne compte que le forfait de 7h (22h-05h) quand aucune
        autre catégorie calendaire ne s'applique ce jour-là.

        Le remplacement est indépendant de cette cascade et correspond aux
        heures travaillées au-delà du seuil réglementaire de 240h/mois : le
        dépassement est prélevé en priorité sur les heures "ordinaires" du
        mois (sans catégorie calendaire), puis, si insuffisant, sur les
        heures "spéciales" restantes (1er mai, férié, décret, dimanche,
        nuit). Chaque heure de remplacement reçoit toujours +100%, cumulé
        avec la majoration de sa catégorie calendaire d'origine (déjà
        comptée séparément) ; la part prélevée sur les heures "ordinaires"
        reçoit en plus +30% supplémentaire.
        """
        from apps.employees.models_conges import JourFerie
        from apps.employees.models_gardiens import RotationGardien

        empty = {
            'has_rotations': False,
            'nuit': Decimal('0'),
            'dimanche': Decimal('0'),
            'ferie': Decimal('0'),
            'chome_paye': Decimal('0'),
            'premier_mai': Decimal('0'),
            'remplacement': Decimal('0'),
            'remplacement_ordinaire': Decimal('0'),
            'dimanches_count': 0,
            'feries_count': 0,
            'chomes_payes_count': 0,
        }
        period_start, period_end = self._get_periode_salaire()
        if not period_start or not period_end or not self.contrat_id or not self.contrat.employe_id:
            return empty

        rotations = list(
            RotationGardien.objects.filter(
                employe_id=self.contrat.employe_id,
                date__range=(period_start, period_end),
            ).order_by('date')
        )
        if not rotations:
            return empty

        holiday_types = dict(
            JourFerie.objects.filter(
                actif=True,
                date__range=(period_start, period_end),
            ).values_list('date', 'type_jour')
        )
        result = dict(empty)
        result['has_rotations'] = True

        heures_ordinaires_total = Decimal('0')
        heures_speciales_total = Decimal('0')

        for rotation in rotations:
            if rotation.shift_type == 'conge':
                continue

            shift_hours = self._gardien_shift_hours(rotation.shift_type)
            if shift_hours <= 0:
                shift_hours = Decimal(str(rotation.heures_travaillees or 0))

            is_holiday = rotation.date in holiday_types or rotation.est_jour_ferie

            if rotation.date.month == 5 and rotation.date.day == 1:
                result['premier_mai'] += shift_hours
                heures_speciales_total += shift_hours
            elif is_holiday and holiday_types.get(rotation.date) == JourFerie.TYPE_DECRET:
                result['chome_paye'] += shift_hours
                result['chomes_payes_count'] += 1
                heures_speciales_total += shift_hours
            elif is_holiday:
                result['ferie'] += shift_hours
                result['feries_count'] += 1
                heures_speciales_total += shift_hours
            elif rotation.date.weekday() == 6 or rotation.est_dimanche:
                result['dimanche'] += shift_hours
                result['dimanches_count'] += 1
                heures_speciales_total += shift_hours
            else:
                night_hours = self._gardien_night_majoration_hours(rotation.shift_type)
                if night_hours > 0:
                    result['nuit'] += night_hours
                heures_ordinaires_total += shift_hours

        # Le remplacement correspond aux heures travaillées au-delà du seuil
        # réglementaire de 240h/mois, prélevées en priorité sur les heures
        # "ordinaires" avant de puiser dans les heures "spéciales".
        heures_total = heures_ordinaires_total + heures_speciales_total
        heures_depassement = max(heures_total - Decimal('240'), Decimal('0'))
        remplacement_ordinaire = min(heures_depassement, heures_ordinaires_total)
        remplacement_special = heures_depassement - remplacement_ordinaire
        result['remplacement'] = remplacement_ordinaire + remplacement_special
        result['remplacement_ordinaire'] = remplacement_ordinaire

        return result

    def calculer_tous_les_champs(self):
        """
        Calcule automatiquement tous les champs dérivés.
        À appeler avant save().
        """
        from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR

        config = ConfigSalaire.get_config()
        salaire_minimum = config.salaire_minimum
        deduction_irsa = config.deduction_irsa
        minimum_irsa = config.minimum_irsa

        salaire_brut = Decimal(str(self.salaire_brut_base))

        if self.utilise_majorations_planning:
            planning_counts = self._compute_planning_majoration_counts()
            self.nb_dimanches_travailles = planning_counts['dimanches']
            self.nb_jours_feries_gardien = planning_counts['jours_feries']
            self.nb_jours_chomes_payes = planning_counts['jours_chomes_payes']
            self.a_travaille_1er_mai = planning_counts['premier_mai']
        elif not self.est_gardien:
            self.nb_dimanches_travailles = 0
            self.nb_jours_chomes_payes = 0

        # 1. Majorations gardien
        if self.est_gardien:
            rotation_hours = self._compute_gardien_rotation_hours()
            if rotation_hours['has_rotations']:
                self.nb_heures_nuit_gardien = rotation_hours['nuit']
                self.nb_heures_dimanche_gardien = rotation_hours['dimanche']
                self.nb_heures_feries_gardien = rotation_hours['ferie']
                self.nb_heures_chomes_payes = rotation_hours['chome_paye']
                self.nb_heures_1er_mai_gardien = rotation_hours['premier_mai']
                self.nb_heures_remplacement_gardien = rotation_hours['remplacement']
                self.nb_heures_remplacement_ordinaire_gardien = rotation_hours['remplacement_ordinaire']
                self.nb_dimanches_travailles = rotation_hours['dimanches_count']
                self.nb_jours_feries_gardien = rotation_hours['feries_count']
                self.nb_jours_chomes_payes = rotation_hours['chomes_payes_count']
                self.a_travaille_1er_mai = rotation_hours['premier_mai'] > 0
            else:
                # Compatibilité des anciennes grilles sans rotation détaillée.
                self.nb_heures_nuit_gardien = Decimal(str(self.nb_heures_nuit_gardien or 0))
                self.nb_heures_dimanche_gardien = Decimal(str(self.nb_heures_dimanche_gardien or 0))
                if self.nb_heures_dimanche_gardien == 0 and self.nb_dimanches_travailles:
                    self.nb_heures_dimanche_gardien = Decimal(str(self.nb_dimanches_travailles)) * Decimal('10')
                self.nb_heures_feries_gardien = Decimal(str(self.nb_heures_feries_gardien or 0))
                if self.nb_heures_feries_gardien == 0 and self.nb_jours_feries_gardien:
                    self.nb_heures_feries_gardien = Decimal(str(self.nb_jours_feries_gardien)) * Decimal('10')
                self.nb_heures_chomes_payes = Decimal(str(self.nb_heures_chomes_payes or 0))
                if self.nb_heures_chomes_payes == 0 and self.nb_jours_chomes_payes:
                    self.nb_heures_chomes_payes = Decimal(str(self.nb_jours_chomes_payes)) * Decimal('10')
                self.nb_heures_1er_mai_gardien = Decimal(str(self.nb_heures_1er_mai_gardien or 0))
                if self.nb_heures_1er_mai_gardien == 0 and self.a_travaille_1er_mai and self.date_salaire and self.date_salaire.month == 5:
                    self.nb_heures_1er_mai_gardien = Decimal('10')
                # Sans détail de rotation, impossible de distinguer la part
                # "jour ordinaire" du remplacement : on applique uniquement
                # le +100% fixe sur le total saisi manuellement.
                self.nb_heures_remplacement_gardien = Decimal(str(self.nb_heures_remplacement_gardien or 0))
                self.nb_heures_remplacement_ordinaire_gardien = Decimal('0')

            amounts = self._calculate_gardien_majoration_amounts(salaire_brut, {
                'nuit': self.nb_heures_nuit_gardien,
                'dimanche': self.nb_heures_dimanche_gardien,
                'ferie': self.nb_heures_feries_gardien,
                'chome_paye': self.nb_heures_chomes_payes,
                'premier_mai': self.nb_heures_1er_mai_gardien,
                'remplacement': self.nb_heures_remplacement_gardien,
                'remplacement_ordinaire': self.nb_heures_remplacement_ordinaire_gardien,
            })
            self.majoration_nuit_gardien = amounts['nuit']
            self.majoration_dimanche_gardien = amounts['dimanche']
            self.montant_jours_feries_gardien = amounts['ferie']
            self.montant_jours_chomes_payes = amounts['chome_paye']
            self.montant_majoration_1er_mai = amounts['premier_mai']
            self.montant_remplacement_gardien = amounts['remplacement']
        else:
            self.nb_heures_nuit_gardien = Decimal('0')
            self.majoration_nuit_gardien = Decimal('0')
            if self.utilise_majorations_planning:
                self.nb_heures_dimanche_gardien = Decimal(str(self.nb_dimanches_travailles or 0)) * Decimal('8')
                self.nb_heures_feries_gardien = Decimal(str(self.nb_jours_feries_gardien or 0)) * Decimal('8')
                self.nb_heures_chomes_payes = Decimal(str(self.nb_jours_chomes_payes or 0)) * Decimal('8')
                self.nb_heures_1er_mai_gardien = Decimal('8') if self.a_travaille_1er_mai else Decimal('0')
                amounts = self._calculate_employee_majoration_amounts(salaire_brut, {
                    'dimanche': self.nb_heures_dimanche_gardien,
                    'ferie': self.nb_heures_feries_gardien,
                    'chome_paye': self.nb_heures_chomes_payes,
                    'premier_mai': self.nb_heures_1er_mai_gardien,
                })
                self.majoration_dimanche_gardien = amounts['dimanche']
                self.montant_jours_feries_gardien = amounts['ferie']
                self.montant_jours_chomes_payes = amounts['chome_paye']
                self.montant_majoration_1er_mai = amounts['premier_mai']
            else:
                self.nb_heures_dimanche_gardien = Decimal('0')
                self.nb_heures_feries_gardien = Decimal('0')
                self.nb_heures_chomes_payes = Decimal('0')
                self.nb_heures_1er_mai_gardien = Decimal('0')
                self.majoration_dimanche_gardien = Decimal('0')
                self.montant_jours_feries_gardien = Decimal('0')
                self.montant_jours_chomes_payes = Decimal('0')
                self.montant_majoration_1er_mai = Decimal('0')
            self.montant_remplacement_gardien = Decimal('0')

        # 2. Salaire brut total
        if self.est_journalier:
            # Si journalier: salaire_brut * nb_jours
            salaire_brut_effectif = salaire_brut * Decimal(str(self.nb_jours_presence))
        elif self.est_prorata and self.nb_jours_presence > 0:
            # Si prorata active: salaire_brut * (nb_jours_presence / 30)
            salaire_brut_effectif = salaire_brut * Decimal(str(self.nb_jours_presence)) / Decimal('30')
        else:
            # Sinon: salaire brut de base uniquement
            salaire_brut_effectif = salaire_brut

        if self.est_gardien or self.utilise_majorations_planning:
            # Pour les postes majores via planning, appliquer les majorations sur la base effective
            self.salaire_brut_total = (
                salaire_brut_effectif +
                self.majoration_nuit_gardien +
                self.majoration_dimanche_gardien +
                self.montant_jours_feries_gardien +
                self.montant_jours_chomes_payes +
                self.montant_majoration_1er_mai +
                self.montant_remplacement_gardien
            )
        else:
            self.salaire_brut_total = salaire_brut_effectif

        # 3. Charge CNaPS employé: 1% du min(salaire_brut_total, 8*salaire_minimum)
        plafond_cnaps = Decimal('8') * salaire_minimum
        base_cnaps = min(self.salaire_brut_total, plafond_cnaps)
        self.charge_cnaps_employe = base_cnaps * Decimal('0.01')

        # 4. Mutuelle Santé: identique à la charge CNaPS employé
        self.mutuelle_sante = self.charge_cnaps_employe

        # 5. Base imposable: salaire_brut_total - charge_cnaps - mutuelle_sante,
        # arrondie à 100 Ar près par valeur inférieure (utilisée telle quelle
        # pour le calcul de l'IRSA ci-dessous).
        base_imposable_exacte = self.salaire_brut_total - self.charge_cnaps_employe - self.mutuelle_sante
        base_imposable = (base_imposable_exacte / Decimal('100')).quantize(
            Decimal('1'),
            rounding=ROUND_FLOOR
        ) * Decimal('100')
        self.base_imposable = base_imposable

        # 6. Déduction d'impôts: nb_personnes * deduction_irsa
        self.deduction_impots = Decimal(str(self.personnes_charge)) * deduction_irsa

        # 7. Calcul IRSA avec les tranches (déduction appliquée après l'IRSA)
        if base_imposable > 0:
            irsa_calcule = ConfigTrancheIRSA.calculer_irsa(base_imposable)
            irsa_apres_deduction = irsa_calcule - self.deduction_impots
            if irsa_apres_deduction < 0:
                irsa_apres_deduction = Decimal('0')
            # Appliquer le minimum IRSA après déduction
            self.irsa = max(irsa_apres_deduction, minimum_irsa)
        else:
            self.irsa = Decimal('0')

        # 8. Salaire net: salaire_brut_total - charge_cnaps - mutuelle_sante - irsa
        salaire_net_calcule = self.salaire_brut_total - self.charge_cnaps_employe - self.mutuelle_sante - self.irsa
        self.salaire_net = (salaire_net_calcule / Decimal('100')).quantize(
            Decimal('1'),
            rounding=ROUND_HALF_UP
        ) * Decimal('100')

    def calculer_salaire_brut_depuis_net(self, salaire_net_cible, max_iterations=100, tolerance=Decimal('1')):
        """
        Fonction valeur cible: calcule le salaire brut nécessaire pour atteindre un salaire net donné.
        Utilise une méthode itérative de recherche par dichotomie.

        Args:
            salaire_net_cible (Decimal): Salaire net souhaité
            max_iterations (int): Nombre maximum d'itérations
            tolerance (Decimal): Tolérance acceptée en Ariary

        Returns:
            Decimal: Salaire brut calculé
        """
        from decimal import Decimal

        salaire_net_cible = Decimal(str(salaire_net_cible))
        if salaire_net_cible <= 0:
            return Decimal('0')

        # La borne basse ne peut pas partir du net cible, car certains modes
        # (journalier, gardien) peuvent générer un net supérieur au brut de base
        # grâce aux majorations ou à la multiplication par jours.
        salaire_brut_min = Decimal('0')
        salaire_brut_max = max(salaire_net_cible, Decimal('1'))

        # Étendre la borne haute jusqu'à encadrer le net cible.
        for _ in range(max_iterations):
            self.salaire_brut_base = salaire_brut_max
            self.calculer_tous_les_champs()
            if self.salaire_net >= salaire_net_cible:
                break
            salaire_brut_max *= Decimal('2')

        for iteration in range(max_iterations):
            # Essayer le milieu de l'intervalle
            salaire_brut_test = (salaire_brut_min + salaire_brut_max) / Decimal('2')

            # Calculer le net avec ce brut
            self.salaire_brut_base = salaire_brut_test
            self.calculer_tous_les_champs()

            # Vérifier si on est proche du net cible
            ecart = abs(self.salaire_net - salaire_net_cible)

            if ecart <= tolerance:
                # Trouvé!
                return salaire_brut_test

            # Ajuster les bornes
            if self.salaire_net < salaire_net_cible:
                # Le net calculé est trop petit, augmenter le brut
                salaire_brut_min = salaire_brut_test
            else:
                # Le net calculé est trop grand, diminuer le brut
                salaire_brut_max = salaire_brut_test

        # Si on sort de la boucle sans avoir trouvé, retourner la dernière valeur
        return salaire_brut_test

    def save(self, *args, **kwargs):
        """Override save pour calculer automatiquement les champs"""

        # Si salaire_brut_base == 0, le récupérer depuis le contrat
        if self.salaire_brut_base == 0 and self.contrat:
            self.salaire_brut_base = self.contrat.salaire_brut_base

        # Si salaire_net_cible est fourni et salaire_brut_base == 0, calculer le brut
        if self.salaire_net_cible and self.salaire_brut_base == 0:
            self.salaire_brut_base = self.calculer_salaire_brut_depuis_net(self.salaire_net_cible)

        # Calculer tous les champs dérivés
        self.calculer_tous_les_champs()

        super().save(*args, **kwargs)


class PaiementCNaPSFMFP(models.Model):
    """Modèle pour gérer les paiements CNaPS et FMFP trimestriels par organisation"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    organisation = models.ForeignKey(
        'organization.Organisation',
        on_delete=models.CASCADE,
        related_name='paiements_cnaps_fmfp',
        verbose_name="Organisation"
    )
    trimestre = models.IntegerField(verbose_name="Trimestre (1-4)")
    annee = models.IntegerField(verbose_name="Année")
    date_paiement = models.DateField(
        verbose_name="Date de paiement",
        help_text="Date de paiement effectif (début du mois suivant le trimestre)"
    )

    # Montants globaux
    montant_total_cnaps = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Total CNaPS"
    )
    montant_total_fmfp = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Total FMFP"
    )

    # Suivi de l'impression et validation
    facture_generee = models.BooleanField(default=False, verbose_name="Facture générée")
    date_generation = models.DateTimeField(null=True, blank=True, verbose_name="Date de génération")
    fichier_facture = models.CharField(max_length=500, null=True, blank=True, verbose_name="Chemin fichier")

    facture_imprimee = models.BooleanField(
        default=False,
        verbose_name="Facture imprimée",
        help_text="Indique si la facture a été imprimée - déclenche l'export"
    )
    date_impression = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Date d'impression"
    )

    statut = models.CharField(
        max_length=20,
        choices=[
            ('brouillon', 'Brouillon'),
            ('valide', 'Validé'),
            ('paye', 'Payé'),
        ],
        default='brouillon',
        verbose_name="Statut"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='paiements_cnaps_fmfp_crees',
        verbose_name="Créé par"
    )

    class Meta:
        db_table = 'paiements_cnaps_fmfp'
        verbose_name = 'Paiement CNaPS/FMFP'
        verbose_name_plural = 'Paiements CNaPS/FMFP'
        unique_together = ('organisation', 'trimestre', 'annee')
        ordering = ['-annee', '-trimestre']

    def __str__(self):
        return f"CNaPS/FMFP {self.organisation.nom_organisation} - T{self.trimestre}/{self.annee}"

    @property
    def periode_label(self):
        """Retourne le label de la période (ex: '1er trimestre 2025')"""
        labels = {1: '1er', 2: '2e', 3: '3e', 4: '4e'}
        return f"{labels.get(self.trimestre, '')} trimestre {self.annee}"

    @property
    def mois_trimestre(self):
        """Retourne la liste des mois du trimestre"""
        mois_par_trimestre = {
            1: [1, 2, 3],    # Janvier, Février, Mars
            2: [4, 5, 6],    # Avril, Mai, Juin
            3: [7, 8, 9],    # Juillet, Août, Septembre
            4: [10, 11, 12]  # Octobre, Novembre, Décembre
        }
        return mois_par_trimestre.get(self.trimestre, [])


class PaiementCNaPSFMFPDetail(models.Model):
    """Détail des paiements CNaPS/FMFP par employé"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    paiement = models.ForeignKey(
        PaiementCNaPSFMFP,
        on_delete=models.CASCADE,
        related_name='details',
        verbose_name="Paiement CNaPS/FMFP"
    )
    employe = models.ForeignKey(
        'Employe',
        on_delete=models.CASCADE,
        related_name='paiements_cnaps_fmfp',
        verbose_name="Employé"
    )

    # Informations employé (dénormalisées pour historique)
    employe_nom_complet = models.CharField(max_length=255, verbose_name="Nom complet")
    employe_fonction = models.CharField(max_length=255, null=True, blank=True, verbose_name="Fonction")
    numero_cnaps = models.CharField(max_length=50, null=True, blank=True, verbose_name="Numéro CNaPS")

    # Montants par mois du trimestre
    mois_1_cnaps = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="CNaPS Mois 1")
    mois_1_fmfp = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="FMFP Mois 1")

    mois_2_cnaps = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="CNaPS Mois 2")
    mois_2_fmfp = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="FMFP Mois 2")

    mois_3_cnaps = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="CNaPS Mois 3")
    mois_3_fmfp = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="FMFP Mois 3")

    # Totaux pour le trimestre
    total_cnaps = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Total CNaPS trimestre")
    total_fmfp = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Total FMFP trimestre")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'paiements_cnaps_fmfp_details'
        verbose_name = 'Détail paiement CNaPS/FMFP'
        verbose_name_plural = 'Détails paiements CNaPS/FMFP'
        ordering = ['employe_fonction', 'employe_nom_complet']

    def __str__(self):
        return f"{self.employe_nom_complet} - CNaPS: {self.total_cnaps} Ar | FMFP: {self.total_fmfp} Ar"


class PaiementMutuelleSante(models.Model):
    """Modèle pour gérer les paiements de mutuelle santé trimestriels par organisation"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    organisation = models.ForeignKey(
        'organization.Organisation',
        on_delete=models.CASCADE,
        related_name='paiements_mutuelle_sante',
        verbose_name="Organisation"
    )
    trimestre = models.IntegerField(verbose_name="Trimestre (1-4)")
    annee = models.IntegerField(verbose_name="Année")

    # Montants globaux par mutuelle
    montant_total_amit = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Total AMIT"
    )
    montant_total_osiefsova = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Total OSIEFSoVa"
    )

    # Statuts et export
    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('valide', 'Validé'),
        ('exporte', 'Exporté vers DiameX'),
    ]
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='brouillon',
        verbose_name="Statut"
    )

    # Liens DiameX AMIT
    numero_diamex_amit = models.CharField(
        max_length=50, null=True, blank=True,
        verbose_name="Numéro DiameX AMIT (ID)"
    )
    base_diamex_amit = models.CharField(
        max_length=255, null=True, blank=True,
        verbose_name="Base DiameX AMIT (Prog)"
    )

    # Liens DiameX OSIEFSoVa
    numero_diamex_osiefsova = models.CharField(
        max_length=50, null=True, blank=True,
        verbose_name="Numéro DiameX OSIEFSoVa (ID)"
    )
    base_diamex_osiefsova = models.CharField(
        max_length=255, null=True, blank=True,
        verbose_name="Base DiameX OSIEFSoVa (Prog)"
    )

    facture_generee = models.BooleanField(
        default=False,
        verbose_name="Facture générée"
    )
    date_generation_facture = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Date génération facture"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='paiements_mutuelle_sante_crees',
        verbose_name="Créé par"
    )

    class Meta:
        db_table = 'paiements_mutuelle_sante'
        verbose_name = 'Paiement Mutuelle Santé'
        verbose_name_plural = 'Paiements Mutuelle Santé'
        unique_together = ('organisation', 'trimestre', 'annee')
        ordering = ['-annee', '-trimestre']

    def __str__(self):
        return f"Mutuelle Santé {self.organisation.nom_organisation} - T{self.trimestre}/{self.annee}"

    @property
    def periode_label(self):
        """Retourne le label de la période (ex: '1er trimestre 2025')"""
        labels = {1: '1er', 2: '2e', 3: '3e', 4: '4e'}
        return f"{labels.get(self.trimestre, str(self.trimestre))} trimestre {self.annee}"

    @property
    def montant_total(self):
        """Retourne le montant total (AMIT + OSIEFSoVa)"""
        return self.montant_total_amit + self.montant_total_osiefsova

    @property
    def mois_trimestre(self):
        """Retourne la liste des mois du trimestre"""
        mois_par_trimestre = {
            1: [1, 2, 3],    # Janvier, Février, Mars
            2: [4, 5, 6],    # Avril, Mai, Juin
            3: [7, 8, 9],    # Juillet, Août, Septembre
            4: [10, 11, 12]  # Octobre, Novembre, Décembre
        }
        return mois_par_trimestre.get(self.trimestre, [])


class PaiementMutuelleSanteDetail(models.Model):
    """Détail des paiements mutuelle santé par employé"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    paiement = models.ForeignKey(
        PaiementMutuelleSante,
        on_delete=models.CASCADE,
        related_name='details',
        verbose_name="Paiement Mutuelle Santé"
    )
    employe = models.ForeignKey(
        'Employe',
        on_delete=models.CASCADE,
        related_name='paiements_mutuelle_sante',
        verbose_name="Employé"
    )

    # Informations employé (dénormalisées pour historique)
    employe_nom_complet = models.CharField(max_length=255, verbose_name="Nom complet")
    employe_fonction = models.CharField(max_length=255, null=True, blank=True, verbose_name="Fonction")
    mutuelle = models.CharField(max_length=20, verbose_name="Mutuelle (AMIT/OSIEFSoVa)")

    # Montants par mois du trimestre
    mois_1 = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Mois 1")
    mois_2 = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Mois 2")
    mois_3 = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Mois 3")

    # Total pour le trimestre
    total_trimestre = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Total trimestre")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'paiements_mutuelle_sante_details'
        verbose_name = 'Détail paiement Mutuelle Santé'
        verbose_name_plural = 'Détails paiements Mutuelle Santé'
        ordering = ['mutuelle', 'employe_fonction', 'employe_nom_complet']

    def __str__(self):
        return f"{self.employe_nom_complet} ({self.mutuelle}) - {self.total_trimestre} Ar"


class PaiementIRI(models.Model):
    """
    Modèle pour gérer les paiements mensuels d'IRI (Impôt sur les Revenus Intermittents)
    Basé sur les transactions DiameX avec préfixe ISI
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    organisation = models.ForeignKey(
        'organization.Organisation',
        on_delete=models.CASCADE,
        related_name='paiements_iri',
        verbose_name="Organisation"
    )
    mois = models.IntegerField(verbose_name="Mois (1-12)")
    annee = models.IntegerField(verbose_name="Année")

    # Montants totaux
    montant_total_achats = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Montant total des achats"
    )
    montant_total_iri = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Montant total IRI (5%)"
    )

    # Statuts
    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('valide', 'Validé'),
        ('exporte', 'Exporté vers DiameX'),
    ]
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='brouillon',
        verbose_name="Statut"
    )

    facture_generee = models.BooleanField(
        default=False,
        verbose_name="Facture générée"
    )
    date_generation_facture = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Date génération facture"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='paiements_iri_crees',
        verbose_name="Créé par"
    )

    class Meta:
        db_table = 'paiements_iri'
        verbose_name = 'Paiement IRI'
        verbose_name_plural = 'Paiements IRI'
        unique_together = ('organisation', 'mois', 'annee')
        ordering = ['-annee', '-mois']

    def __str__(self):
        return f"IRI {self.organisation.nom_organisation} - {self.mois:02d}/{self.annee}"

    @property
    def periode_label(self):
        """Retourne le label de la période (ex: 'Octobre 2025')"""
        mois_noms = [
            'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
            'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
        ]
        return f"{mois_noms[self.mois - 1]} {self.annee}"


class PaiementIRIDetail(models.Model):
    """
    Détail des paiements IRI par transaction DiameX
    Une ligne = une transaction ISI depuis DiameX
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    paiement = models.ForeignKey(
        PaiementIRI,
        on_delete=models.CASCADE,
        related_name='details',
        verbose_name="Paiement IRI"
    )

    # Référence DiameX source
    id_access_source = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="ID Access source"
    )
    numero_diamex_source = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Numéro DiameX source (Rec)"
    )
    base_diamex_source = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Base DiameX source (Prog)"
    )

    # Parsing de la description ISI
    # Format attendu: ISI_[NomFournisseur]_[Libellé]_[Unité]_[PU]_[Date]
    fournisseur_nom = models.CharField(
        max_length=255,
        verbose_name="Nom du fournisseur"
    )
    fournisseur_cin = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="CIN du fournisseur"
    )
    fournisseur_adresse = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Adresse du fournisseur"
    )

    libelle = models.CharField(
        max_length=500,
        verbose_name="Libellé de l'achat"
    )
    unite = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Unité"
    )
    prix_unitaire = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Prix unitaire"
    )
    date_achat = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de l'achat"
    )

    # Montants
    montant_achat = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Montant de l'achat (Out DiameX)"
    )
    montant_iri = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="IR intermittent (5%)"
    )

    # Regroupement par Activ (BURVAVSKJ, EHAFNVSKJ, etc.)
    activ = models.CharField(
        max_length=50,
        verbose_name="Code Activ (regroupement)"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'paiements_iri_details'
        verbose_name = 'Détail paiement IRI'
        verbose_name_plural = 'Détails paiements IRI'
        ordering = ['activ', 'fournisseur_nom', 'date_achat']

    def __str__(self):
        return f"{self.fournisseur_nom} - {self.libelle} - {self.montant_achat} Ar"

    def save(self, *args, **kwargs):
        """Calcul automatique de l'IRI à 5%"""
        self.montant_iri = self.montant_achat * Decimal('0.05')
        super().save(*args, **kwargs)
