# Identité Hydria Terrain

`hydria-vase-master.png` est le master transparent haute définition utilisé
pour les icônes Android. Il a été produit avec l’outil ImageGen intégré à partir
de l’image source `backend/icons8-vase-94.png`, puis contrôlé comme image ARGB.

Prompt de production :

> Recréer fidèlement le même vase orange en haute définition, avec la même
> silhouette, les mêmes bandes, les mêmes reflets et une véritable transparence.
> Le centrer sur une toile carrée avec une zone de sécurité généreuse pour une
> icône Android adaptative. Ne produire ni texte, ni ombre, ni arrière-plan, ni
> élément supplémentaire.

`generate-icons.ps1` recadre les pixels visibles, conserve les proportions et
génère :

- le premier plan adaptatif 432 × 432 ;
- les icônes classiques et rondes pour mdpi à xxxhdpi ;
- le fond bleu nuit cohérent avec l’interface.
