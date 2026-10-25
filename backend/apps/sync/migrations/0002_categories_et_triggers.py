"""Catégories pré-remplies + triggers PostgreSQL qui alimentent ``sync_changes``.

Aucune opération destructive : le sens inverse ne supprime que les triggers, fonctions et
catégories créés ici. Les triggers n'écrivent que dans ``sync_changes`` (jamais dans les tables suivies).

Règle de diffusion (décisions Q1/Q2) :
- référentiel (régions, districts, communes, fokontany, villages, activités) -> organisation_id NULL,
  c'est-à-dire diffusé à tous les utilisateurs authentifiés ;
- ouvrages, équipements, points d'eau -> une ligne par organisation gestionnaire dont la modalité de
  gestion est active (même règle que ``filter_queryset_by_permissions``) ; une modalité sans
  gestionnaire, ou un point d'eau sans ouvrage, donne une ligne NULL (visible de tous, comme aujourd'hui) ;
- fichiers -> l'organisation qui dépose + les gestionnaires de l'ouvrage concerné (jamais NULL).

Limites connues (documentées dans docs/exploitation.md) :
- suppression en cascade d'un ouvrage : ses modalités disparaissent avant le trigger, aucune
  organisation n'est notifiée de la suppression ;
- les valeurs de ``seq`` sont attribuées avant le commit : le client doit relire avec un léger
  recouvrement (since - 100) et dédupliquer par ``seq``.
"""
from django.db import migrations

DOC_EXT = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt', 'odt', 'ods', 'ppt', 'pptx',
           'png', 'jpg', 'jpeg', 'zip']
IMG_EXT = ['jpg', 'jpeg', 'png', 'webp', 'heic']
TECH_EXT = DOC_EXT + ['dwg', 'dxf']

# (code, libellé, portée, domaine, types d'entités, extensions)
CATEGORIES = [
    ('dossier_technique', 'Dossier technique', 'entite', None, ['ouvrage', 'equipement'], TECH_EXT),
    ('planning', 'Planning', 'entite', None, ['activite'], DOC_EXT),
    ('photos_equipement', "Photos d'équipement", 'entite', None, ['equipement'], IMG_EXT),
    ('photos_point_eau', "Photos de point d'eau", 'entite', None, ['point_eau'], IMG_EXT),
    ('photos_village', 'Photos de village', 'entite', None, ['village'], IMG_EXT),
    ('photos_commune', 'Photos de commune', 'entite', None, ['commune'], IMG_EXT),

    ('procedure', 'Procédure', 'organisation', 'operationnel', [], DOC_EXT),
    ('mode_operatoire', 'Mode opératoire', 'organisation', 'operationnel', [], DOC_EXT),
    ('rapport_intervention', "Rapport d'intervention", 'organisation', 'operationnel', [], DOC_EXT),

    ('statuts', 'Statuts', 'organisation', 'administratif', [], DOC_EXT),
    ('document_juridique', 'Document juridique', 'organisation', 'administratif', [], DOC_EXT),
    ('convention', 'Convention', 'organisation', 'administratif', [], DOC_EXT),
    ('dossier_rh', 'Dossier RH', 'organisation', 'administratif', [], DOC_EXT),

    ('budget', 'Budget', 'organisation', 'financier', [], DOC_EXT),
    ('facture', 'Facture', 'organisation', 'financier', [], DOC_EXT),
    ('justificatif', 'Justificatif', 'organisation', 'financier', [], DOC_EXT),
    ('rapport_financier', 'Rapport financier', 'organisation', 'financier', [], DOC_EXT),

    ('inventaire', 'Inventaire', 'organisation', 'logistique', [], DOC_EXT),
    ('bon_livraison', 'Bon de livraison', 'organisation', 'logistique', [], DOC_EXT),
    ('suivi_vehicule_materiel', 'Suivi de véhicule ou de matériel', 'organisation', 'logistique', [], DOC_EXT),
]


