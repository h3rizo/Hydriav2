# -*- coding: utf-8 -*-
from django.db import models
from django.contrib.auth.models import User
import uuid

class SystemParameter(models.Model):
    """Parametres systeme configurables"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=100, unique=True, verbose_name="Cle")
    value = models.TextField(verbose_name="Valeur")
    description = models.TextField(blank=True, verbose_name="Description")
    category = models.CharField(max_length=50, default='general', verbose_name="Categorie")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='system_parameters_updated',
        verbose_name="Modifie par"
    )

    class Meta:
        db_table = 'system_parameters'
        verbose_name = 'Parametre Systeme'
        verbose_name_plural = 'Parametres Systeme'
        ordering = ['category', 'key']

    def __str__(self):
        return f"{self.key}: {self.value}"


class ActivityLog(models.Model):
    """Logs d'activite du systeme"""
    LOG_TYPES = [
        ('create', 'Creation'),
        ('update', 'Modification'),
        ('delete', 'Suppression'),
        ('login', 'Connexion'),
        ('logout', 'Deconnexion'),
        ('export', 'Export'),
        ('import', 'Import'),
        ('error', 'Erreur'),
        ('warning', 'Avertissement'),
        ('info', 'Information'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    log_type = models.CharField(max_length=20, choices=LOG_TYPES, verbose_name="Type")
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
        verbose_name="Utilisateur"
    )
    employe = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
        verbose_name="Employe"
    )
    action = models.CharField(max_length=255, verbose_name="Action")
    model_name = models.CharField(max_length=100, blank=True, verbose_name="Modele")
    object_id = models.CharField(max_length=100, blank=True, verbose_name="ID Objet")
    details = models.TextField(blank=True, verbose_name="Details")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="Adresse IP")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date/Heure")

    class Meta:
        db_table = 'activity_logs'
        verbose_name = 'Log d\'activite'
        verbose_name_plural = 'Logs d\'activite'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['log_type']),
            models.Index(fields=['user']),
            models.Index(fields=['model_name']),
        ]

    def __str__(self):
        return f"{self.created_at} - {self.get_log_type_display()} - {self.action}"


class PasswordResetCode(models.Model):
    """Codes de réinitialisation de mot de passe envoyés par email"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(verbose_name="Email")
    code = models.CharField(max_length=6, verbose_name="Code")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    is_used = models.BooleanField(default=False, verbose_name="Utilisé")

    class Meta:
        db_table = 'password_reset_codes'
        verbose_name = 'Code de réinitialisation'
        verbose_name_plural = 'Codes de réinitialisation'
        ordering = ['-created_at']

class PageVisit(models.Model):
    """Enregistrement des visites de pages"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='page_visits',
        verbose_name="Utilisateur"
    )
    employe = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='page_visits',
        verbose_name="Employe"
    )
    path = models.CharField(max_length=255, verbose_name="Chemin de la page")
    query_params = models.TextField(blank=True, verbose_name="Paramètres de requête")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="Adresse IP")
    user_agent = models.TextField(blank=True, verbose_name="User Agent")
    referer = models.TextField(blank=True, verbose_name="Referer")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Date/Heure")

    class Meta:
        db_table = 'page_visits'
        verbose_name = 'Visite de page'
        verbose_name_plural = 'Visites de pages'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['path']),
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"{self.user or 'Anonyme'} a visité {self.path} le {self.timestamp}"


class UserPresence(models.Model):
    """Suivi des utilisateurs actifs sur les pages en temps réel (polling base)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='presences',
        verbose_name="Utilisateur"
    )
    employe = models.ForeignKey(
        'employees.Employe',
        on_delete=models.CASCADE,
        related_name='presences',
        null=True,
        blank=True,
        verbose_name="Employe"
    )
    path = models.CharField(max_length=255, verbose_name="Chemin de la page")
    last_seen = models.DateTimeField(auto_now=True, verbose_name="Dernière vue")

    class Meta:
        db_table = 'user_presences'
        verbose_name = 'Présence utilisateur'
        verbose_name_plural = 'Présences utilisateurs'
        unique_together = ('user', 'path')
        indexes = [
            models.Index(fields=['path', 'last_seen']),
        ]

    def __str__(self):
        return f"{self.user.username} sur {self.path} (vu {self.last_seen})"


class StorageSnapshot(models.Model):
    """Snapshot periodique de l'occupation disque du serveur."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    root_path = models.CharField(max_length=255, verbose_name="Racine surveillee")
    total_bytes = models.BigIntegerField(verbose_name="Capacite totale")
    used_bytes = models.BigIntegerField(verbose_name="Espace utilise")
    free_bytes = models.BigIntegerField(verbose_name="Espace libre")
    used_percent = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Pourcentage utilise")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date du snapshot")

    class Meta:
        db_table = 'storage_snapshots'
        verbose_name = 'Snapshot stockage'
        verbose_name_plural = 'Snapshots stockage'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['root_path']),
        ]

    def __str__(self):
        return f"{self.root_path} - {self.used_percent}% ({self.created_at})"
