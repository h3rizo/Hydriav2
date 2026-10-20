from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PlanningHierarchicalViewSet, PlanningEmployeeHierarchicalViewSet,
    IndemniteHierarchicalViewSet, PlanningDetailHierarchicalViewSet
)

router = DefaultRouter()
router.register(r'plannings', PlanningHierarchicalViewSet, basename='planning-hierarchical')
router.register(r'planning-employees', PlanningEmployeeHierarchicalViewSet, basename='planning-employee-hierarchical')
router.register(r'indemnites', IndemniteHierarchicalViewSet, basename='indemnite-hierarchical')
router.register(r'planning-details', PlanningDetailHierarchicalViewSet, basename='planning-detail-hierarchical')

urlpatterns = [
    path('api/planning-hierarchical/', include(router.urls)),
]