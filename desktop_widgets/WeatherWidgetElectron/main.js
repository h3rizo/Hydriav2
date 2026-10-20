const { app, BrowserWindow, screen, ipcMain, Menu, Tray, globalShortcut, session, Notification, shell } = require('electron');
const path = require('path');
const fs = require('fs');

// Sur Windows, force Electron a utiliser le fournisseur de localisation
// natif (WinRT) au lieu du service Google Location (bloque en interne).
app.commandLine.appendSwitch('enable-features', 'WinrtGeolocationImplementation');
app.setAppUserModelId('mg.hydria.widget.desktop');

const CONFIG_PATH = path.join(app.getPath('userData'), 'widget-position.json');
const WINDOWS_STARTUP_SCRIPT = process.platform === 'win32' && process.env.APPDATA
  ? path.join(process.env.APPDATA, 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup', 'Hydria Widget.vbs')
  : null;

let win = null;
let tray = null;
let alwaysOnTopEnabled = true;
let openAtLoginEnabled = true;

const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (!win) return;
    if (win.isMinimized()) win.restore();
    win.show();
    win.focus();
  });
}

function loadPosition() {
  try {
    const raw = fs.readFileSync(CONFIG_PATH, 'utf-8');
    const data = JSON.parse(raw);
    return data;
  } catch (e) {}
  return null;
}

function savePosition(x, y) {
  const current = loadPosition() || {};
  current.x = x;
  current.y = y;
  try {
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(current));
  } catch (e) {}
}

function saveAlwaysOnTop(enabled) {
  const current = loadPosition() || {};
  current.alwaysOnTop = enabled;
  try {
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(current));
  } catch (e) {}
}

function saveOpenAtLogin(enabled) {
  const current = loadPosition() || {};
  current.openAtLogin = enabled;
  try {
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(current));
  } catch (e) {}
}

function setOpenAtLogin(enabled) {
  try {
    if (WINDOWS_STARTUP_SCRIPT) {
      if (enabled) {
        const executable = process.execPath.replace(/"/g, '""');
        const appDirectory = path.resolve(__dirname).replace(/"/g, '""');
        const command = process.defaultApp
          ? `Chr(34) & "${executable}" & Chr(34) & " " & Chr(34) & "${appDirectory}" & Chr(34)`
          : `Chr(34) & "${executable}" & Chr(34)`;
        const script = [
          "' Lance Hydria Widget sans fenetre console a l'ouverture de session.",
          'Set shell = CreateObject("WScript.Shell")',
          `shell.CurrentDirectory = "${appDirectory}"`,
          `shell.Run ${command}, 0, False`,
          ''
        ].join('\r\n');
        fs.mkdirSync(path.dirname(WINDOWS_STARTUP_SCRIPT), { recursive: true });
        fs.writeFileSync(WINDOWS_STARTUP_SCRIPT, script, 'utf8');
      } else if (fs.existsSync(WINDOWS_STARTUP_SCRIPT)) {
        fs.unlinkSync(WINDOWS_STARTUP_SCRIPT);
      }
    } else {
      app.setLoginItemSettings({ openAtLogin: enabled });
    }
    openAtLoginEnabled = enabled;
    saveOpenAtLogin(enabled);
  } catch (error) {
    console.error('Impossible de configurer le demarrage Windows :', error);
  }

  if (tray) buildTrayMenu();
}

function saveHydriaToken(token) {
  const current = loadPosition() || {};
  current.hydriaToken = token;
  try {
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(current));
  } catch (e) {}
}

function clearHydriaToken() {
  const current = loadPosition() || {};
  delete current.hydriaToken;
  try {
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(current));
  } catch (e) {}
}

