const { app, BrowserWindow, ipcMain, screen, shell } = require('electron');
const path = require('path');
const fs = require('fs');

app.setName('Hydria Compteurs de tete');
app.setPath('userData', path.join(app.getPath('appData'), 'hydria-compteurs-tete-widget'));
const CONFIG_PATH = path.join(app.getPath('userData'), 'widget-config.json');
const SHARED_WEATHER_CONFIG = path.join(app.getPath('appData'), 'weather-widget', 'widget-position.json');
let win = null;

function readJson(filePath) {
  try { return JSON.parse(fs.readFileSync(filePath, 'utf8')); } catch (_) { return {}; }
}

function saveConfig(patch) {
  const current = readJson(CONFIG_PATH);
  fs.mkdirSync(path.dirname(CONFIG_PATH), { recursive: true });
  fs.writeFileSync(CONFIG_PATH, JSON.stringify({ ...current, ...patch }, null, 2), 'utf8');
}

function getHydriaToken() {
  const ownToken = readJson(CONFIG_PATH).hydriaToken;
  return ownToken || readJson(SHARED_WEATHER_CONFIG).hydriaToken || null;
}

function createWindow() {
  const saved = readJson(CONFIG_PATH);
  const display = saved.x !== undefined && saved.y !== undefined
    ? screen.getDisplayNearestPoint({ x: saved.x, y: saved.y })
    : screen.getPrimaryDisplay();
  const area = display.workArea;
  const width = 332;
  const height = Math.min(680, area.height - 32);
  const x = Number.isFinite(saved.x) ? saved.x : area.x + area.width - width - 28;
  const y = Number.isFinite(saved.y) ? saved.y : area.y + 24;

  win = new BrowserWindow({
    width,
    height,
    x: Math.max(area.x, Math.min(x, area.x + area.width - width)),
    y: Math.max(area.y, Math.min(y, area.y + area.height - height)),
    minWidth: 310,
    minHeight: 420,
    frame: false,
    transparent: false,
    backgroundMaterial: 'acrylic',
    roundedCorners: true,
    resizable: true,
    maximizable: false,
    fullscreenable: false,
    alwaysOnTop: saved.alwaysOnTop !== false,
    show: false,
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  win.loadFile('widget.html', { query: { kind: 'meters' } });
  win.once('ready-to-show', () => win.show());
  win.on('move', () => {
    const [nextX, nextY] = win.getPosition();
    saveConfig({ x: nextX, y: nextY });
  });
  win.on('closed', () => { win = null; });
}

const hasLock = app.requestSingleInstanceLock();
if (!hasLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (!win) return;
    if (win.isMinimized()) win.restore();
    win.show();
    win.focus();
  });
}

ipcMain.on('widget-close', () => win?.close());
ipcMain.on('widget-minimize', () => win?.minimize());
ipcMain.on('widget-refresh', () => win?.webContents.send('force-refresh'));
ipcMain.on('widget-toggle-pin', () => {
  if (!win) return;
  const enabled = !win.isAlwaysOnTop();
  win.setAlwaysOnTop(enabled, 'screen-saver');
  saveConfig({ alwaysOnTop: enabled });
  win.webContents.send('pin-state', enabled);
});
ipcMain.handle('hydria-get-token', () => getHydriaToken());
ipcMain.on('hydria-save-token', (_, token) => saveConfig({ hydriaToken: token }));
ipcMain.on('hydria-clear-token', () => saveConfig({ hydriaToken: null }));
ipcMain.handle('open-external', (_, url) => {
  if (typeof url === 'string' && url.startsWith('https://www.hydria.mg/')) return shell.openExternal(url);
  return false;
});

app.whenReady().then(createWindow);
app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
app.on('window-all-closed', () => app.quit());
