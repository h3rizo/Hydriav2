const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('widgetAPI', {
  drag: (deltaX, deltaY) => ipcRenderer.send('widget-drag', { deltaX, deltaY }),
  close: () => ipcRenderer.send('widget-close'),
  toggleAlwaysOnTop: () => ipcRenderer.send('widget-toggle-always-on-top'),
  onForceRefresh: (callback) => ipcRenderer.on('force-refresh', callback),
  onAlwaysOnTopState: (callback) => ipcRenderer.on('always-on-top-state', (event, enabled) => callback(enabled)),

  getHydriaToken: () => ipcRenderer.invoke('hydria-get-token'),
  saveHydriaToken: (token) => ipcRenderer.send('hydria-save-token', token),
  clearHydriaToken: () => ipcRenderer.send('hydria-clear-token'),
  notify: (title, body) => ipcRenderer.send('hydria-notify', { title, body }),
  openExternal: (url) => ipcRenderer.send('widget-open-external', url),

  resize: (contentHeight) => ipcRenderer.send('widget-resize', contentHeight)
});
