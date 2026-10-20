from django.db import models
from django.contrib.auth.models import User
import uuid


class Tag(models.Model):
    """
    Modèle pour les tags des fichiers
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True, verbose_name="Nom du tag")
    color = models.CharField(max_length=7, default="#3b82f6", help_text="Couleur hexadécimale du tag")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name = "Tag"
        verbose_name_plural = "Tags"
        ordering = ['name']
    
    def __str__(self):
        return self.name


class FileUpload(models.Model):
    """
    Modèle pour les fichiers stockés dans Supabase
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filename = models.CharField(max_length=255, verbose_name="Nom du fichier")
    original_filename = models.CharField(max_length=255, verbose_name="Nom original")
    file_size = models.BigIntegerField(verbose_name="Taille (bytes)")
    content_type = models.CharField(max_length=100, verbose_name="Type MIME")
    supabase_path = models.TextField(verbose_name="Chemin Supabase")
    bucket_name = models.CharField(max_length=100, default="HydriaStock")
    
    # Métadonnées
    tags = models.ManyToManyField(Tag, blank=True, verbose_name="Tags")
    description = models.TextField(blank=True, verbose_name="Description")
    
    # Informations de suivi
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Téléchargé par")
    is_public = models.BooleanField(default=False, verbose_name="Fichier public")
    
    # Statut
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    
    class Meta:
        verbose_name = "Fichier"
        verbose_name_plural = "Fichiers"
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return self.filename
    
    @property
    def file_size_mb(self):
        """Retourne la taille en MB"""
        return round(self.file_size / 1024 / 1024, 2)
    
    @property
    def tags_list(self):
        """Retourne la liste des noms des tags"""
        return [tag.name for tag in self.tags.all()]
    
    def get_download_url(self):
        """Génère l'URL de téléchargement"""
        return f"/fichiers/download/{self.id}/"
    
    def get_supabase_signed_url(self, expires_in=3600):
        """Génère une URL signée Supabase pour accès direct (optionnel)"""
        from .services import storage_service
        return storage_service.create_signed_url(self.supabase_path, expires_in)
