# Estimation du coût pour terminer le lot 2

**État au 20/10/2026 à 08:55 (heure de Madagascar)** :
- forfait Pro, limite hebdomadaire utilisée à 69 % (remise à zéro le 25/10 à 11:59) ;
- limite sur 5 heures utilisée à 13 % (remise à zéro à 13:49) ;
- crédit supplémentaire (« extra usage ») pas activé, facturé en dollars au tarif de l'API.

Ce fichier est mis à jour à chaque étape. La dernière version t'est envoyée **avant** que la limite hebdomadaire soit atteinte.

## Tarifs utilisés (tarifs officiels actuels, par million de tokens)

| Modèle | Entrée | Sortie | Lecture de cache |
|---|---|---|---|
| Claude Sonnet 5.5, pour les agents qui codent | 2 $ | 10 $ | 0,20 $ |
| Claude Opus 5.5, pour le pilotage | 4 $ | 20 $ | 0,20 $ |

Le mélange réellement observé au lot 1 se compose surtout de relectures de cache. Il revient à environ **0,50 à 0,70 $ par million de tokens** pour les agents Sonnet.

## Reste à faire

| Travail | Tokens estimés | Coût estimé |
|---|---|---|
| Alignement Desktop + plans L2-1 et L2-2 (lancés le 20/10) | 1,5 à 2,5 M | 1 à 2 $ |
| L2-1 Formulaire de relevé réordonné + brouillon | 2 à 3,5 M | 1,2 à 2,4 $ |
| L2-2 Garde-fous de plausibilité | 1 à 2 M | 0,6 à 1,4 $ |
| L2-3 File visible + clé anti-doublon (serveur) | 2,5 à 4 M | 1,5 à 2,8 $ |
| L2-4 Centre de synchronisation lisible | 1,5 à 2,5 M | 0,9 à 1,8 $ |
| L2-5 Mes pointages + créneaux prévus par défaut (serveur) | 2 à 3,5 M | 1,2 à 2,4 $ |
| L2-6 Capture GPS partagée (100 m) | 1,5 à 2,5 M | 0,9 à 1,8 $ |
| L2-7 Série Terrain + tournée par distance | 1,5 à 2,5 M | 0,9 à 1,8 $ |
| L2-8 Formateur commun + statuts + migration « planifie » (serveur) | 2 à 3,5 M | 1,2 à 2,4 $ |
| L2-9 Cascade d'activité « — Choisir — » | 0,5 à 1 M | 0,3 à 0,7 $ |
| Pilotage (Opus), dans une **nouvelle** conversation | — | 2 à 4 $ |
| Pilotage (Opus), dans la conversation **actuelle** (855 000 tokens de contexte) | — | 8 à 12 $ |
| **Total** | **16 à 28 M** | **≈ 10 à 23 $** (nouvelle conversation) / **≈ 16 à 31 $** (actuelle) |

**Recommandation** : environ **30 $** de crédit, et reprendre le lot 2 dans une nouvelle conversation. Le fichier `PROMPT_SONNET_CORRECTIONS.md` contient déjà toutes tes décisions, il suffit de le lui faire lire.

## Historique de consommation (pour recaler l'estimation)

| Date | Limite hebdomadaire | Étape terminée |
|---|---|---|
| 20/10 02:40 | 64 % | Lot 1 complet (≈ 6 M tokens d'agents) ; alignement Desktop + plans L2-1/L2-2 lancés |
| 20/10 08:55 | 69 % | Alignement Desktop codé (build vert) + plans L2-1 (effort L) et L2-2 (effort M) ; la revue Desktop a buté sur la limite des 5 h, relancée maintenant |
| 20/10 09:20 | 72 % | Revue Desktop terminée : 0 bloquant, 9 mineurs. Plans validés par l'utilisateur. Lancement de L2-1 (3 agents d'implémentation, une revue, une correction si nécessaire) |

**Recalage (20/10 09:20)** : de 64 % à 72 %, soit 8 points, pour l'alignement Desktop avec sa revue, les deux plans et le pilotage, dont le résumé automatique d'une conversation de 855 000 tokens, une opération coûteuse. L2-1 est le plus gros chantier (effort L) : j'estime son coût à **8 à 12 points**, ce qui amènera la limite vers 80 à 84 %. La limite sur 5 heures (31 % à 09:20) risque d'être atteinte pendant L2-1. Dans ce cas, le travail reprendra là où il s'est arrêté, sans rien perdre.

**Recalage précédent (20/10 08:55)** : l'alignement Desktop et les deux plans ont coûté environ **5 points** de limite hebdomadaire, soit environ 2,5 points par million de tokens d'agents. Le reste du lot 2 (14 à 25 M tokens) représenterait donc **35 à 60 points**, alors qu'il en reste 31 avant la remise à zéro du 25/10. Le seuil d'alerte (85 %) sera atteint après environ **6 M tokens**, soit à peu près L2-1 et L2-2. Tu recevras ce fichier à ce moment-là.
