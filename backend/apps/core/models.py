import binascii
import os
import uuid
from os import path

from django.conf import settings
from django.db import models
from django.utils import timezone


class Region(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, verbose_name="Nom de la région")
    createdat = models.DateTimeField(null=True, blank=True)
    updatedat = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'core_regions'
        verbose_name = 'Région (Legacy)'
        verbose_name_plural = 'Régions (Legacy)'

    def __str__(self):
        return self.nom

    @property
    def region_name(self):
        """Alias pour compatibilité avec les templates"""
        return self.nom


class District(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, verbose_name="Nom du district")
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='districts', db_column='regionid')
    createdat = models.DateTimeField(null=True, blank=True)
    updatedat = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'core_districts'
        verbose_name = 'District (Legacy)'
        verbose_name_plural = 'Districts (Legacy)'

    def __str__(self):
        return f"{self.nom} ({self.region.nom})"

    @property
    def district_name(self):
        """Alias pour compatibilité avec les templates"""
        return self.nom


class Commune(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, verbose_name="Nom de la commune")
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name='communes', db_column='districtid')
    nommaire = models.CharField(max_length=255, null=True, blank=True)
    contactmaire = models.CharField(max_length=255, null=True, blank=True)
    nompresidentconseil = models.CharField(max_length=255, null=True, blank=True)
    contactpresidentconseil = models.CharField(max_length=255, null=True, blank=True)
    nompremierconseiller = models.CharField(max_length=255, null=True, blank=True)
    contactpremierconseiller = models.CharField(max_length=255, null=True, blank=True)
    nomsecondconseiller = models.CharField(max_length=255, null=True, blank=True)
    contactsecondconseiller = models.CharField(max_length=255, null=True, blank=True)
    nomtroisiemeconseiller = models.CharField(max_length=255, null=True, blank=True)
    contacttroisiemeconseiller = models.CharField(max_length=255, null=True, blank=True)
    nomquatriemeconseiller = models.CharField(max_length=255, null=True, blank=True)
    contactquatriemeconseiller = models.CharField(max_length=255, null=True, blank=True)
    nomcinquiemeconseiller = models.CharField(max_length=255, null=True, blank=True)
    contactcinquiemeconseiller = models.CharField(max_length=255, null=True, blank=True)
    createdat = models.DateTimeField(null=True, blank=True)
    updatedat = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'core_communes'
        verbose_name = 'Commune (Legacy)'
        verbose_name_plural = 'Communes (Legacy)'

    def __str__(self):
        return f"{self.nom} ({self.district.district_name})"

    @property
    def commune_name(self):
        """Alias pour compatibilité avec les templates"""
        return self.nom


class Village(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, verbose_name="Nom du village")
    commune = models.ForeignKey(Commune, on_delete=models.CASCADE, related_name='villages', db_column='communeid')
    classeadmin = models.CharField(max_length=255, null=True, blank=True)
    accessibilite = models.CharField(max_length=255, null=True, blank=True)
    distancekm = models.FloatField(null=True, blank=True)
    departpourtaxibrousse = models.CharField(max_length=255, null=True, blank=True)
    nbheuresmarche = models.FloatField(null=True, blank=True)
    idxls = models.IntegerField(null=True, blank=True)
    createdat = models.DateTimeField(null=True, blank=True)
    updatedat = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'core_villages'
        verbose_name = 'Village (Legacy)'
        verbose_name_plural = 'Villages (Legacy)'

    def __str__(self):
        return f"{self.nom} ({self.commune.nom})"

    @property
    def village_name(self):
        """Alias pour compatibilité avec les templates"""
        return self.nom


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org_name = models.CharField(max_length=255)
    org_acronym = models.CharField(max_length=50, null=True, blank=True)
    org_type = models.CharField(max_length=100, null=True, blank=True)
    org_address = models.TextField(null=True, blank=True)
    org_contact = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_organisations'
        verbose_name = 'Organisation (Legacy)'
        verbose_name_plural = 'Organisations (Legacy)'

    def __str__(self):
        return self.org_acronym or self.org_name


