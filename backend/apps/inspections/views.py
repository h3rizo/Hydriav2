from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db.models import Q, Prefetch
from apps.infrastructure.models import EquipementConstitutif
from apps.organization.models import Ouvrage
from apps.organization.scoping import get_user_accessible_gestionnaire_ids
from apps.employees.models import Employe
from apps.employees.permissions import employe_required, filter_queryset_by_permissions
from apps.filemanager.models import FileUpload
from apps.filemanager.services import storage_service
from apps.planning.models import Planning


def get_photo_url(photos):
    if not photos or not isinstance(photos, list):
        return None
    first = photos[0]
    if isinstance(first, str):
        if first.startswith(('data:', 'http://', 'https://', '/media/', '/static/')):
            return first
        return None
    if not isinstance(first, dict):
        return None
    url = first.get('url')
    if url:
        return url
    data = first.get('data')
    if not data:
        return None
    if isinstance(data, bytes):
        data = data.decode('utf-8', errors='ignore')
    if not isinstance(data, str):
        return None
    if data.startswith('data:'):
        return data
    content_type = first.get('content_type') or 'image/jpeg'
    return f"data:{content_type};base64,{data}"

from .models import (
    PointDeControle,
    PointDeControleComposant,
    PointDeControleSpecifique,
    PointDeControleSpecifiquePointEau,
    ComposantTypePointEau,
    Checklist,
    Visite,
    ResultatControle,
    ResultatControlePointEau,
    Inspection,
    InspectionPhoto,
    ResultatInspectionComposant
)
from apps.billing.models import PointEau
from .serializers import (
    PointDeControleSerializer,
    ChecklistSerializer,
    VisiteCreateSerializer,
    VisiteSerializer,
    VisiteDetailSerializer,
    ResultatControleCreateSerializer,
    ResultatControleSerializer,
    InspectionPhotoSerializer,
    PlanningFromInspectionSerializer,
    HistoriqueControleSerializer,
    OuvrageBasicSerializer,
    InfrastructureBasicSerializer,
    EmployeeBasicSerializer
)


TYPE_RESULTAT_TO_CONTROLE = {
    'BOOL': 'booleen',
    'NUM': 'numerique',
    'TEXT': 'texte'
}


def normalize_type_controle(type_resultat):
    if not type_resultat:
        return ''
    return TYPE_RESULTAT_TO_CONTROLE.get(type_resultat, type_resultat.lower())


class PointDeControleViewSet(viewsets.ModelViewSet):
    """ViewSet pour la gestion des points de controle."""
    queryset = PointDeControle.objects.all()
    serializer_class = PointDeControleSerializer
    permission_classes = [permissions.AllowAny]  # Temporaire pour tests

    @action(detail=True, methods=['get'])
    def activites_correctives(self, request, pk=None):
        """Récupère les activités correctives possibles pour ce point de controle."""
        point_controle = self.get_object()
        activites = point_controle.get_activites_correctives_possibles()

        # Sérialiser les activités avec leurs types
        data = []
        for activite in activites:
            data.append({
                'id': str(activite.id),
                'nom': activite.nom,
                'description': activite.description,
                'type_activite': {
                    'id': str(activite.type_activite.id),
                    'nomtype': activite.type_activite.nomtype
                } if activite.type_activite else None
            })

        return Response(data)


class ChecklistViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet pour la consultation des checklists."""
    queryset = Checklist.objects.filter(is_active=True).select_related(
        'equipement_constitutif', 
        'equipement_constitutif__infrastructure'
    ).prefetch_related('points_de_controle')
    serializer_class = ChecklistSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def by_infrastructure_and_type(self, request):
        """Récupère les checklists pour une infrastructure et un type de visite."""
        infrastructure_id = request.query_params.get('infrastructure_id')
        type_visite = request.query_params.get('type_visite')
        
        if not infrastructure_id or not type_visite:
            return Response(
                {'error': 'infrastructure_id et type_visite sont requis'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        checklists = self.get_queryset().filter(
            equipement_constitutif__ouvrage_id=infrastructure_id,
            type_visite=type_visite
        )
        
        serializer = self.get_serializer(checklists, many=True)
        return Response(serializer.data)


class VisiteViewSet(viewsets.ModelViewSet):
    """ViewSet pour la gestion des visites d'inspection."""
    queryset = Visite.objects.select_related(
        'ouvrage', 'agent'
    ).prefetch_related('resultats')
    permission_classes = [permissions.AllowAny]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return VisiteCreateSerializer
        elif self.action == 'retrieve':
            return VisiteDetailSerializer
        return VisiteSerializer
    
    def get_queryset(self):
        """Filtrer les visites selon les paramètres."""
        queryset = super().get_queryset()
        
        # Filtrer par ouvrage (infrastructure)
        infrastructure_id = self.request.query_params.get('infrastructure_id')
        if infrastructure_id:
            queryset = queryset.filter(ouvrage_id=infrastructure_id)
        
        # Filtrer par agent
        agent_id = self.request.query_params.get('agent_id')
        if agent_id:
            queryset = queryset.filter(agent_id=agent_id)
        
        # Filtrer par statut
        statut = self.request.query_params.get('statut')
        if statut:
            queryset = queryset.filter(statut=statut)
        
        # Filtrer par date
        date_debut = self.request.query_params.get('date_debut')
        date_fin = self.request.query_params.get('date_fin')
        if date_debut:
            queryset = queryset.filter(date_visite__gte=date_debut)
        if date_fin:
            queryset = queryset.filter(date_visite__lte=date_fin)
        
        return queryset.order_by('-date_visite')
    
    def perform_create(self, serializer):
        """Créer une visite avec l'agent connecté par défaut."""
        # Si pas d'agent spécifié, utiliser l'utilisateur connecté
        if not serializer.validated_data.get('agent'):
            try:
                employee = Employe.objects.get(user=self.request.user)
                serializer.save(agent=employee)
            except Employe.DoesNotExist:
                # Fallback - utiliser le premier employé actif
                employee = Employe.objects.filter(date_debauchage__isnull=True).first()
                if employee:
                    serializer.save(agent=employee)
                else:
                    serializer.save()
        else:
            serializer.save()
    
    @action(detail=True, methods=['post'])
    def terminer(self, request, pk=None):
        """Terminer une visite."""
        visite = self.get_object()
        if visite.statut == 'en_cours':
            visite.statut = 'terminee'
            visite.save()
            return Response({'status': 'Visite terminée'})
        else:
            return Response(
                {'error': 'La visite n\'est pas en cours'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['get'])
    def points_controle(self, request, pk=None):
        """Récupère tous les points de controle pour cette visite."""
        visite = self.get_object()
        
        # Récupérer tous les équipements de l'ouvrage
        equipements = EquipementConstitutif.objects.filter(
            ouvrage=visite.ouvrage
        ).prefetch_related(
            Prefetch(
                'checklists',
                queryset=Checklist.objects.filter(
                    type_visite=visite.type_visite,
                    is_active=True
                ).prefetch_related('points_de_controle')
            )
        )
        
        points_controle_data = []
        for equipement in equipements:
            for checklist in equipement.checklists.all():
                for relation in checklist.checklistpointcontrole_set.all().order_by('ordre'):
                    points_controle_data.append({
                        'equipement_id': equipement.id,
                        'equipement_nom': equipement.nom,
                        'equipement_type': equipement.type_equipement,
                        'photo_reference_url': equipement.photo_reference.get_download_url() if equipement.photo_reference else None,
                        'point_controle': PointDeControleSerializer(relation.point_de_controle).data,
                        'ordre': relation.ordre,
                        'est_obligatoire': relation.est_obligatoire
                    })
        
        return Response(points_controle_data)


class ResultatControleViewSet(viewsets.ModelViewSet):
    """ViewSet pour la gestion des résultats de controle."""
    queryset = ResultatControle.objects.select_related(
        'visite', 'equipement', 'point_de_controle'
    ).prefetch_related('inspection_photos__file_upload')
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ResultatControleCreateSerializer
        return ResultatControleSerializer
    
    def get_queryset(self):
        """Filtrer les résultats selon les paramètres."""
        queryset = super().get_queryset()
        
        # Filtrer par visite
        visite_id = self.request.query_params.get('visite_id')
        if visite_id:
            queryset = queryset.filter(visite_id=visite_id)
        
        # Filtrer par équipement
        equipement_id = self.request.query_params.get('equipement_id')
        if equipement_id:
            queryset = queryset.filter(equipement_id=equipement_id)
        
        # Filtrer par conformité
        conforme = self.request.query_params.get('conforme')
        if conforme == 'true':
            queryset = queryset.filter(necessite_action=False)
        elif conforme == 'false':
            queryset = queryset.filter(necessite_action=True)
        
        return queryset.order_by('-heure_controle')
    
    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_photos(self, request, pk=None):
        """Upload des photos pour un résultat de controle."""
        resultat = self.get_object()
        uploaded_photos = []

        try:
            with transaction.atomic():
                for file in request.FILES.values():
                    tags = [
                        resultat.equipement.ouvrage.nom,
                        resultat.equipement.type_equipement,
                        resultat.visite.type_visite,
                        str(resultat.visite.date_visite.year)
                    ]

                    file_upload = storage_service.upload_file(
                        file=file,
                        tags=tags,
                        description=f"Photo de controle - {resultat.point_de_controle.nom}",
                        uploaded_by=request.user
                    )

                    photo = InspectionPhoto.objects.create(
                        visite=resultat.visite,
                        file_upload=file_upload,
                        equipement=resultat.equipement,
                        description=f"Photo de controle - {resultat.point_de_controle.nom}"
                    )
                    resultat.inspection_photos.add(photo)
                    uploaded_photos.append(photo)

            serializer = InspectionPhotoSerializer(uploaded_photos, many=True)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {'error': f'Erreur lors de l\'upload: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def creer_tache_maintenance(self, request, pk=None):
        """Créer une tÃ¢che de maintenance Ã  partir d'un résultat de controle."""
        resultat = self.get_object()
        
        if not resultat.necessite_action:
            return Response(
                {'error': 'Ce résultat ne nécessite pas d\'action corrective'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Données de la tÃ¢che
        tache_data = {
            'date': request.data.get('date', timezone.now()),
            'employeid': request.data.get('employeid'),
            'activiteid': request.data.get('activiteid', 1),  # ID activité maintenance
            'ouvrageid': resultat.equipement.ouvrage.id,
            'remarque': request.data.get('remarque', 
                f"Maintenance requise suite Ã  inspection: {resultat.point_de_controle.nom} - {resultat.commentaire}"),
            'origine_resultat': resultat.id,
            'createdat': timezone.now(),
            'updatedat': timezone.now()
        }
        
        serializer = PlanningFromInspectionSerializer(data=tache_data)
        if serializer.is_valid():
            planning = serializer.save()
            return Response({
                'message': 'TÃ¢che de maintenance créée',
                'planning_id': planning.id
            }, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def historique(self, request):
        """Historique des controles pour un équipement."""
        equipement_id = request.query_params.get('equipement_id')
        point_controle_id = request.query_params.get('point_controle_id')
        
        if not equipement_id:
            return Response(
                {'error': 'equipement_id est requis'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset().filter(equipement_id=equipement_id)
        
        if point_controle_id:
            queryset = queryset.filter(point_de_controle_id=point_controle_id)
        
        queryset = queryset.order_by('-heure_controle')[:20]  # 20 derniers résultats
        
        serializer = HistoriqueControleSerializer(queryset, many=True)
        return Response(serializer.data)


# Vues pour les données de référence
class OuvrageListView(viewsets.ReadOnlyModelViewSet):
    """Liste des ouvrages pour les sélecteurs."""
    queryset = Ouvrage.objects.all()
    serializer_class = OuvrageBasicSerializer
    permission_classes = [permissions.AllowAny]

    def _exclude_test_ouvrages(self, queryset):
        """Retirer les ouvrages de test/demo des sélecteurs utilisateurs."""
        return queryset.exclude(
            Q(nom_ouvrage__icontains='test') |
            Q(nom_ouvrage__icontains='demo') |
            Q(nom_ouvrage__icontains='démo') |
            Q(nom_ouvrage__icontains='essai')
        )

    def _get_user_gestionnaire_ids(self):
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return []
        return get_user_accessible_gestionnaire_ids(user)

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = self._exclude_test_ouvrages(queryset)
        gestionnaire_ids = self._get_user_gestionnaire_ids()
        if gestionnaire_ids is not None:
            if gestionnaire_ids:
                queryset = queryset.filter(
                    modalites_gestion__gestionnaire_id__in=gestionnaire_ids,
                    modalites_gestion__date_fin__isnull=True,
                    modalites_gestion__statut='actif'
                ).distinct()
            else:
                queryset = queryset.none()
        else:
            queryset = queryset.filter(
                modalites_gestion__date_fin__isnull=True,
                modalites_gestion__statut='actif'
            ).distinct()

        point_prefetch = Prefetch(
            'pointeau_set',
            queryset=PointEau.objects.filter(
                parcelle__isnull=False,
                parcelle__village__fokontany__commune__isnull=False
            ).select_related('parcelle__village__fokontany__commune'),
            to_attr='points_eau_prefetched'
        )
        return queryset.select_related('type_ouvrage').prefetch_related(point_prefetch)

    def filter_queryset(self, queryset):
        search = self.request.query_params.get('q', '').strip()
        if not search:
            return queryset

        queryset = queryset.filter(
            Q(nom_ouvrage__icontains=search) |
            Q(type_ouvrage__nom_type_ouvrage__icontains=search) |
            Q(modalites_gestion__gestionnaire__nom_organisation__icontains=search)
        ).distinct()
        return queryset
    
    @action(detail=True, methods=['get'])
    def equipements(self, request, pk=None):
        """Récupère les équipements d'un ouvrage."""
        ouvrage = self.get_object()
        equipements = EquipementConstitutif.objects.filter(
            ouvrage=ouvrage
        ).select_related('photo_reference')
        
        data = []
        for equipement in equipements:
            data.append({
                'id': equipement.id,
                'nom': equipement.nom,
                'type_equipement': equipement.type_equipement,
                'code_equipement': equipement.code_equipement,
                'statut': equipement.statut,
                'photo_reference_url': equipement.photo_reference.get_download_url() if equipement.photo_reference else None
            })
        
        return Response(data)

# Alias pour compatibilité
InfrastructureListView = OuvrageListView


class EquipementListView(viewsets.ReadOnlyModelViewSet):
    """Liste des équipements pour les sélecteurs."""
    queryset = EquipementConstitutif.objects.select_related('ouvrage')
    permission_classes = [permissions.AllowAny]

    def list(self, request, *args, **kwargs):
        """Retourne la liste des équipements avec le nom de l'ouvrage."""
        equipements = self.get_queryset()
        ouvrage_id = request.query_params.get('ouvrage_id')
        if ouvrage_id:
            equipements = equipements.filter(ouvrage_id=ouvrage_id)

        data = []
        for equipement in equipements:
            data.append({
                'id': equipement.id,
                'nom': equipement.nom,
                'type_equipement': equipement.type_equipement,
                'code_equipement': equipement.code_equipement,
                'statut': equipement.statut,
                'ouvrage_id': equipement.ouvrage.id if equipement.ouvrage else None,
                'ouvrage_nom': equipement.ouvrage.nom_ouvrage if equipement.ouvrage else ''
            })

        return Response(data)


class EmployeeListView(viewsets.ReadOnlyModelViewSet):
    """Liste des employés pour les sélecteurs."""
    queryset = Employe.objects.filter(date_debauchage__isnull=True)
    serializer_class = EmployeeBasicSerializer
    permission_classes = [permissions.AllowAny]


# Vues HTML pour les interfaces utilisateur
def visite_detail_view(request, visite_id):
    """Vue détaillée d'une visite."""
    from django.shortcuts import get_object_or_404

    visite = get_object_or_404(Visite.objects.select_related('ouvrage', 'agent'), id=visite_id)
    resultats = ResultatControle.objects.filter(visite=visite).select_related('point_de_controle', 'equipement')

    # Calculer les stats
    total_controles = resultats.count()
    anomalies = resultats.filter(necessite_action=True).count()
    score = int((total_controles - anomalies) / total_controles * 100) if total_controles > 0 else None

    return render(request, 'inspections/visite_detail.html', {
        'visite': visite,
        'resultats': resultats,
        'total_controles': total_controles,
        'anomalies': anomalies,
        'score': score,
    })

def dashboard_view(request):
    """Vue HTML du tableau de bord des inspections."""
    from apps.geography.models import Commune
    from django.db.models import Count, Q
    from django.utils import timezone
    from datetime import timedelta

    # Filtres
    commune_filter = request.GET.get('commune', '')
    conforme_filter = request.GET.get('conforme', '')
    ouvrage_filter = request.GET.get('ouvrage', '')

    # Statistiques
    now = timezone.now()
    debut_mois = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Compter les anomalies via ResultatControle
    anomalies_count = ResultatControle.objects.filter(
        necessite_action=True,
        visite__statut__in=['en_cours', 'terminee']
    ).values('visite').distinct().count()

    stats = {
        'visites_ce_mois': Visite.objects.filter(date_visite__gte=debut_mois).count(),
        'en_cours': Visite.objects.filter(statut='en_cours').count(),
        'anomalies': anomalies_count,
        'equipements': EquipementConstitutif.objects.count()
    }

    # Récupérer les visites récentes (7 derniers jours)
    date_limite = timezone.now() - timedelta(days=7)
    inspections_recentes = Visite.objects.filter(
        date_visite__gte=date_limite
    ).select_related('ouvrage', 'agent').order_by('-date_visite')[:10]

    # Récupérer les anomalies récentes (visites avec problèmes)
    visites_avec_anomalies = ResultatControle.objects.filter(
        visite__date_visite__gte=date_limite,
        necessite_action=True
    ).values_list('visite_id', flat=True).distinct()

    anomalies_recentes = Visite.objects.filter(
        id__in=visites_avec_anomalies
    ).select_related('ouvrage', 'agent').order_by('-date_visite')[:10]

    # Tableau consolidé par Ouvrage
    visites_par_ouvrage = Visite.objects.filter(
        ouvrage__isnull=False
    ).select_related('ouvrage', 'agent')

    if commune_filter:
        visites_par_ouvrage = visites_par_ouvrage.filter(
            ouvrage__village__fokontany__commune_id=commune_filter
        )

    if ouvrage_filter:
        visites_par_ouvrage = visites_par_ouvrage.filter(
            ouvrage__nom_ouvrage__icontains=ouvrage_filter
        )

    # Filtrer par conformité (via ResultatControle)
    if conforme_filter == 'true':
        # Visites sans anomalies
        visites_sans_anomalies = Visite.objects.exclude(
            id__in=ResultatControle.objects.filter(necessite_action=True).values_list('visite_id', flat=True)
        )
        visites_par_ouvrage = visites_par_ouvrage.filter(id__in=visites_sans_anomalies)
    elif conforme_filter == 'false':
        # Visites avec anomalies
        visites_avec_problemes = ResultatControle.objects.filter(necessite_action=True).values_list('visite_id', flat=True)
        visites_par_ouvrage = visites_par_ouvrage.filter(id__in=visites_avec_problemes)

    # Regrouper par ouvrage
    ouvrages_data = {}
    for visite in visites_par_ouvrage:
        if visite.ouvrage:
            ouvrage_nom = visite.ouvrage.nom_ouvrage
            if ouvrage_nom not in ouvrages_data:
                ouvrages_data[ouvrage_nom] = []

            # Calculer conformité de cette visite
            anomalies = ResultatControle.objects.filter(visite=visite, necessite_action=True).count()
            total_controles = ResultatControle.objects.filter(visite=visite).count()
            conforme = anomalies == 0 if total_controles > 0 else None
            score = int((total_controles - anomalies) / total_controles * 100) if total_controles > 0 else None

            ouvrages_data[ouvrage_nom].append({
                'date': visite.date_visite,
                'statut': visite.statut,
                'conforme': conforme,
                'score': score,
                'agent': visite.agent.nom_employe,
                'type_visite': visite.get_type_visite_display()
            })

    return render(request, 'inspections/dashboard.html', {
        'stats': stats,
        'visites_recentes': inspections_recentes,
        'visites_anomalies': anomalies_recentes,
        'ouvrages_data': ouvrages_data,
        'ouvrages': Ouvrage.objects.all().order_by('nom_ouvrage'),
        'communes': Commune.objects.all().order_by('nom_commune'),
        'commune_filter': commune_filter,
        'conforme_filter': conforme_filter,
        'ouvrage_filter': ouvrage_filter,
    })

# Vue API pour les données du tableau de bord
@api_view(['GET'])
def dashboard_inspections(request):
    """Données pour le tableau de bord des inspections."""
    # Visites récentes
    visites_recentes = Visite.objects.select_related(
        'ouvrage', 'agent'
    ).order_by('-date_visite')[:5]
    
    # Anomalies nécessitant une action
    anomalies = ResultatControle.objects.filter(
        necessite_action=True
    ).select_related(
        'visite', 'equipement', 'point_de_controle'
    ).order_by('-heure_controle')[:10]
    
    # Statistiques
    stats = {
        'total_visites_mois': Visite.objects.filter(
            date_visite__gte=timezone.now().replace(day=1)
        ).count(),
        'visites_en_cours': Visite.objects.filter(statut='en_cours').count(),
        'anomalies_non_traitees': ResultatControle.objects.filter(
            necessite_action=True
        ).count(),
        'equipements_total': EquipementConstitutif.objects.count()
    }
    
    return Response({
        'visites_recentes': VisiteSerializer(visites_recentes, many=True).data,
        'anomalies': ResultatControleSerializer(anomalies, many=True).data,
        'statistiques': stats
    })


def nouvelle_inspection_view(request):
    """Vue pour créer une nouvelle inspection."""
    # Utiliser le template existant tel quel pour l'instant
    # Le template est complexe et contient du JavaScript pour une interface interactive
    context = {
        'title': 'Nouvelle Inspection'
    }
    return render(request, 'inspections/nouvelle_inspection.html', context)


def inspection_amelioree_view(request):
    """Vue pour l'inspection améliorée avec géolocalisation et workflow optimisé."""
    context = {
        'title': 'Inspection Améliorée'
    }
    return render(request, 'inspections/inspection_formulaire_ameliore.html', context)


@api_view(['GET'])
@permission_classes([AllowAny])
def inspection_form_api(request, planning_id):
    """API pour récupérer les données du formulaire d'inspection pour un planning donné."""
    try:
        from apps.planning.models import Planning

        # Récupérer le planning
        planning = Planning.objects.select_related('employe', 'type_activite', 'ouvrage').get(id=planning_id)

        if not planning.ouvrage:
            return Response({
                'error': 'Aucun ouvrage associé Ã  ce planning'
            }, status=400)

        # Récupérer les équipements de l'ouvrage avec leurs checklists
        equipements = EquipementConstitutif.objects.filter(
            ouvrage=planning.ouvrage
        ).prefetch_related(
            Prefetch(
                'checklists',
                queryset=Checklist.objects.filter(
                    type_visite='COMPLET',  # Controle complet pour les inspections de planning
                    is_active=True
                ).prefetch_related('points_de_controle')
            )
        )

        # Préparer les données des équipements
        equipements_data = []
        for equipement in equipements:
            points_controle = []

            # Récupérer les points de controle des checklists
            for checklist in equipement.checklists.all():
                for relation in checklist.checklistpointcontrole_set.all().order_by('ordre'):
                    points_controle.append({
                        'id': str(relation.point_de_controle.id),
                        'nom': relation.point_de_controle.nom,
                        'description': relation.point_de_controle.description or '',
                        'type_resultat': relation.point_de_controle.type_resultat,
                        'ordre': relation.ordre,
                        'est_obligatoire': relation.est_obligatoire,
                        'unite': relation.point_de_controle.unite or '',
                        'valeur_min': float(relation.point_de_controle.valeur_min) if relation.point_de_controle.valeur_min else None,
                        'valeur_max': float(relation.point_de_controle.valeur_max) if relation.point_de_controle.valeur_max else None
                    })

            equipements_data.append({
                'id': str(equipement.id),
                'nom': equipement.nom,
                'type_equipement': equipement.type_equipement.nom_type if equipement.type_equipement else 'Non défini',
                'code_equipement': equipement.code_equipement,
                'statut': equipement.statut,
                'description': equipement.description or '',
                'photo_reference_url': equipement.photo_reference.get_download_url() if equipement.photo_reference else None,
                'latitude': float(equipement.latitude) if equipement.latitude else None,
                'longitude': float(equipement.longitude) if equipement.longitude else None,
                'points_controle': points_controle
            })

        # Préparer la réponse
        response_data = {
            'planning': {
                'id': str(planning.id),
                'date': planning.date.isoformat() if planning.date else None,
                'employe_nom': planning.employe.nom_complet if planning.employe else 'Non assigné',
                'activite_nom': planning.type_activite.nomtype if planning.type_activite else 'Non défini',
                'ouvrage_nom': planning.ouvrage.nom,
                'remarques': planning.remarque or '',
                'statut': planning.statut or 'en_cours'
            },
            'ouvrage': {
                'id': str(planning.ouvrage.id),
                'nom': planning.ouvrage.nom,
                'description': planning.ouvrage.remarque or '',
                'type_ouvrage': planning.ouvrage.typeouvrage.nomtype if planning.ouvrage.typeouvrage else '',
                'annee_realisation': planning.ouvrage.anneerealisation or ''
            },
            'equipements': equipements_data,
            'total_equipements': len(equipements_data),
            'total_points_controle': sum(len(eq['points_controle']) for eq in equipements_data)
        }

        return Response(response_data)

    except Planning.DoesNotExist:
        return Response({
            'error': 'Planning non trouvé'
        }, status=404)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération des données: {str(e)}'
        }, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def ouvrage_historique_api(request, ouvrage_id):
    """API pour récupérer l'historique des controles non conformes d'un ouvrage."""
    try:
        from apps.planning.models import Planning
        from collections import defaultdict

        # Vérifier que l'ouvrage existe
        ouvrage = Ouvrage.objects.get(id=ouvrage_id)

        # Récupérer tous les résultats de controle non conformes pour cet ouvrage
        # (les résultats oÃ¹ necessite_action=True indiquent un problème)
        resultats_non_conformes = ResultatControle.objects.filter(
            equipement__ouvrage_id=ouvrage_id,
            necessite_action=True  # Seulement les controles qui ont révélé des problèmes
        ).select_related(
            'visite', 'equipement', 'point_de_controle', 'visite__agent'
        ).prefetch_related('inspection_photos__file_upload').order_by('-heure_controle')[:50]

        # Grouper les résultats par visite pour correspondre au format attendu par le frontend
        visites_dict = defaultdict(lambda: {
            'points_controles': [],
            'activites_correctives': [],
            'photos': []
        })

        for resultat in resultats_non_conformes:
            visite_id = resultat.visite.id if resultat.visite else 'sans_visite'

            # Informations de base de la visite
            if 'date' not in visites_dict[visite_id]:
                visites_dict[visite_id].update({
                    'date': resultat.heure_controle.isoformat() if resultat.heure_controle else None,
                    'statut': 'terminee',  # Les controles avec problèmes sont des visites terminées
                    'employe': resultat.visite.agent.nom_complet if resultat.visite and resultat.visite.agent else 'Agent non défini'
                })

            # Ajouter le point de controle non conforme
            visites_dict[visite_id]['points_controles'].append({
                'id': resultat.point_de_controle.id,
                'nom': resultat.point_de_controle.nom,
                'resultat': 'non_conforme',
                'commentaire': resultat.commentaire or 'Problème détecté',
                'valeur_mesuree': resultat.resultat_numeric if resultat.resultat_numeric else None,
                'equipement': resultat.equipement.nom
            })

            # Récupérer les plannings de maintenance créés suite Ã  ce résultat
            plannings_lies = Planning.objects.filter(
                remarque__icontains=f'resultat:{resultat.id}'
            ).select_related('employe', 'type_activite')

            for planning in plannings_lies:
                visites_dict[visite_id]['activites_correctives'].append({
                    'id': planning.id,
                    'activite': planning.type_activite.nomtype if planning.type_activite else 'Activité non définie',
                    'employe': planning.employe.nom_complet if planning.employe else 'Non assigné',
                    'date_prevue': planning.date.isoformat() if planning.date else None,
                    'statut': planning.statut or 'planifie'
                })

            # Récupérer les photos
            for photo in resultat.inspection_photos.all():
                file_obj = photo.file_upload
                if not file_obj:
                    continue
                visites_dict[visite_id]['photos'].append({
                    'id': str(photo.id),
                    'url': file_obj.get_download_url(),
                    'nom': file_obj.original_filename,
                    'date_upload': file_obj.uploaded_at.isoformat() if file_obj.uploaded_at else None
                })

        # Convertir en format attendu par le frontend
        historique_data = []
        for visite_id, visite_data in visites_dict.items():
            # Créer le résumé des notes générales basé sur les problèmes détectés
            problemes = [pc['commentaire'] for pc in visite_data['points_controles']]
            notes_generales = f"Problèmes détectés: {'; '.join(problemes[:3])}"
            if len(problemes) > 3:
                notes_generales += f" (+{len(problemes)-3} autres)"

            historique_data.append({
                'id': visite_id,
                'date': visite_data['date'],
                'statut': visite_data['statut'],
                'employe': visite_data['employe'],
                'resultats': {
                    'points_controles': visite_data['points_controles'],
                    'notes_generales': notes_generales
                },
                'activites_correctives': visite_data['activites_correctives'],
                'photos': visite_data['photos']
            })

        # Trier par date décroissante
        historique_data.sort(key=lambda x: x['date'] or '', reverse=True)

        response_data = {
            'ouvrage': {
                'id': ouvrage.id,
                'nom': ouvrage.nom_ouvrage,
                'description': ouvrage.observation or ''
            },
            'total': len(historique_data),  # Changé de 'total_problemes' Ã  'total'
            'historique': historique_data
        }

        return Response(response_data)

    except Ouvrage.DoesNotExist:
        return Response({
            'error': 'Ouvrage non trouvé'
        }, status=404)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération de l\'historique: {str(e)}'
        }, status=500)


# ============================================================================
# VUES CRUD POUR LA GESTION DES CHECKLISTS ET ACTIVITES CORRECTIVES
# ============================================================================

def checklists_management_view(request):
    """Vue principale pour la gestion des checklists et activités correctives."""
    from apps.organization.models import Ouvrage
    from apps.billing.models import TypePointEau, PointEau

    # Charger tous les ouvrages pour le filtre
    ouvrages = Ouvrage.objects.all().order_by('nom_ouvrage')

    # Charger tous les types de points d'eau pour l'onglet Points PE Communs
    types_points_eau = TypePointEau.objects.filter(actif=True).order_by('nom_type')

    # Charger tous les points d'eau pour l'onglet Points PE Spécifiques
    points_eau = PointEau.objects.select_related('type_point_eau', 'ouvrage').order_by('nomabonne')

    return render(request, 'inspections/checklists_management.html', {
        'title': 'Gestion des Checklists et Activités Correctives',
        'ouvrages': ouvrages,
        'types_points_eau': types_points_eau,
        'points_eau': points_eau,
    })


def points_controle_table_view(request):
    """Vue tableau pour la gestion des points de controle et activités correctives."""
    return render(request, 'inspections/points_controle_table.html', {
        'title': 'Gestion des Points de Controle'
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def checklists_api(request):
    """API pour récupérer les points de controle communs groupés par type d'équipement."""
    try:
        from apps.infrastructure.models import TypeEquipement
        from collections import defaultdict

        # Grouper les points de controle par type d'équipement et type de visite
        types_equipements = TypeEquipement.objects.prefetch_related(
            'composants__points_controle__point_de_controle'
        ).all()

        data = []

        for type_eq in types_equipements:
            # Grouper les points par type de visite
            points_par_visite = defaultdict(list)

            # Récupérer tous les points de controle communs pour ce type
            # Ordonner par composant d'abord, puis par ordre d'affichage (rang)
            points_controle_liens = PointDeControleComposant.objects.filter(
                composant_equipement__type_equipement=type_eq
            ).select_related(
                'point_de_controle',
                'composant_equipement'
            ).order_by('type_visite', 'composant_equipement__nom_composant', 'ordre_affichage')

            for lien in points_controle_liens:
                point = lien.point_de_controle
                type_visite = lien.get_type_visite_display()

                points_par_visite[type_visite].append({
                    'id': str(point.id),
                    'lien_id': str(lien.id),  # ID du lien PointDeControleComposant pour suppression
                    'nom': point.nom,
                    'description': point.description,
                    'type_resultat': point.type_resultat,
                    'composant': lien.composant_equipement.nom_composant,
                    'composant_id': str(lien.composant_equipement.id),
                    'est_obligatoire': lien.est_obligatoire,
                    'ordre': lien.ordre_affichage,
                    'valeur_min': float(point.valeur_min) if point.valeur_min else None,
                    'valeur_max': float(point.valeur_max) if point.valeur_max else None,
                    'unite': point.unite
                })

            # Créer une entrée par type de visite
            for type_visite, points in points_par_visite.items():
                if points:  # Seulement si des points existent
                    data.append({
                        'id': f"{type_eq.id}_{type_visite}",
                        'nom': f"{type_eq.nom_type} - {type_visite}",
                        'type_equipement': {
                            'id': str(type_eq.id),
                            'nom': type_eq.nom_type
                        },
                        'type_visite': type_visite,
                        'points_de_controle': points,
                        'nb_points': len(points),
                        'is_active': True
                    })

        return Response(data)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return Response({
            'error': f'Erreur lors de la récupération des checklists: {str(e)}'
        }, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def points_controle_api(request):
    """API pour récupérer tous les points de controle."""
    try:
        points = PointDeControle.objects.all().order_by('nom')
        data = []

        for point in points:
            data.append({
                'id': str(point.id),
                'nom': point.nom,
                'description': point.description,
                'type_resultat': point.type_resultat,
                'valeur_min': point.valeur_min,
                'valeur_max': point.valeur_max,
                'unite': point.unite
            })

        return Response({
            'success': True,
            'points_controle': data
        })

    except Exception as e:
        return Response({
            'success': False,
            'error': f'Erreur lors de la récupération des points de controle: {str(e)}'
        }, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def activites_list_api(request):
    """API pour récupérer toutes les activités correctives disponibles."""
    try:
        from apps.planning.models import Activite
        # Filtrer uniquement les activités correctives
        activites = Activite.objects.select_related('type_activite').filter(
            is_active=True,
            est_corrective=True
        ).order_by('nom')

        data = []
        for activite in activites:
            data.append({
                'id': str(activite.id),
                'nom': activite.nom,
                'description': activite.description,
                'type_activite': {
                    'id': str(activite.type_activite.id),
                    'nomtype': activite.type_activite.nomtype
                } if activite.type_activite else None,
                'est_corrective': activite.est_corrective
            })

        return Response(data)

    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération des activités: {str(e)}'
        }, status=500)


@api_view(['POST', 'PUT', 'DELETE'])
@permission_classes([AllowAny])
def activites_correctives_manage_api(request):
    """API pour gérer les liaisons entre points de controle et activités correctives."""
    try:
        from .models import PointControleActiviteCorrectible

        if request.method == 'POST':
            # Ajouter une nouvelle liaison
            point_id = request.data.get('point_de_controle_id')
            activite_id = request.data.get('activite_id')
            priorite = request.data.get('priorite', 1)

            if not point_id or not activite_id:
                return Response({
                    'error': 'point_de_controle_id et activite_id sont requis'
                }, status=400)

            # Vérifier que le point de controle existe
            point = PointDeControle.objects.get(id=point_id)

            # Créer la liaison
            liaison, created = PointControleActiviteCorrectible.objects.get_or_create(
                point_de_controle=point,
                activite_id=activite_id,
                defaults={'priorite': priorite}
            )

            if created:
                return Response({
                    'message': 'Liaison créée avec succès',
                    'id': str(liaison.id)
                }, status=201)
            else:
                return Response({
                    'message': 'Liaison existe déjÃ '
                }, status=200)

        elif request.method == 'DELETE':
            # Supprimer une liaison
            liaison_id = request.data.get('liaison_id')
            point_id = request.data.get('point_de_controle_id')
            activite_id = request.data.get('activite_id')

            if liaison_id:
                liaison = PointControleActiviteCorrectible.objects.get(id=liaison_id)
                liaison.delete()
            elif point_id and activite_id:
                liaison = PointControleActiviteCorrectible.objects.get(
                    point_de_controle_id=point_id,
                    activite_id=activite_id
                )
                liaison.delete()
            else:
                return Response({
                    'error': 'liaison_id ou (point_de_controle_id + activite_id) requis'
                }, status=400)

            return Response({
                'message': 'Liaison supprimée avec succès'
            })

        elif request.method == 'PUT':
            # Modifier la priorité d'une liaison
            liaison_id = request.data.get('liaison_id')
            point_id = request.data.get('point_de_controle_id')
            activite_id = request.data.get('activite_id')
            priorite = request.data.get('priorite')

            if priorite is None:
                return Response({
                    'error': 'priorite est requis'
                }, status=400)

            # Trouver la liaison soit par ID direct, soit par point + activité
            if liaison_id:
                liaison = PointControleActiviteCorrectible.objects.get(id=liaison_id)
            elif point_id and activite_id:
                liaison = PointControleActiviteCorrectible.objects.get(
                    point_de_controle_id=point_id,
                    activite_id=activite_id
                )
            else:
                return Response({
                    'error': 'liaison_id ou (point_de_controle_id + activite_id) requis'
                }, status=400)

            liaison.priorite = priorite
            liaison.save()

            return Response({
                'message': 'Priorité mise Ã  jour avec succès'
            })

    except PointDeControle.DoesNotExist:
        return Response({
            'error': 'Point de controle non trouvé'
        }, status=404)
    except PointControleActiviteCorrectible.DoesNotExist:
        return Response({
            'error': 'Liaison non trouvée'
        }, status=404)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la gestion des liaisons: {str(e)}'
        }, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def save_resultat_api(request):
    """API pour sauvegarder un résultat d'inspection."""
    try:
        from apps.planning.models import Planning
        from apps.billing.models import PointEau
        from django.contrib.auth.models import User
        import uuid
        from decimal import Decimal

        data = request.data

        # Validation des données requises
        required_fields = ['item_id', 'point_controle_id', 'type', 'visite_id']
        for field in required_fields:
            if field not in data:
                return Response({
                    'error': f'Champ requis manquant: {field}'
                }, status=400)

        # Récupérer ou créer la visite
        try:
            planning = Planning.objects.get(id=data['visite_id'])

            # Essayer de récupérer une visite existante pour ce planning
            # Utiliser la date et l'ouvrage pour trouver une visite correspondante
            planning_date = planning.date.date() if planning.date else timezone.now().date()
            visite = Visite.objects.filter(
                ouvrage_id=planning.ouvrage.id,
                date_visite__date=planning_date
            ).first()

            if not visite:
                # Créer une nouvelle visite
                # Utiliser l'utilisateur connecté ou un utilisateur par défaut
                agent = request.user if request.user.is_authenticated else User.objects.first()

                visite = Visite.objects.create(
                    ouvrage_id=planning.ouvrage.id,
                    agent=agent,
                    date_visite=timezone.now(),
                    statut='en_cours'
                )

        except Planning.DoesNotExist:
            return Response({
                'error': 'Planning non trouvé'
            }, status=404)

        # Récupérer le point de controle
        try:
            point_controle = PointDeControle.objects.get(id=data['point_controle_id'])
        except PointDeControle.DoesNotExist:
            return Response({
                'error': 'Point de controle non trouvé'
            }, status=404)

        # Traitement selon le type (équipement ou point d'eau)
        if data['type'] == 'equipement':
            # Récupérer l'équipement
            try:
                equipement = EquipementConstitutif.objects.get(id=data['item_id'])
            except EquipementConstitutif.DoesNotExist:
                return Response({
                    'error': 'Equipement non trouvé'
                }, status=404)

            # Créer ou mettre Ã  jour le résultat de controle d'équipement
            resultat, created = ResultatControle.objects.get_or_create(
                visite=visite,
                equipement=equipement,
                point_de_controle=point_controle,
                defaults={
                    'heure_controle': timezone.now()
                }
            )

        elif data['type'] == 'point_eau':
            # Récupérer le point d'eau
            try:
                point_eau = PointEau.objects.get(id=data['item_id'])
            except PointEau.DoesNotExist:
                return Response({
                    'error': 'Point d\'eau non trouvé'
                }, status=404)

            # Créer ou mettre Ã  jour le résultat de controle de point d'eau
            resultat, created = ResultatControlePointEau.objects.get_or_create(
                visite=visite,
                point_eau=point_eau,
                point_de_controle=point_controle,
                defaults={
                    'heure_controle': timezone.now()
                }
            )

        else:
            return Response({
                'error': 'Type invalide'
            }, status=400)

        # Mettre Ã  jour les résultats selon le type de point de controle
        if point_controle.type_resultat == 'BOOL':
            if 'resultat_bool' not in data:
                return Response({
                    'error': 'Résultat booléen requis'
                }, status=400)
            resultat.resultat_bool = data['resultat_bool']
            resultat.resultat_numeric = None
            if hasattr(resultat, 'resultat_text'):
                resultat.resultat_text = ''

        elif point_controle.type_resultat == 'NUM':
            if 'resultat_numeric' not in data:
                return Response({
                    'error': 'Résultat numérique requis'
                }, status=400)
            try:
                resultat.resultat_numeric = Decimal(str(data['resultat_numeric']))
            except (ValueError, TypeError):
                return Response({
                    'error': 'Valeur numérique invalide'
                }, status=400)
            resultat.resultat_bool = None
            if hasattr(resultat, 'resultat_text'):
                resultat.resultat_text = ''

        elif point_controle.type_resultat == 'TEXT':
            if 'resultat_text' not in data:
                return Response({
                    'error': 'Résultat texte requis'
                }, status=400)
            if hasattr(resultat, 'resultat_text'):
                resultat.resultat_text = data['resultat_text']
            else:
                return Response({
                    'error': 'Type de résultat TEXT non supporté pour les équipements'
                }, status=400)
            resultat.resultat_bool = None
            resultat.resultat_numeric = None

        # Commentaire optionnel
        if 'commentaire' in data:
            resultat.commentaire = data['commentaire']

        # Gestion des actions correctives
        resultat.necessite_action = data.get('necessite_action', False)

        if resultat.necessite_action:
            if 'date_action' in data and data['date_action']:
                try:
                    resultat.date_action = data['date_action']
                except ValueError:
                    return Response({
                        'error': 'Format de date invalide'
                    }, status=400)

            if 'remarque_action' in data:
                resultat.remarque_action = data['remarque_action']

        # Lier les photos si un identifiant est fourni
        photo_ids = []
        for key in ['photo_ids', 'inspection_photo_ids', 'photo_id', 'inspection_photo_id']:
            value = data.get(key)
            if not value:
                continue
            if isinstance(value, (list, tuple)):
                photo_ids.extend(value)
            else:
                photo_ids.append(value)

        if photo_ids:
            photos = InspectionPhoto.objects.filter(id__in=set(photo_ids), visite=visite)
            resultat.inspection_photos.set(photos)

        # Sauvegarder le résultat
        resultat.save()

        return Response({
            'success': True,
            'message': 'Résultat sauvegardé avec succès',
            'resultat_id': str(resultat.id),
            'created': created
        })

    except Exception as e:
        return Response({
            'error': f'Erreur lors de la sauvegarde: {str(e)}'
        }, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def points_eau_api(request, planning_id):
    """API pour récupérer les points d'eau d'un planning avec leurs points de controle."""
    try:
        from apps.planning.models import Planning
        from apps.billing.models import PointEau, PointEauControle

        # Récupérer le planning
        planning = Planning.objects.get(id=planning_id)

        # Récupérer les points d'eau associés Ã  l'ouvrage du planning
        points_eau = PointEau.objects.filter(
            ouvrage_id=planning.ouvrage_id
        ).select_related('type_point_eau', 'ouvrage').prefetch_related(
            'points_controle__point_de_controle'
        )

        # Construire la réponse
        points_eau_data = []
        for point_eau in points_eau:
            # Récupérer les points de controle associés
            points_controle = []
            for pc_association in point_eau.points_controle.filter(actif=True).order_by('ordre'):
                point_controle = pc_association.point_de_controle
                points_controle.append({
                    'id': str(point_controle.id),
                    'nom': point_controle.nom,
                    'description': point_controle.description,
                    'type_resultat': point_controle.type_resultat,
                    'unite': point_controle.unite,
                    'valeur_min': float(point_controle.valeur_min) if point_controle.valeur_min else None,
                    'valeur_max': float(point_controle.valeur_max) if point_controle.valeur_max else None,
                    'ordre': pc_association.ordre,
                    'est_obligatoire': pc_association.est_obligatoire,
                    'notes': pc_association.notes
                })

            point_eau_data = {
                'id': str(point_eau.id),
                'nom': point_eau.nomabonne,
                'contact': point_eau.contactabonne,
                'telephone': point_eau.numeroteleph,
                'type_abonne': point_eau.typeabonne,
                'type_point_eau': point_eau.type_point_eau.nom_type if point_eau.type_point_eau else 'Non défini',
                'date_branchement': point_eau.datebranchement.isoformat() if point_eau.datebranchement else None,
                'latitude': point_eau.latitude,
                'longitude': point_eau.longitude,
                'points_controle': points_controle
            }
            points_eau_data.append(point_eau_data)

        response_data = {
            'points_eau': points_eau_data,
            'planning': {
                'id': planning.id,
                'ouvrage_id': str(planning.ouvrage_id),
                'ouvrage_nom': planning.ouvrage.nom_ouvrage if planning.ouvrage else 'Ouvrage non défini'
            }
        }

        return Response(response_data)

    except Planning.DoesNotExist:
        return Response({
            'error': 'Planning non trouvé'
        }, status=404)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération des points d\'eau: {str(e)}'
        }, status=500)


# ============================================================================
# NOUVEAU WORKFLOW D'INSPECTION - PAGES ROBUSTES
# ============================================================================

def equipment_selection_view(request):
    """Vue pour la sélection d'équipement ou point d'eau lors d'une inspection."""
    from apps.planning.models import Planning

    # Récupérer le planning_id depuis les paramètres GET
    planning_id = request.GET.get('planning_id')

    if not planning_id:
        # Rediriger vers le workflow terrain avec filtres par défaut
        from datetime import datetime
        year = datetime.now().year
        month = str(datetime.now().month).zfill(2)
        employe_id = ''
        if request.user.is_authenticated and hasattr(request.user, 'employe') and request.user.employe:
            employe_id = request.user.employe.id
        return redirect(f'/plannings/workflow-terrain/?mois={year}-{month}&employe={employe_id}')

    try:
        # Récupérer le planning
        planning = Planning.objects.select_related('employe', 'type_activite', 'ouvrage').get(id=planning_id)

        if not planning.ouvrage:
            messages.error(request, 'Aucun ouvrage associé Ã  ce planning')
            return redirect('planning:dashboard')

        # Récupérer les équipements de l'ouvrage
        equipements = EquipementConstitutif.objects.filter(
            ouvrage_id=planning.ouvrage.id
        ).select_related('type_equipement')

        # Récupérer les points d'eau de l'ouvrage
        from apps.billing.models import PointEau

        # Le modèle PointEau utilise directement l'ID de l'ouvrage (organization.Ouvrage)
        # Exclure les types BP (Branchement Privé) pour éviter une liste trop longue
        try:
            points_eau = PointEau.objects.filter(
                ouvrage_id=planning.ouvrage.id
            ).select_related('type_point_eau').exclude(
                type_point_eau__nom_type__icontains='BP'
            ).exclude(
                type_point_eau__nom_type__icontains='Branchement'
            )
        except Exception as e:
            print(f"Erreur lors de la récupération des points d'eau: {e}")
            points_eau = PointEau.objects.none()

        # Vérifier les inspections déjÃ  réalisées pour ce planning
        # Utiliser la date et l'ouvrage pour trouver les visites correspondantes
        inspections_faites = []
        planning_date = planning.date.date() if planning.date else None
        if planning_date:
            visites_existantes = Visite.objects.filter(
                ouvrage_id=planning.ouvrage.id,
                date_visite__date=planning_date
            )
        else:
            visites_existantes = Visite.objects.none()

        for visite in visites_existantes:
            # Equipements déjÃ  inspectés
            equipements_inspectes = ResultatControle.objects.filter(
                visite=visite
            ).values_list('equipement_id', flat=True).distinct()

            # Points d'eau déjÃ  inspectés
            points_eau_inspectes = ResultatControlePointEau.objects.filter(
                visite=visite
            ).values_list('point_eau_id', flat=True).distinct()

            inspections_faites.extend(equipements_inspectes)
            inspections_faites.extend(points_eau_inspectes)

        # Normaliser les URLs/photos et flags d'affichage
        for equipement in equipements:
            photo_url = None
            if equipement.photo_reference:
                try:
                    photo_url = equipement.photo_reference.get_download_url()
                except Exception:
                    photo_url = None
            if not photo_url:
                try:
                    photo_url = get_photo_url(equipement.photos)
                except Exception:
                    photo_url = None
            equipement.primary_photo_url = photo_url
            equipement.has_photo = bool(photo_url)
            equipement.has_gps = bool(equipement.latitude and equipement.longitude)

        for point_eau in points_eau:
            try:
                photo_url = get_photo_url(point_eau.photos)
            except Exception:
                photo_url = None
            point_eau.primary_photo_url = photo_url
            point_eau.has_photo = bool(photo_url)
            point_eau.has_gps = bool(point_eau.latitude and point_eau.longitude)


        context = {
            'title': 'Sélection d\'équipement Ã  inspecter',
            'planning': planning,
            'equipements': equipements,
            'points_eau': points_eau,
            'inspections_faites': inspections_faites,  # IDs des éléments déjÃ  inspectés
        }

        return render(request, 'inspections/equipment_selection.html', context)

    except Planning.DoesNotExist:
        messages.error(request, 'Planning non trouvé')
        return redirect('planning:dashboard')
    except Exception as e:
        messages.error(request, f'Erreur lors du chargement: {str(e)}')
        return redirect('planning:dashboard')


def nouvelle_planification_view(request):
    """Vue pour créer une nouvelle planification depuis le calendrier."""
    from apps.planning.models import Activite, PlanningDetail, DesignationCompte
    from apps.employees.models import Employe
    from django.contrib import messages
    from django.shortcuts import redirect
    from django.utils import timezone

    # Récupérer la date depuis les paramètres GET
    date_selectionnee = request.GET.get('date')

    if request.method == 'POST':
        try:
            from apps.planning.models import Planning

            # Créer le nouveau planning
            planning = Planning()
            planning.date = request.POST.get('date')
            planning.ouvrage_id = request.POST.get('ouvrage')
            planning.employe_id = request.POST.get('employe')
            planning.activite_id = request.POST.get('activite')
            planning.remarque = request.POST.get('remarque', '')
            planning.statut = 'en_cours'
            planning.estvalide = False
            planning.createdat = timezone.now()
            planning.updatedat = timezone.now()

            # Validation basique
            if not all([planning.date, planning.ouvrage_id, planning.employe_id, planning.activite_id]):
                messages.error(request, 'Tous les champs obligatoires doivent être remplis')
                return redirect(f'{request.path}?date={date_selectionnee}')

            planning.save()

            # Créer les PlanningDetails en cascade Ã  partir des DesignationCompte de l'activité
            activite = Activite.objects.get(id=planning.activite_id)
            designations_comptes = DesignationCompte.objects.filter(activite=activite).select_related('designation')

            for dc in designations_comptes:
                PlanningDetail.objects.create(
                    planning_id=planning.id,
                    designation=dc.designation,
                    quantity=dc.quantite or 0,
                    pu=dc.prix_unitaire or 0,
                    montant=(dc.quantite or 0) * (dc.prix_unitaire or 0)
                )

            messages.success(request, f'Planification créée avec succès ({designations_comptes.count()} détails ajoutés)')
            return redirect('planning:dashboard')

        except Exception as e:
            messages.error(request, f'Erreur lors de la création: {str(e)}')
            return redirect(f'{request.path}?date={date_selectionnee}')

    # GET request - afficher le formulaire
    try:
        # Récupérer les données nécessaires pour le formulaire
        activites = Activite.objects.filter(is_active=True).select_related('type_activite').order_by('type_activite__nomtype', 'nom')
        ouvrages = Ouvrage.objects.all().order_by('nom')
        employes = Employe.objects.all().order_by('nom', 'prenom')

        context = {
            'title': 'Nouvelle Planification',
            'date_selectionnee': date_selectionnee,
            'activites': activites,
            'ouvrages': ouvrages,
            'employes': employes,
        }

        return render(request, 'inspections/nouvelle_planification.html', context)

    except Exception as e:
        messages.error(request, f'Erreur lors du chargement du formulaire: {str(e)}')
        return redirect('planning:dashboard')


@api_view(['GET'])
@permission_classes([AllowAny])
def equipment_inspection_data_api(request, item_id, item_type):
    """API pour récupérer les données d'inspection d'un équipement ou point d'eau."""
    print(f"[API] Appelée: item_id={item_id}, item_type={item_type}")
    try:
        planning_id = request.GET.get('planning_id')
        print(f"[API] Planning ID: {planning_id}")
        if not planning_id:
            return Response({
                'error': 'planning_id requis'
            }, status=400)

        # Récupérer le planning
        from apps.planning.models import Planning
        planning = Planning.objects.get(id=planning_id)
        print(f"[API] Planning trouvé: {planning}")

        # Initialiser les variables pour éviter UnboundLocalError
        item_data = {}
        points_controle_data = []

        if item_type == 'equipement':
            # Récupérer l'équipement
            equipement = EquipementConstitutif.objects.get(id=item_id)

            # Récupérer les points de controle via l'architecture 3-niveaux
            from apps.inspections.models import ComposantTypeEquipement, PointDeControleComposant

            # Points de controle organisés par composant
            composants = ComposantTypeEquipement.objects.filter(
                type_equipement=equipement.type_equipement
            ).prefetch_related('points_controle')

            points_controle_data = []
            for composant in composants:
                # Récupérer les points de controle de ce composant
                points_controle_composant = PointDeControleComposant.objects.filter(
                    composant_equipement=composant
                ).select_related('point_de_controle').order_by('ordre_affichage')

                if points_controle_composant.exists():
                    composant_data = {
                        'composant': {
                            'id': str(composant.id),
                            'nom': composant.nom_composant,
                            'description': composant.description
                        },
                        'points_controle': []
                    }

                    for pc_relation in points_controle_composant:
                        point = pc_relation.point_de_controle
                        composant_data['points_controle'].append({
                            'id': str(point.id),
                            'nom': point.nom,
                            'description': point.description or '',
                            'type_resultat': point.type_resultat,
                            'unite': point.unite or '',
                            'valeur_min': float(point.valeur_min) if point.valeur_min else None,
                            'valeur_max': float(point.valeur_max) if point.valeur_max else None,
                            'ordre': pc_relation.ordre_affichage,
                            'est_obligatoire': pc_relation.est_obligatoire,
                            'photo_reference_url': pc_relation.photo_reference.get_download_url() if pc_relation.photo_reference else None
                        })

                    points_controle_data.append(composant_data)

            item_data = {
                'id': str(equipement.id),
                'nom': equipement.nom,
                'type': equipement.type_equipement.nom_type if equipement.type_equipement else 'Non défini',
                'code': equipement.code_equipement,
                'statut': equipement.statut,
                'description': equipement.description or '',
                'photo_reference_url': equipement.photo_reference.get_download_url() if equipement.photo_reference else None,
                'latitude': float(equipement.latitude) if equipement.latitude else None,
                'longitude': float(equipement.longitude) if equipement.longitude else None,
            }

        elif item_type == 'point_eau':
            # Récupérer le point d'eau
            point_eau = PointEau.objects.get(id=item_id)

            # Points de controle pour les points d'eau
            from apps.inspections.models import ComposantTypePointEau, PointDeControleComposant

            composants = ComposantTypePointEau.objects.filter(
                type_point_eau=point_eau.type_point_eau
            ).prefetch_related('points_controle')

            points_controle_data = []
            for composant in composants:
                # Récupérer les points de controle de ce composant
                points_controle_composant = PointDeControleComposant.objects.filter(
                    composant_point_eau=composant
                ).select_related('point_de_controle').order_by('ordre_affichage')

                if points_controle_composant.exists():
                    composant_data = {
                        'composant': {
                            'id': str(composant.id),
                            'nom': composant.nom_composant,
                            'description': composant.description
                        },
                        'points_controle': []
                    }

                    for pc_relation in points_controle_composant:
                        point = pc_relation.point_de_controle
                        composant_data['points_controle'].append({
                            'id': str(point.id),
                            'nom': point.nom,
                            'description': point.description or '',
                            'type_resultat': point.type_resultat,
                            'unite': point.unite or '',
                            'valeur_min': float(point.valeur_min) if point.valeur_min else None,
                            'valeur_max': float(point.valeur_max) if point.valeur_max else None,
                            'ordre': pc_relation.ordre_affichage,
                            'est_obligatoire': pc_relation.est_obligatoire,
                            'photo_reference_url': pc_relation.photo_reference.get_download_url() if pc_relation.photo_reference else None
                        })

                    points_controle_data.append(composant_data)

            item_data = {
                'id': str(point_eau.id),
                'nom': point_eau.nomabonne or 'Point d\'eau',
                'type': point_eau.type_point_eau.nom_type if point_eau.type_point_eau else 'Non défini',
                'contact': point_eau.contactabonne or '',
                'telephone': point_eau.numeroteleph or '',
                'type_abonne': point_eau.typeabonne or '',
                'date_branchement': point_eau.datebranchement.isoformat() if point_eau.datebranchement else None,
                'latitude': float(point_eau.latitude) if point_eau.latitude else None,
                'longitude': float(point_eau.longitude) if point_eau.longitude else None,
            }
        else:
            return Response({
                'error': 'Type d\'item invalide'
            }, status=400)

        response_data = {
            'planning': {
                'id': str(planning.id),
                'date': planning.date.isoformat() if planning.date else None,
                'employe_nom': planning.employe.nom_complet if planning.employe else 'Non assigné',
                'activite_nom': planning.type_activite.nomtype if planning.type_activite else 'Non défini',
                'ouvrage_nom': planning.ouvrage.nom_ouvrage if planning.ouvrage else 'Non défini',
            },
            'item': item_data,
            'item_type': item_type,
            'points_controle_par_composant': points_controle_data,
            'total_composants': len(points_controle_data),
            'total_points_controle': sum(len(c['points_controle']) for c in points_controle_data)
        }

        return Response(response_data)

    except (EquipementConstitutif.DoesNotExist, PointEau.DoesNotExist):
        return Response({
            'error': 'Equipement ou point d\'eau non trouvé'
        }, status=404)
    except Planning.DoesNotExist:
        return Response({
            'error': 'Planning non trouvé'
        }, status=404)
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération des données: {str(e)}'
        }, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def existing_inspection_results_api(request, item_id, item_type):
    """
    API pour récupérer les résultats existants d'une inspection pour un équipement/point d'eau donné.
    """
    try:
        planning_id = request.GET.get('planning_id')
        if not planning_id:
            return Response({'error': 'planning_id requis'}, status=400)

        from apps.planning.models import Planning

        planning = Planning.objects.get(id=planning_id)
        planning_date = planning.date.date() if planning.date else None

        if not planning_date:
            return Response({'error': 'Date de planning invalide'}, status=400)

        # Trouver la visite correspondante
        visite = Visite.objects.filter(
            ouvrage_id=planning.ouvrage.id,
            date_visite__date=planning_date
        ).first()

        if not visite:
            return Response({'error': 'Aucune visite trouvée'}, status=404)

        # Charger les résultats selon le type
        points_controle_results = []

        if item_type == 'equipement':
            # Résultats pour équipement
            resultats = ResultatControle.objects.filter(
                visite=visite,
                equipement_id=item_id
            ).select_related('point_controle')

            for resultat in resultats:
                point_data = {
                    'point_id': str(resultat.point_controle.id),
                    'type': resultat.point_controle.type_controle,
                    'conforme': resultat.conforme,
                    'value': None,
                    'photo_actuelle': None,
                    'corrective_action': None
                }

                # Valeur selon le type
                if resultat.point_controle.type_controle == 'BOOL':
                    point_data['value'] = resultat.conforme
                elif resultat.point_controle.type_controle == 'NUM':
                    point_data['value'] = resultat.valeur_numerique
                elif resultat.point_controle.type_controle == 'TEXT':
                    point_data['value'] = resultat.observation

                # Photo
                if resultat.photo:
                    point_data['photo_actuelle'] = {
                        'url': resultat.photo.get_download_url() if hasattr(resultat.photo, 'get_download_url') else None,
                        'timestamp': resultat.created_at.isoformat() if resultat.created_at else None
                    }

                # Action corrective
                if resultat.action_corrective:
                    point_data['corrective_action'] = {
                        'activite': resultat.action_corrective.activite_id if resultat.action_corrective else None,
                        'date': resultat.action_corrective.date_prevue.isoformat() if resultat.action_corrective and resultat.action_corrective.date_prevue else None,
                        'remarque': resultat.action_corrective.remarques if resultat.action_corrective else None
                    }

                points_controle_results.append(point_data)

        elif item_type == 'point_eau':
            # Résultats pour point d'eau
            resultats = ResultatControlePointEau.objects.filter(
                visite=visite,
                point_eau_id=item_id
            ).select_related('point_controle')

            for resultat in resultats:
                point_data = {
                    'point_id': str(resultat.point_controle.id),
                    'type': resultat.point_controle.type_controle,
                    'conforme': resultat.conforme,
                    'value': None,
                    'photo_actuelle': None,
                    'corrective_action': None
                }

                # Valeur selon le type
                if resultat.point_controle.type_controle == 'BOOL':
                    point_data['value'] = resultat.conforme
                elif resultat.point_controle.type_controle == 'NUM':
                    point_data['value'] = resultat.valeur_numerique
                elif resultat.point_controle.type_controle == 'TEXT':
                    point_data['value'] = resultat.observation

                # Photo
                if resultat.photo:
                    point_data['photo_actuelle'] = {
                        'url': resultat.photo.get_download_url() if hasattr(resultat.photo, 'get_download_url') else None,
                        'timestamp': resultat.created_at.isoformat() if resultat.created_at else None
                    }

                points_controle_results.append(point_data)

        return Response({
            'visite_id': str(visite.id),
            'points_controle': points_controle_results
        })

    except Planning.DoesNotExist:
        return Response({'error': 'Planning non trouvé'}, status=404)
    except Exception as e:
        return Response({'error': f'Erreur: {str(e)}'}, status=500)


# ========== GESTION DES PHOTOS DE REFERENCE ==========

@api_view(['GET'])
@permission_classes([AllowAny])
def get_equipements_ouvrage(request, ouvrage_id):
    """Récupère les équipements d'un ouvrage"""
    try:
        from apps.infrastructure.models import EquipementConstitutif

        equipements = EquipementConstitutif.objects.filter(ouvrage_id=ouvrage_id).select_related('type_equipement')

        results = []
        for eq in equipements:
            results.append({
                'id': str(eq.id),
                'nom': eq.nom or 'Sans nom',
                'type': eq.type_equipement.nom_type if eq.type_equipement else 'Equipement'
            })

        return Response(results)

    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_composants_equipement(request, equipement_id):
    """Récupère les composants d'un équipement"""
    try:
        from apps.inspections.models import ChecklistItem, PointDeControleComposant
        from apps.infrastructure.models import EquipementConstitutif

        # Récupérer l'équipement
        equipement = EquipementConstitutif.objects.select_related('type_equipement').get(id=equipement_id)

        # Récupérer tous les composants liés Ã  ce type d'équipement
        composants_ids = PointDeControleComposant.objects.filter(
            composant_equipement__type_equipement=equipement.type_equipement
        ).values_list('composant_equipement_id', flat=True).distinct()

        from apps.inspections.models import ComposantTypeEquipement
        composants = ComposantTypeEquipement.objects.filter(id__in=composants_ids)

        results = [{'id': str(c.id), 'nom': c.nom} for c in composants]

        return Response(results)

    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_photos_references_composant(request, composant_id):
    """Récupère tous les points de controle d'un composant avec leurs photos de référence"""
    try:
        from apps.inspections.models import PointDeControleComposant

        # Récupérer tous les points de controle du composant
        points_controle_composants = PointDeControleComposant.objects.filter(
            Q(composant_equipement_id=composant_id) | Q(composant_point_eau_id=composant_id)
        ).select_related(
            'point_de_controle',
            'composant_equipement__type_equipement',
            'composant_point_eau__type_point_eau',
            'photo_reference'
        )

        # Construire la réponse
        results = []
        for pcc in points_controle_composants:
            # Déterminer le nom du composant et le type
            if pcc.composant_equipement:
                composant_nom = pcc.composant_equipement.nom
                type_nom = pcc.composant_equipement.type_equipement.nom_type_ouvrage if pcc.composant_equipement.type_equipement else 'N/A'
            else:
                composant_nom = pcc.composant_point_eau.nom
                type_nom = pcc.composant_point_eau.type_point_eau.nom_type if pcc.composant_point_eau.type_point_eau else 'N/A'

            # URL de la photo de référence
            photo_url = None
            if pcc.photo_reference:
                photo_url = pcc.photo_reference.get_download_url() if hasattr(pcc.photo_reference, 'get_download_url') else None

            results.append({
                'id': str(pcc.id),
                'point_controle_id': str(pcc.point_de_controle.id),
                'point_controle_nom': pcc.point_de_controle.nom,
                'point_controle_description': pcc.point_de_controle.description,
                'composant_nom': composant_nom,
                'type_nom': type_nom,
                'photo_reference_url': photo_url,
            })

        return Response(results)

    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def upload_photo_reference(request):
    """Upload une photo de référence pour un point de controle"""
    try:
        from apps.inspections.models import PointDeControleComposant

        # Récupérer les données
        point_controle_composant_id = request.data.get('point_controle_composant_id')
        photo_file = request.FILES.get('photo')

        if not point_controle_composant_id or not photo_file:
            return Response({'error': 'Données manquantes'}, status=400)

        # Récupérer le PointDeControleComposant
        pcc = PointDeControleComposant.objects.get(id=point_controle_composant_id)

        # Supprimer l'ancienne photo si elle existe
        if pcc.photo_reference:
            old_photo = pcc.photo_reference
            pcc.photo_reference = None
            pcc.save()
            # Optionnel: supprimer physiquement l'ancien fichier
            # storage_service.delete_file(old_photo.file_path)
            old_photo.delete()

        # Upload la nouvelle photo via storage_service
        file_upload = storage_service.upload_file(
            file=photo_file,
            uploaded_by=request.user if request.user.is_authenticated else None,
            description=f"Photo de référence pour {pcc.point_de_controle.nom}",
            category='inspection_reference'
        )

        # Associer la photo au point de controle
        pcc.photo_reference = file_upload
        pcc.save()

        return Response({
            'success': True,
            'photo_url': file_upload.get_download_url() if hasattr(file_upload, 'get_download_url') else None
        })

    except PointDeControleComposant.DoesNotExist:
        return Response({'error': 'Point de controle composant non trouvé'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['DELETE'])
@permission_classes([AllowAny])
def delete_photo_reference(request, point_controle_composant_id):
    """Supprime la photo de référence d'un point de controle"""
    try:
        from apps.inspections.models import PointDeControleComposant

        pcc = PointDeControleComposant.objects.get(id=point_controle_composant_id)

        if not pcc.photo_reference:
            return Response({'error': 'Aucune photo Ã  supprimer'}, status=400)

        # Supprimer la photo
        photo = pcc.photo_reference
        pcc.photo_reference = None
        pcc.save()

        # Optionnel: supprimer physiquement le fichier
        # storage_service.delete_file(photo.file_path)
        photo.delete()

        return Response({'success': True})

    except PointDeControleComposant.DoesNotExist:
        return Response({'error': 'Point de controle composant non trouvé'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def check_item_data(request, item_id, item_type):
    """Vérifie si un équipement ou point d'eau a des données GPS et photos"""
    try:
        if item_type == 'equipement':
            item = EquipementConstitutif.objects.get(id=item_id)
            has_gps = item.latitude is not None and item.longitude is not None
            has_photo = item.photo is not None and bool(item.photo)
            item_name = item.nom
        elif item_type == 'point_eau':
            item = PointEau.objects.get(id=item_id)
            has_gps = item.latitude is not None and item.longitude is not None
            has_photo = item.photo is not None and bool(item.photo)
            item_name = item.nomabonne or "Point d'eau"
        else:
            return Response({'error': 'Type invalide'}, status=400)

        return Response({
            'has_gps': has_gps,
            'has_photo': has_photo,
            'item_name': item_name
        })

    except (EquipementConstitutif.DoesNotExist, PointEau.DoesNotExist):
        return Response({'error': 'Elément non trouvé'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def update_item_data(request):
    """Met Ã  jour les données GPS et/ou photo d'un équipement ou point d'eau"""
    try:
        item_id = request.data.get('item_id')
        item_type = request.data.get('item_type')
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        photo_file = request.FILES.get('photo')

        if not item_id or not item_type:
            return Response({'error': 'item_id et item_type requis'}, status=400)

        # Récupérer l'élément
        if item_type == 'equipement':
            item = EquipementConstitutif.objects.get(id=item_id)
        elif item_type == 'point_eau':
            item = PointEau.objects.get(id=item_id)
        else:
            return Response({'error': 'Type invalide'}, status=400)

        # Mettre Ã  jour les coordonnées GPS si fournies
        if latitude and longitude:
            item.latitude = float(latitude)
            item.longitude = float(longitude)

        # Mettre Ã  jour la photo si fournie
        if photo_file:
            # Sauvegarder le fichier via le service de stockage
            file_upload = storage_service.save_file(
                file=photo_file,
                related_object=item,
                field_name='photo',
                uploaded_by=request.user if request.user.is_authenticated else None
            )
            item.photo = file_upload

        item.save()

        return Response({
            'success': True,
            'message': 'Données mises Ã  jour avec succès',
            'has_gps': item.latitude is not None and item.longitude is not None,
            'has_photo': item.photo is not None
        })

    except (EquipementConstitutif.DoesNotExist, PointEau.DoesNotExist):
        return Response({'error': 'Elément non trouvé'}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def check_planning_items_data(request, planning_id):
    """Vérifie les données GPS/photos de tous les équipements et points d'eau d'un planning"""
    try:
        planning = Planning.objects.get(id=planning_id)

        items_missing_data = []

        # Vérifier les équipements de l'ouvrage
        if planning.ouvrage:
            equipements = EquipementConstitutif.objects.filter(ouvrage=planning.ouvrage)

            for equip in equipements:
                missing = []
                if not equip.latitude or not equip.longitude:
                    missing.append('GPS')
                if not equip.photo:
                    missing.append('Photo')

                if missing:
                    items_missing_data.append({
                        'id': str(equip.id),
                        'type': 'equipement',
                        'name': equip.nom,
                        'missing': missing,
                        'has_gps': equip.latitude is not None and equip.longitude is not None,
                        'has_photo': equip.photo is not None
                    })

            # Vérifier les points d'eau de l'ouvrage
            points_eau = PointEau.objects.filter(ouvrage=planning.ouvrage)

            for pe in points_eau:
                missing = []
                if not pe.latitude or not pe.longitude:
                    missing.append('GPS')
                if not pe.photo:
                    missing.append('Photo')

                if missing:
                    items_missing_data.append({
                        'id': str(pe.id),
                        'type': 'point_eau',
                        'name': pe.nomabonne or "Point d'eau",
                        'missing': missing,
                        'has_gps': pe.latitude is not None and pe.longitude is not None,
                        'has_photo': pe.photo is not None
                    })

        return Response({
            'planning_id': str(planning.id),
            'ouvrage_name': planning.ouvrage.nom_ouvrage if planning.ouvrage else None,
            'has_missing_data': len(items_missing_data) > 0,
            'items_missing_data': items_missing_data,
            'total_items': len(items_missing_data)
        })

    except Planning.DoesNotExist:
        return Response({'error': 'Planning non trouvé'}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)


# ============================================
# Vues de consultation des résultats d'inspections
# ============================================

@employe_required
def resultats_equipements(request):
    """Page de consultation consolidée des résultats d'inspections équipements

    UTILISE LE NOUVEAU SYSTEME: Inspection + ResultatInspectionComposant
    (Ancien système ResultatControle conservé pour rétrocompatibilité)
    """
    from apps.geography.models import Commune
    from datetime import datetime

    # Récupérer les filtres
    commune_filter = request.GET.get('commune', '')
    ouvrage_filter = request.GET.get('ouvrage', '')
    mois_filter = request.GET.get('mois', '')
    conformite_filter = request.GET.get('conformite', '')

    # ========== NOUVEAU SYSTEME: Inspection + ResultatInspectionComposant ==========
    # Query sur les ResultatInspectionComposant avec leurs relations
    resultats_nouveaux = ResultatInspectionComposant.objects.select_related(
        'inspection',
        'inspection__equipement',
        'inspection__equipement__type_equipement',
        'inspection__equipement__ouvrage',
        'inspection__inspecteur',
        'composant_equipement',
        'point_de_controle'
    ).filter(
        # Accepter tous les types d'inspection qui concernent des équipements
        inspection__equipement__isnull=False,
        inspection__statut='terminee'
    )

    # Appliquer les filtres sur le nouveau système
    if commune_filter:
        resultats_nouveaux = resultats_nouveaux.filter(
            inspection__equipement__ouvrage__pointeau__parcelle__village__fokontany__commune_id=commune_filter
        ).distinct()

    if ouvrage_filter:
        resultats_nouveaux = resultats_nouveaux.filter(
            inspection__equipement__ouvrage__nom_ouvrage__icontains=ouvrage_filter
        )

    if mois_filter:
        try:
            year, month = mois_filter.split('-')
            resultats_nouveaux = resultats_nouveaux.filter(
                inspection__date_inspection__year=year,
                inspection__date_inspection__month=month
            )
        except:
            pass

    if conformite_filter:
        if conformite_filter == 'conforme':
            resultats_nouveaux = resultats_nouveaux.filter(conforme=True)
        elif conformite_filter == 'non_conforme':
            resultats_nouveaux = resultats_nouveaux.filter(conforme=False)

    # Ordonner par date décroissante et limiter
    resultats_nouveaux = resultats_nouveaux.order_by('-inspection__date_inspection')[:500]

    # ========== ADAPTER LES DONNEES POUR LE TEMPLATE ==========
    # Créer des objets adaptateurs pour compatibilité avec le template existant
    class ResultatAdapter:
        """Adapte ResultatInspectionComposant pour le template"""
        def __init__(self, ric):
            self.ric = ric
            self._visite = None
            self._equipement = None

        @property
        def visite(self):
            """Simule l'objet visite pour compatibilité template"""
            if self._visite is None:
                class VisiteAdapter:
                    def __init__(self, inspection):
                        self.date_visite = inspection.date_inspection
                        self.ouvrage = inspection.equipement.ouvrage if inspection.equipement else None
                self._visite = VisiteAdapter(self.ric.inspection)
            return self._visite

        @property
        def equipement(self):
            """Retourne l'équipement de l'inspection"""
            if self._equipement is None:
                equip = self.ric.inspection.equipement
                if equip:
                    class EquipementAdapter:
                        def __init__(self, eq):
                            self.type_equipement = eq.type_equipement
                            # Utiliser code_equipement ou composant pour le nom
                            self.nom = eq.code_equipement or str(eq)
                    self._equipement = EquipementAdapter(equip)
                else:
                    self._equipement = None
            return self._equipement

        @property
        def point_de_controle(self):
            return self.ric.point_de_controle

        @property
        def conforme(self):
            return self.ric.conforme

        @property
        def observations(self):
            return self.ric.observations or ''

        @property
        def action_corrective(self):
            # Vérifier s'il y a une action corrective liée
            if hasattr(self.ric, 'action_corrective') and self.ric.action_corrective:
                return self.ric.action_corrective
            return None

    # Convertir les résultats en adaptateurs
    resultats = [ResultatAdapter(ric) for ric in resultats_nouveaux]

    # ========== ANCIEN SYSTEME (rétrocompatibilité) ==========
    # Récupérer aussi les anciens ResultatControle si pas de filtre ou peu de résultats
    if len(resultats) < 500:
        resultats_anciens = ResultatControle.objects.select_related(
            'visite',
            'visite__ouvrage',
            'point_de_controle',
            'equipement',
            'equipement__type_equipement'
        ).all()

        # Appliquer les mêmes filtres
        if commune_filter:
            resultats_anciens = resultats_anciens.filter(
                visite__ouvrage__parcelle__village__fokontany__commune_id=commune_filter
            )

        if ouvrage_filter:
            resultats_anciens = resultats_anciens.filter(visite__ouvrage__nom_ouvrage__icontains=ouvrage_filter)

        if mois_filter:
            try:
                year, month = mois_filter.split('-')
                resultats_anciens = resultats_anciens.filter(
                    visite__date_visite__year=year,
                    visite__date_visite__month=month
                )
            except:
                pass

        if conformite_filter:
            if conformite_filter == 'conforme':
                resultats_anciens = resultats_anciens.filter(conforme=True)
            elif conformite_filter == 'non_conforme':
                resultats_anciens = resultats_anciens.filter(conforme=False)

        # Limiter le nombre total
        reste = 500 - len(resultats)
        resultats_anciens = resultats_anciens.order_by('-visite__date_visite')[:reste]

        # Combiner les résultats (nouveaux en premier, puis anciens)
        resultats = list(resultats) + list(resultats_anciens)

    # Récupérer les communes pour le filtre
    communes = Commune.objects.all().order_by('nom_commune')

    # Récupérer les ouvrages accessibles
    ouvrages = filter_queryset_by_permissions(
        Ouvrage.objects.all(), request.user
    ).order_by('nom_ouvrage')

    context = {
        'resultats': resultats,
        'communes': communes,
        'ouvrages': ouvrages,
        'commune_filter': commune_filter,
        'ouvrage_filter': ouvrage_filter,
        'mois_filter': mois_filter,
        'conformite_filter': conformite_filter,
        'title': 'Résultats Inspections Equipements'
    }

    return render(request, 'inspections/resultats_equipements.html', context)


@employe_required
def resultats_points_eau(request):
    """Page de consultation consolidée des résultats d'inspections points d'eau"""
    from apps.geography.models import Commune
    from datetime import datetime
    
    # Récupérer les filtres
    commune_filter = request.GET.get('commune', '')
    ouvrage_filter = request.GET.get('ouvrage', '')
    mois_filter = request.GET.get('mois', '')
    conformite_filter = request.GET.get('conformite', '')
    
    # Query de base avec relations
    resultats = ResultatControlePointEau.objects.select_related(
        'visite',
        'visite__ouvrage',
        'point_de_controle',
        'point_eau',
        'point_eau__type_point_eau'
    ).all()
    
    # Appliquer les filtres
    if commune_filter:
        resultats = resultats.filter(
            point_eau__parcelle__village__fokontany__commune_id=commune_filter
        )
    
    if ouvrage_filter:
        resultats = resultats.filter(visite__ouvrage__nom_ouvrage__icontains=ouvrage_filter)
    
    if mois_filter:
        try:
            year, month = mois_filter.split('-')
            resultats = resultats.filter(
                visite__date_visite__year=year,
                visite__date_visite__month=month
            )
        except:
            pass
    
    if conformite_filter:
        if conformite_filter == 'conforme':
            resultats = resultats.filter(conforme=True)
        elif conformite_filter == 'non_conforme':
            resultats = resultats.filter(conforme=False)
    
    # Ordonner par date décroissante
    resultats = resultats.order_by('-visite__date_visite')[:500]  # Limiter Ã  500 résultats
    
    # Récupérer les communes pour le filtre
    communes = Commune.objects.all().order_by('nom_commune')
    
    # Récupérer les ouvrages accessibles
    ouvrages = filter_queryset_by_permissions(
        Ouvrage.objects.all(), request.user
    ).order_by('nom_ouvrage')
    
    context = {
        'resultats': resultats,
        'communes': communes,
        'ouvrages': ouvrages,
        'commune_filter': commune_filter,
        'ouvrage_filter': ouvrage_filter,
        'mois_filter': mois_filter,
        'conformite_filter': conformite_filter,
        'title': 'Résultats Inspections Points d\'Eau'
    }
    
    return render(request, 'inspections/resultats_points_eau.html', context)


@api_view(['GET'])
@permission_classes([AllowAny])
def employe_future_plannings_api(request, employe_id):
    """API pour récupérer les plannings futurs d'un employé pour le calendrier d'actions correctives."""
    try:
        import pytz
        from datetime import datetime, timedelta

        # Timezone Madagascar
        tz_madagascar = pytz.timezone('Indian/Antananarivo')

        # Date d'aujourd'hui en timezone Madagascar
        today = timezone.now().astimezone(tz_madagascar).date()

        # Période: 90 jours futurs (3 mois)
        end_date = today + timedelta(days=90)

        # Jours fériés Madagascar 2025-2026 (Ã  adapter selon l'année)
        jours_feries = [
            '2025-01-01',  # Nouvel An
            '2025-03-29',  # Fête des Martyrs
            '2025-04-21',  # Lundi de PÃ¢ques
            '2025-05-01',  # Fête du Travail
            '2025-05-29',  # Ascension
            '2025-06-09',  # Lundi de Pentecote
            '2025-06-26',  # Fête de l'Indépendance
            '2025-08-15',  # Assomption
            '2025-11-01',  # Toussaint
            '2025-12-25',  # NoÃ«l
            '2026-01-01',  # Nouvel An
            '2026-03-29',  # Fête des Martyrs
            '2026-05-14',  # Ascension
        ]

        # Récupérer les plannings de l'employé
        plannings = Planning.objects.filter(
            employe_id=employe_id,
            date__gte=today,
            date__lte=end_date
        ).select_related(
            'activite',
            'type_activite',
            'ouvrage'
        ).order_by('date')

        # Grouper par date avec indicateurs
        plannings_by_date = {}
        for planning in plannings:
            # Convertir la date en timezone Madagascar
            date_aware = planning.date if planning.date.tzinfo else timezone.make_aware(planning.date)
            date_madagascar = date_aware.astimezone(tz_madagascar)
            date_str = date_madagascar.date().isoformat()

            if date_str not in plannings_by_date:
                plannings_by_date[date_str] = {
                    'activites': [],
                    'has_reparation': False
                }

            activite_nom = planning.activite.nom if planning.activite else 'Non défini'

            # Détecter si c'est une réparation (occupation)
            is_reparation = 'réparation' in activite_nom.lower() or 'reparation' in activite_nom.lower()

            plannings_by_date[date_str]['activites'].append({
                'id': str(planning.id),
                'activite_nom': activite_nom,
                'type_activite': planning.type_activite.nomtype if planning.type_activite else 'Non défini',
                'ouvrage': planning.ouvrage.nom_ouvrage if planning.ouvrage else 'Non défini',
                'heure': date_madagascar.strftime('%H:%M') if date_madagascar.hour != 0 or date_madagascar.minute != 0 else None,
                'is_reparation': is_reparation
            })

            if is_reparation:
                plannings_by_date[date_str]['has_reparation'] = True

        return Response({
            'success': True,
            'employe_id': employe_id,
            'today': today.isoformat(),
            'plannings_by_date': plannings_by_date,
            'jours_feries': jours_feries
        })

    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération des plannings: {str(e)}'
        }, status=500)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def api_points_controle_pour_inspection(request):
    """
    API pour récupérer les points de controle pour une inspection d'un équipement.

    Retourne:
    - Points de controle communs du type d'équipement (routiniers ou routiniers+annuels selon le type de visite)
    - Points de controle spécifiques Ã  l'équipement individuel

    Paramètres:
    - equipement_id: UUID de l'équipement Ã  inspecter (requis)
    - type_visite: 'ROUTINIERE' ou 'ANNUELLE' (requis)
    """
    from apps.infrastructure.models import TypeEquipement

    equipement_id = request.GET.get('equipement_id')
    type_visite = request.GET.get('type_visite', 'ROUTINIERE')

    if not equipement_id:
        return Response({
            'error': 'equipement_id est requis'
        }, status=status.HTTP_400_BAD_REQUEST)

    if type_visite not in ['ROUTINIERE', 'ANNUELLE']:
        return Response({
            'error': 'type_visite doit être "ROUTINIERE" ou "ANNUELLE"'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        equipement = EquipementConstitutif.objects.select_related(
            'type_equipement'
        ).get(id=equipement_id)
    except EquipementConstitutif.DoesNotExist:
        return Response({
            'error': 'Equipement non trouvé'
        }, status=status.HTTP_404_NOT_FOUND)

    # 1. Points de controle communs du type d'équipement
    # Pour visite routinière : seulement les points routiniers
    # Pour visite annuelle : routiniers + annuels

    if type_visite == 'ROUTINIERE':
        # Seulement les points routiniers
        points_communs_qs = PointDeControleComposant.objects.filter(
            composant_equipement__type_equipement=equipement.type_equipement,
            type_visite=PointDeControleComposant.TypeVisite.ROUTINIERE
        ).select_related(
            'point_de_controle',
            'composant_equipement',
            'photo_reference'
        ).order_by('composant_equipement__nom_composant', 'ordre_affichage')
    else:
        # Routiniers + Annuels
        points_communs_qs = PointDeControleComposant.objects.filter(
            composant_equipement__type_equipement=equipement.type_equipement
        ).select_related(
            'point_de_controle',
            'composant_equipement',
            'photo_reference'
        ).order_by('type_visite', 'composant_equipement__nom_composant', 'ordre_affichage')

    points_communs = []
    for pc_composant in points_communs_qs:
        points_communs.append({
            'id': str(pc_composant.id),
            'point_controle_id': str(pc_composant.point_de_controle.id),
            'nom': pc_composant.point_de_controle.nom,
            'description': pc_composant.point_de_controle.description,
            'type_resultat': pc_composant.point_de_controle.type_resultat,
            'valeur_min': float(pc_composant.point_de_controle.valeur_min) if pc_composant.point_de_controle.valeur_min else None,
            'valeur_max': float(pc_composant.point_de_controle.valeur_max) if pc_composant.point_de_controle.valeur_max else None,
            'unite': pc_composant.point_de_controle.unite,
            'est_obligatoire': pc_composant.est_obligatoire,
            'ordre_affichage': pc_composant.ordre_affichage,
            'type_visite': pc_composant.get_type_visite_display(),
            'type_visite_code': pc_composant.type_visite,
            'composant_nom': pc_composant.composant_equipement.nom_composant if pc_composant.composant_equipement else None,
            'photo_reference_url': pc_composant.photo_reference.get_download_url() if pc_composant.photo_reference else None,
            'source': 'commun',  # Marqueur pour identifier l'origine
        })

    # 2. Points de controle spécifiques Ã  cet équipement
    if type_visite == 'ROUTINIERE':
        # Seulement les points routiniers spécifiques
        points_specifiques_qs = PointDeControleSpecifique.objects.filter(
            equipement=equipement,
            type_visite=PointDeControleSpecifique.TypeVisite.ROUTINIERE
        ).select_related('point_de_controle').order_by('ordre_affichage')
    else:
        # Routiniers + Annuels spécifiques
        points_specifiques_qs = PointDeControleSpecifique.objects.filter(
            equipement=equipement
        ).select_related('point_de_controle').order_by('type_visite', 'ordre_affichage')

    points_specifiques = []
    for pc_spec in points_specifiques_qs:
        points_specifiques.append({
            'id': str(pc_spec.id),
            'lien_id': str(pc_spec.id),  # Pour compatibilité avec le JavaScript
            'point_controle_id': str(pc_spec.point_de_controle.id),
            'nom': pc_spec.point_de_controle.nom,
            'description': pc_spec.point_de_controle.description,
            'type_resultat': pc_spec.point_de_controle.type_resultat,
            'valeur_min': float(pc_spec.valeur_min_effective) if pc_spec.valeur_min_effective else None,
            'valeur_max': float(pc_spec.valeur_max_effective) if pc_spec.valeur_max_effective else None,
            'unite': pc_spec.point_de_controle.unite,
            'est_obligatoire': pc_spec.est_obligatoire,
            'ordre_affichage': pc_spec.ordre_affichage,
            'type_visite': pc_spec.get_type_visite_display(),
            'type_visite_code': pc_spec.type_visite,
            'remarques': pc_spec.remarques,
            'source': 'specifique',  # Marqueur pour identifier l'origine
        })

    # 3. Combiner et retourner les résultats
    return Response({
        'success': True,
        'equipement': {
            'id': str(equipement.id),
            'nom': equipement.nom,
            'type': equipement.type_equipement.nom_type if equipement.type_equipement else 'N/A',
            'code': equipement.code_equipement,
        },
        'type_visite': type_visite,
        'type_visite_display': 'Visite Routinière' if type_visite == 'ROUTINIERE' else 'Visite Annuelle',
        'points_communs': points_communs,
        'points_specifiques': points_specifiques,
        'total_points': len(points_communs) + len(points_specifiques),
        'ordre_affichage_info': 'Les points communs sont affichés en premier, suivis des points spécifiques'
    })


@api_view(['GET', 'POST', 'DELETE'])
@permission_classes([permissions.AllowAny])
def api_points_controle_specifiques(request):
    """
    API pour gérer les points de controle spécifiques d'un équipement.

    GET: Liste les points de controle spécifiques d'un équipement
         Paramètres: equipement_id (requis)

    POST: Ajoute un point de controle spécifique Ã  un équipement
          Body JSON: {
              equipement_id, point_de_controle_id, type_visite,
              valeur_min_specifique (optionnel), valeur_max_specifique (optionnel),
              est_obligatoire, ordre_affichage, remarques (optionnel)
          }

    DELETE: Supprime un point de controle spécifique
            Paramètre: id (UUID du PointDeControleSpecifique)
    """

    if request.method == 'GET':
        equipement_id = request.GET.get('equipement_id')

        if not equipement_id:
            return Response({
                'error': 'equipement_id est requis'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            equipement = EquipementConstitutif.objects.get(id=equipement_id)
        except EquipementConstitutif.DoesNotExist:
            return Response({
                'error': 'Equipement non trouvé'
            }, status=status.HTTP_404_NOT_FOUND)

        # Récupérer tous les points de controle spécifiques de cet équipement
        points_specifiques = PointDeControleSpecifique.objects.filter(
            equipement=equipement
        ).select_related('point_de_controle').order_by('type_visite', 'ordre_affichage')

        data = []
        for pc_spec in points_specifiques:
            data.append({
                'id': str(pc_spec.id),
                'point_controle': {
                    'id': str(pc_spec.point_de_controle.id),
                    'nom': pc_spec.point_de_controle.nom,
                    'description': pc_spec.point_de_controle.description,
                    'type_resultat': pc_spec.point_de_controle.type_resultat,
                    'valeur_min': float(pc_spec.point_de_controle.valeur_min) if pc_spec.point_de_controle.valeur_min else None,
                    'valeur_max': float(pc_spec.point_de_controle.valeur_max) if pc_spec.point_de_controle.valeur_max else None,
                    'unite': pc_spec.point_de_controle.unite,
                },
                'type_visite': pc_spec.type_visite,
                'type_visite_display': pc_spec.get_type_visite_display(),
                'valeur_min_specifique': float(pc_spec.valeur_min_specifique) if pc_spec.valeur_min_specifique else None,
                'valeur_max_specifique': float(pc_spec.valeur_max_specifique) if pc_spec.valeur_max_specifique else None,
                'valeur_min_effective': float(pc_spec.valeur_min_effective) if pc_spec.valeur_min_effective else None,
                'valeur_max_effective': float(pc_spec.valeur_max_effective) if pc_spec.valeur_max_effective else None,
                'est_obligatoire': pc_spec.est_obligatoire,
                'ordre_affichage': pc_spec.ordre_affichage,
                'remarques': pc_spec.remarques,
            })

        return Response({
            'success': True,
            'equipement': {
                'id': str(equipement.id),
                'nom': equipement.nom,
            },
            'points_specifiques': data
        })

    elif request.method == 'POST':
        try:
            equipement_id = request.data.get('equipement_id')
            point_de_controle_id = request.data.get('point_de_controle_id')
            type_visite = request.data.get('type_visite', 'ROUTINIERE')

            if not equipement_id or not point_de_controle_id:
                return Response({
                    'error': 'equipement_id et point_de_controle_id sont requis'
                }, status=status.HTTP_400_BAD_REQUEST)

            equipement = EquipementConstitutif.objects.get(id=equipement_id)
            point_de_controle = PointDeControle.objects.get(id=point_de_controle_id)

            # Créer le point de controle spécifique
            pc_spec = PointDeControleSpecifique.objects.create(
                equipement=equipement,
                point_de_controle=point_de_controle,
                type_visite=type_visite,
                valeur_min_specifique=request.data.get('valeur_min_specifique'),
                valeur_max_specifique=request.data.get('valeur_max_specifique'),
                est_obligatoire=request.data.get('est_obligatoire', True),
                ordre_affichage=request.data.get('ordre_affichage', 1),
                remarques=request.data.get('remarques', ''),
            )

            return Response({
                'success': True,
                'message': 'Point de controle spécifique ajouté',
                'id': str(pc_spec.id)
            }, status=status.HTTP_201_CREATED)

        except EquipementConstitutif.DoesNotExist:
            return Response({
                'error': 'Equipement non trouvé'
            }, status=status.HTTP_404_NOT_FOUND)
        except PointDeControle.DoesNotExist:
            return Response({
                'error': 'Point de controle non trouvé'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        pc_spec_id = request.data.get('id')

        if not pc_spec_id:
            return Response({
                'error': 'id est requis'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            pc_spec = PointDeControleSpecifique.objects.get(id=pc_spec_id)
            pc_spec.delete()

            return Response({
                'success': True,
                'message': 'Point de controle spécifique supprimé'
            })

        except PointDeControleSpecifique.DoesNotExist:
            return Response({
                'error': 'Point de controle spécifique non trouvé'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def api_composants_type_equipement(request, type_equipement_id):
    """
    API pour récupérer les composants d'un type d'équipement.
    """
    try:
        from apps.infrastructure.models import TypeEquipement
        from apps.inspections.models import ComposantTypeEquipement

        type_eq = TypeEquipement.objects.get(id=type_equipement_id)
        composants = ComposantTypeEquipement.objects.filter(
            type_equipement=type_eq
        ).order_by('ordre_affichage', 'nom_composant')

        data = []
        for comp in composants:
            data.append({
                'id': str(comp.id),
                'nom': comp.nom_composant,
                'description': comp.description,
                'type_equipement': type_eq.nom_type,
                'est_obligatoire': comp.est_obligatoire
            })

        return Response(data)

    except TypeEquipement.DoesNotExist:
        return Response({
            'error': 'Type d\'équipement non trouvé'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def api_create_point_controle_composant(request):
    """
    API pour créer un lien PointDeControleComposant (ajouter un point de controle commun).
    """
    try:
        from apps.inspections.models import ComposantTypeEquipement

        composant_id = request.data.get('composant_equipement_id')
        point_id = request.data.get('point_de_controle_id')
        type_visite = request.data.get('type_visite', 'ROUTINIERE')
        est_obligatoire = request.data.get('est_obligatoire', True)
        ordre_affichage = request.data.get('ordre_affichage', 1)

        if not composant_id or not point_id:
            return Response({
                'error': 'composant_equipement_id et point_de_controle_id sont requis'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Vérifier que le composant existe
        try:
            composant = ComposantTypeEquipement.objects.get(id=composant_id)
        except ComposantTypeEquipement.DoesNotExist:
            return Response({
                'error': 'Composant non trouvé'
            }, status=status.HTTP_404_NOT_FOUND)

        # Vérifier que le point de controle existe
        try:
            point = PointDeControle.objects.get(id=point_id)
        except PointDeControle.DoesNotExist:
            return Response({
                'error': 'Point de controle non trouvé'
            }, status=status.HTTP_404_NOT_FOUND)

        # Vérifier si le lien existe déjÃ 
        existing = PointDeControleComposant.objects.filter(
            composant_equipement=composant,
            point_de_controle=point,
            type_visite=type_visite
        ).exists()

        if existing:
            return Response({
                'error': 'Ce point de controle est déjÃ  associé Ã  ce composant pour ce type de visite'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Créer le lien
        lien = PointDeControleComposant.objects.create(
            composant_equipement=composant,
            point_de_controle=point,
            type_visite=type_visite,
            est_obligatoire=est_obligatoire,
            ordre_affichage=ordre_affichage
        )

        return Response({
            'success': True,
            'message': 'Point de controle ajouté avec succès',
            'id': str(lien.id)
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([permissions.AllowAny])
def api_delete_point_controle_composant(request, lien_id):
    """
    API pour supprimer un lien PointDeControleComposant (retirer un point de controle commun).
    """
    try:
        lien = PointDeControleComposant.objects.get(id=lien_id)
        lien.delete()

        return Response({
            'success': True,
            'message': 'Point de controle supprimé avec succès'
        })

    except PointDeControleComposant.DoesNotExist:
        return Response({
            'error': 'Lien non trouvé'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH'])
@permission_classes([permissions.AllowAny])
def api_update_type_visite_point_controle_composant(request, lien_id):
    """
    API pour modifier les attributs d'un point de controle commun (PointDeControleComposant).
    Champs modifiables : type_visite, ordre_affichage, est_obligatoire
    """
    try:
        # Récupérer le lien
        lien = PointDeControleComposant.objects.get(id=lien_id)

        # Modifier type_visite si fourni
        type_visite = request.data.get('type_visite')
        if type_visite:
            if type_visite not in ['ROUTINIERE', 'ANNUELLE']:
                return Response({
                    'error': 'type_visite doit être "ROUTINIERE" ou "ANNUELLE"'
                }, status=status.HTTP_400_BAD_REQUEST)
            lien.type_visite = type_visite

        # Modifier ordre_affichage si fourni
        ordre_affichage = request.data.get('ordre_affichage')
        if ordre_affichage is not None:
            try:
                lien.ordre_affichage = int(ordre_affichage)
            except (ValueError, TypeError):
                return Response({
                    'error': 'ordre_affichage doit être un nombre entier'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Modifier est_obligatoire si fourni
        est_obligatoire = request.data.get('est_obligatoire')
        if est_obligatoire is not None:
            lien.est_obligatoire = est_obligatoire in [True, 'true', 'True', 1, '1']

        lien.save()

        return Response({
            'success': True,
            'message': 'Point de controle mis Ã  jour',
            'data': {
                'type_visite': lien.get_type_visite_display(),
                'ordre_affichage': lien.ordre_affichage,
                'est_obligatoire': lien.est_obligatoire
            }
        })

    except PointDeControleComposant.DoesNotExist:
        return Response({
            'error': 'Lien non trouvé'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)

# ============ APIs GESTION COMPOSANTS TYPE POINT D'EAU ============

@api_view(['GET'])
@permission_classes([AllowAny])
def api_composants_type_point_eau(request, type_point_eau_id):
    """
    Récupère les composants d'un type de point d'eau avec leurs points de controle.
    """
    try:
        from apps.billing.models import TypePointEau

        type_pe = TypePointEau.objects.get(id=type_point_eau_id)

        # Récupérer les composants de ce type de point d'eau
        composants = ComposantTypePointEau.objects.filter(
            type_point_eau=type_pe
        ).order_by('ordre_affichage', 'nom_composant')

        composants_data = []
        for comp in composants:
            # Récupérer les points de controle liés Ã  ce composant
            points_controle = PointDeControleComposant.objects.filter(
                composant_point_eau=comp
            ).select_related('point_de_controle').order_by('ordre_affichage')

            pc_data = [{
                'id': str(pc.id),
                'point_controle_id': str(pc.point_de_controle.id),
                'nom': pc.point_de_controle.nom,
                'type_resultat': pc.point_de_controle.type_resultat,
                'type_visite': pc.type_visite,
                'ordre_affichage': pc.ordre_affichage,
                'est_obligatoire': pc.est_obligatoire
            } for pc in points_controle]

            composants_data.append({
                'id': str(comp.id),
                'nom': comp.nom_composant,
                'description': comp.description or '',
                'ordre_affichage': comp.ordre_affichage,
                'points_controle': pc_data,
                'nb_points_controle': len(pc_data)
            })

        return Response({
            'success': True,
            'type_point_eau': {
                'id': str(type_pe.id),
                'nom': type_pe.nom_type
            },
            'composants': composants_data,
            'total': len(composants_data)
        })

    except TypePointEau.DoesNotExist:
        return Response({
            'error': 'Type de point d\'eau non trouvé'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def api_creer_composant_type_point_eau(request):
    """
    Crée un nouveau composant pour un type de point d'eau.
    """
    try:
        from apps.billing.models import TypePointEau

        type_point_eau_id = request.data.get('type_point_eau_id')
        nom = request.data.get('nom')
        description = request.data.get('description', '')
        ordre_affichage = request.data.get('ordre_affichage', 1)

        if not type_point_eau_id or not nom:
            return Response({
                'error': 'type_point_eau_id et nom sont requis'
            }, status=status.HTTP_400_BAD_REQUEST)

        type_pe = TypePointEau.objects.get(id=type_point_eau_id)

        composant = ComposantTypePointEau.objects.create(
            type_point_eau=type_pe,
            nom=nom,
            description=description,
            ordre_affichage=ordre_affichage
        )

        return Response({
            'success': True,
            'message': 'Composant créé avec succès',
            'composant': {
                'id': str(composant.id),
                'nom': composant.nom,
                'description': composant.description,
                'ordre_affichage': composant.ordre_affichage
            }
        }, status=status.HTTP_201_CREATED)

    except TypePointEau.DoesNotExist:
        return Response({
            'error': 'Type de point d\'eau non trouvé'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT', 'DELETE'])
@permission_classes([AllowAny])
def api_modifier_composant_type_point_eau(request, composant_id):
    """
    Modifie ou supprime un composant de type de point d'eau.
    """
    try:
        composant = ComposantTypePointEau.objects.get(id=composant_id)

        if request.method == 'DELETE':
            composant.delete()
            return Response({
                'success': True,
                'message': 'Composant supprimé avec succès'
            })

        # PUT - Modification
        nom = request.data.get('nom')
        if nom:
            composant.nom = nom

        description = request.data.get('description')
        if description is not None:
            composant.description = description

        ordre_affichage = request.data.get('ordre_affichage')
        if ordre_affichage is not None:
            composant.ordre_affichage = ordre_affichage

        composant.save()

        return Response({
            'success': True,
            'message': 'Composant mis Ã  jour avec succès',
            'composant': {
                'id': str(composant.id),
                'nom': composant.nom,
                'description': composant.description,
                'ordre_affichage': composant.ordre_affichage
            }
        })

    except ComposantTypePointEau.DoesNotExist:
        return Response({
            'error': 'Composant non trouvé'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def api_lier_point_controle_composant_pe(request):
    """
    Lie un point de controle Ã  un composant de type de point d'eau.
    """
    try:
        composant_id = request.data.get('composant_id')
        point_controle_id = request.data.get('point_controle_id')
        type_visite = request.data.get('type_visite', 'ROUTINIERE')
        ordre_affichage = request.data.get('ordre_affichage', 1)
        est_obligatoire = request.data.get('est_obligatoire', True)

        if not composant_id or not point_controle_id:
            return Response({
                'error': 'composant_id et point_controle_id sont requis'
            }, status=status.HTTP_400_BAD_REQUEST)

        composant = ComposantTypePointEau.objects.get(id=composant_id)
        point_controle = PointDeControle.objects.get(id=point_controle_id)

        # Vérifier si le lien existe déjÃ 
        lien_existant = PointDeControleComposant.objects.filter(
            composant_point_eau=composant,
            point_de_controle=point_controle,
            type_visite=type_visite
        ).first()

        if lien_existant:
            return Response({
                'error': 'Ce point de controle est déjÃ  lié Ã  ce composant pour ce type de visite'
            }, status=status.HTTP_400_BAD_REQUEST)

        lien = PointDeControleComposant.objects.create(
            composant_point_eau=composant,
            point_de_controle=point_controle,
            type_visite=type_visite,
            ordre_affichage=ordre_affichage,
            est_obligatoire=est_obligatoire in [True, 'true', 'True', 1, '1']
        )

        return Response({
            'success': True,
            'message': 'Point de controle lié avec succès',
            'lien': {
                'id': str(lien.id),
                'point_controle': point_controle.nom,
                'type_visite': lien.get_type_visite_display(),
                'ordre_affichage': lien.ordre_affichage,
                'est_obligatoire': lien.est_obligatoire
            }
        }, status=status.HTTP_201_CREATED)

    except ComposantTypePointEau.DoesNotExist:
        return Response({
            'error': 'Composant non trouvé'
        }, status=status.HTTP_404_NOT_FOUND)
    except PointDeControle.DoesNotExist:
        return Response({
            'error': 'Point de controle non trouvé'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


# ============ APIs POINTS DE CONTROLE SPECIFIQUES POINT D'EAU ============

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def api_points_controle_specifiques_point_eau(request, point_eau_id):
    """
    GET: Récupère les points de controle spécifiques d'un point d'eau.
    POST: Ajoute un point de controle spécifique Ã  un point d'eau.
    """
    try:
        from apps.billing.models import PointEau

        point_eau = PointEau.objects.get(id=point_eau_id)

        if request.method == 'GET':
            type_visite = request.query_params.get('type_visite')

            queryset = PointDeControleSpecifiquePointEau.objects.filter(
                point_eau=point_eau
            ).select_related('point_de_controle')

            if type_visite:
                queryset = queryset.filter(type_visite=type_visite)

            queryset = queryset.order_by('ordre_affichage', 'point_de_controle__nom')

            points_data = [{
                'id': str(p.id),
                'point_controle_id': str(p.point_de_controle.id),
                'nom': p.point_de_controle.nom,
                'type_controle': normalize_type_controle(p.point_de_controle.type_resultat),
                'type_visite': p.type_visite,
                'type_visite_display': p.get_type_visite_display(),
                'valeur_min': float(p.valeur_min_specifique) if p.valeur_min_specifique else None,
                'valeur_max': float(p.valeur_max_specifique) if p.valeur_max_specifique else None,
                'est_obligatoire': p.est_obligatoire,
                'ordre_affichage': p.ordre_affichage,
                'remarques': p.remarques
            } for p in queryset]

            points_type = []
            if point_eau.type_point_eau:
                composants = ComposantTypePointEau.objects.filter(
                    type_point_eau=point_eau.type_point_eau
                ).order_by('ordre_affichage', 'nom_composant')

                for comp in composants:
                    points_controle = PointDeControleComposant.objects.filter(
                        composant_point_eau=comp
                    ).select_related('point_de_controle').order_by('ordre_affichage')

                    for pc in points_controle:
                        points_type.append({
                            'id': str(pc.id),
                            'nom': pc.point_de_controle.nom,
                            'type_controle': normalize_type_controle(pc.point_de_controle.type_resultat),
                            'obligatoire': pc.est_obligatoire,
                            'type_visite': pc.type_visite,
                            'composant': comp.nom_composant
                        })

            return Response({
                'success': True,
                'point_eau': {
                    'id': str(point_eau.id),
                    'nom': point_eau.nomabonne or f'Point d\'eau {point_eau.idxls}'
                },
                'points_controle': points_data,
                'points_specifiques': points_data,
                'points_type': points_type,
                'total': len(points_data)
            })

        # POST - Ajouter un point de controle spécifique
        point_controle_id = request.data.get('point_controle_id')
        type_visite = request.data.get('type_visite', 'ROUTINIERE')
        valeur_min = request.data.get('valeur_min')
        valeur_max = request.data.get('valeur_max')
        est_obligatoire = request.data.get('est_obligatoire', True)
        ordre_affichage = request.data.get('ordre_affichage', 1)
        remarques = request.data.get('remarques', '')

        if not point_controle_id:
            return Response({
                'error': 'point_controle_id est requis'
            }, status=status.HTTP_400_BAD_REQUEST)

        point_controle = PointDeControle.objects.get(id=point_controle_id)

        # Vérifier si le lien existe déjÃ 
        if PointDeControleSpecifiquePointEau.objects.filter(
            point_eau=point_eau,
            point_de_controle=point_controle,
            type_visite=type_visite
        ).exists():
            return Response({
                'error': 'Ce point de controle spécifique existe déjÃ  pour ce point d\'eau et ce type de visite'
            }, status=status.HTTP_400_BAD_REQUEST)

        specifique = PointDeControleSpecifiquePointEau.objects.create(
            point_eau=point_eau,
            point_de_controle=point_controle,
            type_visite=type_visite,
            valeur_min_specifique=valeur_min,
            valeur_max_specifique=valeur_max,
            est_obligatoire=est_obligatoire in [True, 'true', 'True', 1, '1'],
            ordre_affichage=ordre_affichage,
            remarques=remarques
        )

        return Response({
            'success': True,
            'message': 'Point de controle spécifique ajouté avec succès',
            'point_controle_specifique': {
                'id': str(specifique.id),
                'nom': point_controle.nom,
                'type_visite': specifique.get_type_visite_display(),
                'est_obligatoire': specifique.est_obligatoire
            }
        }, status=status.HTTP_201_CREATED)

    except PointEau.DoesNotExist:
        return Response({
            'error': 'Point d\'eau non trouvé'
        }, status=status.HTTP_404_NOT_FOUND)
    except PointDeControle.DoesNotExist:
        return Response({
            'error': 'Point de controle non trouvé'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT', 'DELETE'])
@permission_classes([AllowAny])
def api_modifier_point_controle_specifique_point_eau(request, specifique_id):
    """
    Modifie ou supprime un point de controle spécifique d'un point d'eau.
    """
    try:
        specifique = PointDeControleSpecifiquePointEau.objects.get(id=specifique_id)

        if request.method == 'DELETE':
            specifique.delete()
            return Response({
                'success': True,
                'message': 'Point de controle spécifique supprimé avec succès'
            })

        # PUT - Modification
        type_visite = request.data.get('type_visite')
        if type_visite:
            specifique.type_visite = type_visite

        valeur_min = request.data.get('valeur_min')
        if valeur_min is not None:
            specifique.valeur_min_specifique = valeur_min if valeur_min != '' else None

        valeur_max = request.data.get('valeur_max')
        if valeur_max is not None:
            specifique.valeur_max_specifique = valeur_max if valeur_max != '' else None

        est_obligatoire = request.data.get('est_obligatoire')
        if est_obligatoire is not None:
            specifique.est_obligatoire = est_obligatoire in [True, 'true', 'True', 1, '1']

        ordre_affichage = request.data.get('ordre_affichage')
        if ordre_affichage is not None:
            specifique.ordre_affichage = ordre_affichage

        remarques = request.data.get('remarques')
        if remarques is not None:
            specifique.remarques = remarques

        specifique.save()

        return Response({
            'success': True,
            'message': 'Point de controle spécifique mis Ã  jour avec succès',
            'data': {
                'id': str(specifique.id),
                'type_visite': specifique.get_type_visite_display(),
                'valeur_min': float(specifique.valeur_min_specifique) if specifique.valeur_min_specifique else None,
                'valeur_max': float(specifique.valeur_max_specifique) if specifique.valeur_max_specifique else None,
                'est_obligatoire': specifique.est_obligatoire,
                'ordre_affichage': specifique.ordre_affichage
            }
        })

    except PointDeControleSpecifiquePointEau.DoesNotExist:
        return Response({
            'error': 'Point de controle spécifique non trouvé'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


# ============ APIs GESTION NON-CONFORMITES ============

