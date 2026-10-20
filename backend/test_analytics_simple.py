"""
Test simple des requêtes analytiques
"""
import os
import django
import json
import asyncio

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from chatbot.services.ai_assistant import AIAssistant

async def test_simple():
    """Test simple de l'évolution de consommation"""
    ai_assistant = AIAssistant()
    session_context = {}

    print("="*80)
    print("TEST : Evolution de la consommation d'eau")
    print("="*80)

    question = "Evolution de la consommation d'eau par annee"
    print(f"\n[QUESTION] {question}")

    result = await ai_assistant.process_message(question, session_context)

    print(f"\n[SUCCESS] {result.get('success')}")
    print(f"[TYPE] {result.get('metadata', {}).get('type')}")

    # Afficher le tableau
    metadata = result.get('metadata', {})
    if 'tableau' in metadata:
        tableau = metadata['tableau']
        print(f"\n[TABLEAU] {len(tableau)} annees de donnees:")
        print("\nAnnee | Total (m3) | Moyenne (m3) | Nb releves")
        print("-" * 60)
        for row in tableau:
            print(f"{row['annee']} | {row['total']:>12} | {row['moyenne']:>12} | {row['nb_releves']:>10}")

    # Afficher les données graphique
    if 'data_graphique' in metadata:
        graphique = metadata['data_graphique']
        print(f"\n[GRAPHIQUE] Donnees pour Chart.js:")
        print(f"  Labels: {graphique['labels']}")
        print(f"  Nombre de series: {len([k for k in graphique.keys() if k != 'labels'])}")

        # Montrer les premières valeurs
        for key in graphique:
            if key != 'labels':
                values = graphique[key]
                print(f"  - {key}: {values[:3]}..." if len(values) > 3 else f"  - {key}: {values}")

    # Sauvegarder
    filename = "test_analytics_evolution_simple.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Resultat sauvegarde dans: {filename}")

if __name__ == '__main__':
    asyncio.run(test_simple())
