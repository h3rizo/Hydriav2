# Hydria Sync (client PC)

Synchronise un dossier de votre PC avec les fichiers d'Hydria (dossiers techniques, photos…), dans les deux sens.
Serveur : module `backend/apps/sync` (`/api/sync/*`, `/api/fichiers/*`).

## Utiliser

1. Installer (voir ci-dessous) puis lancer **Hydria Sync** depuis le menu Démarrer.
2. Se connecter avec son compte Hydria et choisir le dossier de synchronisation (par défaut `C:\Users\<nom>\Hydria`).
3. La synchronisation est automatique (toutes les 1 à 30 minutes). Fermer la fenêtre **réduit l'application dans la
   zone de notification** (icône près de l'horloge) : elle continue de synchroniser. Clic droit sur l'icône :
   ouvrir, synchroniser maintenant, ouvrir le dossier, quitter. L'icône **tourne** pendant une synchronisation,
   devient **orange** s'il y a un conflit à résoudre et **rouge** en cas d'erreur.
4. Réglages dans la fenêtre : bouton lune/soleil (**mode sombre**, par défaut celui de Windows) et
   « Démarrer Hydria Sync avec Windows » (activé à la première utilisation, désactivable).

Fichiers de l'application, dans `%APPDATA%\HydriaSync` : `config.json` (compte, jeton), `preferences.json`
(thème, démarrage), `sync.log` (journal). Le dossier synchronisé contient en plus `.hydria-sync\` (état interne).
Une seule instance tourne à la fois : relancer l'application remet la fenêtre existante au premier plan.

## Construire l'installateur (développeur)

Depuis `android_app/HydriaAppAndroid` (PowerShell ; l'option Java évite une erreur de socket de Gradle) :

```powershell
$env:JAVA_TOOL_OPTIONS='-Djdk.net.unixdomain.tmpdir=C:\tmp'
.\gradlew.bat :syncclient:packageExe :syncclient:packageMsi
```

Résultat dans `syncclient/build/compose/binaries/main/exe/HydriaSync-<version>.exe` et `.../msi/HydriaSync-<version>.msi`
(le JRE est embarqué : rien à installer sur les postes). WiX est téléchargé automatiquement par Gradle.

- Installation **par utilisateur** (`%LOCALAPPDATA%\HydriaSync`), sans droits administrateur.
- Pour publier une mise à jour : **augmenter `packageVersion`** dans `build.gradle.kts` ; ne jamais changer `upgradeUuid`.
- L'icône (`packaging/hydria-sync.ico`) est dessinée par code : `gradlew :syncclient:genererIcone` la recrée.
- `gradlew :syncclient:test` : tests du module ; `gradlew :syncclient:run` : lancer la fenêtre en développement
  (le démarrage avec Windows y est indisponible : il ne s'applique qu'à l'application installée).

### Ne pas lancer l'exécutable depuis `Documents\…\build`

Lancé depuis le dossier de build situé dans `Documents`, l'exécutable ne peut créer aucun fichier (erreur « accès
refusé » sur `config.json`). Toujours l'installer (ou copier `build/compose/binaries/main/app/HydriaSync` ailleurs).
Pour des essais sans toucher à la vraie configuration : `$env:HYDRIA_SYNC_DIR = 'C:\tmp\essai'` (le registre de
démarrage de Windows n'est alors jamais modifié).

## SmartScreen : « Windows a protégé votre ordinateur »

SmartScreen bloque les programmes **non signés** téléchargés depuis Internet (fichier marqué « téléchargé »), tant que
leur éditeur n'a pas de réputation. Ce n'est pas un défaut de l'application. Les solutions, de la meilleure à la plus
modeste :

1. **Signer l'installateur** avec un certificat de signature de code d'une autorité reconnue
   (`packaging/signer.ps1`). Depuis 2024, même un certificat EV n'efface plus l'avertissement d'un coup : la
   réputation se construit avec le nombre de téléchargements, mais un éditeur identifié est la condition de départ.
2. **Microsoft Store** (paquet MSIX) : pas d'avertissement SmartScreen, mais un compte développeur payant et une
   certification.
3. **Sans signature** (dépannage, petits déploiements internes) : sur chaque poste, clic droit sur l'installateur
   > Propriétés > cocher **Débloquer** > OK (ou PowerShell : `Unblock-File .\HydriaSync-1.1.0.exe`), puis l'ouvrir ;
   si l'écran bleu s'affiche malgré tout : « Informations complémentaires » > « Exécuter quand même ».
   Un installateur copié depuis une clé USB ou un partage réseau interne n'est pas marqué « téléchargé ».

Ne pas désactiver SmartScreen ni Defender, et ne pas ajouter d'exclusion : cela expose le poste.
