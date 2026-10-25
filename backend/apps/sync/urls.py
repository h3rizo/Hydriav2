"""Montage : ``path('api/sync/', include('apps.sync.urls'))``."""
from django.urls import path

from . import views

app_name = 'sync'

urlpatterns = [
    path('auth/login', views.ConnexionView.as_view(), name='login'),
    path('auth/refresh', views.RenouvellementView.as_view(), name='refresh'),
    path('changes', views.ChangementsView.as_view(), name='changes'),
    path('arborescence', views.ArborescenceView.as_view(), name='arborescence'),
    path('upload', views.DepotView.as_view(), name='upload'),
]
