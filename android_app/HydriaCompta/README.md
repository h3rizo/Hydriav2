# Hydria Compta — application Android (fondation)

Application Android **native, offline-first** pour le module de comptabilité d'Hydria.
Projet **séparé** de l'app terrain `../HydriaAppAndroid`, réutilisant ses conventions
(paquet `mg.hydria.*`, `BASE_URL = https://www.hydria.mg`, toolchain JDK 17 / Gradle 9.5,
client HTTP léger `HttpURLConnection` + `org.json`).

Ce dépôt contient la **fondation** demandée : structure du projet, schéma Room des
entités comptables, et le mécanisme de synchronisation (outbox + workers). Les écrans
métier (grand livre, saisie, facturation, caisse, tiers, paie) restent à construire
par-dessus.

> Document de conception associé : `../../` → artifact « Fondation Compta Mobile Hydria ».

## Stack

| Domaine | Choix | Raison |
|---|---|---|
| UI | Jetpack Compose (Material3) | demandé |
| Persistance | **Room + SQLCipher** | source de vérité locale unique (cahier des charges) |
| Sync arrière-plan | **WorkManager** (3 workers) | retry / backoff / contraintes réseau |
| Réseau | `HttpURLConnection` + `org.json` (`ComptaApi`) | même approche que `HydriaApi`, zéro dépendance réseau |
| DI | manuel (`AppGraph` + `SyncWorkerFactory`) | pas de Hilt, cohérent avec la sobriété de l'app terrain |
| Dates | `java.time` (minSdk 26) | pas de desugaring |
| Chiffrement | SQLCipher, passphrase scellée Keystore | + verrou applicatif PIN/biométrie (à brancher) |

## Arborescence

```
app/src/main/java/mg/hydria/compta/
├── core/            Ariary (value class), enums, AppResult
├── engine/          logique comptable PURE, testable en JVM (équilibre D/C, TVA, balance âgée)
├── data/
│   ├── db/          Room : entities (réplique / locales / sync), DAOs, Converters, ComptaDatabase
│   │   └── entity/  ReplicaEntities · LocalEntities · SyncEntities
│   ├── prefs/       SessionStore (chiffré : device_id + jetons), SyncPreferences
│   ├── remote/      ComptaApi (HttpURLConnection), BootstrapMapper (JSON → entités)
│   ├── repository/  Auth, Outbox, Conflict
│   └── security/    PassphraseProvider (Keystore + EncryptedSharedPreferences)
├── sync/            SyncRepository (bootstrap / pull / push), Workers, SyncManager, SyncWorkerFactory
├── di/              AppGraph
└── ui/              AppRoot (login → écran d'attente sync → accueil) + SyncStatusChip
```

## Avant le premier build (Android Studio)

1. **Gradle wrapper** : `gradle-wrapper.jar` + `gradlew` sont repris de `../HydriaAppAndroid`
   (Gradle 9.5, toolchain JDK 17). Ouvrir le dossier `HydriaCompta` comme projet.
2. **Versions sensibles** — si la synchro Gradle échoue, aligner sur ce que propose l'IDE :
   - KSP `2.2.10-2.0.2` (doit correspondre à Kotlin `2.2.10`) — `build.gradle.kts` racine
   - Compose BOM `2024.06.00` — `app/build.gradle.kts` (un bump est sans risque)
   - AGP `9.3.2` — repris de l'app terrain
3. **SDK** : `compileSdk = 34`, `minSdk = 26`, `targetSdk = 34`.
4. Le dossier `app/schemas/` est généré au premier build (`room.schemaLocation`).

## État — ce qui marche, ce qui reste

**Opérationnel**
- Schéma Room complet (23 tables) + DAOs + chiffrement SQLCipher.
- Outbox transactionnel (`OutboxRepository.enqueue` écrit agrégat + mutation ensemble).
- 3 workers WorkManager + planification (`SyncManager`).
- `SyncRepository` : `runInitialSync` / `runPull` / `runPush` avec gestion
  accepted / conflict / rejected / transient et réconciliation des mutations « en vol ».
- Chip d'état de synchronisation (`SyncStatus`) alimenté par un `Flow` combiné.
- Moteur comptable pur + tests JVM (`EquilibrageTest`, `CalculTvaTest`).

**Connexion & endpoints serveur**
- `ComptaApi.login` → `POST /mobile/api/login/` (endpoint mobile Hydria en production,
  jeton `scope='mobile'` longue durée, form-encodé). Pas de refresh.
- `bootstrap` / `changes` / `mutations` → **`/api/mobile/v1/compta/*`**, livrés côté Django
  (`backend/apps/accounting/mobile_api_v1.py` + `urls_mobile_v1.py`). À déployer sur le VPS.
  Périmètre = **organisation** de l'employé ; grand livre = **exercice courant + N-1** ;
  capacités = lecture + saisie caisse/écritures.
- `changes` renvoie encore `full_refresh_required` (pas de champs de révision serveur).

**Formes de payload des mutations** (à produire par les futurs écrans de saisie) :
```
piece.submit            { base_id?, journal_id? | journal_code?, exercice_id, date,
                          description, lignes:[ {compte_numero, libelle?, debit, credit,
                          activ?, financement?, tiers?} ] }   // équilibre vérifié serveur
caisse.mouvement.create { caisse_id?, date, sens:"ENTREE"|"SORTIE", montant, motif,
                          compte_numero }
tiers.create            { nom, code_tiers?, nif?, stat?, cin?, telephone?, email?, adresse? }
```
Réponse : `{ results:[ {local_uuid, status:"accepted"|"rejected", server_id?, errors?} ] }`.
Idempotence V1 faible : jeton `mobile:<local_uuid>` stocké dans `SaisieComptable.info`.

**À faire (§7)**
- Facture / devis : mutation `facture.*` + modèle `FactureVente` côté Django.
- Champs `revision` / `deleted_at` serveur → vrai delta `changes`.
- `BootstrapMapper` : `caisses`, `baremes`, `employes_paie`, `soldes_reels`.
- Restreindre les tiers aux fournisseurs mouvementés dans le grand livre de l'organisation
  (aujourd'hui : tous les fournisseurs actifs, cap `TIERS_MAX_ROWS`).
- `BootstrapMapper` : compléter `soldes_reels`, `caisses`, `baremes`, `employes_paie`
  (même patron que `comptes` / `tiers`).
- `SyncRepository.appliquerAcceptation` : brancher facture (consommer le numéro de plage),
  mouvement de caisse, règlement, tiers.
- `changes` incrémental : nécessite `updated_at` / `deleted_at` / `revision` côté serveur
  sur `BaseDiameX`, `Compte`, `Journal`, `Fournisseur` — sinon `full_refresh` à chaque fois.
- Verrou applicatif (PIN / biométrie) : `data/security/AppLock` à créer, à insérer avant
  l'ouverture de la base dans `AppRoot`.
- ConnectivityManager `NetworkCallback` → `SyncManager.setOnline(...)`.
- Écrans : grand livre, saisie multi-lignes, facturation + PDF (`android.graphics.pdf`),
  caisse, tiers, simulateur de paie, **file de revue des conflits**.
- Passer l'accès Room derrière des `ViewModel` sur `Dispatchers.IO`
  (l'`AppRoot` de démo y touche encore depuis la composition, via `produceState` + IO).

## Tests

```
./gradlew :app:testDebugUnitTest
```

Les suites `engine/` ne dépendent ni de Room ni du réseau.
