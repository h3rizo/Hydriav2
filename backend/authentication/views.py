from django.contrib.auth import login, logout
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import HouseholdMember, Ingredient, Meal, Profile
from .serializers import (
    HouseholdMemberSerializer,
    IngredientSerializer,
    LoginSerializer,
    MealDetailSerializer,
    MealSerializer,
    ProfileLookupSerializer,
    ProfileSerializer,
    UserSerializer,
)


@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    serializer = LoginSerializer(data=request.data)

    if serializer.is_valid():
        user = serializer.validated_data['user']
        login(request, user)

        response_data = {
            'success': True,
            'message': 'Connexion reussie',
            'user': UserSerializer(user).data,
            'session_key': request.session.session_key,
            'csrf_token': get_token(request),
        }
        return Response(response_data, status=status.HTTP_200_OK)

    return Response({
        'success': False,
        'message': 'Erreur de connexion',
        'errors': serializer.errors,
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_logout(request):
    logout(request)
    return Response({'success': True, 'message': 'Deconnexion reussie'}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_auth_status(request):
    if request.user.is_authenticated:
        response_data = {
            'is_authenticated': True,
            'user': UserSerializer(request.user).data,
            'session_key': request.session.session_key,
            'csrf_token': get_token(request),
        }
    else:
        response_data = {
            'is_authenticated': False,
            'csrf_token': get_token(request),
        }
    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_refresh_session(request):
    request.session.cycle_key()
    response_data = {
        'success': True,
        'message': 'Session rafraichie',
        'user': UserSerializer(request.user).data,
        'session_key': request.session.session_key,
        'csrf_token': get_token(request),
    }
    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def api_csrf_token(request):
    return Response({'csrf_token': get_token(request)}, status=status.HTTP_200_OK)


class ProfileMeView(RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProfileSerializer

    def get_object(self):
        return self.request.user.profile


class ProfileSearchView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProfileLookupSerializer
    http_method_names = ['get']

    def get_queryset(self):
        query = (self.request.query_params.get('q') or '').strip()
        queryset = Profile.objects.exclude(id=self.request.user.profile.id).select_related('user')
        if not query:
            return queryset.none()

        return queryset.filter(
            Q(user__username__icontains=query) |
            Q(user__email__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query)
        ).order_by('user__first_name', 'user__last_name', 'user__username')[:20]


class HouseholdMemberListCreateView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = HouseholdMemberSerializer

    def get_queryset(self):
        return HouseholdMember.objects.filter(owner=self.request.user.profile)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user.profile)


class HouseholdMemberDetailView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = HouseholdMemberSerializer

    def get_queryset(self):
        return HouseholdMember.objects.filter(owner=self.request.user.profile)


class IngredientListCreateView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = IngredientSerializer
    queryset = Ingredient.objects.all().order_by('name')


class MealListCreateView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Meal.objects
            .filter(
                Q(created_by=self.request.user.profile) |
                Q(participants__profile=self.request.user.profile)
            )
            .distinct()
            .select_related('created_by', 'shopping_done_by', 'cooked_by')
            .prefetch_related('ingredients__ingredient', 'participants__profile__user', 'participants__household_member')
        )

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return MealDetailSerializer
        return MealSerializer


class MealDetailView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Meal.objects
            .filter(
                Q(created_by=self.request.user.profile) |
                Q(participants__profile=self.request.user.profile)
            )
            .distinct()
            .select_related('created_by', 'shopping_done_by', 'cooked_by')
            .prefetch_related('ingredients__ingredient', 'participants__profile__user', 'participants__household_member')
        )

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return MealDetailSerializer
        return MealSerializer
