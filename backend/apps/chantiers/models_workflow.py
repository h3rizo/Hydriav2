from __future__ import annotations

import ast
import operator as op
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import DatabaseError, models
from django.utils import timezone


class WorkflowModeleEquipement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=80, unique=True)
    type_equipement = models.ForeignKey("infrastructure.TypeEquipement", on_delete=models.PROTECT, related_name="wf_modeles")
    type_point_eau = models.ForeignKey("billing.TypePointEau", on_delete=models.PROTECT, related_name="wf_modeles", null=True, blank=True)
    actif = models.BooleanField(default=True)

    class Meta:
        db_table = "chantiers_wf_modeles_equipements"
        constraints = [models.UniqueConstraint(fields=["type_equipement", "type_point_eau", "code"], name="uq_wf_modele")]


class CiterneParametrageReference(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=120, unique=True)
    epaisseur_paroi_m = models.DecimalField(max_digits=8, decimal_places=3, default=Decimal("0.15"))
    hauteur_visible_m = models.DecimalField(max_digits=8, decimal_places=3, default=Decimal("0.50"))
    epaisseur_blocage_m = models.DecimalField(max_digits=8, decimal_places=3, default=Decimal("0.20"))
    epaisseur_beton_arme_m = models.DecimalField(max_digits=8, decimal_places=3, default=Decimal("0.10"))
    hauteur_aeration_m = models.DecimalField(max_digits=8, decimal_places=3, default=Decimal("0.10"))
    epaisseur_dalle_couverture_m = models.DecimalField(max_digits=8, decimal_places=3, default=Decimal("0.10"))

    class Meta:
        db_table = "chantiers_citerne_param_references"


class CiterneVolumeConfiguration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.ForeignKey(
        CiterneParametrageReference,
        on_delete=models.CASCADE,
        related_name="volumes_configures",
    )
    volume_cible_m3 = models.DecimalField(max_digits=10, decimal_places=3)
    diametre_interieur_m = models.DecimalField(max_digits=10, decimal_places=3)
    hauteur_trop_plein_m = models.DecimalField(max_digits=10, decimal_places=3)
    diametre_exterieur_m = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    hauteur_interieure_m = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    profondeur_fouille_m = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    hauteur_utile_m = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    actif = models.BooleanField(default=True)

    class Meta:
        db_table = "chantiers_citerne_volumes_config"
        ordering = ["volume_cible_m3"]
        constraints = [
            models.UniqueConstraint(
                fields=["reference", "volume_cible_m3"],
                name="uq_citerne_volume_reference",
            )
        ]


class CiterneDimensionnement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.ForeignKey(CiterneParametrageReference, on_delete=models.PROTECT, related_name="dimensionnements")
    volume_cible_m3 = models.DecimalField(max_digits=10, decimal_places=3)
    diametre_interieur_m = models.DecimalField(max_digits=10, decimal_places=3)
    hauteur_eau_m = models.DecimalField(max_digits=10, decimal_places=3)
    diametre_exterieur_m = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    volume_reel_m3 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = "chantiers_citerne_dimensionnements"

    @property
    def context(self) -> dict[str, Decimal]:
        pi = Decimal("3.141592653589793")
        ep = self.reference.epaisseur_paroi_m
        dint = Decimal(self.diametre_interieur_m)
        h = Decimal(self.hauteur_eau_m)
        dext = dint + (ep * Decimal("2"))
        vol = (pi * dint * dint * h) / Decimal("4")
        return {
            "volume_cible_m3": Decimal(self.volume_cible_m3),
            "diametre_interieur_m": dint,
            "hauteur_eau_m": h,
            "epaisseur_paroi_m": Decimal(ep),
            "hauteur_visible_m": Decimal(self.reference.hauteur_visible_m),
            "epaisseur_blocage_m": Decimal(self.reference.epaisseur_blocage_m),
            "epaisseur_beton_arme_m": Decimal(self.reference.epaisseur_beton_arme_m),
            "diametre_exterieur_m": dext,
            "volume_reel_m3": vol,
        }

    def save(self, *args, **kwargs):
        ctx = self.context
        self.diametre_exterieur_m = ctx["diametre_exterieur_m"]
        self.volume_reel_m3 = ctx["volume_reel_m3"]
        super().save(*args, **kwargs)