function fitWidgetToWorkArea() {
  if (!win) return;
  const current = win.getBounds();
  const display = screen.getDisplayMatching(current);
  const workArea = display.workArea;
  const x = Math.max(workArea.x, Math.min(current.x, workArea.x + workArea.width - current.width));
  const target = {
    x,
    y: workArea.y,
    width: current.width,
    height: workArea.height
  };
  if (
    current.x !== target.x || current.y !== target.y ||
    current.width !== target.width || current.height !== target.height
  ) {
    win.setBounds(target);
  }
}

function createWindow() {
  const saved = loadPosition();
  const primaryDisplay = screen.getPrimaryDisplay();
  const winWidth = 300;
  const savedPoint = saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)
    ? { x: saved.x, y: saved.y }
    : null;
  const targetDisplay = savedPoint ? screen.getDisplayNearestPoint(savedPoint) : primaryDisplay;
  const workArea = targetDisplay.workArea;
  const defaultX = workArea.x + workArea.width - winWidth - 30;
  const initialX = Math.max(
    workArea.x,
    Math.min(savedPoint ? savedPoint.x : defaultX, workArea.x + workArea.width - winWidth)
  );

  win = new BrowserWindow({
    width: winWidth,
    height: workArea.height,
    x: initialX,
    y: workArea.y,
    frame: false,
    // Meme base que les autres widgets Hydria : fond opaque (#071d25) en secours.
    // Sans backgroundColor, une machine ou l'acrylique n'est pas applique
    // (transparence desactivee, economiseur de batterie, bureau a distance,
    // pilote graphique) affichait une fenetre blanche : texte blanc sur blanc.
    transparent: false,
    backgroundColor: '#071d25',
    backgroundMaterial: 'acrylic',
    roundedCorners: true,
    // resizable doit rester true pour que win.setSize() (redimensionnement
    // programmatique automatique selon le contenu) fonctionne de façon
    // fiable sur Windows — sur certaines versions, resizable:false peut
    // faire ignorer setSize() par le compositeur. L'utilisateur ne peut
    // de toute façon pas redimensionner à la souris : pas de bordure
    // visible (frame:false) et aucune poignée de resize n'est exposée.
    resizable: true,
    maximizable: false,
    fullscreenable: false,
    alwaysOnTop: true,
    skipTaskbar: false,
    hasShadow: true,
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  // True always-on-top, above fullscreen apps / taskbar too (unless user disabled it)
  alwaysOnTopEnabled = saved && typeof saved.alwaysOnTop === 'boolean' ? saved.alwaysOnTop : true;
  win.setAlwaysOnTop(alwaysOnTopEnabled, 'screen-saver');
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  win.loadFile('weather_widget.html');

  win.on('move', () => {
    const [x, y] = win.getPosition();
    savePosition(x, y);
  });

  win.on('closed', () => { win = null; });

  win.webContents.on('did-finish-load', () => {
    win.webContents.send('always-on-top-state', alwaysOnTopEnabled);
  });

  createTray();
}

function createTray() {
  const iconPath = path.join(__dirname, 'icon.png');
  try {
    tray = new Tray(iconPath);
  } catch (e) {
    return; // icon missing, skip tray silently
  }
  tray.setToolTip('Widget Meteo');
  buildTrayMenu();
  tray.on('click', () => {
    if (!win) return;
    win.isVisible() ? win.hide() : win.show();
  });
}

function setAlwaysOnTop(enabled) {
  alwaysOnTopEnabled = enabled;
  if (win) {
    win.setAlwaysOnTop(enabled, 'screen-saver');
    win.webContents.send('always-on-top-state', enabled);
  }
  saveAlwaysOnTop(enabled);
  if (tray) buildTrayMenu();
}

function buildTrayMenu() {
  if (!tray) return;
  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Afficher / Masquer',
      click: () => {
        if (!win) return;
        win.isVisible() ? win.hide() : win.show();
      }
    },
    {
      label: 'Actualiser la meteo',
      click: () => { if (win) win.webContents.send('force-refresh'); }
    },
    {
      label: 'Toujours au premier plan',
      type: 'checkbox',
      checked: alwaysOnTopEnabled,
      click: (menuItem) => { setAlwaysOnTop(menuItem.checked); }
    },
    {
      label: 'Lancer avec Windows',
      type: 'checkbox',
      checked: openAtLoginEnabled,
      click: (menuItem) => { setOpenAtLogin(menuItem.checked); }
    },
    { type: 'separator' },
    {
      label: 'Quitter',
      click: () => { app.quit(); }
    }
  ]);
  tray.setContextMenu(contextMenu);
}

