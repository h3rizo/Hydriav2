"""
Modèles pour le système d'évaluation des employés
"""
import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class FichePoste(models.Model):
    """
    Fiche de poste décrivant les tâches, descriptions et outils
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type_activites = models.ForeignKey(
        'planning.TypeActivite',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fiches_poste',
        verbose_name="Type d'activités",
        help_text="Type d'activités associé à cette fiche de poste"
    )
    tache = models.CharField(
        max_length=255,
        verbose_name="Tâche",
        help_text="Nom de la tâche à accomplir"
    )
    description = models.TextField(
        verbose_name="Description",
        help_text="Description détaillée de la tâche"
    )
    outils = models.TextField(
        blank=True,
        verbose_name="Outils nécessaires",
        help_text="Liste des outils, logiciels ou ressources nécessaires"
    )
    ordre = models.PositiveIntegerField(
        default=0,
        verbose_name="Ordre d'affichage",
        help_text="Ordre d'affichage dans la liste des tâches"
    )
    a_evaluer = models.BooleanField(
        default=False,
        verbose_name="À évaluer",
        help_text="Cette fiche doit-elle être utilisée dans les évaluations ?"
    )
    dans_planning = models.BooleanField(
        default=False,
        verbose_name="Dans planning",
        help_text="Cette fiche doit-elle apparaître dans le planning ?"
    )
    preuve_obligatoire = models.BooleanField(
        default=False,
        verbose_name="Preuve obligatoire",
        help_text="Une preuve (piece jointe) est requise pour l'accomplissement"
    )

    preuve_type = models.CharField(
        max_length=30,
        choices=[
            ('piece_jointe', 'Piece jointe'),
            ('evaluation', 'Evaluation'),
        ],
        default='piece_jointe',
        verbose_name="Type de preuve",
        help_text="Type de preuve pour attester l'accomplissement"
    )
    # --- Précisions demandées quand cette activité est saisie sur une réparation / un entretien ---
    MODE_NON = 'non'
    MODE_OPTIONNEL = 'optionnel'
    MODE_OBLIGATOIRE = 'obligatoire'
    MODE_CHOICES = [
        (MODE_NON, 'Non demandée'),
        (MODE_OPTIONNEL, 'Facultative'),
        (MODE_OBLIGATOIRE, 'Obligatoire'),
    ]
    CIBLE_TYPES_CHOICES = [
        ('les_deux', "Point d'eau ou équipement"),
        ('point_eau', "Point d'eau uniquement"),
        ('equipement', 'Équipement uniquement'),
    ]
    cible_mode = models.CharField(
        max_length=12, choices=MODE_CHOICES, default=MODE_OPTIONNEL,
        verbose_name="Précision sur la cible",
        help_text="Faut-il préciser le point d'eau ou l'équipement visé par l'activité ?")
    cible_types = models.CharField(
        max_length=12, choices=CIBLE_TYPES_CHOICES, default='les_deux',
        verbose_name="Types de cible admis")
    composants_mode = models.CharField(
        max_length=12, choices=MODE_CHOICES, default=MODE_OPTIONNEL,
        verbose_name="Précision sur les composants",
        help_text="Faut-il préciser le ou les composants concernés ? "
                  "Obligatoire implique une cible obligatoire.")
    composants_multiple = models.BooleanField(
        default=True, verbose_name="Plusieurs composants possibles",
        help_text="Décoché : un seul composant peut être indiqué.")
    composants_admis = models.TextField(
        blank=True, default='', verbose_name="Composants admis",
        help_text="Un nom de composant par ligne (accents et majuscules ignorés). "
                  "Vide : tous les composants du type de la cible. "
                  "Ex. « Anti-rouille » : Boîte métallique, Fer plat, Cadenas vita gasy.")

    def composants_admis_liste(self):
        """Noms de composants admis, dédoublonnés, dans l'ordre saisi."""
        noms = []
        for ligne in (self.composants_admis or '').replace(';', '\n').splitlines():
            nom = ligne.strip()
            if nom and nom not in noms:
                noms.append(nom)
        return noms

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fiches_poste'
        ordering = ['ordre', 'tache']
        verbose_name = "Fiche de poste"
        verbose_name_plural = "Fiches de poste"

    def __str__(self):
        return f"{self.tache}"