class Base(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    base_name = models.CharField(max_length=255)
    base_code = models.CharField(max_length=50, unique=True)
    village = models.ForeignKey(Village, on_delete=models.CASCADE, related_name='bases')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='bases')
    base_type = models.CharField(max_length=100, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_bases'
        verbose_name = 'Base (Legacy)'
        verbose_name_plural = 'Bases (Legacy)'

    def __str__(self):
        return f"{self.base_name} ({self.base_code})"


def partner_report_archive_upload_to(instance, filename):
    extension = (path.splitext(filename or '')[1] or '').lower() or '.docx'
    scope_fragment = (instance.scope_key or 'scope').replace(':', '_').replace('/', '_')
    return (
        f"partner_report_archives/{instance.organisation_id}/"
        f"{instance.report_year}/T{instance.report_quarter}/"
        f"{scope_fragment}{extension}"
    )


class PartnerQuarterlyReportArchive(models.Model):
    SCOPE_ORGANISATION = 'organisation'
    SCOPE_REGION = 'region'
    SCOPE_DISTRICT = 'district'
    SCOPE_COMMUNE = 'commune'
    SCOPE_CHOICES = [
        (SCOPE_ORGANISATION, 'Organisation'),
        (SCOPE_REGION, 'Region'),
        (SCOPE_DISTRICT, 'District'),
        (SCOPE_COMMUNE, 'Commune'),
    ]

    QUARTER_CHOICES = [
        (1, 'T1'),
        (2, 'T2'),
        (3, 'T3'),
        (4, 'T4'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        'organization.Organisation',
        on_delete=models.CASCADE,
        related_name='partner_report_archives',
        verbose_name='Organisation racine',
    )
    report_year = models.PositiveIntegerField(verbose_name='Annee du rapport')
    report_quarter = models.PositiveSmallIntegerField(
        choices=QUARTER_CHOICES,
        verbose_name='Trimestre',
    )
    scope_level = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default=SCOPE_ORGANISATION,
        verbose_name='Niveau de perimetre',
    )
    scope_key = models.CharField(max_length=120, verbose_name='Cle de perimetre')
    region = models.ForeignKey(
        'geography.Region',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='partner_report_archives',
    )
    district = models.ForeignKey(
        'geography.District',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='partner_report_archives',
    )
    commune = models.ForeignKey(
        'geography.Commune',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='partner_report_archives',
    )
    filters = models.JSONField(default=dict, blank=True, verbose_name='Filtres appliques')
    layout_config = models.JSONField(default=dict, blank=True, verbose_name='Configuration HTML')
    html_content = models.TextField(blank=True, default='', verbose_name='Archive HTML')
    document_file = models.FileField(
        upload_to=partner_report_archive_upload_to,
        verbose_name='Document archive',
        null=True,
        blank=True,
    )
    generated_at = models.DateTimeField(default=timezone.now, db_index=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_partner_report_archives',
    )
    is_automatic = models.BooleanField(default=True, verbose_name='Generation automatique')
    is_user_uploaded = models.BooleanField(default=False, verbose_name='Version utilisateur')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_partner_report_archives',
    )
    file_size = models.PositiveBigIntegerField(null=True, blank=True, verbose_name='Taille en octets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'partner_quarterly_report_archives'
        verbose_name = 'Archive Word rapport partenaires trimestriel'
        verbose_name_plural = 'Archives Word rapport partenaires trimestriel'
        ordering = ['-report_year', '-report_quarter', 'organisation__nom_organisation', 'scope_level']
        constraints = [
            models.UniqueConstraint(
                fields=['organisation', 'report_year', 'report_quarter', 'scope_key'],
                name='uniq_partner_report_archive_scope',
            )
        ]

    def __str__(self):
        return f"{self.organisation} - T{self.report_quarter} {self.report_year} - {self.scope_key}"

    @property
    def period_label(self):
        return f"T{self.report_quarter} {self.report_year}"

    @property
    def territory_label(self):
        if self.scope_level == self.SCOPE_COMMUNE and self.commune:
            return self.commune.nom_commune
        if self.scope_level == self.SCOPE_DISTRICT and self.district:
            return self.district.nom_district
        if self.scope_level == self.SCOPE_REGION and self.region:
            return self.region.nom_region
        return self.organisation.nom_organisation

    @property
    def file_extension(self):
        return (path.splitext(getattr(self.document_file, 'name', '') or '')[1] or '').lower()

    @property
    def is_word_document(self):
        return self.file_extension in {'.docx', '.doc'}

    @property
    def has_html_archive(self):
        return bool((self.html_content or '').strip())

    @property
    def html_size_bytes(self):
        if not self.has_html_archive:
            return 0
        return len((self.html_content or '').encode('utf-8'))


def extracted_document_image_upload_to(instance, filename):
    source = instance.document_source
    source_name = path.splitext(source.source_file_name or 'document')[0]
    month_path = timezone.localtime().strftime('%Y/%m')
    return f"extracted_documents/{month_path}/{source_name}/{filename}"


class DocumentSource(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_EXTRACTED = 'extracted'
    STATUS_UNSUPPORTED = 'unsupported'
    STATUS_ERROR = 'error'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_EXTRACTED, 'Extracted'),
        (STATUS_UNSUPPORTED, 'Unsupported'),
        (STATUS_ERROR, 'Error'),
    ]

    FILE_TYPE_PDF = 'pdf'
    FILE_TYPE_DOCX = 'docx'
    FILE_TYPE_DOC = 'doc'

    FILE_TYPE_CHOICES = [
        (FILE_TYPE_PDF, 'PDF'),
        (FILE_TYPE_DOCX, 'DOCX'),
        (FILE_TYPE_DOC, 'DOC'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_file_name = models.CharField(max_length=255, db_index=True)
    source_file_path = models.TextField(unique=True)
    source_folder_path = models.TextField()
    relative_path = models.TextField(blank=True, default='')
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES)
    file_size = models.PositiveBigIntegerField(default=0)
    file_hash_sha256 = models.CharField(max_length=64, blank=True, default='', db_index=True)
    scanned_at = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    error_message = models.TextField(blank=True, default='')
    images_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'core_document_sources'
        ordering = ['-scanned_at']
        verbose_name = 'Document source extrait'
        verbose_name_plural = 'Documents source extraits'

    def __str__(self):
        return self.source_file_name

    @property
    def parent_folder_name(self):
        return os.path.basename(self.source_folder_path.rstrip('/\\'))


class ExtractedDocumentImage(models.Model):
    STATUS_EXTRACTED = 'extracted'
    STATUS_DUPLICATE = 'duplicate'
    STATUS_ERROR = 'error'

    STATUS_CHOICES = [
        (STATUS_EXTRACTED, 'Extracted'),
        (STATUS_DUPLICATE, 'Duplicate'),
        (STATUS_ERROR, 'Error'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_source = models.ForeignKey(
        DocumentSource,
        on_delete=models.CASCADE,
        related_name='extracted_images',
    )
    image_file = models.ImageField(upload_to=extracted_document_image_upload_to, blank=True, null=True)
    extracted_file_name = models.CharField(max_length=255)
    original_internal_name = models.CharField(max_length=255, blank=True, default='')
    source_page_number = models.PositiveIntegerField(null=True, blank=True)
    image_index = models.PositiveIntegerField(default=1)
    image_extension = models.CharField(max_length=20, blank=True, default='')
    image_size = models.PositiveBigIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    image_hash_sha256 = models.CharField(max_length=64, db_index=True)
    is_duplicate = models.BooleanField(default=False, db_index=True)
    duplicate_of = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='duplicate_children',
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_EXTRACTED, db_index=True)
    error_message = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'core_extracted_document_images'
        ordering = ['-created_at']
        verbose_name = 'Image extraite depuis document'
        verbose_name_plural = 'Images extraites depuis documents'

    def __str__(self):
        return self.extracted_file_name


class DocumentationModule(models.Model):
    WORKSPACE_MAIN = 'main'
    WORKSPACE_ACCOUNTING = 'accounting'
    WORKSPACE_PAYROLL = 'payroll'
    WORKSPACE_ADMIN = 'admin'
    WORKSPACE_ANALYSES = 'analyses'
    WORKSPACE_OUVRAGES = 'ouvrages'

    WORKSPACE_CHOICES = [
        (WORKSPACE_MAIN, 'Site principal'),
        (WORKSPACE_ACCOUNTING, 'Compta'),
        (WORKSPACE_PAYROLL, 'Paie'),
        (WORKSPACE_ADMIN, 'Admin'),
        (WORKSPACE_ANALYSES, 'Analyses'),
        (WORKSPACE_OUVRAGES, 'Ouvrages'),
    ]

    STATUS_DRAFT = 'draft'
    STATUS_REVIEW = 'review'
    STATUS_VALIDATED = 'validated'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Brouillon'),
        (STATUS_REVIEW, 'A relire'),
        (STATUS_VALIDATED, 'Validee'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=120, unique=True)
    workspace = models.CharField(max_length=20, choices=WORKSPACE_CHOICES, default=WORKSPACE_MAIN, db_index=True)
    name = models.CharField(max_length=160, verbose_name='Nom du module')
    short_name = models.CharField(max_length=80, blank=True, default='', verbose_name='Nom court')
    icon = models.CharField(max_length=80, blank=True, default='fas fa-book', verbose_name='Icone')
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    is_priority = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    objective = models.TextField(blank=True, default='', verbose_name='Objectif du module')
    target_audience = models.TextField(blank=True, default='', verbose_name='Public concerne')
    data_used = models.TextField(blank=True, default='', verbose_name='Donnees utilisees')
    pages_in_scope = models.JSONField(default=list, blank=True, verbose_name='Pages ou vues concernees')
    buttons = models.JSONField(default=list, blank=True, verbose_name='Boutons disponibles')
    filters = models.JSONField(default=list, blank=True, verbose_name='Filtres disponibles')
    tables = models.JSONField(default=list, blank=True, verbose_name='Tableaux affiches')
    statistics = models.JSONField(default=list, blank=True, verbose_name='Statistiques affichees')
    charts = models.JSONField(default=list, blank=True, verbose_name='Graphiques affiches')
    calculation_rules_text = models.TextField(blank=True, default='', verbose_name='Regles de calcul')
    display_conditions = models.TextField(blank=True, default='', verbose_name='Conditions d affichage')
    edge_cases = models.TextField(blank=True, default='', verbose_name='Cas particuliers')
    possible_errors = models.TextField(blank=True, default='', verbose_name='Messages d erreur possibles')
    known_limits = models.TextField(blank=True, default='', verbose_name='Limites connues')
    test_notes = models.TextField(blank=True, default='', verbose_name='Tests associes')
    workflow_url = models.CharField(max_length=255, blank=True, default='', verbose_name='URL workflow existante')
    source_code_refs = models.JSONField(default=list, blank=True, verbose_name='References code')
    validation_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    last_reviewed_at = models.DateField(null=True, blank=True, verbose_name='Date de derniere mise a jour')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_documentation_modules'
        ordering = ['display_order', 'name']
        verbose_name = 'Documentation module'
        verbose_name_plural = 'Documentations modules'

    def __str__(self):
        return self.name


class IndicatorDefinition(models.Model):
    UPDATE_DAILY = 'daily'
    UPDATE_WEEKLY = 'weekly'
    UPDATE_MONTHLY = 'monthly'
    UPDATE_ON_DEMAND = 'on_demand'

    UPDATE_CHOICES = [
        (UPDATE_DAILY, 'Quotidienne'),
        (UPDATE_WEEKLY, 'Hebdomadaire'),
        (UPDATE_MONTHLY, 'Mensuelle'),
        (UPDATE_ON_DEMAND, 'A la demande'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.ForeignKey(
        DocumentationModule,
        on_delete=models.CASCADE,
        related_name='indicator_definitions',
    )
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=160, unique=True)
    objective = models.TextField(blank=True, default='')
    formula = models.TextField(blank=True, default='')
    data_source = models.TextField(blank=True, default='')
    refresh_frequency = models.CharField(max_length=20, choices=UPDATE_CHOICES, default=UPDATE_MONTHLY)
    interpretation = models.TextField(blank=True, default='')
    limitations = models.TextField(blank=True, default='')
    example = models.TextField(blank=True, default='')
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_indicator_definitions'
        ordering = ['module__display_order', 'display_order', 'name']
        verbose_name = 'Definition indicateur'
        verbose_name_plural = 'Definitions indicateurs'

    def __str__(self):
        return self.name


class CalculationRule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.ForeignKey(
        DocumentationModule,
        on_delete=models.CASCADE,
        related_name='calculation_rules',
    )
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True, default='')
    formula = models.TextField(blank=True, default='')
    source_fields = models.TextField(blank=True, default='')
    caveats = models.TextField(blank=True, default='')
    example = models.TextField(blank=True, default='')
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_calculation_rules'
        ordering = ['module__display_order', 'display_order', 'title']
        verbose_name = 'Regle de calcul'
        verbose_name_plural = 'Regles de calcul'

    def __str__(self):
        return self.title


class KnownLimitation(models.Model):
    SEVERITY_LOW = 'low'
    SEVERITY_MEDIUM = 'medium'
    SEVERITY_HIGH = 'high'
    SEVERITY_CRITICAL = 'critical'

    SEVERITY_CHOICES = [
        (SEVERITY_LOW, 'Faible'),
        (SEVERITY_MEDIUM, 'Moyenne'),
        (SEVERITY_HIGH, 'Elevee'),
        (SEVERITY_CRITICAL, 'Critique'),
    ]

    STATUS_OPEN = 'open'
    STATUS_MONITORED = 'monitored'
    STATUS_RESOLVED = 'resolved'

    STATUS_CHOICES = [
        (STATUS_OPEN, 'Ouverte'),
        (STATUS_MONITORED, 'Surveillee'),
        (STATUS_RESOLVED, 'Resolue'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.ForeignKey(
        DocumentationModule,
        on_delete=models.CASCADE,
        related_name='known_limitations',
    )
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True, default='')
    impact = models.TextField(blank=True, default='')
    workaround = models.TextField(blank=True, default='')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default=SEVERITY_MEDIUM, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_known_limitations'
        ordering = ['module__display_order', 'display_order', 'title']
        verbose_name = 'Limite connue'
        verbose_name_plural = 'Limites connues'

    def __str__(self):
        return self.title


class TestProtocol(models.Model):
    TYPE_UNIT = 'unit'
    TYPE_FUNCTIONAL = 'functional'
    TYPE_INTEGRATION = 'integration'
    TYPE_DISPLAY = 'display'
    TYPE_CALCULATION = 'calculation'
    TYPE_FILTER = 'filter'
    TYPE_EXPORT = 'export'
    TYPE_IMPORT = 'import'

    TYPE_CHOICES = [
        (TYPE_UNIT, 'Unitaire'),
        (TYPE_FUNCTIONAL, 'Fonctionnel'),
        (TYPE_INTEGRATION, 'Integration'),
        (TYPE_DISPLAY, 'Affichage'),
        (TYPE_CALCULATION, 'Calcul'),
        (TYPE_FILTER, 'Filtre'),
        (TYPE_EXPORT, 'Export'),
        (TYPE_IMPORT, 'Import'),
    ]

    STATUS_TODO = 'todo'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_FIX = 'to_fix'
    STATUS_BLOCKED = 'blocked'

    STATUS_CHOICES = [
        (STATUS_TODO, 'A faire'),
        (STATUS_SUCCESS, 'Reussi'),
        (STATUS_FAILED, 'Echoue'),
        (STATUS_FIX, 'A corriger'),
        (STATUS_BLOCKED, 'Bloque'),
    ]

    CRITICALITY_LOW = 'low'
    CRITICALITY_MEDIUM = 'medium'
    CRITICALITY_HIGH = 'high'
    CRITICALITY_CRITICAL = 'critical'

    CRITICALITY_CHOICES = [
        (CRITICALITY_LOW, 'Faible'),
        (CRITICALITY_MEDIUM, 'Moyenne'),
        (CRITICALITY_HIGH, 'Elevee'),
        (CRITICALITY_CRITICAL, 'Critique'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True, db_index=True, verbose_name='Identifiant du test')
    module = models.ForeignKey(
        DocumentationModule,
        on_delete=models.CASCADE,
        related_name='test_protocols',
    )
    test_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_FUNCTIONAL, db_index=True)
    objective = models.TextField(blank=True, default='')
    preconditions = models.TextField(blank=True, default='')
    required_data = models.TextField(blank=True, default='')
    steps = models.TextField(blank=True, default='')
    expected_result = models.TextField(blank=True, default='')
    last_result = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TODO, db_index=True)
    criticality = models.CharField(max_length=20, choices=CRITICALITY_CHOICES, default=CRITICALITY_MEDIUM, db_index=True)
    last_executed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    executed_by_name = models.CharField(max_length=120, blank=True, default='')
    comment = models.TextField(blank=True, default='')
    evidence_path = models.CharField(max_length=255, blank=True, default='')
    related_issue = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_test_protocols'
        ordering = ['module__display_order', 'code']
        verbose_name = 'Protocole de test'
        verbose_name_plural = 'Protocoles de test'

    def __str__(self):
        return self.code

    @property
    def latest_execution(self):
        return self.executions.order_by('-executed_at').first()


class TestExecution(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    protocol = models.ForeignKey(
        TestProtocol,
        on_delete=models.CASCADE,
        related_name='executions',
    )
    executed_at = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=20, choices=TestProtocol.STATUS_CHOICES, default=TestProtocol.STATUS_TODO, db_index=True)
    result_obtained = models.TextField(blank=True, default='')
    executed_by_name = models.CharField(max_length=120, blank=True, default='')
    comment = models.TextField(blank=True, default='')
    evidence_path = models.CharField(max_length=255, blank=True, default='')
    related_issue = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_test_executions'
        ordering = ['-executed_at']
        verbose_name = 'Execution de test'
        verbose_name_plural = 'Executions de tests'

    def __str__(self):
        return f"{self.protocol.code} - {self.executed_at:%Y-%m-%d %H:%M}"


class DocumentationChangeLog(models.Model):
    TYPE_CORRECTION = 'correction'
    TYPE_VALIDATION = 'validation'
    TYPE_TEST = 'test'
    TYPE_DOC = 'documentation'

    TYPE_CHOICES = [
        (TYPE_CORRECTION, 'Correction'),
        (TYPE_VALIDATION, 'Validation'),
        (TYPE_TEST, 'Test'),
        (TYPE_DOC, 'Documentation'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.ForeignKey(
        DocumentationModule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='change_logs',
    )
    title = models.CharField(max_length=160)
    entry_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_DOC, db_index=True)
    details = models.TextField(blank=True, default='')
    happened_on = models.DateField(default=timezone.localdate, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_documentation_change_logs'
        ordering = ['-happened_on', '-created_at']
        verbose_name = 'Historique documentation'
        verbose_name_plural = 'Historique documentation'

    def __str__(self):
        return self.title


class RepairActivityEquipmentPolicy(models.Model):
    """Activities allowed in the quick repair modal for one equipment type."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type_equipement = models.OneToOneField(
        'infrastructure.TypeEquipement',
        on_delete=models.CASCADE,
        related_name='repair_activity_policy',
        verbose_name="Type d'équipement",
    )
    allowed_activities = models.ManyToManyField(
        'employees.FichePoste',
        blank=True,
        related_name='allowed_equipment_repair_policies',
        verbose_name='Activités autorisées',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_repair_activity_equipment_policies',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_repair_activity_equipment_policies'
        ordering = ['type_equipement__nom_type']
        verbose_name = "Règle d'activités de réparation par type d'équipement"
        verbose_name_plural = "Règles d'activités de réparation par type d'équipement"

    def __str__(self):
        return str(self.type_equipement)


class RepairActivityPointTypePolicy(models.Model):
    """Activities allowed in the quick repair modal for one water-point type."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type_point_eau = models.OneToOneField(
        'billing.TypePointEau',
        on_delete=models.CASCADE,
        related_name='repair_activity_policy',
        verbose_name="Type de point d'eau",
    )
    allowed_activities = models.ManyToManyField(
        'employees.FichePoste',
        blank=True,
        related_name='allowed_point_type_repair_policies',
        verbose_name='Activités autorisées',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_repair_activity_point_type_policies',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_repair_activity_point_type_policies'
        ordering = ['type_point_eau__nom_type']
        verbose_name = "Règle d'activités de réparation par type de point d'eau"
        verbose_name_plural = "Règles d'activités de réparation par type de point d'eau"

    def __str__(self):
        return str(self.type_point_eau)


class ExplicationDepassementIndemnite(models.Model):
    """
    Explication demandee quand les indemnites RBF (compte 621102) d'un ouvrage depassent, sur une annee,
    le plafond de 40 000 Ar par point d'eau public.

    On conserve l'historique : la derniere explication couvre le depassement tant que le montant paye n'a pas
    augmente depuis (montant_paye = total de l'annee au moment de la saisie).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ouvrage = models.ForeignKey(
        'organization.Ouvrage', on_delete=models.CASCADE, related_name='explications_depassement_indemnite')
    annee = models.PositiveIntegerField()
    montant_paye = models.DecimalField(max_digits=14, decimal_places=2)
    plafond = models.DecimalField(max_digits=14, decimal_places=2)
    nb_points_publics = models.PositiveIntegerField()
    explication = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='explications_depassement_indemnite')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_explication_depassement_indemnite'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['ouvrage', 'annee', '-created_at'])]
        verbose_name = "Explication de depassement d'indemnite"
        verbose_name_plural = "Explications de depassement d'indemnite"

    def __str__(self):
        return f"{self.ouvrage_id} {self.annee} : {self.montant_paye} / {self.plafond}"


class ExplicationEcartIndemnitePoint(models.Model):
    """
    Explication d'un point d'eau dont les indemnites RBF (621102) de l'annee depassent 10 000 Ar par unite de
    forfaitaire pointee, ou sont payees sans aucun forfaitaire pointe (page des ecritures DiameX).

    Meme principe que ExplicationDepassementIndemnite (par ouvrage) : la derniere explication couvre l'alerte tant
    que le montant paye n'a pas augmente depuis sa saisie.
    """

    MOTIFS = [('depasse', "Depasse 10 000 Ar par forfaitaire"), ('sans_forfait', "Aucun forfaitaire pointe")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    point_eau = models.ForeignKey(
        'billing.PointEau', on_delete=models.CASCADE, related_name='explications_ecart_indemnite')
    annee = models.PositiveIntegerField()
    motif = models.CharField(max_length=20, choices=MOTIFS)
    montant_paye = models.DecimalField(max_digits=14, decimal_places=2)
    plafond = models.DecimalField(max_digits=14, decimal_places=2)
    unites_forfait = models.PositiveIntegerField()
    explication = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='explications_ecart_indemnite_point')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_explication_ecart_indemnite_point'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['point_eau', 'annee', '-created_at'])]
        verbose_name = "Explication d'ecart d'indemnite (point d'eau)"
        verbose_name_plural = "Explications d'ecart d'indemnite (point d'eau)"

    def __str__(self):
        return f"{self.point_eau_id} {self.annee} : {self.montant_paye} / {self.plafond}"


def generate_widget_token():
    return binascii.hexlify(os.urandom(32)).decode()


class WidgetAuthToken(models.Model):
    """
    Token d'authentification pour les clients hors navigateur (donc sans
    session/cookie Django) : widget desktop Electron, et app terrain
    Android. Le champ `scope` cloisonne chaque token aux endpoints de sa
    famille — un token 'widget' n'ouvre jamais les endpoints mobiles et
    inversement, même s'ils partagent le même mécanisme de vérification
    (voir apps.core.auth_tokens.token_or_session_required).
    """
    SCOPE_WIDGET = 'widget'
    SCOPE_MOBILE = 'mobile'
    SCOPE_CHOICES = [
        (SCOPE_WIDGET, 'Widget desktop (Electron)'),
        (SCOPE_MOBILE, 'App terrain Android'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=64, unique=True, default=generate_widget_token, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='widget_auth_tokens',
    )
    scope = models.CharField(
        max_length=20, choices=SCOPE_CHOICES, default=SCOPE_WIDGET, db_index=True,
        help_text="Famille d'endpoints que ce token peut appeler (widget desktop ou app mobile terrain).",
    )
    device_label = models.CharField(
        max_length=120, blank=True, default='',
        verbose_name='Appareil',
        help_text="Ex: 'PC bureau' ou 'Android - Samsung A14', pour identifier ce token dans l'admin",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Expiration du jeton. Null conserve la compatibilité des anciens clients.",
    )
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'core_widget_auth_tokens'
        verbose_name = 'Token client externe (widget/mobile)'
        verbose_name_plural = 'Tokens clients externes (widget/mobile)'

    def __str__(self):
        return f"{self.user.username} [{self.scope}] — {self.device_label or self.key[:8]}"

    @property
    def is_usable(self):
        now = timezone.now()
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > now)


class MobileRefreshToken(models.Model):
    """Jeton de renouvellement rotatif réservé à l'application logistique native."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=64, unique=True, default=generate_widget_token, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mobile_refresh_tokens',
    )
    device_id = models.UUIDField(db_index=True)
    device_label = models.CharField(max_length=120, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'core_mobile_refresh_tokens'
        ordering = ['-created_at']

    @property
    def is_usable(self):
        return self.revoked_at is None and self.expires_at > timezone.now() and self.user.is_active


class InterventionWidgetState(models.Model):
    """Publication actuellement présentée par le widget à un utilisateur."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='intervention_widget_state',
    )
    current_planning = models.ForeignKey(
        'planning.Planning',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    monitoring_started_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_intervention_widget_states'
        verbose_name = "État du widget des interventions"
        verbose_name_plural = "États du widget des interventions"

    def __str__(self):
        return f"{self.user.username}: {self.current_planning_id or 'aucune publication'}"


class InterventionWidgetRead(models.Model):
    """Accusé de lecture d'une saisie de réparation dans le widget."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='intervention_widget_reads',
    )
    planning = models.ForeignKey(
        'planning.Planning',
        on_delete=models.CASCADE,
        related_name='widget_reads',
    )
    seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'core_intervention_widget_reads'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'planning'],
                name='unique_intervention_widget_read',
            ),
        ]
        indexes = [
            models.Index(fields=['user', '-seen_at'], name='core_int_widget_user_seen_idx'),
        ]
        verbose_name = "Lecture du widget des interventions"
        verbose_name_plural = "Lectures du widget des interventions"

    def __str__(self):
        return f"{self.user.username}: {self.planning_id}"


