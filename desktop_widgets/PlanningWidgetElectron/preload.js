const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('widgetAPI', {
  close: () => ipcRenderer.send('widget-close'),
  minimize: () => ipcRenderer.send('widget-minimize'),
  refresh: () => ipcRenderer.send('widget-refresh'),
  togglePin: () => ipcRenderer.send('widget-toggle-pin'),
  toggleStartup: () => ipcRenderer.invoke('widget-toggle-startup'),
  getStartup: () => ipcRenderer.invoke('widget-get-startup'),
  onForceRefresh: callback => ipcRenderer.on('force-refresh', callback),
  onPinState: callback => ipcRenderer.on('pin-state', (_, enabled) => callback(enabled)),
  getHydriaToken: () => ipcRenderer.invoke('hydria-get-token'),
  saveHydriaToken: token => ipcRenderer.send('hydria-save-token', token),
  clearHydriaToken: () => ipcRenderer.send('hydria-clear-token'),
  getPlanningFiltres: () => ipcRenderer.invoke('hydria-get-planning-filtres'),
  savePlanningFiltres: filtres => ipcRenderer.send('hydria-save-planning-filtres', filtres),
  openExternal: url => ipcRenderer.invoke('open-external', url),
});