def get_or_create_default_citerne_reference():
    reference, _ = CiterneParametrageReference.objects.get_or_create(
        nom="DEFAULT",
        defaults={
            "epaisseur_paroi_m": Decimal("0.10"),
            "hauteur_visible_m": Decimal("0.20"),
            "epaisseur_blocage_m": Decimal("0.20"),
            "epaisseur_beton_arme_m": Decimal("0.10"),
            "hauteur_aeration_m": Decimal("0.10"),
            "epaisseur_dalle_couverture_m": Decimal("0.10"),
        },
    )
    return reference


def _interpolate_decimal(lower_value: Decimal, upper_value: Decimal, ratio: Decimal) -> Decimal:
    return lower_value + ((upper_value - lower_value) * ratio)


def build_citerne_dimensions_from_volume(volume_cible_m3, reference: CiterneParametrageReference | None = None) -> dict:
    volume = Decimal(str(volume_cible_m3 or "0"))
    if volume <= 0:
        raise ValidationError("Le volume citerne doit etre superieur a 0.")

    reference = reference or get_or_create_default_citerne_reference()
    try:
        configs = list(
            CiterneVolumeConfiguration.objects.filter(reference=reference, actif=True).order_by("volume_cible_m3")
        )
    except DatabaseError:
        configs = []

    if not configs:
        diametre = Decimal("1.5")
        pi = Decimal("3.141592653589793")
        hauteur = volume / ((pi * diametre * diametre) / Decimal("4"))
        return {
            "reference": reference,
            "volume_cible_m3": volume,
            "diametre_interieur_m": diametre,
            "hauteur_eau_m": hauteur,
            "mode": "fallback",
        }

    exact = None
    for cfg in configs:
        if Decimal(cfg.volume_cible_m3) == volume:
            exact = cfg
            break

    if exact:
        return {
            "reference": reference,
            "volume_cible_m3": volume,
            "diametre_interieur_m": Decimal(exact.diametre_interieur_m),
            "hauteur_eau_m": Decimal(exact.hauteur_trop_plein_m),
            "config_id": str(exact.id),
            "mode": "config",
        }

    lower = None
    upper = None
    for cfg in configs:
        cfg_volume = Decimal(cfg.volume_cible_m3)
        if cfg_volume < volume:
            lower = cfg
            continue
        if cfg_volume > volume and upper is None:
            upper = cfg
            break

    if lower and upper:
        lower_volume = Decimal(lower.volume_cible_m3)
        upper_volume = Decimal(upper.volume_cible_m3)
        ratio = (volume - lower_volume) / (upper_volume - lower_volume)

        lower_d = Decimal(lower.diametre_interieur_m)
        upper_d = Decimal(upper.diametre_interieur_m)
        if lower_d == upper_d:
            diametre = lower_d
        else:
            diametre = _interpolate_decimal(lower_d, upper_d, ratio)

        hauteur = _interpolate_decimal(
            Decimal(lower.hauteur_trop_plein_m),
            Decimal(upper.hauteur_trop_plein_m),
            ratio,
        )
        return {
            "reference": reference,
            "volume_cible_m3": volume,
            "diametre_interieur_m": diametre,
            "hauteur_eau_m": hauteur,
            "mode": "interpolation",
        }

    nearest = lower or upper or configs[0]
    diametre = Decimal(nearest.diametre_interieur_m)
    pi = Decimal("3.141592653589793")
    hauteur = volume / ((pi * diametre * diametre) / Decimal("4"))
    return {
        "reference": reference,
        "volume_cible_m3": volume,
        "diametre_interieur_m": diametre,
        "hauteur_eau_m": hauteur,
        "mode": "extrapolation",
    }