def creer_categories(apps, schema_editor):
    Categorie = apps.get_model('sync', 'CategorieFichier')
    for code, libelle, portee, domaine, entity_types, extensions in CATEGORIES:
        Categorie.objects.update_or_create(
            code=code,
            defaults={
                'libelle': libelle, 'portee': portee, 'domaine': domaine,
                'entity_types': entity_types, 'extensions': extensions, 'actif': True,
            },
        )


def supprimer_categories(apps, schema_editor):
    Categorie = apps.get_model('sync', 'CategorieFichier')
    # Une catégorie déjà utilisée par un fichier est protégée (PROTECT) : on ne force rien.
    Categorie.objects.filter(code__in=[c[0] for c in CATEGORIES], fichiers__isnull=True).delete()


# (table, entity_type, colonne de l'ouvrage : 'none' | 'self' | nom de colonne)
TABLES_SUIVIES = [
    ('regions', 'region', 'none'),
    ('districts', 'district', 'none'),
    ('communes', 'commune', 'none'),
    ('fokontanys', 'fokontany', 'none'),
    ('villages', 'village', 'none'),
    ('ouvrages', 'ouvrage', 'self'),
    ('equipements_constitutifs', 'equipement', 'ouvrage_id'),
    ('pointseaus', 'point_eau', 'ouvrageid'),
    ('activites', 'activite', 'none'),
]

FN_OUVRAGE_ORGS = """
CREATE OR REPLACE FUNCTION sync_ouvrage_orgs(p_ouvrage uuid) RETURNS uuid[] AS $$
DECLARE
    v_orgs uuid[];
    v_public boolean;
BEGIN
    IF p_ouvrage IS NULL THEN
        RETURN ARRAY[NULL]::uuid[];
    END IF;
    SELECT COALESCE(array_agg(DISTINCT m.gestionnaire_id) FILTER (WHERE m.gestionnaire_id IS NOT NULL), '{}'::uuid[]),
           COALESCE(bool_or(m.gestionnaire_id IS NULL), false)
      INTO v_orgs, v_public
      FROM modalitesgestions m
     WHERE m.ouvrage_id = p_ouvrage
       AND m.statut = 'actif'
       AND m.date_debut <= CURRENT_DATE
       AND (m.date_fin IS NULL OR m.date_fin >= CURRENT_DATE);
    IF v_public THEN
        v_orgs := v_orgs || ARRAY[NULL]::uuid[];
    END IF;
    RETURN v_orgs;
END;
$$ LANGUAGE plpgsql STABLE;
"""

