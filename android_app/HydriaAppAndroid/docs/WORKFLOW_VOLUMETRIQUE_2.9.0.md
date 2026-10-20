# Hydria Android 2.9.0 — workflow volumétrique

## Périmètre de cette version

Écrans Android natifs accessibles par **menu ⋮ → Workflow volumétrique**.
Impression **A4/PDF uniquement**, conformément au choix utilisateur du 5 septembre 2026.
Le Bluetooth thermique n'est pas inclus.

Cette version travaille sur les **relevés déjà présents sur le serveur et préchargés**
sur le téléphone par ouvrage et mois de facturation. Le mois de facturation est le mois
suivant celui du relevé. Les nouveaux relevés saisis dans l'écran Terrain doivent d'abord
être synchronisés, puis préchargés dans ce module avant facturation.

Le calcul repose sur le moteur Django existant, avec abonnement, volume minimum,
cartes sociales, volume non facturé, tranches et arrondi. Le téléphone conserve le calcul
et sa version ; il ne duplique pas le moteur tarifaire. À la synchronisation, le serveur
recalcule et refuse une opération basée sur un relevé ou tarif modifié.

## Utilisation

1. Avec une connexion, ouvrir le module et actualiser les ouvrages.
2. Sélectionner l'ouvrage et le mois, puis **Précharger / actualiser ce mois**.
3. Sans réseau, utiliser **Ouvrir les données hors ligne** pour une période téléchargée.
4. Sélectionner les factures, puis **Actions sur les factures sélectionnées** :
   - **Valider la facturation** enregistre une opération locale de validation.
   - **Imprimer en A4 / PDF** ouvre le service d'impression Android. Le document et le
     QR code sont produits entièrement sur le téléphone, une facture par page A4.
   - **Confirmer l'impression réalisée** s'utilise uniquement après constat de
     l'impression. Ouvrir le dialogue ou enregistrer un PDF ne marque pas automatiquement
     une facture comme imprimée.
   - **Encaisser** demande le journal (caisse personnelle ou journal de la base), puis
     confirme la réception du total exact, sans paiement partiel.
   - **Pointer sur DiameX** propose les écritures préchargées de même montant pour le
     même ouvrage et le même mois. Le serveur vérifie à nouveau cette association.
5. **Scanner une facture** utilise la caméra et le décodeur embarqué. Une saisie manuelle
   du numéro est également disponible. Les scans répétés ne doublent pas la sélection.
6. Au retour du réseau, synchroniser depuis le module ou depuis le menu principal.

L'impression sans Internet reste dépendante de l'accès local à l'imprimante et de son
service Android. **Enregistrer au format PDF** reste possible sans imprimante.

Une validation non encore synchronisée est signalée explicitement sur la facture A4.
Le document distingue le montant de cette facture des arriérés ; il ne vaut pas reçu.
Les factures sont classées par IDXLS numérique, puis nom d'abonné.

## États et traçabilité

- Calcul préchargé / validation à synchroniser / facture validée.
- Encaissement sur ce téléphone / encaissement confirmé par le serveur.
- Pointage à synchroniser / pointage confirmé avec référence DiameX.

Les paiements locaux restent dans SQLite. L'encaissement confirmé crée une ligne
`DiameXTemporaire` au compte `707401`, puis renseigne la date et le montant du paiement.
Le pointage s'effectue sur une **écriture réelle `BaseDiameX`**, après import DiameX.
Le module ne réalise pas lui-même l'export vers Access ni l'import DiameX.

Chaque opération possède un UUID persistant. Le serveur conserve sa réponse dans
`MobileVolumeOperation` dans la même transaction que les effets métier. Une requête
renvoyée après perte de réponse obtient la même confirmation sans nouveau paiement.
Un UUID réutilisé avec un autre contenu ou un autre compte est refusé.

Les factures concernées sont verrouillées pendant la transaction. Le pointage verrouille
aussi l'écriture DiameX et refuse de réutiliser un segment déjà pointé. Le montant du
segment est extrait côté serveur ; le téléphone ne peut pas imposer un montant arbitraire.
Les détails des factures validées/imprimées/encaissées via le module sont conservés dans
`MobileVolumeInvoiceSnapshot` pour les réimpressions après changement de tarif.

Les caches sont isolés par compte. Les opérations sont stockées dans la file Terrain
existante. Un verrou partagé empêche les deux écrans Android de synchroniser la même
opération en parallèle. La réception des factures et le retrait de la file sont atomiques
dans SQLite. Les factures sont conservées séparément pour limiter la taille des lignes.

L'historique local conserve les montants saisis et les refus. Une opération explicitement
refusée peut être clôturée **après vérification manuelle**, avec une note obligatoire.
Cette clôture conserve la trace locale et ne crée ni remboursement ni écriture comptable.
Une réponse réseau incertaine doit être retentée ; elle n'est pas clôturable ainsi.

