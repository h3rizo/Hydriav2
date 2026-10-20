"""Circuit de validation Hydria, indépendant des tables et des exports Access."""
from django.conf import settings
from django.db import models


class MoisPointage(models.Model):
    fichier_source = models.CharField(max_length=255)
    periode = models.DateField(help_text="Premier jour du mois comptable (Date mouvement)")
    empreinte_validee = models.CharField(max_length=64, blank=True)
    valide_le = models.DateTimeField(null=True, blank=True)
    valide_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name='+')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['fichier_source', 'periode'], name='pointage_mois_unique')]


class ObjetPointage(models.Model):
    mois = models.ForeignKey(MoisPointage, on_delete=models.PROTECT, related_name='objets')
    # Clé métier stable : ligne:<id_access>, journal:<code>, tiers:<compte>:<pers>.
    cle = models.CharField(max_length=400)
    nature = models.CharField(max_length=20, choices=[('ligne', 'Ligne DiameX'), ('solde', 'Rapprochement')])
    empreinte = models.CharField(max_length=64, blank=True)
    niveau = models.PositiveSmallIntegerField(default=0)
    correction = models.BooleanField(default=False)
    # Les soldes sont préparés dans Hydria ; aucun champ Access n'est modifié.
    solde_reference = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    justification = models.TextField(blank=True)
    document = models.ForeignKey('accounting.DocumentationComptable', null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name='+')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['mois', 'cle'], name='pointage_objet_unique'),
            models.CheckConstraint(condition=models.Q(niveau__lte=3), name='pointage_niveau_valide'),
        ]


class DecisionPointage(models.Model):
    mois = models.ForeignKey(MoisPointage, on_delete=models.PROTECT, related_name='decisions')
    objet = models.ForeignKey(ObjetPointage, null=True, blank=True, on_delete=models.PROTECT, related_name='decisions')
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    auteur_libelle = models.CharField(max_length=255)
    role = models.CharField(max_length=20, blank=True)
    action = models.CharField(max_length=30)
    remarque = models.TextField(blank=True)
    empreinte = models.CharField(max_length=64, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-cree_le', '-pk']
