from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from apps.employees.models import Employe
from apps.organization.models import Ouvrage

class Post(models.Model):
    """Post dans le fil d'actualité - généré automatiquement depuis inspections/plannings"""
    TYPE_CHOICES = [
        ('inspection', 'Inspection'),
        ('planning', 'Planning'),
        ('paiement_forfaitaire', 'Paiement forfaitaire'),
        ('coupure_eau', 'Coupure d\'eau'),
        ('remise_eau', 'Remise en eau'),
        ('releve_terrain', 'Relevés terrain'),
        ('gps_terrain', 'Positions GPS terrain'),
        ('photo_terrain', 'Photos terrain'),
        ('manuel', 'Post manuel'),
    ]

    STATUT_CHOICES = [
        ('actif', 'Actif'),
        ('termine', 'Terminé'),
        ('annule', 'Annulé'),
    ]

    type_post = models.CharField(max_length=30, choices=TYPE_CHOICES, default='manuel')
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='actif')
    titre = models.CharField(max_length=255)
    contenu = models.TextField()
    resume = models.TextField(blank=True, null=True, help_text="Résumé automatique")

    # Lien générique vers l'objet source (Inspection ou Planning)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.UUIDField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    # Métadonnées pour filtres
    auteur_employe = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts_crees_employe', help_text="Ancien champ auteur (Employe) - déprécié")
    auteur_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts_crees', help_text="Utilisateur qui a créé le post (null pour posts automatiques)")
    auteur_nom = models.CharField(max_length=255, blank=True, help_text="Nom affiché pour l'auteur (ex: 'Système' pour posts auto)")
    ouvrage = models.ForeignKey(Ouvrage, on_delete=models.SET_NULL, null=True, blank=True)
    employe_concerne = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts_concernant')

    # Tags pour recherche
    tags = models.CharField(max_length=500, blank=True, help_text="Tags séparés par des virgules")

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    epingle = models.BooleanField(default=False, help_text="Épingler en haut du fil")
    priorite = models.BooleanField(default=False, help_text="Post prioritaire nécessitant une attention immédiate")

    class Meta:
        db_table = 'feed_posts'
        ordering = ['-epingle', '-priorite', '-date_creation']
        indexes = [
            models.Index(fields=['-date_creation']),
            models.Index(fields=['type_post']),
            models.Index(fields=['ouvrage']),
        ]

    def __str__(self):
        return f"{self.get_type_post_display()} - {self.titre}"

    @property
    def nombre_commentaires(self):
        return self.commentaires.count()

    @property
    def nombre_likes(self):
        return self.likes.count()

    @property
    def nombre_dislikes(self):
        return self.dislikes.count()

    @property
    def nb_likes(self):
        """Alias pour compatibilité template"""
        return self.nombre_likes

    @property
    def nb_comments(self):
        """Alias pour compatibilité template"""
        return self.nombre_commentaires

    @property
    def nb_dislikes(self):
        """Alias pour compatibilité template"""
        return self.nombre_dislikes

    def user_has_liked(self, user):
        """Vérifie si l'utilisateur a liké ce post"""
        if hasattr(user, 'employe') and user.employe:
            return self.likes.filter(auteur_employe=user.employe).exists()
        return self.likes.filter(auteur_user=user).exists()

    def user_has_disliked(self, user):
        """Vérifie si l'utilisateur a disliké ce post"""
        if hasattr(user, 'employe') and user.employe:
            return self.dislikes.filter(auteur_employe=user.employe).exists()
        return self.dislikes.filter(auteur_user=user).exists()

    def get_commune_id(self):
        """Extrait l'ID de la commune depuis les tags"""
        if self.tags:
            for tag in self.tags.split(','):
                if tag.strip().startswith('commune:'):
                    return tag.strip()[8:]
        return None

    def get_ouvrage_id(self):
        """Extrait l'ID de l'ouvrage depuis les tags"""
        if self.tags:
            for tag in self.tags.split(','):
                if tag.strip().startswith('ouvrage:'):
                    return tag.strip()[8:]
        return None

class PostImage(models.Model):
    """Images attachées à un post"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='feed/posts/%Y/%m/')
    legende = models.CharField(max_length=255, blank=True)
    date_upload = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'feed_post_images'

    def __str__(self):
        return f"Image pour {self.post.titre}"

class Comment(models.Model):
    """Commentaire sur un post"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='commentaires')
    auteur_user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, help_text="Utilisateur auteur du commentaire")
    auteur_employe = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, help_text="Employé lié (si applicable)")
    auteur_nom = models.CharField(max_length=255, blank=True, help_text="Nom affiché de l'auteur")
    contenu = models.TextField()
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='reponses')

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'feed_comments'
        ordering = ['date_creation']

    def __str__(self):
        return f"Commentaire de {self.auteur_nom or 'Anonyme'} sur {self.post.titre}"

    @property
    def est_reponse(self):
        return self.parent is not None

class Like(models.Model):
    """Like sur un post"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes')
    auteur_user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    auteur_employe = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'feed_likes'
        # Pas de unique_together car auteur peut être user OU employe

    def __str__(self):
        nom = self.auteur_employe.nom_employe if self.auteur_employe else (self.auteur_user.username if self.auteur_user else 'Anonyme')
        return f"{nom} aime {self.post.titre}"

class Dislike(models.Model):
    """Dislike sur un post - Je n'approuve pas"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='dislikes')
    auteur_user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    auteur_employe = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'feed_dislikes'
        # Pas de unique_together car auteur peut être user OU employe

    def __str__(self):
        nom = self.auteur_employe.nom_employe if self.auteur_employe else (self.auteur_user.username if self.auteur_user else 'Anonyme')
        return f"{nom} n'approuve pas {self.post.titre}"
