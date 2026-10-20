from django.urls import path

from . import mobile_api_v1

app_name = 'compta_mobile_v1'

urlpatterns = [
    path('bootstrap', mobile_api_v1.bootstrap, name='bootstrap'),
    path('changes', mobile_api_v1.changes, name='changes'),
    path('soldes', mobile_api_v1.soldes, name='soldes'),
    path('verification-scans', mobile_api_v1.verification_scans_recap, name='verification_scans_recap'),
    path('verification-scans/detail', mobile_api_v1.verification_scans_detail, name='verification_scans_detail'),
    path('mutations', mobile_api_v1.mutations, name='mutations'),
]
