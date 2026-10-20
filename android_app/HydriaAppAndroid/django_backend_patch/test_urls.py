from django.urls import include, path

urlpatterns = [path('navigation-terrain/', include('apps.navigation_terrain.urls'))]
