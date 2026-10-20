"""
Test final du chatbot après corrections
"""
import os
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from chatbot.services.geography_queries import GeographyQueries
from chatbot.services.ai_assistant import AIAssistant
import asyncio
import json

def test_geography_direct():
    """Test direct des requêtes géographiques"""
    print("\n=== TEST 1: GeographyQueries direct ===")
    gq = GeographyQueries()

    # Test avec "a" sans accent
    result1 = gq.process_query("combien d habitants a Ambato")
    print(f"[RESULTAT] Success: {result1.get('success')}")
    print(f"[RESULTAT] Location: {result1.get('metadata', {}).get('location')}")
    print(f"[RESULTAT] Population: {result1.get('metadata', {}).get('population')}")

    # Test avec "à" avec accent
    result2 = gq.process_query("combien d habitants à Ambato")
    print(f"\n[RESULTAT AVEC ACCENT] Success: {result2.get('success')}")
    print(f"[RESULTAT AVEC ACCENT] Population: {result2.get('metadata', {}).get('population')}")

    return result1.get('success') and result2.get('success')

async def test_ai_assistant():
    """Test via AIAssistant (comme dans l'interface web)"""
    print("\n=== TEST 2: AIAssistant complet ===")
    ai = AIAssistant()

    # Test avec "a" sans accent
    result = await ai.process_message("combien d habitants a Ambato")
    print(f"[AI RESULTAT] Success: {result.get('success')}")

    # Sauvegarder le résultat
    with open('test_chatbot_result_final.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[AI RESULTAT] Sauvegardé dans test_chatbot_result_final.json")
    return result.get('success')

if __name__ == '__main__':
    # Test 1
    success1 = test_geography_direct()

    # Test 2
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    success2 = loop.run_until_complete(test_ai_assistant())
    loop.close()

    # Résumé
    print("\n" + "="*50)
    print("RÉSUMÉ DES TESTS")
    print("="*50)
    print(f"Test GeographyQueries: {'✓ PASS' if success1 else '✗ FAIL'}")
    print(f"Test AIAssistant:      {'✓ PASS' if success2 else '✗ FAIL'}")
    print(f"\nTOUS LES TESTS:        {'✓ PASS' if success1 and success2 else '✗ FAIL'}")
    print("="*50)
