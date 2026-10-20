#!/usr/bin/env bash
# Construit le paquet Linux (.deb) de Hydria Operations depuis Ubuntu (WSL ou PC Linux).
#
# Prérequis (une seule fois) :  sudo apt install -y openjdk-17-jdk-headless fakeroot
# Usage depuis Windows      :  wsl -d Ubuntu-26.04 -- bash "<chemin WSL de ce script>"
#
# Le code est recopié dans ~/hydria-build (compiler sur /mnt/c est lent et mélangerait
# les dossiers build Windows et Linux). Build « desktop seul » : pas d'Android SDK requis.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_SRC="$(cd "$SCRIPT_DIR/.." && pwd)"            # android_app/HydriaAppAndroid
REPO_SRC="$(cd "$PROJECT_SRC/../.." && pwd)"           # racine (contient backend/)
BUILD_ROOT="$HOME/hydria-build"
PROJECT_DST="$BUILD_ROOT/android_app/HydriaAppAndroid"

echo "[1/4] Copie du code vers $BUILD_ROOT"
mkdir -p "$PROJECT_DST" "$BUILD_ROOT/backend/static/js" "$BUILD_ROOT/backend/static/images"
rsync -a --delete \
  --exclude '/app/' --exclude 'build/' --exclude '.gradle/' --exclude '.kotlin/' \
  --exclude '/work/' --exclude '/releases/' --exclude '/Claude outputs/' --exclude '*.apk' \
  --exclude '*.log' --exclude '/local.properties' \
  "$PROJECT_SRC/" "$PROJECT_DST/"
# Gabarit de facture de la page web (copié tel quel dans l'app, voir WebInvoicePrint.kt)
cp "$REPO_SRC/backend/static/js/print_factures_a4.js" "$BUILD_ROOT/backend/static/js/"
cp "$REPO_SRC/backend/static/images/mvola-logo.svg" "$BUILD_ROOT/backend/static/images/"
sed -i 's/\r$//' "$PROJECT_DST/gradlew"
chmod +x "$PROJECT_DST/gradlew"

echo "[2/4] Vérification des outils"
for tool in java fakeroot dpkg-deb objcopy; do
  command -v "$tool" >/dev/null || { echo "Outil manquant : $tool -> sudo apt install -y openjdk-17-jdk-headless fakeroot"; exit 1; }
done

echo "[3/4] Construction du .deb (desktop seul, sans Android)"
cd "$PROJECT_DST"
./gradlew --no-daemon -Phydria.desktopOnly=true :shared:desktopTest :desktopApp:test :desktopApp:packageDeb

echo "[4/4] Copie du paquet vers Windows"
DEB="$(ls "$PROJECT_DST"/desktopApp/build/compose/binaries/main/deb/*.deb)"
OUT="$PROJECT_SRC/desktopApp/build/linux"
mkdir -p "$OUT"
cp "$DEB" "$OUT/"
dpkg-deb --info "$DEB" | sed -n '1,20p'
echo "OK : $OUT/$(basename "$DEB")"
