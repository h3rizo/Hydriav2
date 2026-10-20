from django.contrib import admin
from .models import TarifVolumetriqueTranche


@admin.register(TarifVolumetriqueTranche)
class TarifVolumetriqueTrancheAdmin(admin.ModelAdmin):
    list_display = ('tarifvolumetrique', 'tranchesuperieur', 'tarif')
    list_filter = ('tarifvolumetrique__ouvrage', 'tarifvolumetrique__actif')
    search_fields = ('tarifvolumetrique__ouvrage__nom', 'tarifvolumetrique__ouvrage__infra_name')
    ordering = ('tarifvolumetrique', 'tranchesuperieur')

    fieldsets = (
        ('Informations tranche', {
            'fields': ('tarifvolumetrique', 'tranchesuperieur', 'tarif')
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('tarifvolumetrique__ouvrage')