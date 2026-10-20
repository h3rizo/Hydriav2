from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.conf import settings
from .models import (
    TypeOuvrage, MaintenanceTask, EquipementConstitutif, Incident,
    PointControleInfra, InspectionInfra, ResultatControleInfra
)
from apps.organization.models import Ouvrage
from .serializers import (
    TypeOuvrageSerializer, OuvrageSerializer, MaintenanceTaskSerializer,
    EquipementConstitutifSerializer, IncidentSerializer,
    PointControleInfraSerializer, InspectionInfraSerializer, ResultatControleInfraSerializer
)


class BaseHierarchicalViewSet(viewsets.ModelViewSet):
    """
    Classe de base pour tous les ViewSets avec filtrage hiérarchique.
    Implémente la logique commune de filtrage selon le role de l'utilisateur.
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Filtre dynamiquement le queryset basé sur le role de l'utilisateur.
        - Les postes standards voient les données de leur base.
        - Les postes Ã  privilèges voient les données de leur organisation.
        """
        user = self.request.user

        if not user.is_authenticated:
            return self.get_base_queryset().none()

        # Vérification si l'utilisateur a un profil employé
        if not hasattr(user, 'employee_profile') or not user.employee_profile:
            # Si pas de profil employé, limiter l'accès (par défaut, accès restreint)
            return self.get_base_queryset().none()

        profile = user.employee_profile

        # Si le poste de l'utilisateur est dans la liste des roles Ã  privilèges
        if profile.poste and profile.poste.poste_name in settings.ROLES_NIVEAU_ORGANISATION:
            # On filtre par l'organisation de l'utilisateur
            return self.filter_by_organization(profile.organization)
        else:
            # Sinon, on applique le filtrage standard par base
            return self.filter_by_base(profile.base)

    def get_base_queryset(self):
        """Retourne le queryset de base pour ce ViewSet. Ã€ surcharger dans les sous-classes."""
        return self.queryset

    def filter_by_organization(self, organization):
        """Filtre les données par organisation. Ã€ surcharger dans les sous-classes."""
        raise NotImplementedError("Cette méthode doitêtre implémentée dans les sous-classes.")

    def filter_by_base(self, base):
        """Filtre les données par base. Ã€ surcharger dans les sous-classes."""
        raise NotImplementedError("Cette méthode doitêtre implémentée dans les sous-classes.")


class TypeOuvrageViewSet(BaseHierarchicalViewSet):
    serializer_class = TypeOuvrageSerializer
    queryset = TypeOuvrage.objects.all()

    def get_base_queryset(self):
        return TypeOuvrage.objects.all()

    def filter_by_organization(self, organization):
        # Les types d'ouvrages sont globaux, pas de filtrage nécessaire
        return TypeOuvrage.objects.all()

    def filter_by_base(self, base):
        # Les types d'ouvrages sont globaux, pas de filtrage nécessaire
        return TypeOuvrage.objects.all()


class OuvrageViewSet(BaseHierarchicalViewSet):
    serializer_class = OuvrageSerializer
    queryset = Ouvrage.objects.all()

    def get_base_queryset(self):
        return Ouvrage.objects.all()

    def filter_by_organization(self, organization):
        # Filtrage par organisation via la relation ForeignKey
        return Ouvrage.objects.filter(organisation=organization)

    def filter_by_base(self, base):
        # Pour filtrer par base, nous devons utiliser l'organisation de la base
        # car le modèle Ouvrage n'a pas de relation directe avec Base
        return Ouvrage.objects.filter(organisation=base.organization)

    def perform_create(self, serializer):
        """
        Assigne l'organisation et, pour un employé standard, force son organisation.
        Pour un directeur, l'organisation peutêtre choisie via validation.
        """
        user = self.request.user
        if not hasattr(user, 'employee_profile') or not user.employee_profile:
            # Si pas de profil employé, rejeter la création
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Utilisateur non associé Ã  un profil employé.")
        
        profile = user.employee_profile

        if profile.poste and profile.poste.poste_name in settings.ROLES_NIVEAU_ORGANISATION:
            # Le directeur peut créer pour différentes organisations dans sa hiérarchie
            # L'organisation sera validée par le serializer
            serializer.save()
        else:
            # L'employé standard ne peut créer que pour son organisation
            serializer.save(organisation=profile.organization)


