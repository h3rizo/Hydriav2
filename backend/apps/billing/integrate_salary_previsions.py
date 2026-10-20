import re

# Lire le fichier services_previsions.py
with open('services_previsions.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Trouver la section des stats (lignes 28-40)
stats_pattern = r"(stats = \{[\s\S]*?'avertissements': \[\]\s*\})"
stats_match = re.search(stats_pattern, content)

if stats_match:
    old_stats = stats_match.group(1)
    new_stats = """stats = {
        'annee': annee,
        'supprimees': 0,
        'creees': 0,
        'recettes_forfaitaires': 0,
        'recettes_volumetriques': 0,
        'recettes_nouveaux_pe': 0,
        'depenses_bons_avances': 0,
        'depenses_salaires': 0,
        'depenses_irsa': 0,
        'depenses_charges_sociales': 0,
        'nb_employes_salaires': 0,
        'nb_employes_irsa': 0,
        'nb_prix_manquants': 0,
        'designations_prix_manquants': [],
        'erreurs': [],
        'avertissements': []
    }"""
    content = content.replace(old_stats, new_stats)

# Trouver la section après les indemnités (ligne 98) et ajouter les nouveaux appels
insert_pattern = r"(stats\['nb_employes_indemnites'\] = result_indemnites\['nb_employes'\])"
insert_match = re.search(insert_pattern, content)

if insert_match:
    insertion_point = insert_match.end()
    new_code = """

            # 6. Calcul depenses salaires
            result_salaires = calculer_previsions_salaires(annee, base, config)
            stats['depenses_salaires'] = result_salaires['nb_created']
            stats['creees'] += result_salaires['nb_created']
            stats['nb_employes_salaires'] = result_salaires['nb_employes']

            # 7. Calcul depenses IRSA
            result_irsa = calculer_previsions_irsa(annee, base, config)
            stats['depenses_irsa'] = result_irsa['nb_created']
            stats['creees'] += result_irsa['nb_created']
            stats['nb_employes_irsa'] = result_irsa['nb_employes']

            # 8. Calcul charges sociales (CNAPS, FMFP, Mutuelle)
            result_charges = calculer_previsions_charges_sociales(annee, base, config)
            stats['depenses_charges_sociales'] = result_charges['nb_created']
            stats['creees'] += result_charges['nb_created']"""

    content = content[:insertion_point] + new_code + content[insertion_point:]

# Écrire le fichier modifié
with open('services_previsions.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Integration reussie - fonctions salaires/charges ajoutees a recalculer_previsions_annee()")
