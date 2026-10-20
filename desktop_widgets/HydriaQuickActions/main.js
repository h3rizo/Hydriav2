const { app, BrowserWindow, screen, ipcMain, Menu, Tray, session } = require('electron');
const path = require('path');
const fs = require('fs');

const HYDRIA_BASE_URL = 'https://www.hydria.mg';
const CONFIG_PATH = path.join(app.getPath('userData'), 'quick-actions-position.json');

// Session partagée entre toutes les fenêtres de ce widget (et avec le
// widget Navbar s'il utilise la même partition) : se connecter une fois
// suffit pour toutes les mini-fenêtres Hydria ouvertes ensuite.
const SHARED_PARTITION = 'persist:hydria-shared';

let bubbleWin = null;
let tray = null;
const pageWindows = {};

const BUBBLE_SIZE = 64;
const EDGE_MARGIN = 24;
const POSITION_LAYOUT_VERSION = 2;
// Coin bas-droit ancré (position du bouton visible) : quand le panneau se
// deplie, la fenetre s'agrandit vers le haut/la gauche en gardant ce point
// fixe a l'ecran, pour que le bouton ne "saute" pas visuellement.
let anchorLeft = null;
let anchorRight = null;
let anchorBottom = null;
let expandedSide = 'left';

function loadPosition() {
  try {
    const saved = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8'));
    return saved.layoutVersion === POSITION_LAYOUT_VERSION ? saved : null;
  } catch (e) {
    return null;
  }
}

function savePosition(x, y) {
  try {
    fs.writeFileSync(CONFIG_PATH, JSON.stringify({
      x,
      y,
      layoutVersion: POSITION_LAYOUT_VERSION,
    }));
  } catch (e) {}
}

const ACTIONS = [
  { id: 'conversations', label: 'Conversations', icon: '💬', path: '/conversations/', color: '#3a7bd5' },
  { id: 'applications', label: 'Applications', icon: '🏠', path: '/accueil/', color: '#6c5ce7' },
  { id: 'capture_terrain', label: 'Capture données terrain', icon: '📱', path: '/geography/capture-donnees/', color: '#e17055' },
  { id: 'releve_terrain', label: 'Relevé terrain', icon: '💧', path: '/facturation/releves/', color: '#00b8d4' },
  { id: 'agenda', label: 'Agenda planning', icon: '📅', path: '/plannings/agenda/', color: '#3a7bd5' },
  { id: 'recherche', label: 'Recherche', icon: '🔍', path: '/recherche/', color: '#00b8d4' },
  { id: 'recherche_ouvrages', label: 'Ouvrages', icon: '🏗️', path: '/recherche/ouvrages/', color: '#fdcb6e' },
  { id: 'calculatrice', label: 'Calculatrice', icon: '🧮', path: '/accueil/', color: '#00b894', openCalculator: true },
];

function createBubble() {
  const saved = loadPosition();
  const primaryDisplay = screen.getPrimaryDisplay();
  const workArea = primaryDisplay.workArea;

  const startX = saved ? saved.x : workArea.x + EDGE_MARGIN;
  const startY = saved ? saved.y : workArea.y + workArea.height - BUBBLE_SIZE - EDGE_MARGIN;
  anchorLeft = startX;
  anchorRight = startX + BUBBLE_SIZE;
  anchorBottom = startY + BUBBLE_SIZE;

  bubbleWin = new BrowserWindow({
    width: BUBBLE_SIZE,
    height: BUBBLE_SIZE,
    x: startX,
    y: startY,
    frame: false,
    transparent: true,
    // resizable doit rester true pour que setBounds() programmatique
    // fonctionne de façon fiable sur Windows (même contrainte que le
    // widget météo) — aucune poignée de resize n'est exposée à l'utilisateur.
    resizable: true,
    maximizable: false,
    fullscreenable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  bubbleWin.setAlwaysOnTop(true, 'screen-saver');
  bubbleWin.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  bubbleWin.loadFile('bubble.html');

  // Ne mémoriser la position (pour le prochain démarrage) que lorsque la
  // fenêtre est à sa taille bulle repliée — sinon un déplacement pendant
  // que le panneau est ouvert enregistrerait la position du coin agrandi.
  bubbleWin.on('move', () => {
    const [w] = bubbleWin.getSize();
    if (w !== BUBBLE_SIZE) return;
    const [x, y] = bubbleWin.getPosition();
    anchorLeft = x;
    anchorRight = x + BUBBLE_SIZE;
    anchorBottom = y + BUBBLE_SIZE;
    savePosition(x, y);
  });

  bubbleWin.on('closed', () => { bubbleWin = null; });

  createTray();
}

function createTray() {
  const iconPath = path.join(__dirname, 'icon.png');
  try {
    tray = new Tray(iconPath);
  } catch (e) {
    return;
  }
  tray.setToolTip('Hydria - Actions rapides');
  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Afficher / Masquer',
      click: () => {
        if (!bubbleWin) return;
        bubbleWin.isVisible() ? bubbleWin.hide() : bubbleWin.show();
      }
    },
    { type: 'separator' },
    { label: 'Quitter', click: () => app.quit() }
  ]);
  tray.setContextMenu(contextMenu);
  tray.on('click', () => {
    if (!bubbleWin) return;
    bubbleWin.isVisible() ? bubbleWin.hide() : bubbleWin.show();
  });
}

