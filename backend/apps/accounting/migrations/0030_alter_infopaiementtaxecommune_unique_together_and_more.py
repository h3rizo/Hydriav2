from django.db import migrations, models
import django.db.models.deletion
import uuid


CREATE_IMPUTATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS imputation_remboursement_taxe_commune (
    id uuid NOT NULL PRIMARY KEY,
    annee integer NOT NULL,
    montant_impute numeric(15, 2) NOT NULL,
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    commune_id uuid NOT NULL REFERENCES geography_commune(id) DEFERRABLE INITIALLY DEFERRED,
    organisation_id uuid NULL REFERENCES organization_organisation(id) DEFERRABLE INITIALLY DEFERRED
);
"""


CREATE_IMPUTATION_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS imputation_remboursement_taxe_commune_annee_idx
ON imputation_remboursement_taxe_commune (annee);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'imputation_remboursement_taxe_commune_commune_org_annee_key'
    ) THEN
        ALTER TABLE imputation_remboursement_taxe_commune
        ADD CONSTRAINT imputation_remboursement_taxe_commune_commune_org_annee_key
        UNIQUE (commune_id, organisation_id, annee);
    END IF;
END $$;
"""


FIX_INFO_PAIEMENT_SQL = """
ALTER TABLE info_paiement_taxe_commune
DROP COLUMN IF EXISTS annee;

DO $$
DECLARE
    constraint_name text;
BEGIN
    SELECT conname
    INTO constraint_name
    FROM pg_constraint
    WHERE conrelid = 'info_paiement_taxe_commune'::regclass
      AND contype = 'u'
      AND conkey = ARRAY[
          (SELECT attnum FROM pg_attribute WHERE attrelid = 'info_paiement_taxe_commune'::regclass AND attname = 'commune_id'),
          (SELECT attnum FROM pg_attribute WHERE attrelid = 'info_paiement_taxe_commune'::regclass AND attname = 'organisation_id')
      ];

    IF constraint_name IS NULL THEN
        ALTER TABLE info_paiement_taxe_commune
        ADD CONSTRAINT info_paiement_taxe_commune_commune_id_organisation_id_key
        UNIQUE (commune_id, organisation_id);
    END IF;
END $$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0027_imputationremboursementtaxecommune'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=CREATE_IMPUTATION_TABLE_SQL,
                    reverse_sql="DROP TABLE IF EXISTS imputation_remboursement_taxe_commune CASCADE;",
                ),
                migrations.RunSQL(
                    sql=CREATE_IMPUTATION_INDEXES_SQL,
                    reverse_sql="""
                    ALTER TABLE imputation_remboursement_taxe_commune
                    DROP CONSTRAINT IF EXISTS imputation_remboursement_taxe_commune_commune_org_annee_key;
                    DROP INDEX IF EXISTS imputation_remboursement_taxe_commune_annee_idx;
                    """,
                ),
                migrations.RunSQL(
                    sql=FIX_INFO_PAIEMENT_SQL,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[],
        ),
    ]
