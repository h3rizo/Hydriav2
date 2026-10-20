# Android — Phase 3 (fonctions avancées)

Date de vérification : 31 août 2026.

## Photos de progression

Le module `feature:progress` prend désormais en charge les photos corporelles privées :

- sélection avec le Photo Picker Android, sans permission globale de stockage ;
- capture déléguée à l’application appareil photo avec un URI `FileProvider` temporaire ;
- suppression du fichier temporaire juste après sa lecture ;
- formats JPEG, PNG et WebP, avec limite client et serveur de 10 Mo ;
- date et note facultative limitée à 255 caractères ;
- upload multipart authentifié vers `POST /api/v1/progress/photos/` ;
- téléchargement exclusivement via `GET /api/v1/progress/photos/{id}/content/` ;
- comparaison de la première et de la dernière photo ;
- historique récent et aperçu plein écran.

Les chemins média privés ne sont jamais utilisés par Android. Les octets ne sont
ni journalisés ni persistés par l’application. Au maximum huit images — première
photo incluse — sont conservées en mémoire pour limiter la consommation. Les
captures temporaires se trouvent uniquement dans le cache privé de l’application.

## Recettes personnelles

L’écran Repas permet maintenant de créer une recette privée depuis le catalogue
d’ingrédients Django :

- nom et catégorie de repas ;
- instructions de préparation ;
- recherche dans le catalogue d’ingrédients ;
- ajout et retrait de plusieurs ingrédients ;
- quantité exprimée dans l’unité de base fournie par le serveur ;
- validation locale des champs et des quantités ;
- création authentifiée via `POST /api/v1/nutrition/recipes/` ;
- rechargement complet après création afin d’utiliser les calories et
  macronutriments calculés par Django.

Le client n’envoie ni propriétaire ni indicateur public. Pour un compte standard,
le backend impose `created_by`, `is_personal=True` et `actif=True`. La liste des
recettes reste limitée aux recettes publiques et aux recettes personnelles de
l’utilisateur connecté.

## Foyer et repas partagés

Un écran dédié, accessible depuis Repas, couvre désormais le premier parcours
collectif :

- liste des membres du foyer ;
- ajout d’un membre avec lien de parenté, âge et sexe facultatifs ;
- recherche d’un compte Hydria et association facultative au membre ;
- liste des repas créés par l’utilisateur ou visibles parce qu’il participe ;
- création d’un repas maison, acheté ou pris au restaurant ;
- date, heure, ingrédients, quantités, participants et portions consommées ;
- indication de la personne ayant fait les courses ou cuisiné lorsque c’est
  l’utilisateur courant ;
- notes et totaux nutritionnels calculés par Django.

Les droits du serveur restent déterminants : un participant peut consulter un
repas partagé, mais seul son créateur peut le modifier ou le supprimer. Après une
création, l’application recharge la représentation de lecture, car la réponse POST
utilise volontairement le serializer d’écriture.

## Préférences d’approvisionnement

L’écran Courses contient désormais un gestionnaire de préférences relié aux
catalogues Django :

- recherche dans les ingrédients et les articles bien-être ;
- ingrédient non apprécié ou temporairement indisponible ;
- article bien-être indisponible ;
- vendeur préféré et ville du vendeur ;
- note personnelle limitée à 255 caractères ;
- création, mise à jour ou suppression implicite d’une préférence vide ;
- rechargement des listes après chaque mutation.

Les vendeurs des articles bien-être sont filtrés avec `vendor_ids`. Le backend
reste responsable de la validation finale de la ville de résidence et du lien entre
article et vendeur. Les préférences sont ensuite réutilisées par la génération et
le regroupement des courses côté serveur.

## Courses hors connexion

Les listes de courses disposent maintenant d’un cache local Room et d’une file de
synchronisation WorkManager :

- la dernière représentation complète de l’écran Courses est conservée localement ;
- le cache et les opérations sont cloisonnés par l’identité stable de la session
  (avec empreinte non réversible en repli), sans persister les jetons dans Room, afin
  qu’un autre compte du téléphone ne puisse jamais les relire ;
- elle reste consultable lorsque l’API est inaccessible ;
- cocher ou décocher un article est immédiatement appliqué dans l’interface ;
- la dernière valeur demandée par article remplace les valeurs en attente plus anciennes ;
- chaque opération en attente est visible dans la ligne concernée ;
- WorkManager rejoue les modifications dès qu’une connexion est disponible ;
- les requêtes différées envoient un état idempotent `checked=true/false`, jamais une
  commande ambiguë de type « inverser » ;
- une erreur métier ou d’autorisation annule la mutation locale, tandis qu’une panne
  réseau conserve la mutation dans la file.

Le worker utilise la fabrique Hilt de l’application. L’initialiseur WorkManager par
défaut est retiré du manifeste afin qu’une seule configuration soit active.

## Vérifications

- mapping des métadonnées privées ;
- upload multipart puis rechargement depuis le serveur ;
- absence de mutation si la sélection est invalide ;
- mapping du catalogue d’ingrédients et du marqueur de recette personnelle ;
- création d’une recette puis rechargement de la représentation serveur ;
- rejet local d’une recette invalide sans appel réseau ;
- sérialisation stable des quantités avec un point décimal ;
- mapping des repas collectifs visibles et de leurs totaux nutritionnels ;
- sérialisation des portions individuelles et du total des portions ;
- sauvegarde et rechargement d’une préférence d’ingrédient ;
- conservation des identifiants vendeur et des indicateurs de disponibilité ;
- relecture de la dernière liste depuis Room en l’absence de réseau ;
- mutation optimiste et marquage d’une coche en attente de synchronisation ;
- compilation de l’APK principal et de l’APK de tests Compose ;
- Android Lint.

## Suite de la phase

Le cache Room/WorkManager est volontairement limité aux listes de courses et aux
coches idempotentes. Les autres mutations (prix, dates, préférences, génération)
continuent d’exiger une confirmation immédiate du serveur. Les notifications locales
restent à implémenter.
