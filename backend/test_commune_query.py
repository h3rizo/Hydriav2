"""
Test des requêtes géographiques - communes d'un district
"""
import os
import django
import json

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from chatbot.services.geography_queries import GeographyQueries

def test_commune_query():
    """Test de la requête sur les communes d'un district"""
    gq = GeographyQueries()

    # Test avec différentes questions
    questions = [
        "Liste des communes de Ambohidratrimo",
        "Combien de communes dans Ambohidratrimo",
        "communes de Ambanja"
    ]

    for question in questions:
        print(f"\n{'='*60}")
        print(f"Question: {question}")
        print('='*60)

        result = gq.process_query(question)

        # Sauvegarder dans JSON pour éviter problèmes d'encodage
        filename = f"test_result_{question[:20].replace(' ', '_')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"Success: {result.get('success')}")
        print(f"Type: {result.get('metadata', {}).get('type')}")
        if result.get('success'):
            count = result.get('metadata', {}).get('count', 0)
            location = result.get('metadata', {}).get('district', 'N/A')
            print(f"District: {location}")
            print(f"Nombre de communes: {count}")
            print(f"Resultat sauvegarde dans: {filename}")
        else:
            print(f"Erreur: {result.get('response')}")

if __name__ == '__main__':
    test_commune_query()