class MaintenanceTaskViewSet(BaseHierarchicalViewSet):
    serializer_class = MaintenanceTaskSerializer
    queryset = MaintenanceTask.objects.all()

    def get_base_queryset(self):
        return MaintenanceTask.objects.select_related('infrastructure', 'assigned_employee')

    def filter_by_organization(self, organization):
        # Filtrage par organisation via la relation avec infrastructure
        return MaintenanceTask.objects.filter(infrastructure__organisation=organization)

    def filter_by_base(self, base):
        # Filtrage par base via l'organisation de la base
        return MaintenanceTask.objects.filter(infrastructure__organisation=base.organization)

    def perform_create(self, serializer):
        """
        Assigne l'employé responsable de la tÃ¢che.
        """
        user = self.request.user
        if not hasattr(user, 'employee_profile') or not user.employee_profile:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Utilisateur non associé Ã  un profil employé.")
        
        serializer.save(assigned_employee=user.employee_profile)


class EquipementConstitutifViewSet(BaseHierarchicalViewSet):
    serializer_class = EquipementConstitutifSerializer
    queryset = EquipementConstitutif.objects.all()

    def get_base_queryset(self):
        return EquipementConstitutif.objects.select_related('ouvrage', 'responsable')

    def filter_by_organization(self, organization):
        # Filtrage par organisation via la relation avec ouvrage
        return EquipementConstitutif.objects.filter(ouvrage__organisation=organization)

    def filter_by_base(self, base):
        # Filtrage par base via l'organisation de la base
        return EquipementConstitutif.objects.filter(ouvrage__organisation=base.organization)

    def perform_create(self, serializer):
        """
        Assigne le responsable de l'équipement.
        """
        user = self.request.user
        if not hasattr(user, 'employee_profile') or not user.employee_profile:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Utilisateur non associé Ã  un profil employé.")
        
        serializer.save(responsable=user.employee_profile)


class IncidentViewSet(BaseHierarchicalViewSet):
    serializer_class = IncidentSerializer
    queryset = Incident.objects.all()

    def get_base_queryset(self):
        return Incident.objects.select_related('infrastructure', 'reported_by', 'assigned_to')

    def filter_by_organization(self, organization):
        # Filtrage par organisation via la relation avec infrastructure
        return Incident.objects.filter(infrastructure__organisation=organization)

    def filter_by_base(self, base):
        # Filtrage par base via l'organisation de la base
        return Incident.objects.filter(infrastructure__organisation=base.organization)

    def perform_create(self, serializer):
        """
        Assigne l'utilisateur qui rapporte l'incident.
        """
        user = self.request.user
        if not hasattr(user, 'employee_profile') or not user.employee_profile:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Utilisateur non associé Ã  un profil employé.")
        
        profile = user.employee_profile
        
        # L'incident est assigné Ã  l'utilisateur actuel par défaut
        serializer.save(
            reported_by=profile,
            assigned_to=profile  # Par défaut, assigné Ã  celui qui le rapporte
        )


class PointControleInfraViewSet(BaseHierarchicalViewSet):
    serializer_class = PointControleInfraSerializer
    queryset = PointControleInfra.objects.all()

    def get_base_queryset(self):
        return PointControleInfra.objects.select_related('equipement__ouvrage')

    def filter_by_organization(self, organization):
        # Filtrage par organisation via la relation avec équipement > ouvrage
        return PointControleInfra.objects.filter(equipement__ouvrage__organisation=organization)

    def filter_by_base(self, base):
        # Filtrage par base via l'organisation de la base
        return PointControleInfra.objects.filter(equipement__ouvrage__organisation=base.organization)