FN_LOG_CHANGE = """
CREATE OR REPLACE FUNCTION sync_log_change() RETURNS trigger AS $$
DECLARE
    v jsonb;
    v_id uuid;
    v_action text;
    v_orgs uuid[];
    v_org uuid;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v := to_jsonb(OLD);
        v_action := 'delete';
    ELSIF TG_OP = 'INSERT' THEN
        v := to_jsonb(NEW);
        v_action := 'insert';
    ELSE
        IF to_jsonb(NEW) = to_jsonb(OLD) THEN
            RETURN NULL;
        END IF;
        v := to_jsonb(NEW);
        v_action := 'update';
    END IF;
    v_id := (v->>'id')::uuid;

    IF TG_ARGV[1] = 'none' THEN
        v_orgs := ARRAY[NULL]::uuid[];
    ELSIF TG_ARGV[1] = 'self' THEN
        v_orgs := sync_ouvrage_orgs(v_id);
    ELSE
        v_orgs := sync_ouvrage_orgs(NULLIF(v->>TG_ARGV[1], '')::uuid);
    END IF;

    FOREACH v_org IN ARRAY v_orgs LOOP
        INSERT INTO sync_changes (organisation_id, portee, entity_type, entity_id, domaine, fichier_id, action, created_at)
        VALUES (v_org, 'entite', TG_ARGV[0], v_id, NULL, NULL, v_action, now());
    END LOOP;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

FN_LOG_MODALITE = """
CREATE OR REPLACE FUNCTION sync_log_modalite() RETURNS trigger AS $$
DECLARE
    v_ouvrage uuid;
    v_orgs uuid[];
    v_org uuid;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_ouvrage := OLD.ouvrage_id;
    ELSE
        v_ouvrage := NEW.ouvrage_id;
        IF TG_OP = 'UPDATE' AND to_jsonb(NEW) = to_jsonb(OLD) THEN
            RETURN NULL;
        END IF;
    END IF;

    v_orgs := sync_ouvrage_orgs(v_ouvrage);
    FOREACH v_org IN ARRAY v_orgs LOOP
        INSERT INTO sync_changes (organisation_id, portee, entity_type, entity_id, domaine, fichier_id, action, created_at)
        VALUES (v_org, 'entite', 'ouvrage', v_ouvrage, NULL, NULL, 'update', now());
    END LOOP;

    -- L'ancien gestionnaire qui perd l'accès doit retirer l'ouvrage de son ordinateur.
    IF TG_OP IN ('UPDATE', 'DELETE') AND OLD.gestionnaire_id IS NOT NULL
       AND NOT COALESCE(OLD.gestionnaire_id = ANY(array_remove(v_orgs, NULL)), false) THEN
        INSERT INTO sync_changes (organisation_id, portee, entity_type, entity_id, domaine, fichier_id, action, created_at)
        VALUES (OLD.gestionnaire_id, 'entite', 'ouvrage', v_ouvrage, NULL, NULL, 'delete', now());
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

FN_LOG_FICHIER = """
CREATE OR REPLACE FUNCTION sync_log_fichier() RETURNS trigger AS $$
DECLARE
    v_action text;
    v_ouvrage uuid;
    v_orgs uuid[];
    v_org uuid;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_action := 'insert';
    ELSE
        IF to_jsonb(NEW) = to_jsonb(OLD) THEN
            RETURN NULL;
        END IF;
        IF NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL THEN
            v_action := 'delete';
        ELSIF NEW.deleted_at IS NOT NULL THEN
            RETURN NULL;
        ELSE
            v_action := 'update';
        END IF;
    END IF;

    v_orgs := ARRAY[NEW.organisation_id];
    IF NEW.portee = 'entite' THEN
        v_ouvrage := CASE NEW.entity_type
            WHEN 'ouvrage' THEN NEW.entity_id
            WHEN 'equipement' THEN (SELECT e.ouvrage_id FROM equipements_constitutifs e WHERE e.id = NEW.entity_id)
            WHEN 'point_eau' THEN (SELECT p.ouvrageid FROM pointseaus p WHERE p.id = NEW.entity_id)
            ELSE NULL
        END;
        IF v_ouvrage IS NOT NULL THEN
            v_orgs := v_orgs || array_remove(sync_ouvrage_orgs(v_ouvrage), NULL);
        END IF;
    END IF;

    FOR v_org IN SELECT DISTINCT u FROM unnest(v_orgs) AS u LOOP
        INSERT INTO sync_changes (organisation_id, portee, entity_type, entity_id, domaine, fichier_id, action, created_at)
        VALUES (v_org, NEW.portee, NEW.entity_type, NEW.entity_id, NEW.domaine, NEW.id, v_action, now());
    END LOOP;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

FN_VERIFIER_FICHIER = """
CREATE OR REPLACE FUNCTION sync_verifier_fichier() RETURNS trigger AS $$
DECLARE
    c categories_fichiers%ROWTYPE;