class WorkflowModeleEquipementLigne(models.Model):
    MODE_CHOICES = [("fixe", "Fixe"), ("formule", "Formule")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    modele = models.ForeignKey(WorkflowModeleEquipement, on_delete=models.CASCADE, related_name="lignes")
    designation = models.ForeignKey("planning.Designation", on_delete=models.PROTECT, related_name="wf_lignes")
    mode_quantite = models.CharField(max_length=20, choices=MODE_CHOICES, default="fixe")
    quantite_unitaire = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    formule_quantite = models.CharField(max_length=255, null=True, blank=True)
    ordre = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "chantiers_wf_modele_lignes"

    def clean(self):
        if self.mode_quantite == "fixe" and self.quantite_unitaire is None:
            raise ValidationError("quantite_unitaire est obligatoire en mode fixe.")
        if self.mode_quantite == "formule" and not self.formule_quantite:
            raise ValidationError("formule_quantite est obligatoire en mode formule.")


class PosteMainOeuvre(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=80, unique=True)
    libelle = models.CharField(max_length=255)
    unite = models.CharField(max_length=30, default="U")

    class Meta:
        db_table = "chantiers_postes_main_oeuvre"


class BaremeMainOeuvre(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    poste = models.ForeignKey(PosteMainOeuvre, on_delete=models.PROTECT, related_name="baremes")
    type_equipement = models.ForeignKey("infrastructure.TypeEquipement", on_delete=models.PROTECT, related_name="wf_baremes_mo")
    type_point_eau = models.ForeignKey("billing.TypePointEau", on_delete=models.PROTECT, related_name="wf_baremes_mo", null=True, blank=True)
    quantite_unitaire = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("1"))
    prix_unitaire = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        db_table = "chantiers_baremes_main_oeuvre"
        constraints = [models.UniqueConstraint(fields=["poste", "type_equipement", "type_point_eau"], name="uq_wf_bareme")]


class ChantierWorkflow(models.Model):
    STATUS_CHOICES = [
        ("brouillon", "Brouillon"),
        ("besoins_generes", "Besoins generes"),
        ("devis", "Devis"),
        ("contrat", "Contrat"),
        ("execution", "Execution"),
        ("recollement", "Recollement"),
        ("cloture", "Cloture"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=80, unique=True)
    ouvrage = models.ForeignKey("organization.Ouvrage", on_delete=models.PROTECT, related_name="wf_chantiers")
    caracteristique_chantier = models.OneToOneField("chantiers.CaracteristiqueChantier", on_delete=models.SET_NULL, null=True, blank=True, related_name="workflow")
    statut = models.CharField(max_length=30, choices=STATUS_CHOICES, default="brouillon")
    notes = models.TextField(blank=True)

    # Suivi affiché dans le diagramme de flux « analyse villages desserte » (chantier en cours)
    TYPE_TRAVAUX_CHOICES = [
        ("construction", "Construction"),
        ("rehabilitation", "Réhabilitation"),
    ]
    STATUT_CHANTIER_CHOICES = [
        ("en_preparation", "En préparation"),
        ("en_cours", "En cours"),
        ("suspendu", "Suspendu"),
        ("en_reception", "En réception"),
    ]
    type_travaux = models.CharField(
        max_length=20, choices=TYPE_TRAVAUX_CHOICES, blank=True, default="",
        verbose_name="Type de travaux")
    description = models.TextField(blank=True, default="", verbose_name="Description du chantier")
    statut_chantier = models.CharField(
        max_length=20, choices=STATUT_CHANTIER_CHOICES, default="en_cours",
        verbose_name="Statut du chantier")

    class Meta:
        db_table = "chantiers_workflows"

    @classmethod
    def next_code(cls, dt=None):
        target_dt = dt or timezone.now()
        year = target_dt.year
        prefix = f"WF-{year}-"

        max_seq = 0
        existing_codes = cls.objects.filter(code__startswith=prefix).values_list("code", flat=True)
        for current_code in existing_codes:
            suffix = (current_code or "")[len(prefix):]
            if suffix.isdigit():
                max_seq = max(max_seq, int(suffix))

        return f"{prefix}{max_seq + 1:04d}"


class ChantierSelectionEquipement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chantier = models.ForeignKey(ChantierWorkflow, on_delete=models.CASCADE, related_name="selections")
    type_equipement = models.ForeignKey("infrastructure.TypeEquipement", on_delete=models.PROTECT, related_name="wf_selections")
    type_point_eau = models.ForeignKey("billing.TypePointEau", on_delete=models.PROTECT, related_name="wf_selections", null=True, blank=True)
    quantite = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("1"))
    citerne_dimensionnement = models.ForeignKey(CiterneDimensionnement, on_delete=models.SET_NULL, null=True, blank=True, related_name="selections")

    class Meta:
        db_table = "chantiers_selections_equipements"


class ChantierBesoinLigne(models.Model):
    TYPE_CHOICES = [("designation", "Designation"), ("main_oeuvre", "Main oeuvre")]
    ORIGINE_CHOICES = [("auto", "Auto"), ("surplus", "Surplus"), ("recollement", "Recollement")]
    STATUT_CHOICES = [("a_commander", "A commander"), ("commande", "Commande"), ("livre", "Livre"), ("utilise", "Utilise"), ("retourne", "Retourne")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chantier = models.ForeignKey(ChantierWorkflow, on_delete=models.CASCADE, related_name="besoins")
    selection = models.ForeignKey(ChantierSelectionEquipement, on_delete=models.SET_NULL, null=True, blank=True, related_name="besoins")
    type_ligne = models.CharField(max_length=20, choices=TYPE_CHOICES)
    designation = models.ForeignKey("planning.Designation", on_delete=models.PROTECT, null=True, blank=True, related_name="wf_besoins")
    poste_main_oeuvre = models.ForeignKey(PosteMainOeuvre, on_delete=models.PROTECT, null=True, blank=True, related_name="wf_besoins")
    quantite = models.DecimalField(max_digits=14, decimal_places=4)
    prix_unitaire = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    origine = models.CharField(max_length=20, choices=ORIGINE_CHOICES, default="auto")
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default="a_commander")

    class Meta:
        db_table = "chantiers_besoins_lignes"


class ChantierSurplusLigne(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chantier = models.ForeignKey(ChantierWorkflow, on_delete=models.CASCADE, related_name="surplus")
    type_ligne = models.CharField(max_length=20, choices=ChantierBesoinLigne.TYPE_CHOICES)
    designation = models.ForeignKey("planning.Designation", on_delete=models.PROTECT, null=True, blank=True, related_name="wf_surplus")
    poste_main_oeuvre = models.ForeignKey(PosteMainOeuvre, on_delete=models.PROTECT, null=True, blank=True, related_name="wf_surplus")
    quantite = models.DecimalField(max_digits=14, decimal_places=4)
    prix_unitaire = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    justification = models.TextField(blank=True)

    class Meta:
        db_table = "chantiers_surplus_lignes"


class ChantierDocument(models.Model):
    TYPE_CHOICES = [("devis", "Devis"), ("contrat", "Contrat"), ("avenant", "Avenant"), ("facture_tranche", "Facture tranche"), ("devis_final", "Devis final")]
    STATUT_CHOICES = [("brouillon", "Brouillon"), ("valide", "Valide"), ("annule", "Annule")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chantier = models.ForeignKey(ChantierWorkflow, on_delete=models.CASCADE, related_name="documents")
    type_document = models.CharField(max_length=30, choices=TYPE_CHOICES)
    numero = models.CharField(max_length=120)
    date_document = models.DateField(null=True, blank=True)
    tacheron = models.ForeignKey("chantiers.Tacheron", on_delete=models.SET_NULL, null=True, blank=True, related_name="wf_documents")
    montant = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default="brouillon")
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="enfants")

    class Meta:
        db_table = "chantiers_documents"
        constraints = [models.UniqueConstraint(fields=["chantier", "type_document", "numero"], name="uq_wf_document")]


class ChantierMouvement(models.Model):
    TYPE_CHOICES = [("commande", "Commande"), ("livraison", "Livraison"), ("utilisation", "Utilisation"), ("retour", "Retour"), ("recollement", "Recollement")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chantier = models.ForeignKey(ChantierWorkflow, on_delete=models.CASCADE, related_name="mouvements")
    besoin = models.ForeignKey(ChantierBesoinLigne, on_delete=models.SET_NULL, null=True, blank=True, related_name="mouvements")
    type_mouvement = models.CharField(max_length=20, choices=TYPE_CHOICES)
    date_mouvement = models.DateTimeField()
    quantite = models.DecimalField(max_digits=14, decimal_places=4)
    reference_document = models.CharField(max_length=120, blank=True)

    class Meta:
        db_table = "chantiers_mouvements"


_SAFE_OPERATORS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv, ast.Pow: op.pow, ast.USub: op.neg}


def _safe_eval_formula(expr: str, variables: dict[str, Decimal]) -> Decimal:
    def _eval(node):
        if isinstance(node, ast.Constant):
            return Decimal(str(node.value))
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ValidationError(f"Variable inconnue: {node.id}")
            return Decimal(variables[node.id])
        if isinstance(node, ast.BinOp):
            return _SAFE_OPERATORS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            return _SAFE_OPERATORS[type(node.op)](_eval(node.operand))
        raise ValidationError("Formule non supportee.")

    return _eval(ast.parse(expr, mode="eval").body)


def generer_besoins_chantier(chantier: ChantierWorkflow, reset_auto: bool = True) -> int:
    if reset_auto:
        chantier.besoins.filter(origine="auto").delete()
    created = 0
    sels = chantier.selections.select_related("type_equipement", "type_point_eau", "citerne_dimensionnement")
    for sel in sels:
        modeles = WorkflowModeleEquipement.objects.filter(actif=True, type_equipement=sel.type_equipement).filter(models.Q(type_point_eau=sel.type_point_eau) | models.Q(type_point_eau__isnull=True))
        for modele in modeles.prefetch_related("lignes__designation"):
            for ligne in modele.lignes.all():
                qte_u = Decimal(ligne.quantite_unitaire or 0)
                if ligne.mode_quantite == "formule":
                    if not sel.citerne_dimensionnement:
                        continue
                    qte_u = _safe_eval_formula(ligne.formule_quantite or "0", sel.citerne_dimensionnement.context)
                qte = qte_u * Decimal(sel.quantite)
                if qte <= 0:
                    continue
                ChantierBesoinLigne.objects.create(chantier=chantier, selection=sel, type_ligne="designation", designation=ligne.designation, quantite=qte, prix_unitaire=ligne.designation.prix_unitaire, origine="auto")
                created += 1
        baremes = BaremeMainOeuvre.objects.filter(type_equipement=sel.type_equipement).filter(models.Q(type_point_eau=sel.type_point_eau) | models.Q(type_point_eau__isnull=True))
        for b in baremes:
            qte = Decimal(b.quantite_unitaire) * Decimal(sel.quantite)
            if qte <= 0:
                continue
            ChantierBesoinLigne.objects.create(chantier=chantier, selection=sel, type_ligne="main_oeuvre", poste_main_oeuvre=b.poste, quantite=qte, prix_unitaire=b.prix_unitaire, origine="auto")
            created += 1
    if created:
        chantier.statut = "besoins_generes"
        chantier.save(update_fields=["statut"])
    return created