class InspectionInfraViewSet(BaseHierarchicalViewSet):
    serializer_class = InspectionInfraSerializer
    queryset = InspectionInfra.objects.all()

    def get_base_queryset(self):
        return InspectionInfra.objects.select_related('equipement__ouvrage', 'inspecteur')

    def filter_by_organization(self, organization):
        # Filtrage par organisation via la relation avec équipement > ouvrage
        return InspectionInfra.objects.filter(equipement__ouvrage__organisation=organization)

    def filter_by_base(self, base):
        # Filtrage par base via l'organisation de la base
        return InspectionInfra.objects.filter(equipement__ouvrage__organisation=base.organization)

    def perform_create(self, serializer):
        """
        Assigne l'inspecteur Ã  l'utilisateur actuel.
        """
        user = self.request.user
        if not hasattr(user, 'employee_profile') or not user.employee_profile:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Utilisateur non associé Ã  un profil employé.")

        # Assigner l'inspecteur Ã  l'utilisateur actuel
        inspection = serializer.save(inspecteur=user.employee_profile)

        # Créer automatiquement les résultats de controle pour tous les points de controle actifs
        points_controle = inspection.equipement.points_controle_infra.filter(is_active=True)
        for point in points_controle:
            ResultatControleInfra.objects.create(
                inspection=inspection,
                point_controle=point,
                statut='en_attente'
            )


