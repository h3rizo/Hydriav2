"""
Test du contexte conversationnel - Follow-up sur questions précédentes
"""
import os
import django
import json
import asyncio

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from chatbot.services.ai_assistant import AIAssistant

async def test_conversation():
    """Test d'une conversation avec contexte"""
    ai_assistant = AIAssistant()

    # Contexte de session partagé entre les messages
    session_context = {}

    conversations = [
        {
            "scenario": "Scenario 1: Question simple puis demande de details",
            "messages": [
                "Combien de points d'eau à Ambato",
                "Tu peux me donner les détails de ce calcul?"
            ]
        },
        {
            "scenario": "Scenario 2: Variante avec 'explique'",
            "messages": [
                "Combien de points d'eau à Ambato",
                "Explique moi comment tu arrives à ce résultat"
            ]
        },
        {
            "scenario": "Scenario 3: Variante avec 'par ouvrage'",
            "messages": [
                "Combien de points d'eau à Ambato",
                "Par ouvrage stp"
            ]
        }
    ]

    for conv in conversations:
        print(f"\n{'='*80}")
        print(f"[TEST] {conv['scenario']}")
        print('='*80)

        # Réinitialiser le contexte pour chaque scénario
        session_context = {}

        for i, message in enumerate(conv['messages']):
            print(f"\n[Q{i+1}] {message}")

            try:
                result = await ai_assistant.process_message(message, session_context)

                print(f"[OK] Success: {result.get('success')}")
                print(f"[OK] Type: {result.get('metadata', {}).get('type')}")

                # Afficher résumé de la réponse
                response = result.get('response', '')
                lines = response.split('\n')
                print(f"[REPONSE] {lines[0][:100]}...")

                # Si détails, afficher le nombre d'ouvrages
                metadata = result.get('metadata', {})
                if 'ouvrages_count' in metadata:
                    print(f"[OK] Nombre d'ouvrages: {metadata['ouvrages_count']}")

            except Exception as e:
                print(f"[ERROR] Exception: {str(e)}")
                import traceback
                traceback.print_exc()

        print(f"\n[CONTEXTE] Derniere question: {session_context.get('last_query', 'N/A')[:50]}")
        print(f"[CONTEXTE] Type derniere reponse: {session_context.get('last_result', {}).get('metadata', {}).get('type', 'N/A')}")

if __name__ == '__main__':
    asyncio.run(test_conversation())