## Backend à mettre en service avant distribution

Le code et la migration sont préparés localement. Ils ne sont pas déployés automatiquement.

Fichiers nouveaux :

- `backend/apps/billing/models_mobile_volume.py`
- `backend/apps/billing/views_mobile_volume.py`
- `backend/apps/billing/migrations/0078_mobile_volume_operation.py`

Intégrations à reporter dans les fichiers existants :

- `backend/apps/billing/models.py` : importer les deux modèles mobiles.
- `backend/apps/billing/urls.py` : importer `views_mobile_volume` et ajouter les routes
  `api/mobile/volume/bootstrap/` et `api/mobile/volume/sync/`.

Import à ajouter dans `apps/billing/models.py` :

```python
from .models_mobile_volume import MobileVolumeOperation, MobileVolumeInvoiceSnapshot
```

Import à ajouter dans `apps/billing/urls.py` :

```python
from . import views_mobile_volume
```

Routes à ajouter dans la liste `urlpatterns` existante :

```python
path('api/mobile/volume/bootstrap/', views_mobile_volume.bootstrap, name='mobile_volume_bootstrap'),
path('api/mobile/volume/sync/', views_mobile_volume.sync_operation, name='mobile_volume_sync'),
```

Sur le VPS, dans `/home/soakoja/hydria/backend`, avec l'environnement Django de production :

```bash
python manage.py check
python manage.py migrate billing 0078_mobile_volume_operation
sudo systemctl restart gunicorn
```

Utiliser la procédure WinSCP du projet, sauvegarder les fichiers serveur et comparer les
fichiers existants avant remplacement. La migration ajoute deux tables ; elle ne modifie
pas les anciennes données de relevés. Aucun build Nuxt n'est requis pour ce module natif.

Routes (authentification mobile existante) :

```text
GET  /facturation/api/mobile/volume/bootstrap/
GET  /facturation/api/mobile/volume/bootstrap/?ouvrage_id=UUID&mois=2026-09
POST /facturation/api/mobile/volume/sync/
```

Une sélection est limitée à 500 factures par opération et à un seul ouvrage/mois pour
l'encaissement et le pointage. Les paiements partiels ne sont pas pris en charge.

## Vérifications

Vérifications automatiques préparées :

```text
python manage.py test apps.billing.tests_mobile_volume
python manage.py makemigrations billing --check --dry-run
gradlew.bat :app:testDebugUnitTest :app:assembleDebug
```

Les tests Django du module isolent la logique avec des doubles de base de données ; ils
ne constituent pas un test de concurrence PostgreSQL en production. Ils couvrent la
reprise d'une réponse perdue, la version du calcul, le refus des doublons, le périmètre,
les journaux, le montant DiameX et la séparation impression/encaissement/pointage.

À vérifier sur un appareil de recette après mise en service du backend :

1. Précharger, activer le mode avion, fermer puis rouvrir l'application.
2. Valider une facture, scanner son QR, imprimer en A4/PDF et enregistrer un encaissement.
3. Revenir en ligne et synchroniser deux fois : une seule ligne temporaire doit exister.
4. Pointer une écriture importée ; tenter de réutiliser la même écriture depuis un second appareil.
5. Vérifier un refus après modification d'un tarif ou encaissement depuis le web.
6. Vérifier l'impression réelle, les caractères accentués, le scan caméra, l'annulation
   du dialogue d'impression et la conservation des opérations après redémarrage.

Aucun appareil Android ni émulateur n'était connecté lors de la préparation. Le scan
caméra et l'impression physique nécessitent donc cette recette matérielle.

Résultats du 6 septembre 2026 : **14 tests Django du module réussis**, **46 tests
unitaires Android réussis**, APK debug 2.9.0 compilé, aucune modification de modèle
non couverte par migration détectée pour `billing`. La base de production n'a pas été
modifiée et le backend n'a pas été déployé pendant cette préparation.

## Compilation Windows

Sur ce poste, Gradle peut échouer avec `Unable to establish loopback connection`.
Le répertoire de sockets Java a été redirigé vers un chemin court pour la commande :

```powershell
$env:JAVA_HOME='C:/Users/Dir Soakoja/.gradle/jdks/jetbrains_s_r_o_-17-amd64-windows.2'
$env:JAVA_TOOL_OPTIONS='-Djdk.net.unixdomain.tmpdir=C:/tmp/hydria-gradle'
.\gradlew.bat :app:testDebugUnitTest :app:assembleDebug --console=plain --no-daemon
```

Références techniques : [scanner ZXing embarqué](https://github.com/journeyapps/zxing-android-embedded)
et [propriété Java du répertoire de sockets](https://docs.oracle.com/en/java/javase/16/core/networking-properties.html).
