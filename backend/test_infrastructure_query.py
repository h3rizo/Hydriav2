"""
Test des requêtes sur les infrastructures
"""
import os
import django
import json
import asyncio

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from chatbot.services.ai_assistant import AIAssistant

async def test_infrastructure_queries():
    """Test des requêtes sur les infrastructures"""
    ai_assistant = AIAssistant()

    # Test avec différentes questions
    questions = [
        "Quels sont les types d'ouvrages disponibles?",
        "Liste les types de points d'eau",
        "Quels sont les types d'équipements?",
        "Quels ouvrages ont un compteur de tête?"
    ]

    for question in questions:
        print(f"\n{'='*60}")
        print(f"Question: {question}")
        print('='*60)

        try:
            result = await ai_assistant.process_message(question)

            # Sauvegarder dans JSON pour éviter problèmes d'encodage
            filename = f"test_result_infra_{question[:30].replace(' ', '_').replace('?', '')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            print(f"Success: {result.get('success')}")
            print(f"Type: {result.get('metadata', {}).get('type')}")
            if result.get('success'):
                print(f"Resultat sauvegarde dans: {filename}")
            else:
                print(f"Erreur: {result.get('response')}")
        except Exception as e:
            print(f"[ERROR] Exception: {str(e)}")

if __name__ == '__main__':
    asyncio.run(test_infrastructure_queries())
