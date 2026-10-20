#!/usr/bin/env bash
# Construit le paquet Linux « hydria-widgets » (.deb) : les widgets Hydria de bureau (Electron)
# avec UN SEUL moteur Electron partagé, une entrée de menu par widget et le démarrage
# automatique Linux (~/.config/autostart).
#
# Usage depuis Windows : wsl -d Ubuntu-26.04 -- bash "<chemin WSL de ce script>"
# Aucun prérequis à installer (curl, python3, dpkg-deb sont fournis par Ubuntu).
#
# Les sources Windows ne sont PAS modifiées : un petit lanceur (linux-main.js) est ajouté
# dans le paquet ; il remplace app.setLoginItemSettings (sans effet sous Linux) puis
# charge le main.js d'origine du widget.
set -euo pipefail

VERSION="1.0.2"
ELECTRON_VERSION="31.7.7"          # même version que les widgets Windows
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_WIDGETS="$SCRIPT_DIR"
WORK="$HOME/hydria-build/widgets"
CACHE="$HOME/hydria-build/cache"
ROOT="$WORK/root"
PREFIX="/opt/hydria-widgets"

# id | nom affiché | dossier source | fichiers | description
WIDGETS=(
  "hydria-widget|Hydria Widget|$REPO_WIDGETS/WeatherWidgetElectron|main.js preload.js package.json icon.png weather_widget.html|Indicateurs Hydria : factures non pointées, opérations, DiameX"
  "hydria-compteurs|Hydria Compteurs de tête|$REPO_WIDGETS/CompteursTeteWidgetElectron|main.js preload.js package.json icon.png widget.html|Compteurs de tête : écarts du réseau"
  "hydria-debits|Hydria Débits source|$REPO_WIDGETS/DebitsSourceWidgetElectron|main.js preload.js package.json icon.png widget.html|Suivi des débits source"
  "hydria-consommation|Hydria Consommation|$REPO_WIDGETS/ConsommationWidgetElectron|main.js preload.js package.json icon.png widget.html|Analyse de la consommation"
  "hydria-interventions|Hydria Interventions|$REPO_WIDGETS/InterventionsWidgetElectron|main.js preload.js package.json icon.png widget.html|Interventions de la semaine"
  "hydria-planning|Hydria Planning|$REPO_WIDGETS/PlanningWidgetElectron|main.js preload.js package.json icon.png widget.html|Planning du jour et calendrier"
  "hydria-actions-rapides|Hydria Actions rapides|$REPO_WIDGETS/HydriaQuickActions|main.js preload.js package.json icon.png bubble.html|Bulle d'actions rapides Hydria"
)

echo "[1/5] Moteur Electron $ELECTRON_VERSION (Linux x64)"
mkdir -p "$CACHE"
ZIP="electron-v$ELECTRON_VERSION-linux-x64.zip"
BASE_URL="https://github.com/electron/electron/releases/download/v$ELECTRON_VERSION"
[ -f "$CACHE/$ZIP" ] || curl -fL --retry 3 -o "$CACHE/$ZIP" "$BASE_URL/$ZIP"
curl -fsL --retry 3 -o "$CACHE/SHASUMS256-$ELECTRON_VERSION.txt" "$BASE_URL/SHASUMS256.txt"
EXPECTED="$(grep " \*\?$ZIP\$" "$CACHE/SHASUMS256-$ELECTRON_VERSION.txt" | awk '{print $1}')"
ACTUAL="$(sha256sum "$CACHE/$ZIP" | awk '{print $1}')"
[ -n "$EXPECTED" ] && [ "$EXPECTED" = "$ACTUAL" ] || { echo "Empreinte SHA-256 invalide pour $ZIP"; rm -f "$CACHE/$ZIP"; exit 1; }
echo "  empreinte vérifiée : $ACTUAL"

echo "[2/5] Arborescence du paquet"
rm -rf "$WORK" && mkdir -p "$ROOT$PREFIX/electron" "$ROOT$PREFIX/apps" "$ROOT/usr/bin" "$ROOT/usr/share/applications" "$ROOT/DEBIAN"
python3 -m zipfile -e "$CACHE/$ZIP" "$ROOT$PREFIX/electron/"
chmod 755 "$ROOT$PREFIX/electron/electron"
# Bac à sable Chromium : doit être setuid root (voir postinst), sinon Electron refuse de démarrer
# sur les Ubuntu récents qui restreignent les espaces de noms non privilégiés.
chmod 4755 "$ROOT$PREFIX/electron/chrome-sandbox"

