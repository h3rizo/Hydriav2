# IMPORT DIAMEX LOCAL - SYSTÈME DE CHEMINS DYNAMIQUES

## 📋 Vue d'ensemble

Ce document décrit le système d'import des données DiameX depuis les fichiers Access locaux vers Django, avec support des chemins dynamiques par employé.

## 🏗️ Architecture

### Principe
Au lieu de hardcoder les chemins des fichiers Access dans le script d'import, le système récupère dynamiquement la liste des fichiers depuis la base de données Django via une API REST.

### Flux de données
```
Windows Client (Ordinateur employé)
         ↓
  import_access_local.py
         ↓
  GET https://www.hydria.mg/employes/api/bases-diamex/
         ↓
Django API (views_bases_diamex.py)
         ↓
  Query EmployeBaseDiameX.objects.all()
         ↓
  Return JSON: {success: true, fichiers: [...]}
         ↓
Client reçoit liste des fichiers
         ↓
Import chaque fichier Access un par un
```

## 📂 Fichiers du système

### 1. API Django : `views_bases_diamex.py`

**Endpoint** : `GET /employes/api/bases-diamex/`

**Réponse JSON** :
```json
{
  "success": true,
  "fichiers": [
    {
      "path": "G:\\Mon Drive\\Compta\\fichier1.accde",
      "nom": "fichier1.accde",
      "employe": "HERIZO RAMAHEFARISOA",
      "employe_id": "uuid-123"
    }
  ],
  "count": 1
}
```

### 2. Script client : `import_access_local.py`

**Mode automatique** :
```bash
python import_access_local.py
```
- Récupère tous les fichiers depuis l'API
- Importe chaque fichier un par un

**Mode fichier unique** :
```bash
python import_access_local.py "G:\chemin\fichier.accde"
```
- Importe un seul fichier spécifié

## 🚀 Configuration

### Dans Django Admin

1. **Accéder à l'admin** : `https://www.hydria.mg/admin/employees/employebasediamex/`

2. **Créer une configuration** : Cliquer "Ajouter Employe base diame x"

3. **Remplir les champs** :
   - **Employé** : Sélectionner l'employé concerné
   - **Chemin dossier DiameX** : `G:\Mon Drive\Compta\` (avec backslash final)
   - **Nom fichier Base DiameX** : `fichier.accde`

4. **Enregistrer**

### Exemple de configuration

| Employé | Chemin dossier | Nom fichier |
|---------|----------------|-------------|
| HERIZO | `G:\Mon Drive\Compta Soakoja\` | `DiameX v3.16.1 - Base 1.accde` |
| VELONASY | `G:\Mon Drive\Compta Vavatenina\` | `DiameX v3.16.1 - Base 2.accde` |

## 📝 Utilisation

### Étape 1 : Vérifier configuration
```bash
cd "C:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend"
python import_access_local.py
```

### Étape 2 : Lire la sortie
**Sortie normale** :
```
============================================================
IMPORT DIAMEX LOCAL → DJANGO
============================================================
[API] Récupération de la liste des fichiers depuis Django...
[OK] 2 fichier(s) récupéré(s) depuis l'API
   1. DiameX v3.16.1 - Base 1.accde
   2. DiameX v3.16.1 - Base 2.accde

============================================================
Fichier: DiameX v3.16.1 - Base 1.accde
============================================================
[READ] Lecture du fichier Access...
[OK] 150 lignes DATA lues
[OK] 75 lignes SoldesReels lues
[SEND] Envoi vers Django...
[SUCCESS] Import réussi
```

## 🔧 Dépannage

### Erreur : HTTP 404
```
[ERROR] HTTP 404: <!DOCTYPE html>
```

**Solutions** :
1. Vérifier que Django est démarré
2. Vérifier URL dans script (ligne 21) : `DJANGO_URL = 'https://www.hydria.mg'`
3. Contacter admin pour vérifier route dans `urls.py`

### Erreur : Aucun fichier à importer
```
[ERROR] Aucun fichier à importer. Vérifiez la configuration dans Django.
```

**Solutions** :
1. Aller dans Django Admin
2. Créer au moins une entrée `EmployeBaseDiameX`
3. Vérifier que le chemin et nom sont corrects

### Erreur : Fichier introuvable
```
FileNotFoundError: Fichier introuvable: G:\...
```

**Solutions** :
1. Vérifier que le fichier existe à l'emplacement configuré
2. Vérifier que Google Drive est monté (si G:\)
3. Ouvrir l'explorateur Windows et copier/coller le chemin exact
4. Corriger la configuration dans Django Admin

### Erreur : Erreur réseau
```
[ERROR] Erreur réseau: ...
```

**Solutions** :
1. Vérifier connexion internet
2. Vérifier que `https://www.hydria.mg` est accessible
3. Essayer en mode local : `DJANGO_URL = 'http://localhost:8000'`

## ⚠️ Points d'attention CRITICAL

1. **Route URL** : La route `path('api/bases-diamex/', ...)` DOIT être placée AVANT les routes avec paramètres UUID dans `urls.py`

2. **Chemin avec backslash** : Le chemin doit se terminer par `\` : `G:\Mon Drive\Compta\` (PAS `G:\Mon Drive\Compta`)

3. **Google Drive** : Les fichiers doivent être synchronisés localement et accessibles via lettre de lecteur

4. **Permissions** : L'utilisateur doit avoir droits de lecture sur les fichiers Access

## ✅ Checklist déploiement

### Sur VPS Django :
- [ ] Fichier `views_bases_diamex.py` copié dans `backend/apps/employees/`
- [ ] Route ajoutée dans `urls.py` (AVANT routes avec paramètres)
- [ ] Gunicorn redémarré : `sudo systemctl restart gunicorn`
- [ ] API testée : `curl https://www.hydria.mg/employes/api/bases-diamex/`

### Sur ordinateur Windows :
- [ ] Python 3.x installé
- [ ] `pip install pyodbc requests`
- [ ] Microsoft Access Driver installé
- [ ] Chemins configurés dans Django Admin
- [ ] Script testé : `python import_access_local.py`

## 📞 Support

En cas de problème :
1. Vérifier logs du script (console)
2. Vérifier configuration Django Admin
3. Vérifier existence fichiers
4. Contacter équipe technique Hydria
