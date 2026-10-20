from django.contrib import admin

from .models import HouseholdMember, Ingredient, Meal, MealIngredient, MealParticipant, Profile


class MealIngredientInline(admin.TabularInline):
    model = MealIngredient
    extra = 0


class MealParticipantInline(admin.TabularInline):
    model = MealParticipant
    extra = 0


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'supabase_uid', 'goal')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name')


@admin.register(HouseholdMember)
class HouseholdMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'relationship', 'linked_profile')
    search_fields = ('name', 'owner__user__username')


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ('name', 'default_unit', 'kcal_per_100g')
    search_fields = ('name',)


@admin.register(Meal)
class MealAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_by', 'eaten_at', 'total_servings')
    search_fields = ('title', 'created_by__user__username')
    inlines = [MealIngredientInline, MealParticipantInline]