function openActionWindow(actionId) {
  const action = ACTIONS.find(a => a.id === actionId);
  if (!action) return;

  // Réutilise la fenêtre existante pour cette action si déjà ouverte,
  // au lieu d'en empiler des dizaines.
  if (pageWindows[actionId] && !pageWindows[actionId].isDestroyed()) {
    pageWindows[actionId].focus();
    return;
  }

  const win = new BrowserWindow({
    width: 1100,
    height: 780,
    title: `Hydria — ${action.label}`,
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      partition: SHARED_PARTITION,
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  win.loadURL(`${HYDRIA_BASE_URL}${action.path}`);

  if (action.openCalculator) {
    win.webContents.on('did-finish-load', () => {
      // Le modal calculatrice existe déjà dans base.html de chaque page
      // Hydria — on se contente de l'ouvrir via son propre JS, sans le
      // réimplémenter côté widget (évite la duplication et la dérive).
      win.webContents.executeJavaScript(
        'if (typeof openCalculatorModal === "function") { openCalculatorModal(); }'
      ).catch(() => {});
    });
  }

  pageWindows[actionId] = win;
  win.on('closed', () => { delete pageWindows[actionId]; });
}

ipcMain.on('quick-action', (event, actionId) => {
  openActionWindow(actionId);
});

ipcMain.on('bubble-drag', (event, { deltaX, deltaY }) => {
  if (!bubbleWin) return;
  const bounds = bubbleWin.getBounds();
  const buttonX = bounds.width === BUBBLE_SIZE || expandedSide === 'left'
    ? bounds.x
    : bounds.x + bounds.width - BUBBLE_SIZE;
  const buttonY = bounds.y + bounds.height - BUBBLE_SIZE;
  const display = screen.getDisplayNearestPoint({
    x: buttonX + Math.floor(BUBBLE_SIZE / 2),
    y: buttonY + Math.floor(BUBBLE_SIZE / 2),
  });
  const area = display.workArea;
  const nextButtonX = Math.min(
    area.x + area.width - BUBBLE_SIZE,
    Math.max(area.x, buttonX + deltaX),
  );
  const nextButtonY = Math.min(
    area.y + area.height - BUBBLE_SIZE,
    Math.max(area.y, buttonY + deltaY),
  );
  const appliedX = nextButtonX - buttonX;
  const appliedY = nextButtonY - buttonY;
  bubbleWin.setPosition(bounds.x + appliedX, bounds.y + appliedY);
  anchorLeft = nextButtonX;
  anchorRight = nextButtonX + BUBBLE_SIZE;
  anchorBottom = nextButtonY + BUBBLE_SIZE;
  savePosition(nextButtonX, nextButtonY);
});

ipcMain.handle('get-bubble-alignment', () => {
  if (!bubbleWin || anchorLeft === null) return 'left';
  const center = {
    x: anchorLeft + Math.floor(BUBBLE_SIZE / 2),
    y: anchorBottom - Math.floor(BUBBLE_SIZE / 2),
  };
  const area = screen.getDisplayNearestPoint(center).workArea;
  return center.x < area.x + area.width / 2 ? 'left' : 'right';
});

// IPC: le renderer mesure la taille reelle du panneau deplie
// (#actions-panel) et demande d'agrandir/retrecir la fenetre en
// consequence, en gardant le coin bas-droit (bouton principal) fixe a
// l'ecran — sinon le panneau deborde hors de la zone Electron et devient
// invisible/incliquable (Electron rogne tout ce qui depasse sa fenetre).
ipcMain.on('bubble-toggle', (event, { open, panelWidth, panelHeight, side }) => {
  if (!bubbleWin || anchorRight === null) return;

  if (open) {
    // Marge genereuse au-dela de la mesure exacte : absorbe les arrondis
    // de layout et les transitions CSS en cours, pour ne jamais rogner
    // le contenu (ce qui forcerait un scroll invisible dans une fenetre
    // sans barre de defilement visible).
    const width = Math.max(BUBBLE_SIZE, Math.ceil(panelWidth) + 24);
    const height = Math.max(BUBBLE_SIZE, Math.ceil(panelHeight) + BUBBLE_SIZE + 32);
    expandedSide = side === 'right' ? 'right' : 'left';
    const x = expandedSide === 'left' ? anchorLeft : anchorRight - width;
    const y = anchorBottom - height;
    bubbleWin.setBounds({ x, y, width, height });
  } else {
    const x = anchorLeft;
    const y = anchorBottom - BUBBLE_SIZE;
    bubbleWin.setBounds({ x, y, width: BUBBLE_SIZE, height: BUBBLE_SIZE });
  }
});

ipcMain.handle('get-actions', () => ACTIONS);

app.whenReady().then(() => {
  createBubble();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createBubble();
  });
});

app.on('window-all-closed', () => {
  // Ne pas quitter : le bouton flottant doit rester actif même si toutes
  // les fenêtres de pages ouvertes sont fermées.
  if (BrowserWindow.getAllWindows().length === 0 && !bubbleWin) {
    app.quit();
  }
});
