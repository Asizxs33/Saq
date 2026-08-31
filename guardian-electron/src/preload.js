const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("guardianAPI", {
  getState: () => ipcRenderer.invoke("get-state"),
  setThreshold: (v) => ipcRenderer.invoke("set-threshold", v),
  setBackend: (v) => ipcRenderer.invoke("set-backend", v),
  setRunning: (v) => ipcRenderer.invoke("set-running", v),
  hide: () => ipcRenderer.invoke("hide-window"),
  minimize: () => ipcRenderer.invoke("minimize-window"),
  onStateUpdate: (cb) => ipcRenderer.on("state-update", (_e, data) => cb(data)),
});
