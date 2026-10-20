from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0002_remove_mealparticipant_meal_participant_one_target_only_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='householdmember',
            name='linked_profile',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='linked_household_members', to='authentication.profile'),
        ),
        migrations.RemoveConstraint(
            model_name='mealparticipant',
            name='meal_participant_one_target_only',
        ),
        migrations.AddConstraint(
            model_name='mealparticipant',
            constraint=models.CheckConstraint(
                condition=models.Q(('profile__isnull', False), _connector='OR', ) | models.Q(('household_member__isnull', False), _connector='OR'),
                name='meal_participant_requires_target',
            ),
        ),
    ]
