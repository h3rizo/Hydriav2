"""Journal des SMS de rappel de paiement (un enregistrement par SMS envoyé)."""
import uuid

from django.db import models


class SmsLog(models.Model):
    """
    Un SMS de rappel adressé à un abonné (point d'eau) pour une échéance donnée.

    Un rappel peut tenir en 1 ou 2 SMS (`partie` = 1 ou 2) : la contrainte
    d'unicité garantit qu'une même partie d'un même rappel n'est jamais
    envoyée deux fois, même si la commande est relancée.
    """

    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('envoye', 'Envoyé'),
        ('echec', 'Échec'),
        ('simule', 'Simulé (mode test)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    point_eau = models.ForeignKey(
        'billing.PointEau',
        on_delete=models.CASCADE,
        related_name='sms_logs',
        verbose_name="Point d'eau",
    )
    date_echeance = models.DateField(
        verbose_name="Date limite de paiement",
        help_text="Date limite de la (des) facture(s) courante(s) visée(s) par ce rappel",
    )
    type_rappel = models.CharField(max_length=10, verbose_name="Type de rappel", help_text='Ex : "J-3", "J-1"')
    partie = models.PositiveSmallIntegerField(default=1, verbose_name="Partie du rappel (1 ou 2)")
    telephone = models.CharField(max_length=20, verbose_name="Téléphone (format international)")
    message = models.CharField(max_length=320, verbose_name="Message envoyé")
    montant_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name="Montant total réclamé",
        help_text="Facture(s) courante(s) + factures antérieures non pointées",
    )
    factures = models.JSONField(
        default=list, blank=True,
        verbose_name="Factures concernées",
        help_text='Liste de {"type": "releve|forfait", "id": ..., "reference": ..., "montant": ...}',
    )
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente')
    gateway_id = models.CharField(max_length=64, blank=True, default='', verbose_name="Identifiant passerelle")
    erreur = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")

    class Meta:
        db_table = 'sms_log'
        verbose_name = 'SMS de rappel'
        verbose_name_plural = 'SMS de rappel'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['point_eau', 'date_echeance', 'type_rappel', 'partie'],
                name='uniq_sms_rappel_par_echeance',
            ),
        ]
        indexes = [
            models.Index(fields=['statut']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"SMS {self.type_rappel} p{self.partie} - {self.telephone} - {self.get_statut_display()}"
