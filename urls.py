 from django.urls import path
 from . import views
 
 app_name = 'organizations'
 
 urlpatterns = [
     # Page principale
     path('', views.organization_list, name='list'),
 
     # Endpoints HTMX
     path('<int:pk>/', views.organization_detail, name='detail'),
     path('<int:pk>/edit/', views.organization_edit, name='edit'),
     path('<int:pk>/update/', views.organization_update, name='update'),
 ]