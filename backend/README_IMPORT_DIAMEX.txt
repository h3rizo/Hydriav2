================================================================================
                    IMPORT DIAMEX LOCAL - GUIDE D'INSTALLATION
================================================================================

📋 DESCRIPTION

Ce package permet d'importer les données des fichiers DiameX (Access) depuis
n'importe quel ordinateur Windows vers le système Hydria.

Les données sont lues localement depuis les fichiers .accde et envoyées
automatiquement vers le serveur Django via l'API REST.


📦 CONTENU DU PACKAGE

1. INSTALLER_IMPORT_DIAMEX.bat    - Script d'installation (a executer UNE FOIS)
2. LANCER_IMPORT.bat              - Script de lancement (a executer pour importer)
3. LANCER_AGENT_DIAMEX.bat        - Lancement de l'agent local (boutons web)
4. import_diamex_portable.py      - Script Python portable
5. diamex_local_agent.py          - Agent local (serveur)
6. config_import.ini              - Fichier de configuration
7. README_IMPORT_DIAMEX.txt       - Documentation complete

PRÉREQUIS

1. ✅ Système d'exploitation : Windows 7 ou supérieur

2. ✅ Python 3.6 ou supérieur installé
   - Télécharger depuis : https://www.python.org/downloads/
   - IMPORTANT : Cocher "Add Python to PATH" lors de l'installation

3. ✅ Microsoft Access Database Engine (driver ODBC)
   - Automatiquement installé si vous avez Microsoft Office
   - Sinon, télécharger "Microsoft Access Database Engine 2016 Redistributable"
     https://www.microsoft.com/en-us/download/details.aspx?id=54920
   - Choisir la version selon votre système :
     * 32-bit (x86) pour Windows 32-bit OU Office 32-bit
     * 64-bit (x64) pour Windows 64-bit ET Office 64-bit