BEGIN
    SELECT * INTO c FROM categories_fichiers WHERE code = NEW.categorie;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Catégorie de fichier inconnue : %', NEW.categorie USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' AND NOT c.actif THEN
        RAISE EXCEPTION 'Catégorie de fichier désactivée : %', NEW.categorie USING ERRCODE = '23514';
    END IF;
    IF c.portee <> NEW.portee THEN
        RAISE EXCEPTION 'La catégorie % est de portée %, pas %', NEW.categorie, c.portee, NEW.portee
            USING ERRCODE = '23514';
    END IF;
    IF NEW.portee = 'organisation' AND c.domaine IS DISTINCT FROM NEW.domaine THEN
        RAISE EXCEPTION 'La catégorie % appartient au domaine %, pas %', NEW.categorie, c.domaine, NEW.domaine
            USING ERRCODE = '23514';
    END IF;
    IF NEW.portee = 'entite' AND jsonb_array_length(c.entity_types) > 0
       AND NOT jsonb_exists(c.entity_types, NEW.entity_type) THEN
        RAISE EXCEPTION 'La catégorie % n''accepte pas le type d''entité %', NEW.categorie, NEW.entity_type
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def _sql_avant():
    instructions = [FN_OUVRAGE_ORGS, FN_LOG_CHANGE, FN_LOG_MODALITE, FN_LOG_FICHIER, FN_VERIFIER_FICHIER]
    for table, entity_type, colonne in TABLES_SUIVIES:
        instructions.append(f"DROP TRIGGER IF EXISTS sync_trg_{table} ON {table};")
        instructions.append(
            f"CREATE TRIGGER sync_trg_{table} AFTER INSERT OR UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE PROCEDURE sync_log_change('{entity_type}', '{colonne}');"
        )
    instructions += [
        "DROP TRIGGER IF EXISTS sync_trg_modalitesgestions ON modalitesgestions;",
        "CREATE TRIGGER sync_trg_modalitesgestions AFTER INSERT OR UPDATE OR DELETE ON modalitesgestions "
        "FOR EACH ROW EXECUTE PROCEDURE sync_log_modalite();",
        "DROP TRIGGER IF EXISTS sync_trg_fichiers_verifier ON fichiers;",
        "CREATE TRIGGER sync_trg_fichiers_verifier BEFORE INSERT OR UPDATE ON fichiers "
        "FOR EACH ROW EXECUTE PROCEDURE sync_verifier_fichier();",
        "DROP TRIGGER IF EXISTS sync_trg_fichiers ON fichiers;",
        "CREATE TRIGGER sync_trg_fichiers AFTER INSERT OR UPDATE ON fichiers "
        "FOR EACH ROW EXECUTE PROCEDURE sync_log_fichier();",
    ]
    return instructions


def _sql_inverse():
    instructions = [
        "DROP TRIGGER IF EXISTS sync_trg_fichiers ON fichiers;",
        "DROP TRIGGER IF EXISTS sync_trg_fichiers_verifier ON fichiers;",
        "DROP TRIGGER IF EXISTS sync_trg_modalitesgestions ON modalitesgestions;",
    ]
    for table, _entity_type, _colonne in TABLES_SUIVIES:
        instructions.append(f"DROP TRIGGER IF EXISTS sync_trg_{table} ON {table};")
    instructions += [
        "DROP FUNCTION IF EXISTS sync_verifier_fichier();",
        "DROP FUNCTION IF EXISTS sync_log_fichier();",
        "DROP FUNCTION IF EXISTS sync_log_modalite();",
        "DROP FUNCTION IF EXISTS sync_log_change();",
        "DROP FUNCTION IF EXISTS sync_ouvrage_orgs(uuid);",
    ]
    return instructions


class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0001_tables_initiales'),
        # Les triggers lisent/écrivent ces tables : on s'appuie sur leurs dernières migrations.
        ('organization', '0039_base_lieu_depart'),
        ('geography', '0019_contours_admin_cle_longue'),
        ('infrastructure', '0029_merge_20260726_1812'),
        ('billing', '0093_etalonnage_compteur_facultatif'),
        ('planning', '0067_terrain_contributions'),
    ]

    operations = [
        migrations.RunPython(creer_categories, supprimer_categories),
        migrations.RunSQL(sql=_sql_avant(), reverse_sql=_sql_inverse()),
    ]
