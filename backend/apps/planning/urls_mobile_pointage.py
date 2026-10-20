from django.urls import path

from . import mobile_api_pointage as api

app_name = 'pointage_mobile_v1'

urlpatterns = [
    path('aujourdhui', api.aujourdhui, name='aujourdhui'),
    path('pointer', api.pointer, name='pointer'),
    path('declarer', api.declarer, name='declarer'),
    path('equipe', api.equipe, name='equipe'),
]
