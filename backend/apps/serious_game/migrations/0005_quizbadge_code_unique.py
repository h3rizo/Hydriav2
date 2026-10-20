from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("serious_game", "0004_seed_quiz_badges"),
    ]

    operations = [
        migrations.AlterField(
            model_name="quizbadge",
            name="code",
            field=models.CharField(max_length=120, unique=True, verbose_name="Code"),
        ),
    ]
