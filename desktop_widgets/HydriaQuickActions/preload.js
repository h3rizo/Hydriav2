const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('quickActionsAPI', {
  triggerAction: (actionId) => ipcRenderer.send('quick-action', actionId),
  drag: (deltaX, deltaY) => ipcRenderer.send('bubble-drag', { deltaX, deltaY }),
  getActions: () => ipcRenderer.invoke('get-actions'),
  getAlignment: () => ipcRenderer.invoke('get-bubble-alignment'),
  toggle: (open, panelWidth, panelHeight, side) => ipcRenderer.send('bubble-toggle', { open, panelWidth, panelHeight, side })
});
