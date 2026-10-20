from django.urls import path
from . import views

app_name = 'feed'

urlpatterns = [
    path('', views.feed_home, name='home'),
    path('post/create/', views.post_create, name='post_create'),
    path('post/<int:post_id>/comment/', views.comment_create, name='comment_create'),
    path('post/<int:post_id>/like/', views.like_toggle, name='like_toggle'),
    path('post/<int:post_id>/status/', views.post_change_status, name='post_change_status'),
    path('post/<int:post_id>/delete/', views.post_delete, name='post_delete'),
    path('post/<int:post_id>/toggle-priority/', views.post_toggle_priority, name='post_toggle_priority'),
    path('sync/', views.sync_feed, name='sync'),
    path('sync-priority/', views.sync_priority, name='sync_priority'),
    path('generer-paiements-forfaitaires/', views.generer_posts_paiements_forfaitaires, name='generer_paiements_forfaitaires'),
    path('generer-coupures-eau/', views.generer_posts_coupures_eau, name='generer_coupures_eau'),
    path('generer-remises-eau/', views.generer_posts_remises_eau, name='generer_remises_eau'),
]