4. ✅ Accès réseau au serveur Django (https://www.hydria.mg)


📥 INSTALLATION (PREMIÈRE FOIS UNIQUEMENT)

Étape 1 : Créer un dossier pour l'import
-------------------------------------------
1. Créer un nouveau dossier, par exemple :
   C:\ImportDiameX

2. Copier TOUS les fichiers du package dans ce dossier


Étape 2 : Exécuter l'installation
-----------------------------------
1. Double-cliquer sur INSTALLER_IMPORT_DIAMEX.bat

2. Le script va :
   ✓ Vérifier que Python est installé
   ✓ Installer les dépendances Python (pyodbc, requests, pillow)
   ✓ Vérifier la disponibilité du driver Access

3. Si tout est OK, vous verrez :
   [OK] Python détecté
   [OK] Dépendances installées avec succès
   [OK] Driver Access disponible

4. Si des erreurs apparaissent :
   - Installer Python si manquant
   - Installer le driver Access si manquant


Étape 3 : Vérifier la configuration
-------------------------------------
1. Ouvrir config_import.ini avec le Bloc-notes

2. Vérifier l'URL du serveur Django :
   DJANGO_URL = https://compta.hydria.mg

3. Pour tester en local (développement uniquement) :
   # DJANGO_URL = https://compta.hydria.mg   (commenter avec #)
   DJANGO_URL = http://localhost:8000         (décommenter)

4. Ajuster le timeout si nécessaire (par défaut 300 secondes = 5 minutes)


🚀 UTILISATION QUOTIDIENNE

NOUVEAU - IMPORT VIA AGENT LOCAL (BOUTONS WEB)
----------------------------------------------
1. Lancer LANCER_AGENT_DIAMEX.bat (laisser la fenetre ouverte)
2. Ouvrir https://www.hydria.mg/comptabilite/import/
3. Cliquer sur "Importer depuis Windows" puis:
   - Tester connexion agent
   - Importer via agent local
   - Choisir "Lignes de compta seulement" ou "Lignes de compta + scans"

Note:
- L'agent local lit les fichiers Access depuis votre PC
- Les scans peuvent aussi etre copies vers le serveur pour consultation web/mobile
- Les scans .tif/.tiff sont convertis en PDF pendant l'upload pour un affichage navigateur plus lisible
- Les scans deja presents sur le serveur ne sont pas renvoyes
- Le navigateur ne peut pas lancer les .bat directement (securite)



Une fois l'installation terminée, pour importer les données :

1. Double-cliquer sur LANCER_IMPORT.bat

2. Le script va :
   ✓ Se connecter à l'API Django
   ✓ Récupérer la liste des fichiers Access configurés
   ✓ Importer chaque fichier automatiquement

3. Vous verrez la progression :
   [API] Récupération de la liste des fichiers depuis Django...
   [OK] 2 fichier(s) récupéré(s) depuis l'API
      1. DiameX v3.16.1 - Base 1.accde
      2. DiameX v3.16.1 - Base 2.accde

   [READ] Lecture du fichier Access...
   [OK] 1234 lignes DATA lues
   [OK] 567 lignes SoldesReels lues

   [SEND] Envoi vers Django...
   [SUCCESS] Import réussi
   [✓] Import réussi pour DiameX v3.16.1 - Base 1.accde


📁 CONFIGURATION DES FICHIERS DIAMEX

Les chemins des fichiers Access à importer sont configurés dans Django :

1. Accéder à : https://www.hydria.mg/admin/employees/employebasediamex/

2. Pour chaque employé, renseigner :
   - Employé : Sélectionner l'employé
   - Chemin dossier DiameX : Ex: G:\Mon Drive\Compta Soakoja\
   - Nom fichier Base DiameX : Ex: DiameX v3.16.1 - Base 1.accde

3. Le chemin complet sera automatiquement généré :
   G:\Mon Drive\Compta Soakoja\DiameX v3.16.1 - Base 1.accde


🐛 DÉPANNAGE

Problème : "Python n'est pas installé"
-----------------------------------------
Solution :
1. Télécharger Python depuis https://www.python.org/downloads/
2. IMPORTANT : Cocher "Add Python to PATH" lors de l'installation
3. Redémarrer l'ordinateur
4. Relancer INSTALLER_IMPORT_DIAMEX.bat


Problème : "Driver Microsoft Access non détecté"
--------------------------------------------------
Solution :
1. Si Microsoft Office installé → Le driver devrait être présent
2. Sinon, télécharger "Access Database Engine 2016 Redistributable"
3. Choisir la bonne version (32-bit OU 64-bit selon votre Office)
4. Installer et redémarrer
5. Relancer INSTALLER_IMPORT_DIAMEX.bat


Problème : "Fichier introuvable"
----------------------------------
Solution :
1. Vérifier que le chemin dans Django est correct
2. Vérifier que le fichier .accde existe bien à cet emplacement
3. Vérifier les permissions d'accès au fichier


Problème : "Erreur réseau"
---------------------------
Solution :
1. Vérifier la connexion internet
2. Vérifier que https://www.hydria.mg est accessible
3. Augmenter le TIMEOUT dans config_import.ini si la connexion est lente


Problème : "HTTP 500 - Erreur serveur"
----------------------------------------
Solution :
1. Vérifier que l'employé est bien configuré dans Django
2. Vérifier que le surnom de l'employé est correct
3. Contacter l'administrateur système


📞 SUPPORT

En cas de problème non résolu, contacter l'administrateur système avec :
- Message d'erreur complet affiché
- Capture d'écran si possible
- Contenu du fichier config_import.ini


📋 NOTES IMPORTANTES

1. L'import peut prendre plusieurs minutes selon :
   - La taille des fichiers Access
   - Le nombre de fichiers à importer
   - La vitesse de la connexion internet

2. Ne PAS fermer la fenêtre pendant l'import
   - Attendre le message "TERMINÉ"
   - Vérifier qu'il n'y a pas d'erreurs

3. Les données importées sont automatiquement :
   - Associées à votre compte employé
   - Visibles dans l'interface web Hydria
   - Sauvegardées en base de données

4. Chaque import :
   - Met à jour les données existantes (pas de doublons)
   - Crée de nouvelles entrées si nécessaire
   - Conserve l'historique des modifications


🔄 MISE À JOUR

Pour mettre à jour le package d'import :
1. Télécharger la nouvelle version
2. Remplacer les fichiers existants
3. Relancer INSTALLER_IMPORT_DIAMEX.bat (pour mettre à jour les dépendances)


📜 HISTORIQUE DES VERSIONS

Version 1.0 - Janvier 2026
- Première version portable
- Support configuration INI
- Installation automatique des dépendances
- Documentation complète


================================================================================
                            FIN DU GUIDE
================================================================================
