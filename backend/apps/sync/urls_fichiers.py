"""Montage : ``path('api/fichiers/', include('apps.sync.urls_fichiers'))``."""
from django.urls import path

from . import views

app_name = 'sync_fichiers'

urlpatterns = [
    path('', views.FichiersView.as_view(), name='liste'),
    path('<uuid:pk>/', views.FichierView.as_view(), name='detail'),
    path('<uuid:pk>/telechargement', views.TelechargementView.as_view(), name='telechargement'),
    path('<uuid:pk>/versions/', views.VersionsView.as_view(), name='versions'),
    path('<uuid:pk>/versions/<int:numero>/telechargement', views.VersionTelechargementView.as_view(),
         name='version_telechargement'),
    path('<uuid:pk>/versions/<int:numero>/restaurer', views.RestaurerVersionView.as_view(), name='restaurer'),
]
