# Generated manually to keep planning state aligned after raw SQL timestamp cleanup
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0040_fix_createdat_column'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='planning',
                    name='createdat',
                ),
                migrations.RemoveField(
                    model_name='planning',
                    name='updatedat',
                ),
            ],
            database_operations=[],
        ),
        migrations.AlterField(
            model_name='planning',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AlterField(
            model_name='planning',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, null=True),
        ),
    ]
