-- Migration 001: Création des tables pour la gestion des fichiers
-- Date: 2025-09-11
-- Description: Tables pour stocker les fichiers avec système de tags

-- Table des fichiers
CREATE TABLE files (
    id BIGSERIAL PRIMARY KEY,
    path TEXT NOT NULL,
    bucket TEXT NOT NULL DEFAULT 'HydriaStock',
    filename TEXT NOT NULL,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table des tags
CREATE TABLE tags (
    id BIGSERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

-- Table de liaison file_tags (relation N-N)
CREATE TABLE file_tags (
    file_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    PRIMARY KEY (file_id, tag_id),
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

-- Indexes pour optimiser les requêtes
CREATE INDEX idx_tags_name ON tags(name);
CREATE INDEX idx_files_uploaded_at ON files(uploaded_at DESC);
CREATE INDEX idx_files_filename ON files(filename);
CREATE INDEX idx_file_tags_file_id ON file_tags(file_id);
CREATE INDEX idx_file_tags_tag_id ON file_tags(tag_id);

-- Commentaires pour la documentation
COMMENT ON TABLE files IS 'Table des fichiers stockés dans Supabase Storage';
COMMENT ON TABLE tags IS 'Table des tags pour catégoriser les fichiers';
COMMENT ON TABLE file_tags IS 'Table de liaison entre fichiers et tags (relation N-N)';

COMMENT ON COLUMN files.path IS 'Chemin complet du fichier dans le bucket Supabase Storage';
COMMENT ON COLUMN files.bucket IS 'Nom du bucket Supabase Storage (par défaut: HydriaStock)';
COMMENT ON COLUMN files.filename IS 'Nom original du fichier';
COMMENT ON COLUMN files.uploaded_at IS 'Date et heure d''upload du fichier';

COMMENT ON COLUMN tags.name IS 'Nom unique du tag';