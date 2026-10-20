import os
# Pour un projet réel, utilisez openai ou langchain. Ceci est un service simulant les appels LLM.
# pip install openai
# from openai import OpenAI

# client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def generate_embedding(text):
    """
    Appelle l'API d'embeddings (ex: text-embedding-3-small).
    Retourne un vecteur de dimension 1536.
    """
    if not text.strip():
        return None
    
    '''
    # Vraie implémentation OpenAI
    response = client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )
    return response.data[0].embedding
    '''
    
    # Simulation pour le prototype
    return [0.0] * 1536 

def generate_summary(text):
    """
    Demande au LLM (ex: gpt-4o-mini) de résumer le contenu de la note.
    """
    if not text.strip():
        return "Pas de contenu à résumer."
        
    '''
    # Vraie implémentation OpenAI
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Tu es un assistant expert en gestion de réseau d'eau. Résume cette note d'intervention/réunion en 3 points clés."},
            {"role": "user", "content": text}
        ]
    )
    return response.choices[0].message.content
    '''
    
    # Simulation
    return "Résumé simulé par l'IA : \n- Point 1\n- Point 2\n- Point 3"

def ask_assistant(note_text, user_question):
    """
    Pose une question à l'IA en lui donnant le texte de la note comme contexte.
    """
    '''
    # Vraie implémentation OpenAI
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"Tu es un assistant Hydria. Voici le contexte actuel de la note :\n\n{note_text}\n\nRéponds de manière concise à la question de l'utilisateur en te basant sur ce contexte."},
            {"role": "user", "content": user_question}
        ]
    )
    return response.choices[0].message.content
    '''
    
    # Simulation
    return f"Réponse IA simulée à votre question : '{user_question}'. Le contexte a bien été analysé."
