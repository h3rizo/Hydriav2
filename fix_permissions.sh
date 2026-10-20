#!/bin/bash
# Script pour corriger les permissions pour Nginx + SELinux

echo "========================================="
echo "Correction des permissions pour PWA"
echo "========================================="

# 1. Donner accès exécution au répertoire home (sans toucher lecture/écriture)
echo "[1/4] Ajout permission exécution pour /home/soakoja..."
sudo chmod o+x /home/soakoja

# 2. Vérifier les permissions
echo "[2/4] Vérification des permissions..."
ls -ld /home/soakoja

# 3. Appliquer les bons contextes SELinux
echo "[3/4] Application des contextes SELinux..."
sudo semanage fcontext -a -t httpd_sys_content_t "/home/soakoja/hydria/backend/staticfiles(/.*)?"
sudo restorecon -Rv /home/soakoja/hydria/backend/staticfiles

# 4. Créer le dossier media s'il n'existe pas et appliquer les permissions
echo "[4/4] Configuration du dossier media..."
sudo mkdir -p /home/soakoja/hydria/backend/media
sudo chown soakoja:soakoja /home/soakoja/hydria/backend/media
sudo chmod 755 /home/soakoja/hydria/backend/media
sudo semanage fcontext -a -t httpd_sys_content_t "/home/soakoja/hydria/backend/media(/.*)?"
sudo restorecon -Rv /home/soakoja/hydria/backend/media

echo ""
echo "========================================="
echo "Permissions corrigées !"
echo "========================================="
echo ""
echo "Test d'accès au manifest :"
curl -I https://www.hydria.mg/static/manifest.json
