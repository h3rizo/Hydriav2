# Matrice de parité formulaires web / Android

Cette matrice est issue des formulaires et modales du dépôt Django. La colonne API désigne le contrat mobile à implémenter, pas les routes HTML existantes.

## Création d’un transfert

| Élément | Site existant | Android Compose | Obligatoire | Format API | Conforme |
|---|---|---|---|---|---|
| Numéro de transfert | Généré serveur | Lecture seule après synchronisation | Non saisi | `transfer_number` | Oui |
| Date et heure du transfert | Date/heure | Sélecteurs natifs | Oui | ISO 8601 Madagascar | Oui |
| Magasin d’origine | Liste | Sélecteur avec recherche | Oui | UUID | Oui |
| Magasin de destination | Liste | Sélecteur avec recherche | Oui | UUID | Oui |
| Initié par | Liste | Sélecteur avec recherche | Non | UUID nullable | Oui |
| Arrivée prévue | Date/heure | Sélecteurs natifs | Non | ISO 8601 nullable | Oui |
| Notes | Texte | Champ multiligne | Non | Chaîne nullable | Oui |
| Articles | Lignes dynamiques | Lignes dynamiques plein écran | Oui, ≥ 1 | Tableau | Oui |
| Désignation | Liste | Sélecteur article local | Oui | UUID | Oui |
| Quantité | Nombre | Clavier décimal | Oui, > 0 | Chaîne décimale | Oui |
| Vérifier le stock | Action | Étape de confirmation | Oui avant envoi | Validation serveur | Oui |

Effet attendu : créer un transfert `en_attente`. L’effet exact sur le stock reste bloqué jusqu’au test de contrat serveur.

## Réception d’un transfert

| Élément | Site existant | Android Compose | Obligatoire | Format API | Conforme |
|---|---|---|---|---|---|
| Utilisateur ayant reçu | Liste | Sélecteur | Non | UUID nullable | Oui |
| Désignation | Lecture seule | Texte | — | Non renvoyé | Oui |
| Quantité envoyée | Lecture seule | Texte décimal | — | Non modifié | Oui |
| Quantité reçue | Nombre, défaut envoyé, min 0, max envoyé | Champ décimal | Oui | Chaîne à 2 décimales par ID ligne | Oui |

## Bon de livraison depuis une fiche

| Élément | Site existant | Android Compose | Obligatoire | Condition | Conforme |
|---|---|---|---|---|---|
| Article/base/magasin | Contexte | En-tête lecture seule | — | Toujours | Oui |
| Ouvrage | Liste | Sélecteur recherché | Oui | Toujours | Oui |
| Planning | Dépend de l’ouvrage | Sélecteur filtré | Oui | Après ouvrage | Oui |
| Quantité | Nombre | Champ décimal | Oui | > 0 | Oui |
| Statut | `en_attente` ou `livre` | Choix segmenté | Oui | Toujours | Oui |
| Date d’utilisation | Date | Sélecteur date | Si `livre` | Statut `livre` | Oui |
| Numéro de bon | Texte | Champ texte | Non | Toujours | Oui |

## Inventaire

| Élément | Site existant | Android Compose | Obligatoire | Conforme |
|---|---|---|---|---|
| Article/base/magasin | Contexte | Lecture seule | — | Oui |
| Quantité inventoriée | Nombre | Champ décimal | Oui | Oui |
| Date d’inventaire | Date | Sélecteur date | Oui | Oui |
| Notes | Texte | Multiligne | Non | Oui |
| Rapproché | Case | Interrupteur | Non | Oui |

L’inventaire ne contient ni état, ni utilisateur, ni photo. Ces champs appartiennent exclusivement à l’ajustement.

## Ajustement manuel

| Élément | Site existant | Android Compose | Obligatoire | Conforme |
|---|---|---|---|---|
| Désignation/code/nature/base/magasin | Contexte | Lecture seule | — | Oui |
| Stock actuel | Lecture seule | Valeur mise en évidence | — | Oui |
| Nouvelle quantité | Nombre | Champ décimal | Oui | Oui |
| Date d’inventaire | Date | Sélecteur date | Oui | Oui |
| État | Bon/Moyen/Mauvais/HS | Liste | Oui | Oui |
| Rapproché | Case | Interrupteur | Non | Oui |
| Utilisateur | Liste | Sélecteur | Non | Oui |
| Photo | Galerie/appareil | Photo Picker/CameraX | Non | Oui |

## Retour terrain

| Élément | Site existant | Android Compose | Obligatoire | Conforme |
|---|---|---|---|---|
| Article/base | Contexte | Lecture seule | — | Oui |
| Magasin | Facultatif, non ventilé possible | Sélecteur avec option `Non ventilé (base)` | Non | Oui |
| Date opération | Date | Sélecteur date | Oui | Oui |
| Quantité | Positive | Champ décimal | Oui | Oui |
| Référence | Texte | Champ texte | Non | Oui |
| Notes | Texte | Multiligne | Non | Oui |

## Documents

Les bons officiels sont toujours téléchargés depuis le serveur. Un aperçu local hors ligne porte exactement `PROVISOIRE — OPÉRATION NON SYNCHRONISÉE` et ne remplace jamais le PDF canonique.
