from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.utils import OperationalError, ProgrammingError
from django.db.models.signals import post_save
from django.dispatch import receiver


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    supabase_uid = models.UUIDField(null=True, blank=True, unique=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    sex = models.CharField(max_length=20, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    height_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    goal = models.CharField(max_length=100, blank=True)
    allergies = models.TextField(blank=True)

    def __str__(self):
        return self.user.username


class HouseholdMember(models.Model):
    owner = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='household_members')
    name = models.CharField(max_length=120)
    relationship = models.CharField(max_length=50, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    sex = models.CharField(max_length=20, blank=True)
    linked_profile = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='linked_household_members',
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.owner})"


class Ingredient(models.Model):
    name = models.CharField(max_length=150, unique=True)
    default_unit = models.CharField(max_length=30, default='g')
    kcal_per_100g = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    protein_per_100g = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    carbs_per_100g = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    fat_per_100g = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Meal(models.Model):
    created_by = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='meals')
    title = models.CharField(max_length=150)
    eaten_at = models.DateTimeField()
    total_servings = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    notes = models.TextField(blank=True)
    shopping_done_by = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shopping_meals',
    )
    cooked_by = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cooked_meals',
    )

    class Meta:
        ordering = ['-eaten_at', '-id']

    def __str__(self):
        return self.title


class MealIngredient(models.Model):
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, related_name='ingredients')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name='meal_usages')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=30)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.ingredient} - {self.quantity} {self.unit}"

    def nutrition_multiplier(self):
        if self.unit == 'kg':
            return Decimal('10')
        if self.unit == 'g':
            return Decimal('0.01')
        return Decimal('0')

    def nutrition_totals(self):
        multiplier = self.nutrition_multiplier()
        return {
            'kcal': (self.ingredient.kcal_per_100g or Decimal('0')) * multiplier * self.quantity,
            'protein': (self.ingredient.protein_per_100g or Decimal('0')) * multiplier * self.quantity,
            'carbs': (self.ingredient.carbs_per_100g or Decimal('0')) * multiplier * self.quantity,
            'fat': (self.ingredient.fat_per_100g or Decimal('0')) * multiplier * self.quantity,
        }


class MealParticipant(models.Model):
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, related_name='participants')
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='meal_participations',
    )
    household_member = models.ForeignKey(
        HouseholdMember,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='meal_participations',
    )
    servings_eaten = models.DecimalField(max_digits=6, decimal_places=2, default=1)

    class Meta:
        ordering = ['id']
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(profile__isnull=False) | models.Q(household_member__isnull=False)
                ),
                name='meal_participant_requires_target',
            )
        ]

    def __str__(self):
        target = self.profile or self.household_member
        return f"{target} - {self.servings_eaten} portion(s)"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        try:
            # Profile est optionnel sur certains deploiements Hydria. Le
            # savepoint evite qu'une table absente casse la transaction User.
            with transaction.atomic():
                Profile.objects.create(user=instance)
        except (OperationalError, ProgrammingError):
            # Do not block user creation/login when the optional profile table
            # is unavailable on this deployment.
            return


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    try:
        # Toute la lecture/ecriture doit etre dans le savepoint : une simple
        # lecture de la relation echoue aussi si la table n'existe pas.
        with transaction.atomic():
            instance.profile.save()
    except Profile.DoesNotExist:
        try:
            with transaction.atomic():
                Profile.objects.create(user=instance)
        except (OperationalError, ProgrammingError):
            return
    except (OperationalError, ProgrammingError):
        return