class FiltreSauvegarde(models.Model):
    """Combinaison de filtres nommée et réutilisable pour une page de rapport.

    `page_key` identifie la page (ex: 'villages_desserte') et `parametres` stocke
    les paramètres GET de la page (region/district/commune/fokontany/etc.) tels
    quels, sous forme de dict JSON — les valeurs multi-select sont des listes.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page_key = models.CharField(max_length=100, verbose_name="Page")
    nom = models.CharField(max_length=150, verbose_name="Nom du filtre")
    parametres = models.JSONField(default=dict, verbose_name="Paramètres")
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='filtres_sauvegardes',
        verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'filtres_sauvegardes'
        ordering = ['nom']
        verbose_name = "Filtre sauvegardé"
        verbose_name_plural = "Filtres sauvegardés"
        constraints = [
            models.UniqueConstraint(
                fields=['page_key', 'nom'],
                name='unique_filtre_sauvegarde_page_nom',
            ),
        ]

    def __str__(self):
        return f"{self.nom} ({self.page_key})"


class ContributionTerrain(models.Model):
    """Journal (ajout seulement) des données apportées ou corrigées par les employés.

    Une ligne par intervention : qui, quand, quel objet, quelle catégorie de donnée.
    Alimenté automatiquement par apps/core/contributions.py ; ne jamais modifier ni
    écraser une ligne existante.
    """
    CATEGORIES = [
        ('photo', 'Photo'),
        ('gps', 'Point GPS'),
        ('telephone', 'Contact téléphonique'),
        ('nom_abonne', "Nom d'abonné"),
        ('volume_citerne', 'Volume de citerne'),
    ]
    ACTIONS = [
        ('ajout', 'Ajout (donnée jusque-là vide)'),
        ('modification', 'Modification'),
        ('suppression', 'Suppression'),
    ]
    SOURCES = [('web', 'Web'), ('mobile', 'Application mobile'), ('systeme', 'Système / import')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date = models.DateTimeField(default=timezone.now, db_index=True)
    employe = models.ForeignKey(
        'employees.Employe', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='contributions_terrain', verbose_name='Employé',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='+', verbose_name='Utilisateur',
    )
    modele = models.CharField(max_length=40, verbose_name="Type d'objet")
    objet_id = models.CharField(max_length=64, db_index=True)
    objet_libelle = models.CharField(max_length=255, blank=True)
    categorie = models.CharField(max_length=20, choices=CATEGORIES, db_index=True)
    champ = models.CharField(max_length=60, blank=True, verbose_name='Champ modifié')
    action = models.CharField(max_length=15, choices=ACTIONS)
    quantite = models.PositiveIntegerField(default=1, help_text='Nombre de photos ajoutées ; 1 pour les autres données')
    ancienne_valeur = models.CharField(max_length=255, blank=True)
    nouvelle_valeur = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=10, choices=SOURCES, default='web')

    class Meta:
        db_table = 'contributions_terrain'
        ordering = ['-date']
        verbose_name = 'Contribution terrain'
        verbose_name_plural = 'Contributions terrain'
        indexes = [models.Index(fields=['employe', 'date'], name='contrib_employe_date_idx')]

    def __str__(self):
        return f"{self.date:%d/%m/%Y} {self.employe_id} {self.categorie} {self.action}"


from apps.core.models_realisations import ConstatRealisation  # noqa: E402,F401