// IPC: renderer asks main to move the window while dragging
ipcMain.on('widget-drag', (event, { deltaX, deltaY }) => {
  if (!win) return;
  const [x, y] = win.getPosition();
  const display = screen.getDisplayNearestPoint({ x, y });
  const workArea = display.workArea;
  const [width] = win.getSize();
  const nextX = Math.max(workArea.x, Math.min(x + deltaX, workArea.x + workArea.width - width));
  // Le widget occupe toute la hauteur utile : le glissement reste horizontal
  // et son bord superieur demeure aligne avec la zone de travail Windows.
  win.setPosition(nextX, workArea.y);
});

ipcMain.on('widget-close', () => {
  if (win) win.close();
});

ipcMain.on('widget-toggle-always-on-top', () => {
  setAlwaysOnTop(!alwaysOnTopEnabled);
});

// IPC: stockage local du token Hydria (widget desktop, pas de session
// navigateur possible ici — voir apps/core/views_widget.py côté serveur).
ipcMain.handle('hydria-get-token', () => {
  const saved = loadPosition();
  return saved && saved.hydriaToken ? saved.hydriaToken : null;
});

ipcMain.on('hydria-save-token', (event, token) => {
  saveHydriaToken(token);
});

ipcMain.on('hydria-clear-token', () => {
  clearHydriaToken();
});

// IPC: ouvre un lien Hydria dans le navigateur par defaut (deep-link vers un
// modal de facture depuis les details du widget). Restreint au domaine
// Hydria pour eviter toute ouverture externe arbitraire depuis le contenu web.
ipcMain.on('widget-open-external', (event, url) => {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'https:' && parsed.hostname === 'www.hydria.mg') {
      shell.openExternal(url);
    }
  } catch (e) {}
});

ipcMain.on('hydria-notify', (event, payload) => {
  if (!Notification.isSupported() || !payload || typeof payload !== 'object') return;
  const notification = new Notification({
    title: String(payload.title || 'Hydria'),
    body: String(payload.body || ''),
    icon: path.join(__dirname, 'icon.png'),
  });
  notification.on('click', () => {
    if (!win) return;
    if (win.isMinimized()) win.restore();
    win.show();
    win.focus();
  });
  notification.show();
});

// Le renderer continue d'emettre sa mesure de contenu pour compatibilite,
// mais la hauteur est maintenant imposee par la zone de travail du moniteur.
ipcMain.on('widget-resize', () => {
  // Le contenu ne dicte plus la hauteur : le widget conserve en permanence
  // toute la hauteur utile du moniteur courant, sans recouvrir la barre des taches.
  fitWidgetToWorkArea();
});

app.whenReady().then(() => {
  // Auto-accorder la permission de geolocalisation (pas d'UI de prompt
  // dans une fenetre frameless), sinon getCurrentPosition echoue toujours.
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    if (permission === 'geolocation') {
      callback(true);
      return;
    }
    callback(false);
  });

  const saved = loadPosition();
  openAtLoginEnabled = saved && typeof saved.openAtLogin === 'boolean'
    ? saved.openAtLogin
    : true;
  setOpenAtLogin(openAtLoginEnabled);

  createWindow();

  screen.on('display-metrics-changed', () => {
    fitWidgetToWorkArea();
  });

  // Global shortcut to toggle visibility: Ctrl+Alt+W
  globalShortcut.register('Control+Alt+W', () => {
    if (!win) return;
    win.isVisible() ? win.hide() : win.show();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  app.quit();
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});
