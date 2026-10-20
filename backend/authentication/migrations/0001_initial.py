from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Ingredient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True)),
                ('default_unit', models.CharField(default='g', max_length=30)),
                ('kcal_per_100g', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('protein_per_100g', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('carbs_per_100g', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('fat_per_100g', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('supabase_uid', models.UUIDField(blank=True, null=True, unique=True)),
                ('age', models.PositiveIntegerField(blank=True, null=True)),
                ('sex', models.CharField(blank=True, max_length=20)),
                ('weight_kg', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('height_cm', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('goal', models.CharField(blank=True, max_length=100)),
                ('allergies', models.TextField(blank=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='HouseholdMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('relationship', models.CharField(blank=True, max_length=50)),
                ('age', models.PositiveIntegerField(blank=True, null=True)),
                ('sex', models.CharField(blank=True, max_length=20)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='household_members', to='authentication.profile')),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Meal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=150)),
                ('eaten_at', models.DateTimeField()),
                ('total_servings', models.DecimalField(decimal_places=2, default=1, max_digits=6)),
                ('notes', models.TextField(blank=True)),
                ('cooked_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cooked_meals', to='authentication.profile')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='meals', to='authentication.profile')),
                ('shopping_done_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='shopping_meals', to='authentication.profile')),
            ],
            options={'ordering': ['-eaten_at', '-id']},
        ),
        migrations.CreateModel(
            name='MealIngredient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.DecimalField(decimal_places=2, max_digits=10)),
                ('unit', models.CharField(max_length=30)),
                ('ingredient', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='meal_usages', to='authentication.ingredient')),
                ('meal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ingredients', to='authentication.meal')),
            ],
            options={'ordering': ['id']},
        ),
        migrations.CreateModel(
            name='MealParticipant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('servings_eaten', models.DecimalField(decimal_places=2, default=1, max_digits=6)),
                ('household_member', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='meal_participations', to='authentication.householdmember')),
                ('meal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='participants', to='authentication.meal')),
                ('profile', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='meal_participations', to='authentication.profile')),
            ],
            options={'ordering': ['id']},
        ),
        migrations.AddConstraint(
            model_name='mealparticipant',
            constraint=models.CheckConstraint(
                condition=models.Q(('profile__isnull', False), ('household_member__isnull', True), _connector='AND') | models.Q(('profile__isnull', True), ('household_member__isnull', False), _connector='AND'),
                name='meal_participant_one_target_only',
            ),
        ),
    ]
