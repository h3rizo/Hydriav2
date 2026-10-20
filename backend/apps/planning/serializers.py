from rest_framework import serializers
from django.conf import settings
from .models import Planning, PlanningDetail, TypeActivite, ActivitePoste, PlanningEmploye, Indemnite
from apps.employees.models import Employe
from apps.organization.models import Base, Ouvrage
from .repair_workflow_grading import get_repair_workflow_grading_from_plannings


class TypeActiviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeActivite
        fields = ['id', 'nomtype', 'description', 'is_active']


class ActivitePosteSerializer(serializers.ModelSerializer):
    type_activite_nom = serializers.CharField(source='type_activite.nomtype', read_only=True)
    
    class Meta:
        model = ActivitePoste
        fields = [
            'id', 'nom', 'description', 'type_activite', 'type_activite_nom',
            'is_active', 'frequence_mois', 'mode_frequence'
        ]


class EmployeSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employe
        fields = ['id', 'emp_id', 'emp_firstname', 'emp_lastname', 'full_name']


class OuvrageSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ouvrage
        fields = ['id', 'nom_ouvrage', 'observation']


class PlanningDetailSerializer(serializers.ModelSerializer):
    designation = serializers.CharField(source='designation.nom', read_only=True)
    equipement_nom = serializers.CharField(source='equipement_constitutif.nom', read_only=True)
    point_eau_code = serializers.CharField(source='point_eau.code_point_eau', read_only=True)
    point_a_nom = serializers.CharField(source='point_a.nom_village', read_only=True)
    point_b_nom = serializers.CharField(source='point_b.nom_village', read_only=True)

    class Meta:
        model = PlanningDetail
        fields = [
            'id', 'designation', 'quantity', 'pu', 'montant', 'acheteur',
            'equipement_nom', 'point_eau_code', 'trajet', 'point_a_nom', 'point_b_nom', 'moyen_transport'
        ]


class PlanningSerializer(serializers.ModelSerializer):
    employe_nom = serializers.CharField(read_only=True)
    type_activite_nom = serializers.CharField(read_only=True)
    activite_nom = serializers.CharField(source='fiche_poste.tache', read_only=True)
    activite = serializers.PrimaryKeyRelatedField(source='fiche_poste', read_only=True)
    fiche_poste = serializers.PrimaryKeyRelatedField(read_only=True)
    ouvrage_nom = serializers.CharField(read_only=True)
    details = PlanningDetailSerializer(many=True, read_only=True)
    activite_display = serializers.CharField(read_only=True)
    fiche_poste_display = serializers.CharField(read_only=True)
    date_planning = serializers.CharField(source='planning_date', read_only=True)
    validation = serializers.BooleanField(read_only=True)
    remarques = serializers.CharField(read_only=True)
    ouvrage_grading = serializers.SerializerMethodField()
    
    class Meta:
        model = Planning
        fields = [
            'id', 'date_planning', 'type_activite', 'type_activite_nom',
            'activite', 'fiche_poste', 'activite_nom', 'activite_text', 'activite_display',
            'fiche_poste_display',
            'ouvrage', 'ouvrage_nom', 'employe', 'employe_nom',
            'remarques', 'validation', 'statut', 'details', 'ouvrage_grading',
            'datesignalementactivite', 'debitmesure', 'bilan', 'suiteadonner',
            'date', 'employeid', 'activiteid', 'ouvrageid', 'estvalide', 'remarque'
        ]

    def get_ouvrage_grading(self, obj):
        ouvrage_id = getattr(obj, 'ouvrage_id', None)
        if not ouvrage_id:
            return ''

        cache = self.context.setdefault('ouvrage_grading_cache', {})
        cache_key = str(ouvrage_id)
        if cache_key not in cache:
            try:
                reparations = Planning.objects.filter(
                    ouvrage_id=ouvrage_id
                ).select_related('fiche_poste')
                cache[cache_key] = (
                    get_repair_workflow_grading_from_plannings(reparations).get('code') or ''
                ).strip()
            except Exception:
                cache[cache_key] = ''
        return cache[cache_key]


