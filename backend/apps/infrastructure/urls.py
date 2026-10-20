from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.conf import settings
from . import views
from .views import (
    TypeOuvrageViewSet, OuvrageViewSet, MaintenanceTaskViewSet,
    EquipementConstitutifViewSet, IncidentViewSet,
    PointControleInfraViewSet, InspectionInfraViewSet, ResultatControleInfraViewSet,
    inspection_detail, inspection_summary, consolidated_equipements
)
from apps.core import views_photos


router = DefaultRouter()
router.register(r'types-ouvrages', TypeOuvrageViewSet)
router.register(r'ouvrages', OuvrageViewSet)
router.register(r'maintenance-tasks', MaintenanceTaskViewSet)
router.register(r'equipements', EquipementConstitutifViewSet)
router.register(r'incidents', IncidentViewSet)
router.register(r'points-controle-infra', PointControleInfraViewSet)
router.register(r'inspections-infra', InspectionInfraViewSet)
router.register(r'resultats-controle-infra', ResultatControleInfraViewSet)

app_name = 'infrastructure'

urlpatterns = [
    path('api/infrastructure/', include(router.urls)),
    # Vues templates pour les inspections
    path('inspections/<uuid:inspection_id>/', inspection_detail, name='inspection_detail'),
    path('inspections/<uuid:inspection_id>/summary/', inspection_summary, name='inspection_summary'),

    # Page consolidée des équipements
    path('consolidated-equipements/', views.consolidated_equipements, name='consolidated_equipements'),

    # API pour mise à jour équipement
    path('api/equipement/<uuid:equipement_id>/update/', views.update_equipement_api, name='update_equipement_api'),

    # Upload photos Équipements
    path('api/equipement/<uuid:equipement_id>/upload-photos/', views_photos.upload_equipement_photos, name='upload_equipement_photos'),
]

