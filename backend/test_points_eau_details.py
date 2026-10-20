"""
Test du système de détails pour les points d'eau
"""
import os
import django
import json
import asyncio

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from chatbot.services.ai_assistant import AIAssistant

async def test_questions():
    """Test des questions avec et sans détails"""
    ai_assistant = AIAssistant()

    questions = [
        "Combien de points d'eau à Ambato",
        "Combien de points d'eau à Ambato détail",
        "Liste des points d'eau par ouvrage à Ambato",
        "Donne moi les détails des points d'eau à Ambato",
    ]

    for question in questions:
        print(f"\n{'='*80}")
        print(f"Question: {question}")
        print('='*80)

        try:
            result = await ai_assistant.process_message(question)

            # Sauvegarder dans JSON
            filename = f"test_result_pe_{question.replace(' ', '_').replace('?', '').replace("'", '')[:50]}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            print(f"[OK] Success: {result.get('success')}")
            print(f"[OK] Type: {result.get('metadata', {}).get('type')}")

            # Afficher la réponse
            print(f"\nReponse:")
            print(result.get('response', ''))

            # Si détails, afficher les infos supplémentaires
            metadata = result.get('metadata', {})
            if 'ouvrages_count' in metadata:
                print(f"\n[OK] Nombre d'ouvrages: {metadata['ouvrages_count']}")
                print(f"[OK] Details par ouvrage: {list(metadata.get('details', {}).keys())[:3]}...")

            print(f"\n[OK] Resultat sauvegarde dans: {filename}")

        except Exception as e:
            print(f"[ERROR] Exception: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_questions())
