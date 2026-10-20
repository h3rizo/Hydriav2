from django.urls import path
from . import views

app_name = 'authentication'

urlpatterns = [
    path('login/', views.api_login, name='api_login'),
    path('logout/', views.api_logout, name='api_logout'),
    path('status/', views.api_auth_status, name='api_auth_status'),
    path('refresh/', views.api_refresh_session, name='api_refresh_session'),
    path('csrf/', views.api_csrf_token, name='api_csrf_token'),
    path('profile/me/', views.ProfileMeView.as_view(), name='profile_me'),
    path('profiles/search/', views.ProfileSearchView.as_view(), name='profile_search'),
    path('household-members/', views.HouseholdMemberListCreateView.as_view(), name='household_member_list'),
    path('household-members/<int:pk>/', views.HouseholdMemberDetailView.as_view(), name='household_member_detail'),
    path('ingredients/', views.IngredientListCreateView.as_view(), name='ingredient_list'),
    path('meals/', views.MealListCreateView.as_view(), name='meal_list'),
    path('meals/<int:pk>/', views.MealDetailView.as_view(), name='meal_detail'),
]
