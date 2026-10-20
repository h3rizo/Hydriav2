from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0011_remove_planningdetail_planning_and_more'),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
