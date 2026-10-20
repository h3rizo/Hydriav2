 from django.db import models
 
 class Organization(models.Model):
     name = models.CharField(max_length=255, unique=True, verbose_name="Nom de l'organisation")
     address = models.CharField(max_length=255, blank=True, verbose_name="Adresse")
     is_active = models.BooleanField(default=True, verbose_name="Active")
 
     def __str__(self):
         return self.name
 
     class Meta:
         verbose_name = "Organisation"
         verbose_name_plural = "Organisations"
         ordering = ['name']