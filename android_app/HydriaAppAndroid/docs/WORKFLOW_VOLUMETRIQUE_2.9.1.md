# Hydria Android 2.9.1 — parcours aligné sur Hydria web

Cette version remplace le menu d'actions générique de la 2.9.0 par trois espaces distincts,
avec sélection d'un **ouvrage** et d'un **mois de facturation**. Le mois de facturation
correspond au mois suivant le relevé, comme sur le site.

## 1. Facturation

1. Choisir ouvrage/mois et lancer **Calculer les factures de tout le lot**.
2. Consulter tous les relevés, les montants calculés, le total et les erreurs éventuelles.
3. **Enregistrer toutes les factures calculées** valide le lot calculable. Les factures
   verrouillées (imprimées, encaissées ou pointées) conservent leur montant.
4. **Imprimer les factures du lot** ouvre l'impression A4/PDF native.
5. Confirmer l'impression effectivement réalisée.

Il n'est plus nécessaire de sélectionner les relevés un à un pour lancer la facturation.
Les lots de validation et de confirmation d'impression dépassant 500 factures sont
conservés atomiquement dans plusieurs opérations de synchronisation de 500 factures.
Les erreurs de calcul restent affichées, sans facturation silencieuse des relevés en erreur.

## 2. Encaissement

- Ouvrir l'ouvrage et le mois : la fenêtre affiche les factures non pointées.
- Cocher manuellement les factures ou les ajouter par scan QR ; la saisie du numéro
  reste disponible si le QR est abîmé.
- Le nombre de factures sélectionnées et leur somme sont visibles en permanence.
- Les factures déjà encaissées mais non pointées sont identifiées et non sélectionnables,
  pour empêcher un second encaissement.
- Choisir la date et le journal, puis valider l'encaissement.
- Ouvrir et imprimer le récapitulatif : ouvrage/mois, date, journal, référence, total,
  ligne temporaire DiameX après synchronisation, liste des factures et grille IDXLS.

Le récapitulatif est conservé dans SQLite dès l'enregistrement de l'encaissement, dans
la même transaction. Son contenu reste figé même si les factures sont actualisées ensuite.
Il peut être réimprimé par **dernier récapitulatif** dans la période ou via **Outils →
Historique / récapitulatifs**. Il affiche explicitement les états local, synchronisé,
refusé ou clôturé après vérification manuelle.

La grille IDXLS reprend la convention du site : dernier chiffre en colonne, autres chiffres
en ligne ; noir pour le récapitulatif courant, gris pour les IDXLS déjà pointés lors de la
préparation. Les lignes entièrement vides sont omises pour éviter des milliers de pages
avec de grands identifiants. Le récapitulatif est paginé automatiquement en A4.

## 3. Pointage DiameX

- Ouvrir l'ouvrage et le mois.
- Les **relevés sont à gauche**, les **lignes DiameX à droite**. Sur petit écran, faire
  défiler horizontalement la comparaison pour garder des colonnes lisibles.
- Cocher les relevés et choisir une ligne DiameX. Toutes les lignes préchargées sont
  visibles, y compris celles qui ne correspondent pas encore au total sélectionné.
- Les deux montants et l'écart sont affichés. Le bouton de pointage devient disponible
  lorsque les montants correspondent et que la ligne n'est pas déjà pointée.
- Le serveur vérifie à nouveau l'ouvrage, la période, le montant réel du segment DiameX,
  le périmètre et l'absence de pointage précédent.

## Hors ligne

Les références et calculs doivent être téléchargés avant de partir. Sans réseau, le bouton
de calcul ouvre les résultats préchargés de **tout le lot**. Le moteur tarifaire de
référence reste Django ; cette version ne calcule pas de nouveaux relevés jamais
synchronisés. La saisie des encaissements, le scan, le récapitulatif et la préparation du
pointage restent disponibles sur les données préchargées.

En ligne, les validations déclenchent la synchronisation. Hors ligne, les opérations restent
dans la file persistante. L'impression A4/PDF est entièrement locale ; l'accès physique à
l'imprimante dépend du service d'impression Android et du réseau local.

## Installation et contrôles

- APK : version **2.9.1**, code **39**.
- Mettre à jour `backend/apps/billing/views_mobile_volume.py` : ajout du type de point
  d'eau dans les factures, et date/état de pointage des écritures DiameX.
- Si la 2.9.0 n'a pas été déployée, appliquer aussi son intégration et sa migration 0078,
  décrites dans `WORKFLOW_VOLUMETRIQUE_2.9.0.md`. Aucune nouvelle migration en 2.9.1.
- Aucun déploiement serveur automatique n'est réalisé par la compilation Android.

Tests ajoutés : affichage des non-pointées sans double encaissement, total du lot complet,
correspondance exacte avec une écriture, récapitulatif immuable, grille des déjà pointées,
refus d'un récapitulatif mélangeant plusieurs mois.

La recette sur téléphone doit couvrir le parcours ouvrage/mois complet, le scan d'une
facture papier, la sélection manuelle d'une facture au QR endommagé, l'impression et la
réimpression du récapitulatif, puis le rapprochement côte à côte et le retour du réseau.
