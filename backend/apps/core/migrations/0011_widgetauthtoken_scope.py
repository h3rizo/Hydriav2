# Ajoute le scope (widget desktop vs app mobile terrain) au token existant,
# cloisonnant chaque token à sa famille d'endpoints sans dupliquer le modèle.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_widgetauthtoken'),
    ]

    operations = [
        migrations.AddField(
            model_name='widgetauthtoken',
            name='scope',
            field=models.CharField(
                choices=[('widget', 'Widget desktop (Electron)'), ('mobile', 'App terrain Android')],
                db_index=True,
                default='widget',
                help_text="Famille d'endpoints que ce token peut appeler (widget desktop ou app mobile terrain).",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='widgetauthtoken',
            name='device_label',
            field=models.CharField(
                blank=True, default='',
                help_text="Ex: 'PC bureau' ou 'Android - Samsung A14', pour identifier ce token dans l'admin",
                max_length=120, verbose_name='Appareil',
            ),
        ),
        migrations.AlterModelOptions(
            name='widgetauthtoken',
            options={
                'verbose_name': 'Token client externe (widget/mobile)',
                'verbose_name_plural': 'Tokens clients externes (widget/mobile)',
            },
        ),
    ]