class ResultatControleInfraViewSet(BaseHierarchicalViewSet):
    serializer_class = ResultatControleInfraSerializer
    queryset = ResultatControleInfra.objects.all()

    def get_base_queryset(self):
        return ResultatControleInfra.objects.select_related(
            'inspection__equipement__ouvrage',
            'point_controle',
            'photo_resultat'
        )

    def filter_by_organization(self, organization):
        # Filtrage par organisation via la relation avec inspection > équipement > ouvrage
        return ResultatControleInfra.objects.filter(
            inspection__equipement__ouvrage__organisation=organization
        )

    def filter_by_base(self, base):
        # Filtrage par base via l'organisation de la base
        return ResultatControleInfra.objects.filter(
            inspection__equipement__ouvrage__organisation=base.organization
        )

    @action(detail=True, methods=['post'])
    def upload_photo(self, request, pk=None):
        """
        Endpoint pour uploader une photo de résultat
        """
        resultat = self.get_object()

        if 'photo_resultat' not in request.FILES:
            return Response({'error': 'Aucune photo fournie'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.filemanager.models import FileUpload

        # Créer le fichier dans le système de gestion de fichiers
        photo_file = request.FILES['photo_resultat']
        file_upload = FileUpload.objects.create(
            file=photo_file,
            original_name=photo_file.name,
            uploaded_by=request.user.employee_profile if hasattr(request.user, 'employee_profile') else None,
            file_type='image',
            description=f"Photo de controle - {resultat.point_controle.nom}"
        )

        # Associer la photo au résultat
        resultat.photo_resultat = file_upload
        resultat.save()

        return Response({
            'message': 'Photo uploadée avec succès',
            'photo_url': request.build_absolute_uri(file_upload.file.url)
        }, status=status.HTTP_200_OK)


# Vues Django Templates
def inspection_detail(request, inspection_id):
    """
    Vue pour afficher le détail d'une inspection avec navigation par points de controle
    """
    inspection = get_object_or_404(InspectionInfra, id=inspection_id)

    # Vérifier les permissions
    if not request.user.is_authenticated:
        return render(request, 'auth/login.html')

    if not hasattr(request.user, 'employee_profile'):
        return render(request, 'errors/403.html')

    profile = request.user.employee_profile

    # Vérifier l'accès selon les roles
    # Note: Sans champ organisation sur ouvrage, vérification désactivée temporairement
    # Ã€ rétablir via modalitegestion si nécessaire

    return render(request, 'infrastructure/inspection_detail.html', {
        'inspection': inspection
    })


def inspection_summary(request, inspection_id):
    """
    Vue pour afficher le résumé final d'une inspection
    """
    inspection = get_object_or_404(InspectionInfra, id=inspection_id)

    # Vérifier les permissions (mÃªme logique que inspection_detail)
    if not request.user.is_authenticated:
        return render(request, 'auth/login.html')

    if not hasattr(request.user, 'employee_profile'):
        return render(request, 'errors/403.html')

    profile = request.user.employee_profile

    # Note: Sans champ organisation sur ouvrage, vérification désactivée temporairement
    # Ã€ rétablir via modalitegestion si nécessaire

    # Marquer l'inspection comme terminée si tous les points sont complétés
    if inspection.progression == 100 and inspection.statut == 'en_cours':
        inspection.statut = 'terminee'
        inspection.date_fin = timezone.now()
        inspection.save()

    return render(request, 'infrastructure/inspection_summary.html', {
        'inspection': inspection
    })


def consolidated_equipements(request):
    """Page consolidee plate des equipements, triee par recence."""
    from django.core.paginator import Paginator
    from django.db.models import Count, Q
    from django.db.models.functions import Coalesce
    from datetime import date
    from django.utils import timezone as dj_timezone
    from apps.employees.permissions import filter_queryset_by_permissions
    from apps.employees.models import Employe, EmployeOuvrages, HierarchieEmploye
    from apps.billing.models import PointEau
    from apps.geography.models import Region, District, Commune
    from .models import EquipementConstitutif, TypeEquipement

    today = date.today()
    employe_filter = request.GET.get('employe', 'all').strip()
    print_mode = request.GET.get('print', '') == '1'
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', 'all').strip()
    type_filter = request.GET.get('type_equipement', 'all').strip()
    missing_filter = request.GET.get('missing', 'all').strip()
    region_filter = request.GET.get('region', 'all').strip() or 'all'
    district_filter = request.GET.get('district', 'all').strip() or 'all'
    commune_filter = request.GET.get('commune', 'all').strip() or 'all'
    ouvrage_filter = request.GET.get('ouvrage', 'all').strip() or 'all'
    search_columns = request.GET.getlist('search_columns') or ['ouvrage', 'equipement']
    result_parameters = {
        'load', 'page', 'search', 'search_columns', 'employe', 'status',
        'type_equipement', 'missing', 'print',
        'region', 'district', 'commune', 'ouvrage',
    }
    results_loaded = print_mode or any(
        parameter in request.GET for parameter in result_parameters
    )

    # Build employes_grouped for dropdown
    active_responsibilities = EmployeOuvrages.objects.filter(
        employe__date_debauchage__isnull=True,
        date_debut__lte=today,
    ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=today))
    employes_qs = Employe.objects.filter(
        date_debauchage__isnull=True,
        id__in=active_responsibilities.values('employe_id'),
    ).select_related('base', 'poste').order_by('base__nom_base', 'poste__ordre_affichage', 'poste__nom_poste', 'surnom', 'nom')
    _base_dict = {}
    for emp in employes_qs:
        base_nom = emp.base.nom_base if emp.base else 'Sans base'
        poste_nom = emp.poste.nom_poste if emp.poste else 'Sans poste'
        if base_nom not in _base_dict:
            _base_dict[base_nom] = {}
        if poste_nom not in _base_dict[base_nom]:
            _base_dict[base_nom][poste_nom] = []
        _base_dict[base_nom][poste_nom].append(emp)
    employes_grouped = []
    for base_nom, postes in _base_dict.items():
        base_group = {'base': base_nom, 'postes': []}
        for poste_nom, emps in postes.items():
            base_group['postes'].append({'poste': poste_nom, 'employes': emps})
        employes_grouped.append(base_group)

    equipements = EquipementConstitutif.objects.select_related(
        'ouvrage',
        'type_equipement',
        'updated_by'
    ).annotate(
        recent_activity=Coalesce('updated_at', 'created_at', 'date_installation')
    ).order_by(
        '-recent_activity',
        '-date_installation',
        '-id'
    )

    equipements = filter_queryset_by_permissions(equipements, request.user)
    equipements_scope = equipements
    types_equipement = TypeEquipement.objects.filter(
        id__in=equipements_scope.values('type_equipement_id')
    ).order_by('nom_type')

    # Listes des filtres géographiques, limitées aux ouvrages visibles par l'utilisateur
    # (Ouvrage -> PointEau -> Parcelle -> Village -> Fokontany -> Commune -> District -> Région)
    geo_prefix = 'parcelle__village__fokontany__commune'
    scope_ouvrage_ids = equipements_scope.order_by().values('ouvrage_id')
    geo_points = PointEau.objects.filter(ouvrage_id__in=scope_ouvrage_ids).order_by()
    regions = Region.objects.filter(
        id__in=geo_points.values(f'{geo_prefix}__district__region_id')
    ).order_by('nom_region')
    districts = District.objects.filter(
        id__in=geo_points.values(f'{geo_prefix}__district_id')
    ).order_by('nom_district')
    if region_filter != 'all':
        districts = districts.filter(region_id=region_filter)
    communes = Commune.objects.filter(
        id__in=geo_points.values(f'{geo_prefix}_id')
    ).order_by('nom_commune')
    if district_filter != 'all':
        communes = communes.filter(district_id=district_filter)
    elif region_filter != 'all':
        communes = communes.filter(district__region_id=region_filter)
    ouvrages_geo = geo_points
    if region_filter != 'all':
        ouvrages_geo = ouvrages_geo.filter(**{f'{geo_prefix}__district__region_id': region_filter})
    if district_filter != 'all':
        ouvrages_geo = ouvrages_geo.filter(**{f'{geo_prefix}__district_id': district_filter})
    if commune_filter != 'all':
        ouvrages_geo = ouvrages_geo.filter(**{f'{geo_prefix}_id': commune_filter})
    ouvrages = Ouvrage.objects.filter(
        id__in=ouvrages_geo.values('ouvrage_id')
    ).order_by('nom_ouvrage')

    # Filtre géographique appliqué aux équipements (via les points d'eau de l'ouvrage)
    if any(f != 'all' for f in (region_filter, district_filter, commune_filter)):
        geo_filtered = PointEau.objects.order_by()
        if region_filter != 'all':
            geo_filtered = geo_filtered.filter(**{f'{geo_prefix}__district__region_id': region_filter})
        if district_filter != 'all':
            geo_filtered = geo_filtered.filter(**{f'{geo_prefix}__district_id': district_filter})
        if commune_filter != 'all':
            geo_filtered = geo_filtered.filter(**{f'{geo_prefix}_id': commune_filter})
        equipements = equipements.filter(ouvrage_id__in=geo_filtered.values('ouvrage_id'))
    if ouvrage_filter != 'all':
        equipements = equipements.filter(ouvrage_id=ouvrage_filter)

    # Employee filter with active subordinates
    if employe_filter and employe_filter != 'all':
        subordinate_ids = list(HierarchieEmploye.objects.filter(
            superieur_id=employe_filter,
            date_debut__lte=today,
        ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=today)
        ).values_list('employe_id', flat=True))
        employe_ids = [employe_filter] + subordinate_ids
        employee_ouvrage_ids = EmployeOuvrages.objects.filter(
            employe_id__in=employe_ids,
            employe__date_debauchage__isnull=True,
            date_debut__lte=today,
        ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=today)
        ).values('ouvrage_id')
        equipements = equipements.filter(ouvrage_id__in=employee_ouvrage_ids)

    if search_query:
        search_filters = Q()
        if 'equipement' in search_columns:
            search_filters |= Q(nom__icontains=search_query)
        if 'ouvrage' in search_columns:
            search_filters |= Q(ouvrage__nom_ouvrage__icontains=search_query)
        if search_filters:
            equipements = equipements.filter(search_filters).distinct()

    if status_filter and status_filter != 'all':
        equipements = equipements.filter(statut=status_filter)
    if type_filter and type_filter != 'all':
        equipements = equipements.filter(type_equipement_id=type_filter)
    if missing_filter == 'gps':
        equipements = equipements.filter(Q(latitude__isnull=True) | Q(longitude__isnull=True))
    elif missing_filter == 'photos':
        equipements = equipements.filter(
            Q(photos__isnull=True) | Q(photos__exact='[]') | Q(photos__exact='')
        )

    # Keep the landing request light. Filters remain available, while the
    # actual rows and aggregates are evaluated only after user confirmation.
    if not results_loaded:
        equipements = equipements.none()

    # Print mode: GPS-missing equipements only, grouped by Commune > Ouvrage
    if print_mode:
        equip_sans_gps = equipements.filter(
            Q(latitude__isnull=True) | Q(longitude__isnull=True)
        ).select_related('ouvrage', 'type_equipement').order_by('ouvrage__nom_ouvrage', 'nom')

        # Bulk geographic lookup to avoid N+1
        ouvrage_ids = list(equip_sans_gps.values_list('ouvrage_id', flat=True).distinct())
        pe_qs = PointEau.objects.filter(
            ouvrage_id__in=ouvrage_ids
        ).select_related('parcelle__village__fokontany__commune')
        ouvrage_geo = {}
        for pe in pe_qs:
            sid = str(pe.ouvrage_id)
            if sid not in ouvrage_geo:
                ouvrage_geo[sid] = pe

        commune_dict = {}
        print_index = 0
        total_ouvrages_set = set()
        for eq in equip_sans_gps:
            pe = ouvrage_geo.get(str(eq.ouvrage_id)) if eq.ouvrage_id else None
            commune_nom = 'Sans commune'
            localisation = ''
            if pe and pe.parcelle:
                parts = []
                if pe.parcelle.village:
                    parts.append(pe.parcelle.village.nom_village)
                    if pe.parcelle.village.fokontany:
                        parts.append(pe.parcelle.village.fokontany.nom_fokontany)
                        if pe.parcelle.village.fokontany.commune:
                            commune_nom = pe.parcelle.village.fokontany.commune.nom_commune
                localisation = ', '.join(parts)

            ouvrage_nom = eq.ouvrage.nom_ouvrage if eq.ouvrage else 'Sans ouvrage'
            type_nom = eq.type_equipement.nom_type if eq.type_equipement else '-'
            print_index += 1
            total_ouvrages_set.add(ouvrage_nom)

            if commune_nom not in commune_dict:
                commune_dict[commune_nom] = {}
            if ouvrage_nom not in commune_dict[commune_nom]:
                commune_dict[commune_nom][ouvrage_nom] = []
            commune_dict[commune_nom][ouvrage_nom].append({
                'print_index': print_index,
                'nom': eq.nom or '-',
                'type': type_nom,
                'ouvrage': ouvrage_nom,
                'localisation': localisation,
                'latitude': eq.latitude,
                'longitude': eq.longitude,
                'volume_m3': eq.volume_m3,
                'is_citerne': type_nom.lower() == 'citerne',
            })

        commune_groups = []
        for commune_nom, ouvrages in sorted(commune_dict.items()):
            commune_count = sum(len(v) for v in ouvrages.values())
            commune_groups.append({
                'nom_commune': commune_nom,
                'count': commune_count,
                'ouvrages': [
                    {'nom_ouvrage': ouvrage_nom, 'equipements': equips}
                    for ouvrage_nom, equips in sorted(ouvrages.items())
                ],
            })

        employe_label = 'Tous les employes'
        if employe_filter and employe_filter != 'all':
            selected_employe = Employe.objects.filter(id=employe_filter).first()
            if selected_employe:
                employe_label = selected_employe.nom_affichage if hasattr(selected_employe, 'nom_affichage') else (selected_employe.surnom or selected_employe.nom)

        return render(request, 'infrastructure/consolidated_equipements_print.html', {
            'commune_groups': commune_groups,
            'ouvrages_count': len(total_ouvrages_set),
            'equipements_count': print_index,
            'employe_label': employe_label,
            'commune_label': 'Toutes les communes',
            'generated_at': dj_timezone.now(),
        })

    # Normal mode
    total_equipements = equipements.count()
    equipements_avec_gps = equipements.filter(latitude__isnull=False, longitude__isnull=False).count()
    equipements_sans_gps = total_equipements - equipements_avec_gps
    equipements_avec_photos = equipements.filter(photos__isnull=False).exclude(photos__exact='[]').exclude(photos__exact='').count()
    equipements_sans_photos = total_equipements - equipements_avec_photos
    ouvrages_distincts = equipements.values('ouvrage').distinct().count()

    types_stats = equipements.values('type_equipement__nom_type').annotate(
        count=Count('id')
    ).order_by('-count')

    paginator = Paginator(equipements, 50)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    pagination_params = request.GET.copy()
    pagination_params.pop('page', None)
    pagination_query = pagination_params.urlencode()

    context = {
        'page_obj': page_obj,
        'equipements': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'missing_filter': missing_filter,
        'types_equipement': types_equipement,
        'types_equipement_form': TypeEquipement.objects.order_by('nom_type'),
        'employe_filter': employe_filter,
        'employes_grouped': employes_grouped,
        'region_filter': region_filter,
        'district_filter': district_filter,
        'commune_filter': commune_filter,
        'ouvrage_filter': ouvrage_filter,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'ouvrages': ouvrages,
        'total_equipements': total_equipements,
        'equipements_avec_gps': equipements_avec_gps,
        'equipements_sans_gps': equipements_sans_gps,
        'equipements_avec_photos': equipements_avec_photos,
        'equipements_sans_photos': equipements_sans_photos,
        'ouvrages_distincts': ouvrages_distincts,
        'search_columns': search_columns,
        'types_stats': types_stats,
        'current_employe_id': getattr(getattr(request.user, 'employe', None), 'id', ''),
        'results_loaded': results_loaded,
        'pagination_query': pagination_query,
    }

    return render(request, 'infrastructure/consolidated_equipements.html', context)
