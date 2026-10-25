# Hydria Backend - Django API

## Configuration
API Django avec connexion Supabase PostgreSQL pour la gestion des activités d'approvisionnement en eau à Madagascar.

## Commandes

### Activer l'environnement virtuel
```powershell
# PowerShell (recommandé)
.\venv\Scripts\Activate.ps1

# Command Prompt
venv\Scripts\activate.bat

# Git Bash
source venv/Scripts/activate
```

### Installation et lancement
```bash
# Installer dépendances
pip install -r requirements.txt

# Migrations
python manage.py migrate

# Lancer le serveur
python manage.py runserver
```

## Structure
- `hydria/` - Configuration Django principale
- `apps/` - Applications Django modulaires
- `static/` - Fichiers statiques
- `templates/` - Templates Django
- `media/` - Fichiers media uploadés
## Synchronisation de fichiers (`apps/sync`)

Synchronisation type Dropbox entre Hydria et les ordinateurs des utilisateurs, et accès aux fichiers depuis
les pages Hydria. Le client desktop n'est pas dans ce dépôt. Analyse : `docs/sync-analysis.md` ;
exploitation (sauvegardes, disque) : `docs/exploitation.md`.

### Routes

Erreurs : `{"code": "...", "message": "..."}`. Authentification : `Authorization: Bearer <jeton>` (scope `sync`)
ou session Django (pages Hydria, CSRF exigé).

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/api/sync/auth/login` | `username`, `password`, `device_id` (UUID), `device_label` → `access_token` (1 h) + `refresh_token` (30 j) |
| POST | `/api/sync/auth/refresh` | `refresh_token` → nouvelle paire (le renouvellement est à usage unique) |
| GET | `/api/sync/changes?since=<seq>&limit=&organisation=&appareil=` | Changements visibles, par `seq` croissant ; `next_seq`, `has_more` |
| GET | `/api/sync/arborescence?organisation=<id>` | Branche territoire + branche organisation (domaines et catégories) |
| POST | `/api/sync/upload` | multipart : `fichier`, `categorie`, et (`entity_type` + `entity_id`) **ou** `domaine` |
| GET | `/api/fichiers/?entity_type=&entity_id=` ou `?domaine=[&categorie=]` | Liste des fichiers (pages Hydria) |
| PATCH | `/api/fichiers/<id>/` | Renommer (`nom`) et/ou remplacer le contenu (`fichier`, crée une version) ; **`If-Match: <version>`** obligatoire, `409` si conflit |
| DELETE | `/api/fichiers/<id>/` | Suppression logique (toutes les versions déplacées dans `_corbeille/`) |
| GET | `/api/fichiers/<id>/versions/` | Historique du contenu (numéro, nom, sha256, taille, origine, courante) |
| GET | `/api/fichiers/<id>/versions/<n>/telechargement` | Contenu d'une ancienne version |
| POST | `/api/fichiers/<id>/versions/<n>/restaurer` | Recopie la version n comme nouvelle version courante (`If-Match` obligatoire) |
| GET | `/api/fichiers/<id>/telechargement` | Contenu, après contrôle des droits (aucun lien public) |

Types d'entités : `region`, `district`, `commune`, `fokontany`, `village`, `ouvrage`, `equipement`, `point_eau`, `activite`.
Domaines : `operationnel`, `administratif`, `financier`, `logistique`.

### Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `HYDRIA_STORAGE_DIR` | `/srv/hydria/storage` | Répertoire des fichiers (jamais servi par nginx/Django, hors `media/`) |
| `HYDRIA_TAILLE_MAX_MO` | `100` | Taille maximale par fichier |
| `HYDRIA_QUOTA_ORGA_GO` | `50` | Quota par organisation (compte toutes les versions) |
| `HYDRIA_VERSIONS_MAX` | `20` | Versions de contenu conservées par fichier (les plus anciennes vont dans `_corbeille/`) |

Droits par domaine : `apps/sync/acces.py` (réglage `HYDRIA_SYNC_REGLES_DOMAINES`). Les domaines financier et
administratif n'ont volontairement aucune règle : seuls les superutilisateurs y accèdent.

### Tests

```bash
python manage.py test apps.sync            # stockage (sans base) + routes/triggers (base PostgreSQL de test)
python manage.py test apps.sync.tests.test_stockage
```
Les tests de routes créent une base `test_<nom>` séparée (la base de développement n'est pas modifiée) ; la
création rejoue toutes les migrations du projet et prend quelques minutes.
