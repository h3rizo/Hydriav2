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

## Protection de l'arborescence

Activée par défaut (interrupteur « Protéger l'arborescence » dans la fenêtre). Elle évite qu'une fausse manipulation
dans le dossier Hydria désorganise l'arborescence ou fasse « perdre » des fichiers sur www.hydria.mg.

- **Dossiers verrouillés (Windows/NTFS)** : un sous-dossier de l'arborescence ne peut plus être supprimé, renommé ni
  déplacé (l'Explorateur répond « accès refusé »). On peut toujours y créer des fichiers, les ouvrir, les modifier et les
  enregistrer avec Word ou Excel : les fichiers ne sont volontairement pas verrouillés.
- **Rétablissement automatique** : à la synchronisation suivante (environ 1 min), un fichier déplacé ou renommé est
  remis à sa place (reconnu par son empreinte SHA-256, sans retéléchargement) ; un fichier supprimé est retéléchargé ; un
  dossier supprimé est recréé avec ses fichiers ; le dossier renommé qui reste vide est supprimé (s'il contient des fichiers
  de l'utilisateur, il n'est jamais touché). Rien n'est jamais envoyé au serveur par ce chemin : seul le PC est remis en ordre.
- **Le serveur n'est jamais touché** par un déplacement, un renommage ou une suppression faits sur le PC, protection ou non.

Limites :
- le **dossier racine** (par défaut `C:\Users\<nom>\Hydria`) ne peut pas être protégé contre le renommage ou la suppression,
  son parent étant le profil Windows : s'il est supprimé, l'application recrée l'arbre et retélécharge les fichiers ;
- ce n'est pas une barrière de sécurité : le propriétaire ou un administrateur peut lever les refus (Propriétés > Sécurité) ;
- hors NTFS, seul le rétablissement automatique agit.

**Avant de désinstaller** (sinon les dossiers verrouillés ne pourront plus être supprimés) : désactiver l'interrupteur,
ou cliquer sur « Se déconnecter » — les dossiers sont alors rendus. Si l'application n'est déjà plus là :

```powershell
icacls "$env:USERPROFILE\Hydria" /remove:d $env:USERNAME /t /c
```

(adapter le dossier s'il a été changé ; le résultat est vérifié par un test automatique). `HydriaSync.exe --lever-protection`
fait la même chose depuis l'application installée, sans ouvrir la fenêtre.

Pour les développeurs : `core/Protection.kt` (refus « Supprimer » + « Supprimer les enfants » sur chaque dossier géré, posés
par `AclFileAttributeView`) ; le moteur ne verrouille que les dossiers nouvellement créés après le premier scellement
(`Etat.protection`) car relire les permissions de milliers de dossiers coûte environ 1 ms chacun. Pourquoi les deux droits :
dans un dossier du profil, le contrôle total hérité donne « Supprimer les enfants » au parent, ce qui contournerait le seul refus
de « Supprimer » (mesuré, voir `ProtectionTest`). Les tests créent leurs dossiers dans le profil, pas dans le dossier temporaire
du système, dont les permissions varient d'une machine à l'autre.

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
   (`packaging/signer.ps1`, après `packageExe` / `packageMsi`, puis republier les fichiers signés). À savoir :
   - depuis juin 2023, la clé d'un certificat neuf est sur **matériel certifié** (clé USB du fournisseur) ou
     dans un **service cloud** (SSL.com eSigner, DigiCert KeyLocker…) : on ne reçoit plus de fichier `.pfx`.
     Le script accepte le certificat du magasin Windows (`HYDRIA_CERT_THUMBPRINT`), Azure Artifact Signing
     (`HYDRIA_SIGN_DLIB` + `HYDRIA_SIGN_METADATA`) ou un ancien `.pfx` ;
   - **Azure Artifact Signing** (ex-Trusted Signing, environ 10 $ par mois) est le moins cher, mais il est réservé
     aux organisations de certains pays (États-Unis, Canada, Union européenne, Royaume-Uni, Australie, Japon…) et
     aux particuliers des États-Unis et du Canada : **Madagascar n'y figure pas** d'après la documentation
     Microsoft consultée le 2026-10-27 (liste à revérifier : elle évolue) ;
   - un certificat classique (Sectigo, DigiCert, SSL.com…) coûte plusieurs centaines de dollars par an et exige une
     vérification d'identité de l'organisation (documents d'immatriculation) ;
   - une signature ne supprime pas l'avertissement le premier jour : la réputation se construit avec le nombre
     de téléchargements, mais un éditeur identifié en est la condition, et elle se conserve d'une version à
     l'autre (sans signature, chaque nouvelle version repart de zéro).
2. **Microsoft Store** (paquet MSIX) : pas d'avertissement SmartScreen, mais un compte développeur payant et une
   certification ; jpackage ne produit pas de MSIX, il faudrait un outil de paquetage en plus.
3. **Sans signature** (dépannage, petits déploiements internes) : sur chaque poste, clic droit sur l'installateur
   > Propriétés > cocher **Débloquer** > OK (ou PowerShell : `Unblock-File .\hydria-sync-1.1.1.exe`), puis l'ouvrir ;
   si l'écran bleu s'affiche malgré tout : « Informations complémentaires » > « Exécuter quand même ».
   Un installateur copié depuis une clé USB ou un partage réseau interne n'est pas marqué « téléchargé ».

Ne pas désactiver SmartScreen ni Defender, et ne pas ajouter d'exclusion : cela expose le poste.
