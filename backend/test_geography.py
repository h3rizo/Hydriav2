#!/usr/bin/env python
"""
Script de test pour le service GeographyQueries
"""
import os
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from chatbot.services.geography_queries import GeographyQueries

def test_extraction():
    """Teste l'extraction du nom de localité"""
    geo_service = GeographyQueries()
    test_cases = [
        "Combien d'habitants à Ankazondandy",
        "Population de Ambanja",
        "Habitants dans Nosy Be",
        "Combien d'habitants Antsiranana ?",
    ]

    print("=" * 60)
    print("TEST D'EXTRACTION DES NOMS DE LOCALITÉS")
    print("=" * 60)

    for query in test_cases:
        location = geo_service._extract_location_name(query)
        print(f"\nQuery: {query}")
        print(f"  -> Location: {location}")

def test_population_query():
    """Teste une requête de population complète"""
    geo_service = GeographyQueries()
    test_query = "Combien d'habitants à Ankazondandy"

    print("\n" + "=" * 60)
    print("TEST DE REQUÊTE DE POPULATION")
    print("=" * 60)
    print(f"\nQuery: {test_query}")

    result = geo_service.process_query(test_query)

    print(f"\nSuccess: {result.get('success')}")

    if result.get('success'):
        print(f"\nResponse:")
        # Enlever les emojis pour l'affichage console Windows
        response = result.get('response', '')
        response = response.replace('🏘️', '[VILLAGE]').replace('📍', '[LOCATION]')
        print(response)

        # Afficher les métadonnées
        metadata = result.get('metadata', {})
        print(f"\nMetadata:")
        for key, value in metadata.items():
            print(f"  {key}: {value}")
    else:
        print(f"\nError/Response:")
        print(result.get('response'))

if __name__ == "__main__":
    test_extraction()
    test_population_query()
