from django.db import migrations


def backfill_planning_employees(apps, schema_editor):
    Planning = apps.get_model('planning', 'Planning')
    PlanningEmploye = apps.get_model('planning', 'PlanningEmploye')
    db_alias = schema_editor.connection.alias

    batch = []
    for planning_id, employe_id in (
        Planning.objects.using(db_alias)
        .filter(employe_id__isnull=False)
        .values_list('id', 'employe_id')
        .iterator()
    ):
        if not employe_id:
            continue
        batch.append(
            PlanningEmploye(planning_id=planning_id, employee_id=employe_id)
        )
        if len(batch) >= 1000:
            PlanningEmploye.objects.using(db_alias).bulk_create(
                batch, ignore_conflicts=True
            )
            batch.clear()

    if batch:
        PlanningEmploye.objects.using(db_alias).bulk_create(
            batch, ignore_conflicts=True
        )


class Migration(migrations.Migration):
    dependencies = [
        ('planning', '0046_fix_indemnites_uuid'),
    ]

    operations = [
        migrations.RunPython(backfill_planning_employees, migrations.RunPython.noop),
    ]