class Evaluation(models.Model):
    """
    Évaluation d'un employé sur l'ensemble des tâches de son poste
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employe = models.ForeignKey(
        'employees.Employe',
        on_delete=models.CASCADE,
        related_name='evaluations_recues',
        verbose_name="Employé évalué"
    )
    evaluateur = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        related_name='evaluations_effectuees',
        verbose_name="Évaluateur",
        help_text="Employé qui effectue l'évaluation (peut être l'employé lui-même)"
    )
    date_evaluation = models.DateField(
        default=timezone.now,
        verbose_name="Date d'évaluation"
    )
    periode_debut = models.DateField(
        verbose_name="Début de la période évaluée",
        help_text="Date de début de la période couverte par l'évaluation"
    )
    periode_fin = models.DateField(
        verbose_name="Fin de la période évaluée",
        help_text="Date de fin de la période couverte par l'évaluation"
    )
    commentaire_general = models.TextField(
        blank=True,
        verbose_name="Commentaire général",
        help_text="Appréciation globale de l'évaluateur"
    )
    besoins_formation = models.TextField(
        blank=True,
        verbose_name="Besoins en formation",
        help_text="Formations identifiees pour renforcer les competences de l'employe"
    )
    perspectives_evolution = models.TextField(
        blank=True,
        verbose_name="Perspectives d'evolution et axes de progression",
        help_text="Perspectives d'evolution, objectifs de progression et axes de developpement"
    )
    priorite_1 = models.ForeignKey(
        'EvaluationDetail',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name="Priorité 1",
        help_text="Fiche de poste à améliorer en priorité 1"
    )
    priorite_2 = models.ForeignKey(
        'EvaluationDetail',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name="Priorité 2",
        help_text="Fiche de poste à améliorer en priorité 2"
    )
    priorite_3 = models.ForeignKey(
        'EvaluationDetail',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name="Priorité 3",
        help_text="Fiche de poste à améliorer en priorité 3"
    )
    est_auto_evaluation = models.BooleanField(
        default=False,
        verbose_name="Auto-évaluation",
        help_text="Coché si l'employé s'évalue lui-même"
    )
    statut = models.CharField(
        max_length=20,
        choices=[
            ('brouillon', 'Brouillon'),
            ('terminee', 'Terminée'),
            ('validee', 'Validée par le responsable'),
        ],
        default='brouillon',
        verbose_name="Statut"
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'evaluations'
        ordering = ['-date_evaluation', '-date_creation']
        verbose_name = "Évaluation"
        verbose_name_plural = "Évaluations"

    def __str__(self):
        auto = " (auto)" if self.est_auto_evaluation else ""
        return f"Évaluation de {self.employe.nom_complet} - {self.date_evaluation}{auto}"

    @property
    def note_totale(self):
        """Calcule la note totale de l'évaluation"""
        details = self.details.all()
        if not details:
            return None
        return sum(d.note for d in details)

    @property
    def note_maximale(self):
        """Calcule la note maximale possible"""
        return self.details.count() * 2

    @property
    def pourcentage(self):
        """Calcule le pourcentage de réussite"""
        if self.note_maximale == 0:
            return 0
        return round((self.note_totale / self.note_maximale) * 100, 1)

    def save(self, *args, **kwargs):
        # Vérifier si c'est une auto-évaluation
        if self.evaluateur and self.employe:
            self.est_auto_evaluation = (self.evaluateur.id == self.employe.id)
        super().save(*args, **kwargs)


class EvaluationDetail(models.Model):
    """
    Détail d'une évaluation : note et remarques pour une tâche spécifique
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evaluation = models.ForeignKey(
        'Evaluation',
        on_delete=models.CASCADE,
        related_name='details',
        verbose_name="Évaluation"
    )
    fiche_poste = models.ForeignKey(
        'FichePoste',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='evaluations_details',
        verbose_name="Tâche évaluée"
    )
    note = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(2)],
        verbose_name="Note",
        help_text="Note de 0 à 2 : 0=Non acquis, 1=En cours, 2=Maîtrisé"
    )
    remarques = models.TextField(
        blank=True,
        verbose_name="Remarques",
        help_text="Observations de l'évaluateur sur cette tâche"
    )
    piece_jointe = models.FileField(
        upload_to='evaluations/pieces_jointes/',
        null=True,
        blank=True,
        verbose_name="Piece jointe",
        help_text="Piece justificative liee a cette tache"
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'evaluations_details'
        ordering = ['fiche_poste__ordre', 'fiche_poste__tache']
        verbose_name = "Détail d'évaluation"
        verbose_name_plural = "Détails d'évaluation"
        unique_together = ('evaluation', 'fiche_poste')

    def __str__(self):
        return f"{self.evaluation} - {self.fiche_poste.tache} : {self.note}/2"

    @property
    def note_label(self):
        """Retourne le label textuel de la note"""
        labels = {
            0: "Non acquis",
            1: "En cours d'acquisition",
            2: "Maîtrisé"
        }
        return labels.get(self.note, "Non évalué")
