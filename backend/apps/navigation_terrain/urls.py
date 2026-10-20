from django.urls import path

from . import views

app_name = 'navigation_terrain'

urlpatterns = [
    path('api/mobile/config/', views.api_config, name='mobile_config'),
    path('api/mobile/entities/', views.api_entities, name='mobile_entities'),
    path('api/mobile/itineraire/', views.api_itineraire, name='mobile_itineraire'),
    path('api/mobile/positions/upsert/', views.api_position_upsert, name='mobile_position_upsert'),
    path('api/mobile/reperes/upsert/', views.api_repere_upsert, name='mobile_repere_upsert'),
    path('api/mobile/reperes/<uuid:repere_id>/archive/', views.api_repere_archive, name='mobile_repere_archive'),
    path('api/mobile/reperes/<uuid:repere_id>/photos/', views.api_repere_photo, name='mobile_repere_photo'),
]
