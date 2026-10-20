# Migration Supabase - Chatbot Hydria

## Instructions pour exécuter la migration SQL

### Étape 1: Accéder à Supabase
1. Connectez-vous à votre tableau de bord Supabase : https://app.supabase.com
2. Sélectionnez le projet Hydria
3. Allez dans l'onglet **SQL Editor**

### Étape 2: Exécuter le script de migration
1. Créez une nouvelle query dans l'éditeur SQL
2. Copiez et collez tout le contenu du fichier `backend/sql_migrations/001_create_chat_tables.sql`
3. Cliquez sur **Run** pour exécuter la migration

### Étape 3: Vérifier la création des tables
Après l'exécution, vérifiez que les tables ont été créées :

```sql
-- Vérifier l'existence des tables
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('chat_sessions', 'chat_messages');

-- Vérifier la structure des tables
\d public.chat_sessions
\d public.chat_messages
```

### Étape 4: Vérifier les politiques RLS
```sql
-- Vérifier les politiques de sécurité
SELECT schemaname, tablename, policyname, roles, cmd 
FROM pg_policies 
WHERE tablename IN ('chat_sessions', 'chat_messages');
```

### Étape 5: Test des permissions
Vous pouvez tester que tout fonctionne avec cette requête :

```sql
-- Test d'insertion (remplacez l'UUID par un utilisateur existant)
INSERT INTO public.chat_sessions (user_id, title) 
VALUES ('your-user-uuid-here', 'Test Session');
```

## Résolution de problèmes courants

### Si vous obtenez une erreur de permissions :
- Vérifiez que RLS est activé sur les tables
- Vérifiez que les politiques sont correctement créées
- Assurez-vous que l'utilisateur authentifié existe

### Si les triggers ne fonctionnent pas :
```sql
-- Vérifier les triggers
SELECT trigger_name, table_name, action_timing, event_manipulation 
FROM information_schema.triggers 
WHERE table_name IN ('chat_sessions', 'chat_messages');
```

### Structure finale attendue :

**Tables créées :**
- `public.chat_sessions` - Sessions de chat
- `public.chat_messages` - Messages individuels

**Fonctions créées :**
- `public.handle_updated_at()` - Met à jour automatiquement le timestamp
- `public.generate_session_title()` - Génère automatiquement les titres

**Index créés :**
- Performance optimisée pour les requêtes fréquentes
- Index sur user_id, session_id, dates

**Politiques RLS :**
- Sécurité au niveau ligne activée
- Utilisateurs voient seulement leurs propres données

## Commandes Django après migration

Une fois la migration Supabase terminée, vous pouvez tester depuis Django :

```python
# Dans le shell Django (python manage.py shell)
from chatbot.models import ChatSession, ChatMessage
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.first()

# Créer une session test
session = ChatSession.objects.create(
    user=user,
    title="Test depuis Django"
)

# Créer un message test  
message = ChatMessage.objects.create(
    session=session,
    role="user",
    content="Bonjour, ceci est un test"
)

print(f"Session créée: {session.id}")
print(f"Message créé: {message.id}")
```