const { app, BrowserWindow, ipcMain, screen, shell } = require('electron');
const path = require('path');
const fs = require('fs');

app.setName('Hydria Dernières réparations');
app.setPath('userData', path.join(app.getPath('appData'), 'hydria-interventions-widget'));
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
  return readJson(CONFIG_PATH).hydriaToken || readJson(SHARED_WEATHER_CONFIG).hydriaToken || null;
}

function setStartup(enabled) {
  try {
    app.setLoginItemSettings({
      openAtLogin: enabled,
      path: process.execPath,
      args: app.isPackaged ? [] : [app.getAppPath()],
    });
    saveConfig({ openAtLogin: enabled });
    return enabled;
  } catch (_) { return false; }
}

function createWindow() {
  const saved = readJson(CONFIG_PATH);
  const display = saved.x !== undefined && saved.y !== undefined
    ? screen.getDisplayNearestPoint({ x: saved.x, y: saved.y })
    : screen.getPrimaryDisplay();
  const area = display.workArea;
  const width = Math.min(470, area.width);
  const height = area.height;
  const x = Number.isFinite(saved.x) ? saved.x : area.x + area.width - width;
  const y = area.y;

  win = new BrowserWindow({
    width, height, x: Math.max(area.x, Math.min(x, area.x + area.width - width)), y,
    minWidth: 390, minHeight: 540,
    frame: false, transparent: false, backgroundColor: '#071d25',
    backgroundMaterial: 'acrylic', roundedCorners: true,
    resizable: true, maximizable: false, fullscreenable: false,
    alwaysOnTop: saved.alwaysOnTop !== false, show: false,
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false },
  });
  win.loadFile('widget.html');
  win.once('ready-to-show', () => win.show());
  win.on('move', () => { const [nextX, nextY] = win.getPosition(); saveConfig({ x: nextX, y: nextY }); });
  win.on('closed', () => { win = null; });
  if (saved.openAtLogin !== false) setStartup(true);
}

const hasLock = app.requestSingleInstanceLock();
if (!hasLock) app.quit();
else app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.show(); win.focus(); } });

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
ipcMain.handle('widget-get-startup', () => readJson(CONFIG_PATH).openAtLogin !== false);
ipcMain.handle('widget-toggle-startup', () => setStartup(readJson(CONFIG_PATH).openAtLogin === false));
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