echo "[3/5] Widgets"
for entry in "${WIDGETS[@]}"; do
  IFS='|' read -r ID NAME SRC FILES COMMENT <<<"$entry"
  APP="$ROOT$PREFIX/apps/$ID"
  mkdir -p "$APP"
  for f in $FILES; do cp "$SRC/$f" "$APP/"; done
  # Classe de fenêtre (WM_CLASS) du widget = son app.setName(...), sinon le nom du package.json.
  # Déclarée dans StartupWMClass : sans elle, le bureau Linux ne sait pas relier la fenêtre à
  # son entrée de menu et peut afficher/activer la fenêtre d'un AUTRE widget (ex. Débits source
  # à la place de Hydria Widget).
  WMCLASS="$(python3 - "$SRC" <<'PY'
import json, os, re, sys
src = sys.argv[1]
m = re.search(r"app\.setName\(\s*['\"]([^'\"]+)['\"]", open(os.path.join(src, 'main.js'), encoding='utf-8').read())
pkg = json.load(open(os.path.join(src, 'package.json'), encoding='utf-8'))
print(m.group(1) if m else (pkg.get('productName') or pkg['name']))
PY
)"
  # package.json : point d'entrée = lanceur Linux (le main.js d'origine est chargé ensuite).
  python3 - "$APP/package.json" <<'PY'
import json, sys
p = sys.argv[1]
data = json.load(open(p, encoding='utf-8'))
data['main'] = 'linux-main.js'
json.dump(data, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
PY
  cat > "$APP/linux-main.js" <<JS
// Lanceur Linux ajouté au paquet .deb (source Windows inchangée).
// Sous Linux, app.setLoginItemSettings ne fait rien : on le remplace par un fichier
// ~/.config/autostart/$ID.desktop, puis on charge le widget d'origine.
const { app } = require('electron');
const fs = require('fs');
const os = require('os');
const path = require('path');

const autostartDir = path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config'), 'autostart');
const autostartFile = path.join(autostartDir, '$ID.desktop');
const entry = [
  '[Desktop Entry]',
  'Type=Application',
  'Name=$NAME',
  'Exec=/usr/bin/$ID',
  'Icon=$PREFIX/apps/$ID/icon.png',
  'StartupWMClass=$WMCLASS',
  'X-GNOME-Autostart-enabled=true',
  'NoDisplay=false',
  '',
].join('\n');

app.setLoginItemSettings = (settings = {}) => {
  try {
    if (settings.openAtLogin) {
      fs.mkdirSync(autostartDir, { recursive: true });
      fs.writeFileSync(autostartFile, entry, 'utf8');
    } else if (fs.existsSync(autostartFile)) {
      fs.unlinkSync(autostartFile);
    }
  } catch (error) {
    console.error('Démarrage automatique Linux impossible :', error);
  }
};
app.getLoginItemSettings = () => ({ openAtLogin: fs.existsSync(autostartFile) });

require('./main.js');
JS
  cat > "$ROOT/usr/bin/$ID" <<SH
#!/bin/sh
exec $PREFIX/electron/electron $PREFIX/apps/$ID "\$@"
SH
  chmod 755 "$ROOT/usr/bin/$ID"
  cat > "$ROOT/usr/share/applications/mg.hydria.$ID.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=$NAME
Comment=$COMMENT
Exec=/usr/bin/$ID
Icon=$PREFIX/apps/$ID/icon.png
StartupWMClass=$WMCLASS
Terminal=false
Categories=Utility;Office;
DESK
  echo "  $NAME  (fenêtre : $WMCLASS)"
done

echo "[4/5] Métadonnées Debian"
SIZE_KB="$(du -sk "$ROOT" | awk '{print $1}')"
cat > "$ROOT/DEBIAN/control" <<CTRL
Package: hydria-widgets
Version: $VERSION
Section: misc
Priority: optional
Architecture: amd64
Maintainer: Hydria <contact@hydria.mg>
Installed-Size: $SIZE_KB
Depends: libgtk-3-0t64 | libgtk-3-0, libnss3, libasound2t64 | libasound2, libgbm1, libxss1, libxtst6, libnotify4, xdg-utils
Description: Widgets de bureau Hydria
 Widgets Hydria (indicateurs, compteurs de tête, débits source, consommation,
 interventions, planning, actions rapides) avec un moteur Electron partagé.
CTRL
cat > "$ROOT/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
chown root:root /opt/hydria-widgets/electron/chrome-sandbox
chmod 4755 /opt/hydria-widgets/electron/chrome-sandbox
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
POST
chmod 755 "$ROOT/DEBIAN/postinst"

echo "[5/5] Construction du .deb"
DEB="$WORK/hydria-widgets_${VERSION}_amd64.deb"
dpkg-deb --root-owner-group --build "$ROOT" "$DEB" >/dev/null
OUT="$SCRIPT_DIR/build/linux"
mkdir -p "$OUT"
cp "$DEB" "$OUT/"
dpkg-deb --info "$DEB" | sed -n '1,16p'
echo "OK : $OUT/$(basename "$DEB") ($(du -h "$DEB" | cut -f1))"
