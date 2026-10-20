"""
Test de la question sur les points d'eau à Ambato
"""
import os
import django
import json
import asyncio

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from chatbot.services.ai_assistant import AIAssistant

async def test_question():
    """Test de la question"""
    ai_assistant = AIAssistant()

    question = "Combien de points d'eau à Ambato"

    print(f"Question: {question}")
    print("="*60)

    try:
        result = await ai_assistant.process_message(question)

        # Sauvegarder dans JSON
        filename = "test_result_points_eau_ambato.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"Success: {result.get('success')}")
        print(f"Type: {result.get('metadata', {}).get('type')}")
        print(f"Response saved in: {filename}")

    except Exception as e:
        print(f"[ERROR] Exception: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_question())
