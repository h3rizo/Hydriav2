import uuid

from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from apps.organization.models import Base


class Tag(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    color = models.CharField(max_length=7, default='#2563eb')
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Note(models.Model):
    NOTE_TYPE_CHOICES = [
        ('page', 'Page'),
        ('note', 'Note'),
        ('decision', 'Décision'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Brouillon'),
        ('active', 'Active'),
        ('archived', 'Archivée'),
    ]
    VISIBILITY_CHOICES = [
        ('private', 'Privée'),
        ('team', 'Partagée équipe'),
        ('all', 'Visible par tous'),
        ('antenne', 'Visible par antenne'),
        ('role', 'Visible par rôle'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subpages')
    title = models.CharField(max_length=255)
    note_type = models.CharField(max_length=20, choices=NOTE_TYPE_CHOICES, default='note')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    content_json = models.JSONField(default=list, blank=True)
    content_text = models.TextField(blank=True)
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='private')
    is_template = models.BooleanField(default=False, help_text="Si vrai, cette note est un modèle réutilisable")
    is_favorite = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    shared_with_base = models.ForeignKey(
        Base,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shared_notes'
    )
    visible_role_name = models.CharField(max_length=120, blank=True)
    team_label = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_notes')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_notes')
    favorited_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='favorite_notes', blank=True)
    tags = models.ManyToManyField(Tag, related_name='notes', blank=True)
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    ai_summary = models.TextField(blank=True, help_text="Résumé généré automatiquement par l'IA")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']
        indexes = [
            models.Index(fields=['note_type'], name='notes_note_ty_1156b6_idx'),
            models.Index(fields=['status'], name='notes_status_c41bea_idx'),
            models.Index(fields=['visibility'], name='notes_visibil_abebd7_idx'),
            models.Index(fields=['is_archived'], name='notes_is_arch_da2b38_idx'),
            models.Index(fields=['updated_at'], name='notes_updated_9a6ec7_idx'),
        ]

    def __str__(self):
        return self.title


class NoteLink(models.Model):
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='links')
    content_type = models.ForeignKey('contenttypes.ContentType', on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    label = models.CharField(max_length=255, blank=True)
    entity_type = models.CharField(max_length=80, blank=True)
    entity_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['content_type', 'object_id'], name='notes_notel_content_58cc9d_idx'),
            models.Index(fields=['entity_type', 'entity_id'], name='note_links_entity__5d70f7_idx'),
        ]

    def __str__(self):
        return f'{self.note.title} -> {self.label or self.entity_type or self.object_id}'


class NoteTask(models.Model):
    STATUS_CHOICES = [
        ('todo', 'À faire'),
        ('in_progress', 'En cours'),
        ('done', 'Terminé'),
        ('cancelled', 'Annulé'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_note_tasks')
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo')
    content_type = models.ForeignKey('contenttypes.ContentType', on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    entity_type = models.CharField(max_length=80, blank=True)
    entity_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['status', 'due_date', 'title']


class NoteDecision(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Brouillon'),
        ('approved', 'Approuvée'),
        ('rejected', 'Rejetée'),
        ('implemented', 'Mise en oeuvre'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='decisions')
    decision_text = models.TextField()
    context = models.TextField(blank=True)
    justification = models.TextField(blank=True)
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='note_decisions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    date_decided = models.DateField(null=True, blank=True)
    content_type = models.ForeignKey('contenttypes.ContentType', on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    entity_type = models.CharField(max_length=80, blank=True)
    entity_id = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['-date_decided', '-id']


class NoteComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']


class NoteVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='versions')
    title = models.CharField(max_length=255, blank=True)
    content_json = models.JSONField(default=list, blank=True)
    content_text = models.TextField(blank=True)
    saved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class NoteAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='notes/attachments/%Y/%m/')
    label = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

