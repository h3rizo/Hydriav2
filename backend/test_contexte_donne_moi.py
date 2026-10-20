"""
Test du contexte conversationnel - Cas "donne moi les détails"
"""
import os
import django
import asyncio

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from chatbot.services.ai_assistant import AIAssistant

async def test_donne_moi():
    """Test du cas spécifique 'donne moi les détails'"""
    ai_assistant = AIAssistant()
    session_context = {}

    print("="*80)
    print("TEST: Question 'donne moi les détails par ouvrage'")
    print("="*80)

    # Question 1
    print("\n[Q1] Combien de points d'eau à Ambato")
    result1 = await ai_assistant.process_message("Combien de points d'eau à Ambato", session_context)
    print(f"[OK] Success: {result1.get('success')}")
    print(f"[OK] Type: {result1.get('metadata', {}).get('type')}")

    # Question 2
    print("\n[Q2] donne moi les détails par ouvrage")
    result2 = await ai_assistant.process_message("donne moi les détails par ouvrage", session_context)
    print(f"[OK] Success: {result2.get('success')}")
    print(f"[OK] Type: {result2.get('metadata', {}).get('type')}")

    metadata = result2.get('metadata', {})
    if 'ouvrages_count' in metadata:
        print(f"[OK] FOLLOW-UP DETECTE - Nombre d'ouvrages: {metadata['ouvrages_count']}")
    else:
        print(f"[ERROR] FOLLOW-UP NON DETECTE - Mauvaise reponse")

    print(f"\n[CONTEXTE] Dernière question: {session_context.get('last_query', 'N/A')}")
    print(f"[CONTEXTE] Type dernière réponse: {session_context.get('last_result', {}).get('metadata', {}).get('type', 'N/A')}")

    # Test avec nouvelle question
    print("\n" + "="*80)
    print("TEST: Nouvelle question avec détail (doit créer NOUVELLE requête)")
    print("="*80)

    session_context2 = {}
    print("\n[Q] Combien de points d'eau à Ankazomanga détail")
    result3 = await ai_assistant.process_message("Combien de points d'eau à Ankazomanga détail", session_context2)
    print(f"[OK] Success: {result3.get('success')}")
    print(f"[OK] Type: {result3.get('metadata', {}).get('type')}")

    metadata3 = result3.get('metadata', {})
    if metadata3.get('type') == 'points_eau_details':
        print(f"[OK] NOUVELLE QUESTION DETECTEE - Details directs pour Ankazomanga")
    else:
        print(f"[ERROR] Devrait etre une nouvelle question avec details")

if __name__ == '__main__':
    asyncio.run(test_donne_moi())
