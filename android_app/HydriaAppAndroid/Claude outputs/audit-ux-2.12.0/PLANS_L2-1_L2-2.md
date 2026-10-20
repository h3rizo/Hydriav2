# Lot 2 : plans des chantiers L2-1 et L2-2, à valider

**Date** : 20 octobre 2026, 09:00 (heure de Madagascar).
**Préparés par** des agents Sonnet, en lecture seule : aucun code n'a été modifié pour ces deux chantiers.
**Comment répondre** : un message suffit, par exemple « OK pour toutes tes recommandations » ou « Q2 : impression en principal, le reste OK ». Le code ne commencera qu'après ta réponse.

---

## L2-1 : formulaire de relevé réordonné et brouillon (effort L, environ 2 à 3 jours de travail d'agent)

### Ce que l'agent terrain verra

- À l'ouverture d'un point, il voit tout de suite le nom de l'abonné et le dernier index, et le clavier est déjà ouvert sur « Nouvel index ».
- **« Enregistrer · point suivant » reste fixe en bas de l'écran** : plus besoin de faire défiler. Il faut 2 à 3 gestes par relevé au lieu de 5 à 9.
- Après l'enregistrement, l'app passe au point **suivant** de la liste, et non plus au premier.
- La remarque, le volume non facturé, les cartes sociales, le GPS et les anciennes factures sont rangés dans **« Plus de détails »**. Cette section s'ouvre toute seule quand c'est nécessaire : remarque obligatoire, ou kiosque avec cartes sociales (sinon l'agent oublierait les bidons et la facture serait fausse).
- **Brouillon point par point** : ce qui a été tapé est gardé en cas de changement de point, de synchronisation, ou si le téléphone ferme l'app pendant une photo. À la réouverture, l'agent voit « Brouillon repris ».
- Boutons ‹ › de 48 dp pour passer au point précédent ou suivant.

### Côté technique

- Les règles sont dans `shared` et testées : signature du formulaire, livre de brouillons, point suivant, ouverture automatique de « Plus de détails », et refus d'une date de campagne qui n'existe pas.
- Brouillons stockés dans les préférences du compte : pas de nouvelle table ni de migration.
- Desktop : point suivant après enregistrement, brouillons en mémoire, focus sur l'index, bouton d'enregistrement toujours visible. La remarque obligatoire et le sélecteur de date y sont déjà depuis ce matin.

### Questions

1. **Touche « ✓ » du clavier sur l'index**. Faut-il qu'elle ferme seulement le clavier, ou qu'elle enregistre directement ?
   *Recommandation : fermer seulement le clavier tant que L2-2 n'est pas livré. Sinon, une faute de frappe partirait en un seul geste.*
2. **Barre du bas**. Je propose « Enregistrer · point suivant » en bouton principal et « Calculer et imprimer (80 mm) » en secondaire. Quelle part des relevés est imprimée sur place ?
   *Si c'est la majorité, je mets les deux boutons à égalité, ou l'impression en principal.*
3. **Choix du point** (parcelle, recherche, proches de moi, voir mes saisies). Deux options :
   - un bloc repliable simple dans la page ;
   - une feuille du bas, avec l'index déjà saisi visible sur chaque ligne. C'est mieux, mais cela coûte environ 1 à 2 jours de plus.

   *Recommandation : le bloc repliable.*
4. **Relevé quitté sans enregistrer** (Retour ou « Changer »). Faut-il garder le brouillon sans rien demander, avec « Brouillon repris » à la réouverture, ou garder la boîte « Abandonner la saisie ? » du lot 1 ? Et combien de temps garder un brouillon ?
   *Recommandation : garder le brouillon sans question, jusqu'à la fermeture de la campagne et au plus 3 jours.*
5. **Clavier ouvert**. Faut-il masquer l'en-tête et la barre d'onglets pendant la saisie de l'index, pour garder de la place sur les petits téléphones ?
   *Recommandation : oui, seulement sur l'écran de relevé.*

---

## L2-2 : garde-fous de plausibilité et « Annuler » (effort M, environ 1 à 2 jours)

### Ce que l'agent terrain verra

- **Index qui a l'air faux** (un chiffre en trop, 1 300 au lieu de 130, ou un point très loin de lui) : une seule boîte s'affiche, par exemple « Vérifiez ce relevé — Leonce : index 1 300, soit +1 169 m³ ; moyenne 12 m³ ». Il a deux choix :
  - **Corriger** : le curseur revient dans l'index ;
  - **Enregistrer quand même**.
- Quand tout est normal, il n'y a aucune question en plus.
- Après l'enregistrement, le petit message qui disparaissait est remplacé par un bandeau : « ✓ Leonce · 131,50 m³ enregistré · 51 points restants — **ANNULER** ». Pendant quelques secondes, ANNULER retire le relevé de la file et rouvre le point avec ce qui avait été saisi. Pendant ce délai, l'envoi de ce relevé est retenu.
- **Un ticket déjà imprimé n'est jamais annulable**, car il a été remis à l'abonné.
- L'ancienne alerte de distance (250 m) est intégrée dans la même boîte.

### Côté technique

- Les données existent déjà dans la tournée (moyenne de consommation et nombre de relevés du point) : **aucun changement serveur**.
- Règles et phrases dans `shared`, testées, donc les mêmes sur le téléphone et sur le Desktop.
- Desktop : même boîte de confirmation, et bouton « Annuler le dernier enregistrement » tant que l'entrée est encore dans la file. Le Desktop n'envoie qu'au clic, donc il n'y a pas de délai à gérer.

### Questions

6. **Seuils d'alerte**. Valides-tu ces valeurs ?
   - (a) La consommation dépasse **5 fois** la moyenne du point.
   - (b) Le point a au moins **3 relevés** avec une consommation.
   - (c) L'excédent dépasse **10 m³** (pour ne pas alerter un point à 1 m³ qui passe à 6).
   - (d) Sans historique fiable : alerte au-dessus de **500 m³**.
   - (e) Distance au point : **250 m**, comme aujourd'hui.

   Attention à (a) et (d) : un kiosque peut légitimement consommer beaucoup plus qu'une borne privée.
7. **Consommation nulle** sur un point qui consomme d'habitude. La remarque y est déjà obligatoire.
   *Recommandation : ne pas ajouter de boîte en plus.*
8. **Valeur extrême** (par exemple plus de 20 fois la moyenne). Faut-il une simple confirmation pour tout le monde, ou un blocage avec déblocage réservé au Directeur, comme pour l'impression ?
   *Recommandation : une simple confirmation.*
9. **Durée d'annulation** : 8 secondes. L'envoi de chaque relevé est retardé d'autant. Tu préfères 5, 8 ou 10 secondes ?
   *Recommandation : 8 secondes.*

---

## Ordre et budget

- L2-1 d'abord, puis L2-2 : le bandeau « Annuler » de L2-2 prend place dans la barre fixe de L2-1.
- Limite hebdomadaire : **69 %** à 08:55, avec remise à zéro le 25/10 à 11:59. D'après la consommation mesurée, **L2-1 + L2-2 ≈ 6 M tokens**, ce qui amène la limite vers **85 %**. À ce moment, je m'arrête et je t'envoie `ESTIMATION_COUT_LOT2.md` à jour, avant de lancer quoi que ce soit d'autre.
