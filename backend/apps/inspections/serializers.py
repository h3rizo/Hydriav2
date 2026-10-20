from rest_framework import serializers
from django.contrib.auth.models import User
from django.utils import timezone
from apps.employees.models import Employe
from apps.infrastructure.models import EquipementConstitutif
from apps.organization.models import Ouvrage
from apps.filemanager.models import FileUpload
from apps.planning.models import Planning
from .models import (
    PointDeControle,
    Checklist,
    ChecklistPointControle,
    Visite,
    ResultatControle,
    InspectionPhoto
)


class PointDeControleSerializer(serializers.ModelSerializer):
    """Serializer pour les points de controle."""
    
    class Meta:
        model = PointDeControle
        fields = [
            'id', 'nom', 'description', 'type_resultat',
            'valeur_min', 'valeur_max', 'unite',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ChecklistPointControleSerializer(serializers.ModelSerializer):
    """Serializer pour les points de controle d'une checklist avec ordre."""
    point_de_controle = PointDeControleSerializer(read_only=True)
    
    class Meta:
        model = ChecklistPointControle
        fields = ['id', 'point_de_controle', 'ordre', 'est_obligatoire']


class EquipementConstitutifBasicSerializer(serializers.ModelSerializer):
    """Serializer basique pour les équipements constitutifs."""
    photo_reference_url = serializers.SerializerMethodField()
    
    class Meta:
        model = EquipementConstitutif
        fields = [
            'id', 'nom', 'description', 'type_equipement', 
            'code_equipement', 'statut', 'photo_reference_url'
        ]
    
    def get_photo_reference_url(self, obj):
        if obj.photo_reference:
            # Retourner l'URL de téléchargement du fichier
            return obj.photo_reference.get_download_url()
        return None


class ChecklistSerializer(serializers.ModelSerializer):
    """Serializer pour les checklists."""
    equipement_constitutif = EquipementConstitutifBasicSerializer(read_only=True)
    points_de_controle_detail = ChecklistPointControleSerializer(
        source='checklistpointcontrole_set', 
        many=True, 
        read_only=True
    )
    
    class Meta:
        model = Checklist
        fields = [
            'id', 'nom', 'equipement_constitutif', 'type_visite',
            'frequence_jours', 'is_active', 'points_de_controle_detail',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class OuvrageBasicSerializer(serializers.ModelSerializer):
    """Serializer basique pour les ouvrages."""

    commune_nom = serializers.SerializerMethodField()

    class Meta:
        model = Ouvrage
        fields = ['id', 'nom_ouvrage', 'type_ouvrage', 'annee_realisation', 'commune_nom']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        type_nom = ''
        if getattr(instance, 'type_ouvrage', None):
            type_nom = getattr(instance.type_ouvrage, 'nom_type_ouvrage', '') or ''
        # Alias pour compatibilité
        data['nom'] = data['nom_ouvrage']
        data['typeouvrage'] = {'nomtype': type_nom} if type_nom else None
        data['type_ouvrage_nom'] = type_nom
        data['anneerealisation'] = data['annee_realisation']
        data['infra_name'] = data['nom_ouvrage']
        data['infra_code'] = f"OUV-{instance.id}"
        data['infra_status'] = 'operationnel'
        data['commune'] = data.get('commune_nom')
        return data

    def get_commune_nom(self, instance):
        points = getattr(instance, 'points_eau_prefetched', None)
        if points is None:
            points_manager = getattr(instance, 'pointeau_set', None)
            if points_manager is None:
                points = []
            else:
                points = points_manager.all().select_related('parcelle__village__fokontany__commune')

        for point in points:
            parcelle = getattr(point, 'parcelle', None)
            if not parcelle:
                continue
            village = getattr(parcelle, 'village', None)
            fokontany = getattr(village, 'fokontany', None) if village else None
            commune = getattr(fokontany, 'commune', None) if fokontany else None
            if commune and getattr(commune, 'nom_commune', None):
                return commune.nom_commune

        return None

# Alias pour compatibilité
InfrastructureBasicSerializer = OuvrageBasicSerializer


class EmployeeBasicSerializer(serializers.ModelSerializer):
    """Serializer basique pour les employés."""

    class Meta:
        model = Employe
        fields = ['id', 'nom', 'prenom', 'nom_employe', 'poste']
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        type_nom = ''
        if getattr(instance, 'type_ouvrage', None):
            type_nom = getattr(instance.type_ouvrage, 'nom_type_ouvrage', '') or ''
        data['full_name'] = f"{instance.prenom} {instance.nom}"
        return data


class VisiteCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer une nouvelle visite."""
    
    class Meta:
        model = Visite
        fields = [
            'ouvrage', 'agent', 'type_visite', 
            'commentaires_generaux', 'latitude', 'longitude',
            'conditions_meteo'
        ]
    
    def create(self, validated_data):
        # L'agent est automatiquement défini Ã  partir de l'utilisateur connecté
        if 'agent' not in validated_data:
            validated_data['agent'] = self.context['request'].user.employee
        return super().create(validated_data)


class VisiteSerializer(serializers.ModelSerializer):
    """Serializer complet pour les visites."""
    ouvrage = OuvrageBasicSerializer(read_only=True)
    agent = EmployeeBasicSerializer(read_only=True)
    nombre_anomalies = serializers.ReadOnlyField()
    
    # Alias pour compatibilité
    infrastructure = serializers.SerializerMethodField()
    
    class Meta:
        model = Visite
        fields = [
            'id', 'ouvrage', 'infrastructure', 'agent', 'date_visite', 'type_visite', 
            'statut', 'commentaires_generaux', 'latitude', 'longitude',
            'conditions_meteo', 'nombre_anomalies',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'infrastructure', 'created_at', 'updated_at', 'nombre_anomalies']
    
    def get_infrastructure(self, obj):
        """Alias pour compatibilité avec infrastructure."""
        return OuvrageBasicSerializer(obj.ouvrage).data


class FileUploadBasicSerializer(serializers.ModelSerializer):
    """Serializer basique pour les fichiers uploadés."""
    download_url = serializers.SerializerMethodField()
    
    class Meta:
        model = FileUpload
        fields = ['id', 'filename', 'original_filename', 'content_type', 'download_url']
    
    def get_download_url(self, obj):
        return obj.get_download_url()


class InspectionPhotoSerializer(serializers.ModelSerializer):
    """Serializer pour les photos d'inspection groupées."""
    file = FileUploadBasicSerializer(source='file_upload', read_only=True)
    equipement_nom = serializers.SerializerMethodField()
    point_eau_nom = serializers.SerializerMethodField()

    class Meta:
        model = InspectionPhoto
        fields = [
            'id', 'visite', 'equipement', 'equipement_nom',
            'point_eau', 'point_eau_nom', 'description', 'pris_le',
            'file', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'file', 'created_at', 'updated_at']

    def get_equipement_nom(self, obj):
        return obj.equipement.nom if obj.equipement else None

    def get_point_eau_nom(self, obj):
        return getattr(obj.point_eau, 'nomabonne', None)


class ResultatControleCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer/modifier un résultat de controle."""

    inspection_photos = serializers.PrimaryKeyRelatedField(
        queryset=InspectionPhoto.objects.all(),
        many=True,
        required=False
    )
    
    class Meta:
        model = ResultatControle
        fields = [
            'visite', 'equipement', 'point_de_controle',
            'resultat_bool', 'resultat_numeric', 'commentaire',
            'inspection_photos'
        ]
    
    def validate(self, data):
        """Validation spécifique selon le type de point de controle."""
        point_controle = data['point_de_controle']
        
        if point_controle.type_resultat == 'BOOL':
            if data.get('resultat_bool') is None:
                raise serializers.ValidationError(
                    "Le résultat booléen est requis pour ce point de controle."
                )
            if 'resultat_numeric' in data:
                data['resultat_numeric'] = None
        
        elif point_controle.type_resultat == 'NUM':
            if data.get('resultat_numeric') is None:
                raise serializers.ValidationError(
                    "Le résultat numérique est requis pour ce point de controle."
                )
            if 'resultat_bool' in data:
                data['resultat_bool'] = None
        
        return data


class ResultatControleSerializer(serializers.ModelSerializer):
    """Serializer complet pour les résultats de controle."""
    equipement = EquipementConstitutifBasicSerializer(read_only=True)
    point_de_controle = PointDeControleSerializer(read_only=True)
    inspection_photos = InspectionPhotoSerializer(many=True, read_only=True)
    resultat_display = serializers.ReadOnlyField()
    est_conforme = serializers.ReadOnlyField()
    
    class Meta:
        model = ResultatControle
        fields = [
            'id', 'visite', 'equipement', 'point_de_controle',
            'resultat_bool', 'resultat_numeric', 'commentaire', 'inspection_photos',
            'heure_controle', 'necessite_action', 'resultat_display', 'est_conforme',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'necessite_action', 'resultat_display', 'est_conforme',
            'created_at', 'updated_at'
        ]


class PlanningFromInspectionSerializer(serializers.ModelSerializer):
    """Serializer pour créer une tÃ¢che de planning Ã  partir d'un résultat d'inspection."""
    
    class Meta:
        model = Planning
        fields = [
            'date', 'remarque', 'ouvrageid', 'employeid', 'activiteid',
            'origine_resultat'
        ]
    
    def create(self, validated_data):
        """Créer automatiquement une tÃ¢che de maintenance."""
        # Copier les données du résultat d'inspection
        resultat = validated_data.get('origine_resultat')
        if resultat:
            validated_data['ouvrageid'] = resultat.equipement.infrastructure.id
            if not validated_data.get('remarque'):
                validated_data['remarque'] = f"Maintenance requise suite Ã  inspection: {resultat.point_de_controle.nom}"
        
        # Valeurs par défaut
        validated_data.setdefault('activiteid', 1)  # ID d'activité de maintenance
        validated_data.setdefault('createdat', timezone.now())
        validated_data.setdefault('updatedat', timezone.now())
        
        return super().create(validated_data)


class VisiteDetailSerializer(serializers.ModelSerializer):
    """Serializer détaillé pour une visite avec tous ses résultats."""
    infrastructure = InfrastructureBasicSerializer(read_only=True)
    agent = EmployeeBasicSerializer(read_only=True)
    resultats = ResultatControleSerializer(many=True, read_only=True)
    nombre_anomalies = serializers.ReadOnlyField()
    
    # Equipements de l'infrastructure avec leurs checklists
    equipements_checklists = serializers.SerializerMethodField()
    
    class Meta:
        model = Visite
        fields = [
            'id', 'infrastructure', 'agent', 'date_visite', 'type_visite',
            'statut', 'commentaires_generaux', 'latitude', 'longitude',
            'conditions_meteo', 'nombre_anomalies', 'resultats',
            'equipements_checklists', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'nombre_anomalies']
    
    def get_equipements_checklists(self, obj):
        """Retourne les équipements avec leurs checklists pour ce type de visite."""
        equipements = EquipementConstitutif.objects.filter(
            infrastructure=obj.infrastructure
        ).prefetch_related('checklists', 'checklists__points_de_controle')
        
        result = []
        for equipement in equipements:
            # Chercher la checklist correspondante au type de visite
            checklist = equipement.checklists.filter(
                type_visite=obj.type_visite,
                is_active=True
            ).first()
            
            if checklist:
                result.append({
                    'equipement': EquipementConstitutifBasicSerializer(equipement).data,
                    'checklist': ChecklistSerializer(checklist).data
                })
        
        return result


class HistoriqueControleSerializer(serializers.ModelSerializer):
    """Serializer pour l'historique des controles d'un équipement."""
    visite = VisiteSerializer(read_only=True)
    point_de_controle = PointDeControleSerializer(read_only=True)
    resultat_display = serializers.ReadOnlyField()
    est_conforme = serializers.ReadOnlyField()
    
    class Meta:
        model = ResultatControle
        fields = [
            'id', 'visite', 'point_de_controle', 'resultat_display',
            'est_conforme', 'commentaire', 'heure_controle', 'necessite_action'
        ]

