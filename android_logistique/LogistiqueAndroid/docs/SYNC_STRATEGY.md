# Stratégie de synchronisation

## Cycle

`Brouillon → À synchroniser → En cours → Synchronisé`

Une opération peut quitter `En cours` vers `Conflit`, `Rejeté` ou revenir à `À synchroniser` après une panne réseau récupérable.

## Garanties

- Le UUID `clientOperationId` est créé une seule fois et conservé pendant tous les retries.
- Les dépendances sont envoyées avant l’opération dépendante.
- Une projection locale est marquée `Estimé`.
- La réponse canonique remplace la projection dans une transaction Room.
- Un conflit conserve simultanément la charge utile locale et l’état serveur.
- Aucun conflit de stock n’est résolu par dernier écrivain gagnant.
- Les photos restent locales tant que le serveur n’a pas confirmé leur stockage.

## Reprise

WorkManager s’exécute uniquement avec réseau. Une erreur transport replace l’opération en attente. Une erreur métier définitive la place en rejet. Un changement concurrent crée un conflit visible et récupérable.
