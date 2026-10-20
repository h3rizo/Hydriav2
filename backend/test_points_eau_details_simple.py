"""
Test du système de détails pour les points d'eau (version simplifiée sans emojis)
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
        ("Question simple", "Combien de points d'eau à Ambato"),
        ("Avec 'détail'", "Combien de points d'eau à Ambato détail"),
        ("Avec 'par ouvrage'", "Liste des points d'eau par ouvrage à Ambato"),
        ("Avec 'détails'", "Donne moi les détails des points d'eau à Ambato"),
    ]

    for label, question in questions:
        print(f"\n{'='*80}")
        print(f"[TEST] {label}: {question}")
        print('='*80)

        try:
            result = await ai_assistant.process_message(question)

            # Sauvegarder dans JSON
            filename = f"test_result_pe_{label.replace(' ', '_')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            print(f"[OK] Success: {result.get('success')}")
            print(f"[OK] Type: {result.get('metadata', {}).get('type')}")

            # Si détails, afficher les infos supplémentaires
            metadata = result.get('metadata', {})
            if 'ouvrages_count' in metadata:
                print(f"[OK] Nombre d'ouvrages: {metadata['ouvrages_count']}")
                print(f"[OK] Nombre de points d'eau: {metadata['count']}")

                # Afficher les 3 premiers ouvrages
                details = metadata.get('details', {})
                if details:
                    print(f"[OK] Premiers ouvrages:")
                    for i, (ouvrage, count) in enumerate(list(details.items())[:3]):
                        print(f"     {i+1}. {ouvrage}: {count} point(s) d'eau")

            print(f"[OK] Resultat sauvegarde dans: {filename}")

        except Exception as e:
            print(f"[ERROR] Exception: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_questions())