class PlanningCreateSerializer(serializers.ModelSerializer):
    activite = serializers.UUIDField(required=False, allow_null=True)
    fiche_poste = serializers.UUIDField(required=False, allow_null=True)
    class Meta:
        model = Planning
        fields = [
            'date_planning', 'type_activite', 'activite', 'fiche_poste', 'activite_text',
            'ouvrage', 'employe', 'remarques', 'validation', 'statut'
        ]
    
    def create(self, validated_data):
        activite_id = validated_data.pop('activite', None)
        fiche_poste_id = validated_data.pop('fiche_poste', None)
        if fiche_poste_id and not activite_id:
            validated_data['fiche_poste_id'] = fiche_poste_id
        elif activite_id:
            validated_data['fiche_poste_id'] = activite_id
        planning = Planning.objects.create(**validated_data)
        return planning


class PlanningFilterSerializer(serializers.Serializer):
    employe = serializers.UUIDField(required=False)
    mois = serializers.CharField(max_length=7, required=False)  # Format: YYYY-MM
    ouvrage = serializers.UUIDField(required=False)
    type_activite = serializers.IntegerField(required=False)
    activite = serializers.UUIDField(required=False)
    validation = serializers.BooleanField(required=False)


# Nouveaux serializers avec validation hiérarchique

class PlanningHierarchicalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Planning
        fields = '__all__'
        read_only_fields = ('employe', 'createdat', 'updatedat')

    def validate_ouvrage(self, value):
        """
        Valide que l'ouvrage appartient à une organisation autorisée pour l'utilisateur.
        """
        if not value:  # L'ouvrage peut être null
            return value
            
        user = self.context['request'].user
        
        if not hasattr(user, 'employee_profile'):
            raise serializers.ValidationError("Utilisateur non associé à un profil employé.")
        
        profile = user.employee_profile

        if profile.poste and profile.poste.poste_name in settings.ROLES_NIVEAU_ORGANISATION:
            # Un directeur peut créer des plannings pour tous les ouvrages de son organisation
            if value.organisationid != profile.organization.id:
                raise serializers.ValidationError("Cet ouvrage n'appartient pas à votre organisation.")
        else:
            # Un employé standard doit être limité aux ouvrages de son organisation
            if value.organisationid != profile.organization.id:
                raise serializers.ValidationError("Vous ne pouvez pas créer de planning pour cet ouvrage.")
        
        return value


class PlanningEmployeHierarchicalSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanningEmploye
        fields = '__all__'

    def validate_employee(self, value):
        """
        Valide que l'employé appartient à l'organisation de l'utilisateur.
        """
        user = self.context['request'].user
        
        if not hasattr(user, 'employee_profile'):
            raise serializers.ValidationError("Utilisateur non associé à un profil employé.")
        
        profile = user.employee_profile

        # Même pour les directeurs, on s'assure que l'employé fait partie de l'organisation
        if value.organization != profile.organization:
            raise serializers.ValidationError("Cet employé n'appartient pas à votre organisation.")
        
        return value


class IndemniteHierarchicalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Indemnite
        fields = '__all__'
        read_only_fields = ('employee',)

    def validate_planning(self, value):
        """
        Valide que le planning appartient à l'organisation de l'utilisateur.
        """
        if not value:  # Le planning peut être null
            return value
            
        user = self.context['request'].user
        
        if not hasattr(user, 'employee_profile'):
            raise serializers.ValidationError("Utilisateur non associé à un profil employé.")
        
        profile = user.employee_profile

        # Vérification via l'employé du planning
        if value.employe and value.employe.organization != profile.organization:
            raise serializers.ValidationError("Ce planning n'appartient pas à votre organisation.")
        
        return value


class PlanningDetailHierarchicalSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanningDetail
        fields = '__all__'

    def validate_planning(self, value):
        """
        Valide que le planning appartient à l'organisation de l'utilisateur.
        """
        user = self.context['request'].user
        
        if not hasattr(user, 'employee_profile'):
            raise serializers.ValidationError("Utilisateur non associé à un profil employé.")
        
        profile = user.employee_profile

        # Vérification via l'employé du planning
        if value.employe and value.employe.organization != profile.organization:
            raise serializers.ValidationError("Ce planning n'appartient pas à votre organisation.")
        
        return value
