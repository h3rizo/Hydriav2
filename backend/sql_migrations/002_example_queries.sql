-- Requêtes d'exemple pour la gestion des fichiers
-- Date: 2025-09-11

-- ========================================
-- REQUÊTES D'EXEMPLE
-- ========================================

-- 1. Tous les fichiers ayant un certain tag
-- Exemple: Tous les fichiers avec le tag "documents"
SELECT f.id, f.filename, f.path, f.uploaded_at
FROM files f
INNER JOIN file_tags ft ON f.id = ft.file_id
INNER JOIN tags t ON ft.tag_id = t.id
WHERE t.name = 'documents'
ORDER BY f.uploaded_at DESC;

-- 2. Tous les fichiers ayant TOUS les tags d'une liste donnée
-- Exemple: Fichiers ayant à la fois les tags "contrat" ET "pdf"
SELECT f.id, f.filename, f.path, f.uploaded_at
FROM files f
WHERE f.id IN (
    SELECT ft.file_id
    FROM file_tags ft
    INNER JOIN tags t ON ft.tag_id = t.id
    WHERE t.name IN ('contrat', 'pdf')
    GROUP BY ft.file_id
    HAVING COUNT(DISTINCT t.name) = 2  -- Nombre de tags recherchés
)
ORDER BY f.uploaded_at DESC;

-- 3. Tous les fichiers avec leurs tags (requête complète pour l'affichage)
SELECT 
    f.id,
    f.filename,
    f.path,
    f.uploaded_at,
    STRING_AGG(t.name, ', ') AS tags
FROM files f
LEFT JOIN file_tags ft ON f.id = ft.file_id
LEFT JOIN tags t ON ft.tag_id = t.id
GROUP BY f.id, f.filename, f.path, f.uploaded_at
ORDER BY f.uploaded_at DESC;

-- 4. Recherche de fichiers par nom ET tags
-- Exemple: Fichiers dont le nom contient "rapport" ET qui ont le tag "important"
SELECT DISTINCT f.id, f.filename, f.path, f.uploaded_at
FROM files f
LEFT JOIN file_tags ft ON f.id = ft.file_id
LEFT JOIN tags t ON ft.tag_id = t.id
WHERE 
    f.filename ILIKE '%rapport%'
    AND (t.name = 'important' OR ft.tag_id IS NULL)
ORDER BY f.uploaded_at DESC;

-- 5. Tags les plus utilisés
SELECT 
    t.name,
    COUNT(ft.file_id) AS usage_count
FROM tags t
LEFT JOIN file_tags ft ON t.id = ft.tag_id
GROUP BY t.id, t.name
ORDER BY usage_count DESC, t.name ASC;

-- 6. Fichiers sans tags
SELECT f.id, f.filename, f.path, f.uploaded_at
FROM files f
LEFT JOIN file_tags ft ON f.id = ft.file_id
WHERE ft.file_id IS NULL
ORDER BY f.uploaded_at DESC;

-- ========================================
-- FONCTIONS UTILITAIRES
-- ========================================

-- Fonction pour rechercher des fichiers par tags multiples
-- Usage: SELECT * FROM search_files_by_tags(ARRAY['pdf', 'contrat']);
CREATE OR REPLACE FUNCTION search_files_by_tags(tag_names TEXT[])
RETURNS TABLE(
    id BIGINT,
    filename TEXT,
    path TEXT,
    uploaded_at TIMESTAMP WITH TIME ZONE,
    tags TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        f.id,
        f.filename,
        f.path,
        f.uploaded_at,
        STRING_AGG(t.name, ', ') AS tags
    FROM files f
    LEFT JOIN file_tags ft ON f.id = ft.file_id
    LEFT JOIN tags t ON ft.tag_id = t.id
    WHERE f.id IN (
        SELECT ft2.file_id
        FROM file_tags ft2
        INNER JOIN tags t2 ON ft2.tag_id = t2.id
        WHERE t2.name = ANY(tag_names)
        GROUP BY ft2.file_id
        HAVING COUNT(DISTINCT t2.name) = array_length(tag_names, 1)
    )
    GROUP BY f.id, f.filename, f.path, f.uploaded_at
    ORDER BY f.uploaded_at DESC;
END;
$$ LANGUAGE plpgsql;

-- Fonction pour obtenir tous les tags d'un fichier
CREATE OR REPLACE FUNCTION get_file_tags(file_id_param BIGINT)
RETURNS TEXT[] AS $$
DECLARE
    tag_array TEXT[];
BEGIN
    SELECT ARRAY_AGG(t.name)
    INTO tag_array
    FROM file_tags ft
    INNER JOIN tags t ON ft.tag_id = t.id
    WHERE ft.file_id = file_id_param;
    
    RETURN COALESCE(tag_array, ARRAY[]::TEXT[]);
END;
$$ LANGUAGE plpgsql;