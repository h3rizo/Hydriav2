"""
Test des requêtes analytiques - Tableaux, graphiques, évolutions
"""
import os
import django
import json
import asyncio

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from chatbot.services.ai_assistant import AIAssistant

async def test_analytics():
    """Test des requêtes analytiques complexes"""
    ai_assistant = AIAssistant()
    session_context = {}

    questions = [
        {
            "titre": "Evolution de la consommation",
            "question": "Montre moi l'évolution de la consommation d'eau par année"
        },
        {
            "titre": "Evolution points d'eau Ambato",
            "question": "Évolution du nombre de points d'eau à Ambato"
        },
        {
            "titre": "Tableau comparatif communes",
            "question": "Tableau comparatif des communes"
        },
        {
            "titre": "Tableau ouvrages Ambato",
            "question": "Liste des ouvrages à Ambato"
        },
        {
            "titre": "Top 10 communes - Points d'eau",
            "question": "Top 10 des communes par nombre de points d'eau"
        },
        {
            "titre": "Top 5 communes - Consommation 2024",
            "question": "Top 5 des communes par consommation en 2024"
        }
    ]

    for test in questions:
        print("\n" + "="*80)
        print(f"[TEST] {test['titre']}")
        print("="*80)
        print(f"[QUESTION] {test['question']}")

        try:
            result = await ai_assistant.process_message(test['question'], session_context)

            print(f"\n[OK] Success: {result.get('success')}")
            print(f"[OK] Type: {result.get('metadata', {}).get('type')}")

            # Afficher un extrait de la réponse
            response = result.get('response', '')
            if response:
                lines = response.split('\n')
                print(f"\n[REPONSE] Extrait (10 premieres lignes):")
                for line in lines[:10]:
                    print(f"  {line}")
                if len(lines) > 10:
                    print(f"  ... ({len(lines) - 10} lignes supplémentaires)")

            # Afficher les métadonnées intéressantes
            metadata = result.get('metadata', {})
            if 'data_graphique' in metadata:
                graphique = metadata['data_graphique']
                print(f"\n[GRAPHIQUE] Données disponibles:")
                print(f"  - Labels: {graphique.get('labels', [])[:5]}..." if len(graphique.get('labels', [])) > 5 else f"  - Labels: {graphique.get('labels', [])}")
                for key in graphique:
                    if key != 'labels':
                        values = graphique[key]
                        if isinstance(values, list) and len(values) > 0:
                            print(f"  - {key}: {values[:3]}..." if len(values) > 3 else f"  - {key}: {values}")

            if 'tableau' in metadata:
                nb_rows = len(metadata['tableau'])
                print(f"\n[TABLEAU] {nb_rows} ligne(s) de données")

            if 'classement' in metadata:
                nb_items = len(metadata['classement'])
                print(f"\n[CLASSEMENT] {nb_items} élément(s)")

            # Sauvegarder dans JSON
            filename = f"test_analytics_{test['titre'].replace(' ', '_').replace('é', 'e').replace('è', 'e')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n[OK] Resultat sauvegarde dans: {filename}")

        except Exception as e:
            print(f"\n[ERROR] Exception: {str(e)}")
            import traceback
            traceback.print_exc()

    # Test de follow-up
    print("\n" + "="*80)
    print("[TEST] Follow-up sur evolution")
    print("="*80)

    # Question initiale
    print("\n[Q1] Évolution de la consommation à Ambato")
    result1 = await ai_assistant.process_message("Évolution de la consommation à Ambato", session_context)
    print(f"[OK] Type: {result1.get('metadata', {}).get('type')}")

    # Follow-up
    print("\n[Q2] Montre moi le graphique")
    result2 = await ai_assistant.process_message("Montre moi le graphique", session_context)
    print(f"[OK] Type: {result2.get('metadata', {}).get('type')}")

    if result2.get('metadata', {}).get('data_graphique'):
        print("[OK] FOLLOW-UP DETECTE - Données graphique disponibles")
    else:
        print("[WARNING] Follow-up non détecté ou pas de données graphique")

if __name__ == '__main__':
    asyncio.run(test_analytics())
