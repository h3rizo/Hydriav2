# Refonte Hydria Terrain

## Direction retenue

La refonte reprend des références fournies leur hiérarchie dense et très lisible, leur navigation mobile stable et leur traitement visuel sombre. Elle écarte volontairement le violet néon et les petits textes au profit d'une palette liée à l'eau et plus accessible.

- Fond minéral sombre : `#07151f`
- Surface principale : `#0b202c`
- Accent eau : `#32d6c6`
- Attention : `#f5b95f`
- Urgence uniquement : `#ff6b6b`
- Texte principal : `#f2f8f9`

Les quatre images de ce dossier sont les références visuelles de l'accueil terrain, du tableau de bord, de la recherche et du planning.

## Principes d'ergonomie

- Navigation basse persistante sur mobile et rail latéral sur ordinateur.
- Action centrale « Ajouter » ouvrant un panneau d'actions rapides.
- État de connexion et de synchronisation toujours visible.
- Priorité aux tâches du jour avant les indicateurs secondaires.
- Zones tactiles d'au moins 44 à 48 px.
- État communiqué par une icône et un libellé, jamais uniquement par la couleur.
- Chiffres en style tabulaire et unités affichées à proximité immédiate.
- Mode sombre par défaut, mode clair conservé.

## Accessibilité intégrée

- Lien d'évitement vers le contenu principal.
- Indication `aria-current` dans les navigations.
- Libellés accessibles pour les boutons icônes.
- Anneaux de focus très visibles.
- Prise en charge de `prefers-reduced-motion` et `prefers-contrast`.
- Contenu utilisable sans survol et états hors ligne explicites.

## Parcours refondus

- Accueil terrain et priorités quotidiennes.
- Tableau de bord opérationnel.
- Recherche globale et suggestions de proximité.
- Planning journalier et détails progressifs.
- Hubs Facturation et Stocks.

Les appels API de recherche et de tableau de bord ainsi que les composables existants ont été conservés.
