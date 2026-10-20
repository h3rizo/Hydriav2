#!/usr/bin/env python
"""
Test complet du chatbot avec AIAssistant
"""
import os
import django
import asyncio

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from chatbot.services.ai_assistant import AIAssistant

async def test_chatbot():
    """Teste le chatbot complet"""
    assistant = AIAssistant()

    test_queries = [
        "Combien d'habitants à Ankazondandy",
        "Population de Ambanja",
        "Bonjour",
    ]

    print("=" * 60)
    print("TEST COMPLET DU CHATBOT")
    print("=" * 60)

    for query in test_queries:
        print(f"\n{'=' * 60}")
        print(f"Query: {query}")
        print("=" * 60)

        result = await assistant.process_message(query)

        print(f"\nSuccess: {result.get('success')}")

        # Enlever les emojis pour l'affichage console Windows
        response = result.get('response', '')
        if response:
            response = response.replace('🏘️', '[VILLAGE]').replace('📍', '[LOCATION]')
            print(f"\nResponse:\n{response}")

        # Afficher les métadonnées
        metadata = result.get('metadata', {})
        if metadata:
            print(f"\nMetadata:")
            for key, value in metadata.items():
                print(f"  {key}: {value}")

if __name__ == "__main__":
    asyncio.run(test_chatbot())