def update_equipement_api(request, equipement_id):
    """API pour mettre Ã  jour un équipement avec photos et GPS"""
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)

    try:
        equipement = EquipementConstitutif.objects.get(id=equipement_id)

        # Mise Ã  jour des champs
        if 'statut' in request.POST:
            equipement.statut = request.POST.get('statut')

        if 'latitude' in request.POST and request.POST.get('latitude'):
            equipement.latitude = float(request.POST.get('latitude'))

        if 'longitude' in request.POST and request.POST.get('longitude'):
            equipement.longitude = float(request.POST.get('longitude'))

        # Mise Ã  jour du champ est_dans_village
        equipement.est_dans_village = request.POST.get('est_dans_village') == 'on'

        if request.user.is_authenticated:
            equipement.updated_by = request.user

        # Gestion des photos (stockage en JSON)
        if request.FILES.getlist('photos'):
            import json
            import base64
            from datetime import datetime

            # Récupérer les photos existantes ou initialiser
            photos_data = equipement.photos if equipement.photos else []
            if not isinstance(photos_data, list):
                photos_data = []

            # Ajouter les nouvelles photos
            for photo in request.FILES.getlist('photos'):
                # Lire le contenu de l'image
                photo_content = photo.read()
                photo_base64 = base64.b64encode(photo_content).decode('utf-8')

                photo_info = {
                    'filename': photo.name,
                    'size': photo.size,
                    'content_type': photo.content_type,
                    'data': photo_base64,
                    'uploaded_at': datetime.now().isoformat(),
                }
                photos_data.append(photo_info)

            equipement.photos = photos_data

        equipement.save()

        return JsonResponse({
            'success': True,
            'message': 'Equipement mis Ã  jour avec succès',
            'equipement': {
                'id': str(equipement.id),
                'nom': equipement.nom,
                'statut': equipement.statut,
                'latitude': float(equipement.latitude) if equipement.latitude else None,
                'longitude': float(equipement.longitude) if equipement.longitude else None,
                'photos_count': len(equipement.photos) if equipement.photos else 0
            }
        })

    except EquipementConstitutif.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Equipement introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

