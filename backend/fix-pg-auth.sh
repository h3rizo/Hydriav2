#!/bin/bash
# Script pour corriger l'authentification PostgreSQL
# Exécuter avec: sudo bash fix-pg-auth.sh

set -e

echo "========================================="
echo "  CORRECTION AUTHENTIFICATION POSTGRESQL"
echo "========================================="

PG_HBA="/var/lib/pgsql/data/pg_hba.conf"

echo "[1/4] Sauvegarde du fichier pg_hba.conf..."
cp "$PG_HBA" "${PG_HBA}.backup.$(date +%Y%m%d_%H%M%S)"
echo "[OK] Backup créé"

echo ""
echo "[2/4] Modification de l'authentification..."
# Remplacer 'ident' par 'md5' pour les connexions locales
sed -i 's/\(host.*all.*all.*127\.0\.0\.1\/32.*\)ident/\1md5/g' "$PG_HBA"
sed -i 's/\(host.*all.*all.*::1\/128.*\)ident/\1md5/g' "$PG_HBA"

echo "[OK] Fichier modifié"

echo ""
echo "[3/4] Affichage de la configuration..."
echo "--- Lignes pertinentes dans pg_hba.conf ---"
grep -E "^host.*all.*all.*(127\.0\.0\.1|::1)" "$PG_HBA" || echo "Aucune ligne trouvée"
echo "-------------------------------------------"

echo ""
echo "[4/4] Redémarrage de PostgreSQL..."
systemctl restart postgresql
echo "[OK] Service redémarré"

echo ""
echo "========================================="
echo "  TEST DE CONNEXION"
echo "========================================="
echo ""
echo "Test avec psql..."
PGPASSWORD='hydria_password_2025' psql -h localhost -U hydria -d hydria -c "SELECT version();" && echo "" && echo "[OK] Connexion réussie!" || echo "[ERREUR] La connexion a échoué"

echo ""
echo "========================================="
echo "  CORRECTION TERMINÉE"
echo "========================================="
