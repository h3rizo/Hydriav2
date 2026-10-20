-- Migration: Création des tables pour le chatbot
-- Date: 2025-09-11
-- Description: Tables chat_sessions et chat_messages avec RLS policies

-- =====================================================
-- 1. Table chat_sessions
-- =====================================================

CREATE TABLE IF NOT EXISTS public.chat_sessions (
    id bigserial PRIMARY KEY,
    user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    ended_at timestamp with time zone,
    title text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

-- Index pour performances
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON public.chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_started_at ON public.chat_sessions(started_at DESC);

-- =====================================================
-- 2. Table chat_messages  
-- =====================================================

CREATE TABLE IF NOT EXISTS public.chat_messages (
    id bigserial PRIMARY KEY,
    session_id bigint REFERENCES public.chat_sessions(id) ON DELETE CASCADE NOT NULL,
    role text NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content text NOT NULL,
    metadata jsonb DEFAULT '{}',
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

-- Index pour performances
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON public.chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON public.chat_messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_role ON public.chat_messages(role);

-- =====================================================
-- 3. RLS (Row Level Security) Policies
-- =====================================================

-- Activer RLS sur les tables
ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;

-- Policies pour chat_sessions
-- Les utilisateurs peuvent voir leurs propres sessions
CREATE POLICY "Users can view own chat sessions" ON public.chat_sessions
    FOR SELECT USING (auth.uid() = user_id);

-- Les utilisateurs peuvent créer leurs propres sessions
CREATE POLICY "Users can create own chat sessions" ON public.chat_sessions
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Les utilisateurs peuvent modifier leurs propres sessions
CREATE POLICY "Users can update own chat sessions" ON public.chat_sessions
    FOR UPDATE USING (auth.uid() = user_id);

-- Les utilisateurs peuvent supprimer leurs propres sessions
CREATE POLICY "Users can delete own chat sessions" ON public.chat_sessions
    FOR DELETE USING (auth.uid() = user_id);

-- Policies pour chat_messages
-- Les utilisateurs peuvent voir les messages de leurs sessions
CREATE POLICY "Users can view messages from own sessions" ON public.chat_messages
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.chat_sessions 
            WHERE chat_sessions.id = chat_messages.session_id 
            AND chat_sessions.user_id = auth.uid()
        )
    );

-- Les utilisateurs peuvent créer des messages dans leurs sessions
CREATE POLICY "Users can create messages in own sessions" ON public.chat_messages
    FOR INSERT WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.chat_sessions 
            WHERE chat_sessions.id = chat_messages.session_id 
            AND chat_sessions.user_id = auth.uid()
        )
    );

-- Les utilisateurs peuvent modifier les messages de leurs sessions
CREATE POLICY "Users can update messages in own sessions" ON public.chat_messages
    FOR UPDATE USING (
        EXISTS (
            SELECT 1 FROM public.chat_sessions 
            WHERE chat_sessions.id = chat_messages.session_id 
            AND chat_sessions.user_id = auth.uid()
        )
    );

-- Les utilisateurs peuvent supprimer les messages de leurs sessions
CREATE POLICY "Users can delete messages in own sessions" ON public.chat_messages
    FOR DELETE USING (
        EXISTS (
            SELECT 1 FROM public.chat_sessions 
            WHERE chat_sessions.id = chat_messages.session_id 
            AND chat_sessions.user_id = auth.uid()
        )
    );

-- =====================================================
-- 4. Fonctions utilitaires
-- =====================================================

-- Fonction pour mettre à jour automatiquement updated_at
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger pour chat_sessions
CREATE TRIGGER handle_chat_sessions_updated_at
    BEFORE UPDATE ON public.chat_sessions
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- Fonction pour générer automatiquement un titre de session
CREATE OR REPLACE FUNCTION public.generate_session_title(session_id_param bigint)
RETURNS text AS $$
DECLARE
    first_user_message text;
    message_count integer;
BEGIN
    -- Récupérer le premier message utilisateur
    SELECT content INTO first_user_message
    FROM public.chat_messages 
    WHERE session_id = session_id_param 
    AND role = 'user' 
    ORDER BY created_at ASC 
    LIMIT 1;
    
    -- Compter le nombre de messages
    SELECT COUNT(*) INTO message_count
    FROM public.chat_messages 
    WHERE session_id = session_id_param;
    
    -- Générer le titre
    IF first_user_message IS NOT NULL THEN
        RETURN LEFT(first_user_message, 50) || CASE WHEN LENGTH(first_user_message) > 50 THEN '...' ELSE '' END;
    ELSE
        RETURN 'Nouvelle conversation (' || message_count || ' messages)';
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =====================================================
-- 5. Données de test (optionnel)
-- =====================================================

-- Insérer une session de test si l'utilisateur admin existe
-- (à adapter selon votre structure d'authentification)

-- =====================================================
-- 6. Permissions pour les rôles
-- =====================================================

-- Permettre au rôle authenticated d'utiliser les tables
GRANT SELECT, INSERT, UPDATE, DELETE ON public.chat_sessions TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.chat_messages TO authenticated;

-- Permettre l'utilisation des séquences
GRANT USAGE, SELECT ON SEQUENCE public.chat_sessions_id_seq TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE public.chat_messages_id_seq TO authenticated;