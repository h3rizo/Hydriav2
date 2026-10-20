from decimal import Decimal

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import serializers

from .models import HouseholdMember, Ingredient, Meal, MealIngredient, MealParticipant, Profile


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()

    def validate(self, data):
        username = data.get('username')
        password = data.get('password')

        if username and password:
            user = authenticate(username=username, password=password)
            if user:
                if user.is_active:
                    data['user'] = user
                    return data
                raise serializers.ValidationError('Compte utilisateur desactive.')
            raise serializers.ValidationError("Nom d'utilisateur ou mot de passe incorrect.")
        raise serializers.ValidationError("Nom d'utilisateur et mot de passe requis.")


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active']
        read_only_fields = ['id', 'is_staff', 'is_active']


class AuthStatusSerializer(serializers.Serializer):
    is_authenticated = serializers.BooleanField()
    user = UserSerializer(required=False)
    session_key = serializers.CharField(required=False)
    csrf_token = serializers.CharField(required=False)


class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Profile
        fields = [
            'id', 'user', 'supabase_uid', 'age', 'sex',
            'weight_kg', 'height_cm', 'goal', 'allergies',
        ]
        read_only_fields = ['id', 'user']


class ProfileLookupSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'display_name']

    def get_display_name(self, obj):
        full_name = obj.user.get_full_name().strip()
        if full_name:
            return f"{full_name} ({obj.user.username})"
        return obj.user.username


class HouseholdMemberSerializer(serializers.ModelSerializer):
    linked_profile_display_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = HouseholdMember
        fields = ['id', 'name', 'relationship', 'age', 'sex', 'linked_profile', 'linked_profile_display_name']
        read_only_fields = ['id']

    def get_linked_profile_display_name(self, obj):
        if not obj.linked_profile_id:
            return ""
        full_name = obj.linked_profile.user.get_full_name().strip()
        if full_name:
            return f"{full_name} ({obj.linked_profile.user.username})"
        return obj.linked_profile.user.username


class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = [
            'id', 'name', 'default_unit',
            'kcal_per_100g', 'protein_per_100g', 'carbs_per_100g', 'fat_per_100g',
        ]
        read_only_fields = ['id']


class MealIngredientWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = MealIngredient
        fields = ['id', 'ingredient', 'quantity', 'unit']
        read_only_fields = ['id']


class MealIngredientReadSerializer(serializers.ModelSerializer):
    ingredient = IngredientSerializer(read_only=True)
    nutrition_totals = serializers.SerializerMethodField()

    class Meta:
        model = MealIngredient
        fields = ['id', 'ingredient', 'quantity', 'unit', 'nutrition_totals']

    def get_nutrition_totals(self, obj):
        totals = obj.nutrition_totals()
        return {key: str(value) for key, value in totals.items()}


class MealParticipantWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = MealParticipant
        fields = ['id', 'profile', 'household_member', 'servings_eaten']
        read_only_fields = ['id']

    def validate(self, attrs):
        profile = attrs.get('profile')
        household_member = attrs.get('household_member')
        if not profile and not household_member:
            raise serializers.ValidationError("Choisir au moins 'profile' ou 'household_member'.")

        request = self.context['request']
        owner_profile = request.user.profile

        if household_member and household_member.owner_id != owner_profile.id:
            raise serializers.ValidationError("Ce membre du foyer n'appartient pas au profil courant.")

        if profile and profile.id != owner_profile.id:
            linked_member_ids = owner_profile.household_members.filter(linked_profile=profile).values_list('id', flat=True)
            if not household_member or household_member.id not in linked_member_ids:
                raise serializers.ValidationError("Ce profil participant doit etre relie a un membre du foyer du profil courant.")

        return attrs


class MealParticipantReadSerializer(serializers.ModelSerializer):
    participant_name = serializers.SerializerMethodField()
    nutrition_totals = serializers.SerializerMethodField()

    class Meta:
        model = MealParticipant
        fields = ['id', 'profile', 'household_member', 'participant_name', 'servings_eaten', 'nutrition_totals']

    def get_participant_name(self, obj):
        if obj.household_member_id:
            return obj.household_member.name
        if obj.profile_id:
            return obj.profile.user.get_full_name() or obj.profile.user.username
        return ''

    def get_nutrition_totals(self, obj):
        meal = obj.meal
        if not meal.total_servings:
            return {'kcal': '0', 'protein': '0', 'carbs': '0', 'fat': '0'}

        totals = {
            'kcal': Decimal('0'),
            'protein': Decimal('0'),
            'carbs': Decimal('0'),
            'fat': Decimal('0'),
        }
        for meal_ingredient in meal.ingredients.select_related('ingredient').all():
            ingredient_totals = meal_ingredient.nutrition_totals()
            for key in totals:
                totals[key] += ingredient_totals[key]

        divisor = meal.total_servings
        return {
            key: str((value / divisor) * obj.servings_eaten)
            for key, value in totals.items()
        }


class MealSerializer(serializers.ModelSerializer):
    ingredients = MealIngredientWriteSerializer(many=True)
    participants = MealParticipantWriteSerializer(many=True)
    shopping_done_by = serializers.PrimaryKeyRelatedField(
        queryset=Profile.objects.all(),
        allow_null=True,
        required=False,
    )
    cooked_by = serializers.PrimaryKeyRelatedField(
        queryset=Profile.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Meal
        fields = [
            'id', 'title', 'eaten_at', 'total_servings', 'notes',
            'shopping_done_by', 'cooked_by', 'ingredients', 'participants',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        owner_profile = self.context['request'].user.profile
        for field_name in ['shopping_done_by', 'cooked_by']:
            profile = attrs.get(field_name)
            if profile and profile.id != owner_profile.id:
                raise serializers.ValidationError({field_name: "Seul le profil courant est autorise ici pour l'instant."})
        return attrs

    def create(self, validated_data):
        ingredients_data = validated_data.pop('ingredients', [])
        participants_data = validated_data.pop('participants', [])
        meal = Meal.objects.create(created_by=self.context['request'].user.profile, **validated_data)
        self._save_nested(meal, ingredients_data, participants_data)
        return meal

    def update(self, instance, validated_data):
        ingredients_data = validated_data.pop('ingredients', None)
        participants_data = validated_data.pop('participants', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if ingredients_data is not None or participants_data is not None:
            instance.ingredients.all().delete()
            instance.participants.all().delete()
            self._save_nested(instance, ingredients_data or [], participants_data or [])

        return instance

    def _save_nested(self, meal, ingredients_data, participants_data):
        for ingredient_data in ingredients_data:
            MealIngredient.objects.create(meal=meal, **ingredient_data)
        for participant_data in participants_data:
            household_member = participant_data.get('household_member')
            if household_member and household_member.linked_profile and not participant_data.get('profile'):
                participant_data['profile'] = household_member.linked_profile
            MealParticipant.objects.create(meal=meal, **participant_data)


class MealDetailSerializer(serializers.ModelSerializer):
    created_by = ProfileSerializer(read_only=True)
    shopping_done_by = ProfileSerializer(read_only=True)
    cooked_by = ProfileSerializer(read_only=True)
    ingredients = MealIngredientReadSerializer(many=True, read_only=True)
    participants = MealParticipantReadSerializer(many=True, read_only=True)

    class Meta:
        model = Meal
        fields = [
            'id', 'created_by', 'title', 'eaten_at', 'total_servings', 'notes',
            'shopping_done_by', 'cooked_by', 'ingredients', 'participants',
        ]
