from django.db import migrations, models
from django.db.models import Count


def _longest_text(records, field_name):
    best_value = ""
    for record in records:
        value = (getattr(record, field_name, None) or "").strip()
        if len(value) > len(best_value):
            best_value = value
    return best_value or None


def dedupe_avisrepresentant(apps, schema_editor):
    AvisRepresentant = apps.get_model("usagers", "AvisRepresentant")
    db_alias = schema_editor.connection.alias

    duplicate_groups = (
        AvisRepresentant.objects.using(db_alias)
        .values("representant_id", "date_avis")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )

    bool_fields = [
        "quantite_ok",
        "qualite_ok",
        "delai_reparation_ok",
        "relation_gestionnaire_ok",
    ]
    text_fields = [
        "probleme_technique",
        "probleme_recouvrement",
        "probleme_regles_utilisation",
        "remarque",
    ]

    for group in duplicate_groups.iterator():
        records = list(
            AvisRepresentant.objects.using(db_alias)
            .filter(
                representant_id=group["representant_id"],
                date_avis=group["date_avis"],
            )
            .order_by("-updated_at", "-created_at", "-id")
        )

        if len(records) < 2:
            continue

        canonical = records[0]
        duplicates = records[1:]
        changed_fields = []

        for field_name in bool_fields:
            true_count = sum(1 for record in records if getattr(record, field_name))
            false_count = len(records) - true_count

            if true_count == false_count:
                continue

            new_value = true_count > false_count
            if getattr(canonical, field_name) != new_value:
                setattr(canonical, field_name, new_value)
                changed_fields.append(field_name)

        if not canonical.employe_id:
            for record in records:
                if record.employe_id:
                    canonical.employe_id = record.employe_id
                    changed_fields.append("employe")
                    break

        for field_name in text_fields:
            new_value = _longest_text(records, field_name)
            if getattr(canonical, field_name) != new_value:
                setattr(canonical, field_name, new_value)
                changed_fields.append(field_name)

        if changed_fields:
            canonical.save(using=db_alias, update_fields=sorted(set(changed_fields)))

        AvisRepresentant.objects.using(db_alias).filter(
            id__in=[record.id for record in duplicates]
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("usagers", "0004_avisrepresentant_probleme_recouvrement_and_more"),
    ]

    operations = [
        migrations.RunPython(dedupe_avisrepresentant, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="avisrepresentant",
            constraint=models.UniqueConstraint(
                fields=("representant", "date_avis"),
                name="uniq_avis_representant_date",
            ),
        ),
    ]
