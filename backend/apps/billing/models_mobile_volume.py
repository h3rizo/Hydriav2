from django.conf import settings
from django.db import models


class MobileVolumeOperation(models.Model):
    """Durable receipt: replaying a mobile operation never repeats its effects."""

    id = models.UUIDField(primary_key=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    payload_hash = models.CharField(max_length=64)
    response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class MobileVolumeInvoiceSnapshot(models.Model):
    releve = models.OneToOneField('billing.Releve', primary_key=True, on_delete=models.CASCADE)
    data = models.JSONField()
