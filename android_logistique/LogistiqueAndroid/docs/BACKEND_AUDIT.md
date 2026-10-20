# Audit backend avant implémentation mobile

Sources vérifiées localement le 1 septembre 2026 :

- `backend/apps/inventory/models.py`
- `backend/apps/inventory/views_transferts.py`
- `backend/apps/inventory/urls.py`
- `backend/apps/planning/views_livraisons.py`
- `backend/templates/inventory/transferts_list.html`
- `backend/templates/inventory/fiche_stock_list.html`
- `backend/templates/planning/gestion_livraisons.html`

## Règles confirmées

| Domaine | Règle observée | Conséquence mobile |
|---|---|---|
| Quantités | `DecimalField(... decimal_places=2)` | Chaîne décimale à deux chiffres, jamais `Double`/`Float` |
| Stock | Disponible calculé par `current_quantity - reserved_quantity` | Afficher les trois valeurs retournées ; projection locale marquée estimée |
| Ventilation | Le modèle historique `Stock` est base-centrique mais les workflows récents utilisent les magasins | `magasinId` reste nullable et `Non ventilé (base)` n’est jamais redistribué |
| Achat | Statuts `brouillon`, `commande`, `livre`, `recu`, `facture`, `paye`, `annule` | Valeurs filaires conservées exactement |
| Réception achat | Route web `purchase_receive` et réception complète | Pas de formulaire mobile de réception partielle |
| Transfert | Statuts `en_attente`, `en_cours`, `recu`, `annule` | Transitions nommées `envoyer`, `recevoir`, `annuler` |
| Création transfert | Origine ≠ destination, au moins une ligne positive, contrôle du stock d’origine | Même validation locale puis validation atomique serveur |
| Réception transfert | Quantité reçue par ligne, initialisée à l’envoyée, comprise entre 0 et l’envoyée | Contrôle décimal à deux chiffres et conservation de l’écart |
| Suppression transfert | Autorisée par la vue uniquement si `en_attente` | Action sensible, uniquement en ligne et selon `allowed_actions` |
| Mouvements | `entree`, `sortie`, `transfert`, `ajustement`, `perte` | Un mouvement validé reste immuable dans le mobile |
| Fiche de stock | Opérations distinctes : livraison, achat, transfert sortie/entrée, retour, inventaire, ajustement | Aucun formulaire générique de mouvement |

## Écarts bloquants pour la production

### État de l’API mobile v1

Les éléments 1 et 2 sont désormais implémentés : jetons d’accès courts, renouvellement rotatif, profil/capacités et bootstrap filtré par le périmètre logistique. Le bootstrap stocke des chaînes décimales et signale explicitement les positions magasin estimées. L’endpoint `changes` demande encore un bootstrap complet, car tous les référentiels historiques ne disposent pas de révisions fiables.

Les mutations restent désactivées : l’idempotence persistée, les transitions atomiques, les révisions et les PDF officiels doivent être implémentés et testés avant d’activer les formulaires Compose.

Les routes existantes utilisent session Django, `login_required` et parfois des réponses contenant des nombres JSON flottants. Elles ne satisfont pas le contrat offline-first ni l’idempotence demandée. Avant toute mutation de production, le backend doit fournir :

1. ~~authentification par jetons mobiles courts et renouvelables~~ — implémentée ;
2. ~~bootstrap filtré par capacités, bases et magasins~~ — implémenté ;
3. `clientOperationId` unique persisté côté serveur ;
4. traitement atomique avec verrouillage des positions ;
5. curseur de changements ;
6. révisions serveur ;
7. erreurs métier structurées ;
8. `allowed_actions` calculé côté serveur ;
9. quantités sérialisées en chaînes ;
10. téléchargement des PDF officiels.

## Règles à confirmer par tests de contrat

- Moment exact du débit d’origine d’un transfert : création ou passage en transit.
- Portée exacte du rapprochement : base seule ou couple base + magasin.
- Calcul précis du stock réservé par une livraison `en_attente`.
- Effet comptable et stock d’un écart de réception de transfert.
- Politique de durée maximale d’utilisation hors ligne.

Le mobile n’invente aucune de ces règles. Les commandes concernées doivent rester désactivées tant que le serveur ne les formalise pas.
