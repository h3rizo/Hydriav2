# Hydria Terrain — Android natif

Application Android terrain reliée à `www.hydria.mg`.

## Version 2.1.0

Cette version modernise l’interface native sans modifier les contrats API ni le
fonctionnement hors connexion : palette bleu nuit, navigation active, cartes de
statistiques, badges accessibles, progression de tournée et graphiques fondés
sur les données déjà reçues du serveur.

L’icône de lancement utilise désormais le vase orange Hydria sous forme d’icône
Android adaptative, ronde et compatible avec les anciennes versions d’Android.

La préparation des relevés reprend exactement le périmètre de la page web
`/facturation/releves/` : ouvrages autorisés pour l'utilisateur connecté avec
une modalité de paiement active **Au volume** ou **Mixte**. Un message explicite
remplace les listes silencieusement vides lorsqu'aucun ouvrage n'est disponible.

## Écrans natifs

1. **Relevés** : sélection ouvrage/point d’eau, contrôle de l’index, date,
   volume non facturé et remarque. Une saisie hors connexion rejoint la file
   locale, puis le moteur Django calcule la facture après synchronisation.
2. **Réparations** : interventions échues de l’agent, consultables hors ligne,
   avec action « Marquer terminée » synchronisable.
3. **Plannings** : activités des 14 prochains jours, disponibles hors ligne
   après préchargement.

L’authentification est native et utilise un token Hydria de scope `mobile`.
Les données de tournée et les actions en attente sont conservées localement.
Le bouton **WEB** ouvre le site complet dans le navigateur pour les autres
modules.

## Compiler

Depuis Android Studio, ouvrir ce dossier et lancer `app`. En ligne de commande :

```powershell
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
.\gradlew.bat assembleDebug
```

APK généré : `app/build/outputs/apk/debug/app-debug.apk`.

Les ressources d’icône peuvent être régénérées depuis le master conservé dans
`branding/` avec `branding/generate-icons.ps1`.

## API Django requise

- `POST /mobile/api/login/`
- `GET /plannings/api/preparer-tournee/`
- `POST /billing/api/save-releve-terrain/`
- `POST /plannings/reparations/api/{id}/marquer-terminee/`

Ces routes doivent être déployées avant les tests avec un compte réel.
