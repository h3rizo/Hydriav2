"""
Test final des requêtes analytiques - Validation après corrections
"""
import os
import django
import asyncio

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from chatbot.services.ai_assistant import AIAssistant

async def test_final():
    """Test final de validation des corrections"""
    ai_assistant = AIAssistant()
    session_context = {}

    tests = [
        {
            "nom": "Evolution consommation (avec accent)",
            "question": "Évolution de la consommation d'eau par année",
            "type_attendu": "evolution_consommation"
        },
        {
            "nom": "Evolution consommation (sans accent)",
            "question": "Evolution de la consommation d'eau par annee",
            "type_attendu": "evolution_consommation"
        },
        {
            "nom": "Tableau comparatif communes",
            "question": "Tableau comparatif des communes",
            "type_attendu": "tableau_communes"
        },
        {
            "nom": "Top 10 points d'eau (sans apostrophe)",
            "question": "Top 10 des communes par nombre de points d eau",
            "type_attendu": "classement_points_eau"
        },
        {
            "nom": "Top 5 consommation",
            "question": "Top 5 des communes par consommation en 2024",
            "type_attendu": "classement_consommation"
        },
        {
            "nom": "Evolution points d'eau (sans accent ni apostrophe)",
            "question": "Evolution du nombre de points d eau par annee",
            "type_attendu": "evolution_points_eau"
        }
    ]

    print("="*80)
    print("TEST FINAL - Validation corrections analytics")
    print("="*80)

    nb_succes = 0
    nb_total = len(tests)

    for test in tests:
        print(f"\n[TEST] {test['nom']}")
        print(f"[QUESTION] {test['question']}")

        try:
            result = await ai_assistant.process_message(test['question'], session_context)

            success = result.get('success')
            type_obtenu = result.get('metadata', {}).get('type')
            type_attendu = test['type_attendu']

            if success and type_obtenu == type_attendu:
                print(f"[OK] Success: {success} | Type: {type_obtenu}")
                nb_succes += 1
            else:
                print(f"[ERREUR] Success: {success} | Type attendu: {type_attendu} | Type obtenu: {type_obtenu}")

        except Exception as e:
            print(f"[EXCEPTION] {str(e)}")

    print("\n" + "="*80)
    print(f"RESULTAT FINAL: {nb_succes}/{nb_total} tests reussis ({nb_succes*100//nb_total}%)")
    print("="*80)

    if nb_succes == nb_total:
        print("\n[OK] TOUS LES TESTS SONT VALIDES")
    else:
        print(f"\n[ATTENTION] {nb_total - nb_succes} test(s) echoue(s)")

if __name__ == '__main__':
    asyncio.run(test_final())
