from rest_framework import serializers
from django.conf import settings
from .models import (
    TypeOuvrage, MaintenanceTask, EquipementConstitutif, Incident,
    PointControleInfra, InspectionInfra, ResultatControleInfra
)
from apps.organization.models import Base, Ouvrage


class TypeOuvrageSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeOuvrage
        fields = '__all__'


class OuvrageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ouvrage
        fields = '__all__'

    def validate_base(self, value):
        """
        Valide que la base sélectionnée est autorisée pour l'utilisateur.
        Applique uniquement lors de la création avec une base explicite.
        """
        user = self.context['request'].user
        
        if not hasattr(user, 'employee_profile'):
            raise serializers.ValidationError("Utilisateur non associé à un profil employé.")
        
        profile = user.employee_profile

        # Vérifier si le poste de l'utilisateur lui donne des privilèges organisationnels
        if profile.poste and profile.poste.poste_name in settings.ROLES_NIVEAU_ORGANISATION:
            # Un directeur peut choisir une base, mais elle doit être dans son organisation
            if value.organization != profile.organization:
                raise serializers.ValidationError("Cette base n'appartient pas à votre organisation.")
        else:
            # Un employé standard ne peut pas choisir une autre base que la sienne
            if value != profile.base:
                raise serializers.ValidationError("Vous ne pouvez pas créer d'entrée pour une autre base.")
        
        return value


class MaintenanceTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceTask
        fields = '__all__'
        read_only_fields = ('assigned_employee',)

    def validate_infrastructure(self, value):
        """
        Valide que l'infrastructure appartient à une base autorisée pour l'utilisateur.
        """
        user = self.context['request'].user
        
        if not hasattr(user, 'employee_profile'):
            raise serializers.ValidationError("Utilisateur non associé à un profil employé.")
        
        profile = user.employee_profile

        # Pour l'infrastructure, nous devons vérifier via la relation organisationid
        if profile.poste and profile.poste.poste_name in settings.ROLES_NIVEAU_ORGANISATION:
            # Un directeur peut créer des tâches pour toutes les infrastructures de son organisation
            if value.organisation != profile.organization:
                raise serializers.ValidationError("Cette infrastructure n'appartient pas à votre organisation.")
        else:
            # Un employé standard doit être limité aux infrastructures de sa base
            if value.organisation != profile.organization:
                raise serializers.ValidationError("Vous ne pouvez pas créer de tâches pour cette infrastructure.")
        
        return value


class EquipementConstitutifSerializer(serializers.ModelSerializer):
    class Meta:
        model = EquipementConstitutif
        fields = '__all__'
        read_only_fields = ('responsable',)

    def validate_ouvrage(self, value):
        """
        Valide que l'ouvrage appartient à une organisation autorisée pour l'utilisateur.
        """
        user = self.context['request'].user
        
        if not hasattr(user, 'employee_profile'):
            raise serializers.ValidationError("Utilisateur non associé à un profil employé.")
        
        profile = user.employee_profile

        if profile.poste and profile.poste.poste_name in settings.ROLES_NIVEAU_ORGANISATION:
            # Un directeur peut créer des équipements pour tous les ouvrages de son organisation
            if value.organisation != profile.organization:
                raise serializers.ValidationError("Cet ouvrage n'appartient pas à votre organisation.")
        else:
            # Un employé standard doit être limité aux ouvrages de son organisation
            if value.organisation != profile.organization:
                raise serializers.ValidationError("Vous ne pouvez pas créer d'équipements pour cet ouvrage.")
        
        return value


class IncidentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Incident
        fields = '__all__'
        read_only_fields = ('reported_by', 'assigned_to')

    def validate_infrastructure(self, value):
        """
        Valide que l'infrastructure appartient à une organisation autorisée pour l'utilisateur.
        """
        user = self.context['request'].user
        
        if not hasattr(user, 'employee_profile'):
            raise serializers.ValidationError("Utilisateur non associé à un profil employé.")
        
        profile = user.employee_profile

        if profile.poste and profile.poste.poste_name in settings.ROLES_NIVEAU_ORGANISATION:
            # Un directeur peut rapporter des incidents pour toutes les infrastructures de son organisation
            if value.organisation != profile.organization:
                raise serializers.ValidationError("Cette infrastructure n'appartient pas à votre organisation.")
        else:
            # Un employé standard doit être limité aux infrastructures de son organisation
            if value.organisation != profile.organization:
                raise serializers.ValidationError("Vous ne pouvez pas rapporter d'incidents pour cette infrastructure.")

        return value


class PointControleInfraSerializer(serializers.ModelSerializer):
    photo_reference_url = serializers.SerializerMethodField()

    class Meta:
        model = PointControleInfra
        fields = '__all__'

    def get_photo_reference_url(self, obj):
        """Retourne l'URL de la photo de référence si elle existe"""
        if obj.photo_reference and obj.photo_reference.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.photo_reference.file.url)
        return None


class ResultatControleInfraSerializer(serializers.ModelSerializer):
    photo_reference_url = serializers.SerializerMethodField()
    photo_resultat_url = serializers.SerializerMethodField()
    point_controle_details = PointControleInfraSerializer(source='point_controle', read_only=True)

    class Meta:
        model = ResultatControleInfra
        fields = '__all__'

    def get_photo_reference_url(self, obj):
        """Retourne l'URL de la photo de référence du point de contrôle"""
        if obj.point_controle.photo_reference and obj.point_controle.photo_reference.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.point_controle.photo_reference.file.url)
        return None

    def get_photo_resultat_url(self, obj):
        """Retourne l'URL de la photo de résultat si elle existe"""
        if obj.photo_resultat and obj.photo_resultat.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.photo_resultat.file.url)
        return None


class InspectionInfraSerializer(serializers.ModelSerializer):
    resultats_controle_infra = ResultatControleInfraSerializer(many=True, read_only=True)
    equipement_details = EquipementConstitutifSerializer(source='equipement', read_only=True)
    progression = serializers.ReadOnlyField()
    nb_points_controle = serializers.ReadOnlyField()
    nb_points_completes = serializers.ReadOnlyField()

    class Meta:
        model = InspectionInfra
        fields = '__all__'
        read_only_fields = ('inspecteur',)

    def validate_equipement(self, value):
        """
        Valide que l'équipement appartient à une organisation autorisée pour l'utilisateur.
        """
        user = self.context['request'].user

        if not hasattr(user, 'employee_profile'):
            raise serializers.ValidationError("Utilisateur non associé à un profil employé.")

        profile = user.employee_profile

        # Note: Sans champ organisation sur ouvrage, vérification désactivée temporairement
        # À rétablir via modalitegestion si nécessaire

        return value