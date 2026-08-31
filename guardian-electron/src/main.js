"use strict";
/**
 * SAQ Guardian (Electron) — фоновая защита от финансовых пирамид.
 * Полностью на Node/JS, без Python в рантайме.
 *
 * Как работает:
 * 1. Раз в settings.interval секунд узнаёт активное окно (active-win),
 *    снимает экран (screenshot-desktop) и обрезает до его границ (sharp).
 * 2. Распознаёт текст через tesseract.js (OCR на WASM, без внешних бинарников).
 * 3. Достаёт домены/телефоны/фразы-маркеры пирамид (detect.js).
 * 4. Каждое новое значение прогоняет через backend SAQ (POST /investigate).
 * 5. При высоком risk-score — нативное Windows-уведомление (Electron
 *    регистрирует AppUserModelID сам, тосты показываются надёжно —
 *    в отличие от plyer в старой Python-версии, где они молча пропадали).
 *
 * Крестик сворачивает в трей, полностью завершает только пункт «Выход».
 */

const { app, BrowserWindow, Tray, Menu, ipcMain, Notification, nativeImage, desktopCapturer, screen } = require("electron");
const path = require("path");
const { createWorker } = require("tesseract.js");
const { extractCandidates } = require("./detect");

const settings = {
  // публичный туннель к бэкенду на машине разработчика (ngrok, статичный
  // домен) — так у друзей, кому передан exe, всё работает из коробки без
  // ручной настройки. Держится, пока на исходной машине запущены backend
  // (uvicorn) и `ngrok http --url=disposal-pliable-trial.ngrok-free.dev 8000`
  backendUrl: "https://disposal-pliable-trial.ngrok-free.dev",
  interval: 8,
  threshold: 60,
  running: true,
};
const state = { window: "", checked: 0, flagged: 0 };
const findings = [];
const seenValues = new Set();

let mainWindow = null;
let tray = null;
let ocrWorker = null;

function pushState() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("state-update", {
      window: state.window,
      checked: state.checked,
      flagged: state.flagged,
      findings,
    });
  }
}

function notify(title, body) {
  if (!Notification.isSupported()) {
    console.error("[notify] Notification.isSupported() === false — тост не покажется:", title);
    return;
  }
  try {
    const n = new Notification({ title, body: body.slice(0, 250), icon: path.join(__dirname, "..", "assets", "icon.ico") });
    n.on("failed", (_e, err) => console.error("[notify] failed:", err));
    n.show();
  } catch (err) {
    console.error("[notify] threw:", err);
  }
}

function addFinding(f) {
  findings.push({ ...f, at: new Date().toTimeString().slice(0, 8) });
  state.flagged += 1;
  pushState();
}

async function checkBackend(query) {
  try {
    const res = await fetch(`${settings.backendUrl}/investigate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, synthesize: false }),
      signal: AbortSignal.timeout(15000),
    });
    if (res.ok) return await res.json();
  } catch {
    /* бэкенд недоступен — просто пропускаем эту проверку до следующего цикла */
  }
  return null;
}

async function reportTip(target, note) {
  // Домены/телефоны с высоким risk-score уже попадают в общий реестр через
  // /investigate — они "в одном месте" автоматически. А вот фразы-маркеры
  // пирамид и казино-контент нигде не сохранялись, кроме локального лога
  // этой конкретной программы — reportTip кладёт их туда же, куда падают
  // наводки с сайта (/tips), с пометкой source=guardian_app, чтобы админ
  // видел их вместе со всем остальным, а не только на экране у пользователя.
  try {
    await fetch(`${settings.backendUrl}/tips`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target, note, source: "guardian_app" }),
      signal: AbortSignal.timeout(10000),
    });
  } catch {
    /* бэкенд недоступен — находка всё равно осталась видна в самом Guardian */
  }
}

async function tick() {
  if (!settings.running) return;
  try {
    const { default: activeWin } = await import("active-win");
    const win = await activeWin();
    if (!win) return;
    state.window = win.title || win.owner?.name || "";
    pushState();

    const b = win.bounds;
    if (!b || b.width <= 0 || b.height <= 0) return;

    // desktopCapturer — часть самого Electron, без внешних бинарников
    // (screenshot-desktop на этой машине не смог найти свой bundled .exe —
    // antivirus/путь; NativeImage.crop() заодно заменяет sharp для обрезки)
    const display = screen.getPrimaryDisplay();
    const { width: sw, height: sh } = display.size;
    const scale = display.scaleFactor || 1;
    const sources = await desktopCapturer.getSources({
      types: ["screen"],
      thumbnailSize: { width: Math.round(sw * scale), height: Math.round(sh * scale) },
    });
    const source = sources[0];
    if (!source) return;
    const full = source.thumbnail;
    const fullSize = full.getSize();

    const left = Math.max(0, Math.min(Math.round(b.x * scale), fullSize.width - 1));
    const top = Math.max(0, Math.min(Math.round(b.y * scale), fullSize.height - 1));
    const width = Math.max(1, Math.min(Math.round(b.width * scale), fullSize.width - left));
    const height = Math.max(1, Math.min(Math.round(b.height * scale), fullSize.height - top));
    const cropped = full.crop({ x: left, y: top, width, height }).toPNG();

    const { data } = await ocrWorker.recognize(cropped);
    const text = data.text || "";

    for (const { value: cand, kind } of extractCandidates(text)) {
      const key = cand.toLowerCase().trim();
      if (!key || seenValues.has(key)) continue;
      seenValues.add(key);
      state.checked += 1;

      if (kind === "phrase") {
        addFinding({ value: cand, window: state.window, score: null, flags: "", flagList: [], sources: 0, kind });
        notify("SAQ Guardian — подозрительная формулировка", `В окне «${state.window}» встретилась фраза: «${cand}».`);
        reportTip(cand, `Фраза-маркер пирамиды в окне «${state.window}» (SAQ Guardian).`);
        continue;
      }

      if (kind === "casino") {
        addFinding({ value: cand, window: state.window, score: null, flags: "", flagList: [], sources: 0, kind });
        notify("SAQ Guardian — азартный контент", `В окне «${state.window}» обнаружена реклама/контент казино: «${cand}».`);
        reportTip(cand, `Казино/гэмблинг-контент в окне «${state.window}» (SAQ Guardian).`);
        continue;
      }

      const res = await checkBackend(cand);
      const score = res?.risk_score;
      if (score != null && score >= settings.threshold) {
        const flagList = res.risk_flags || [];
        addFinding({
          value: cand, window: state.window, score,
          flags: flagList.slice(0, 3).join(", "), flagList,
          sources: (res.connectors_run || []).length, kind,
        });
        notify("SAQ Guardian — обнаружен риск", `«${cand}» в окне «${state.window}»: risk-score ${score}/100.`);
      }
    }
  } catch {
    /* один неудачный цикл не должен останавливать сканирование */
  } finally {
    pushState();
    setTimeout(tick, settings.interval * 1000);
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 470,
    height: 720,
    frame: false,
    transparent: true,
    backgroundColor: "#00000000",
    resizable: false,
    icon: path.join(__dirname, "..", "assets", "icon.ico"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
  mainWindow.on("close", (e) => {
    if (!app.isQuiting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });
}

function createTray() {
  const icon = nativeImage.createFromPath(path.join(__dirname, "..", "assets", "icon.ico"));
  tray = new Tray(icon.resize({ width: 16, height: 16 }));
  tray.setToolTip("SAQ Guardian — активен");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Открыть", click: () => mainWindow.show() },
      { label: "Выход", click: () => { app.isQuiting = true; app.quit(); } },
    ])
  );
  tray.on("click", () => mainWindow.show());
}

ipcMain.handle("get-state", () => ({ ...state, findings, settings }));
ipcMain.handle("set-threshold", (_e, v) => { settings.threshold = Number(v); });
ipcMain.handle("set-backend", (_e, v) => { if (v) settings.backendUrl = v; });
ipcMain.handle("set-running", (_e, v) => { settings.running = Boolean(v); });
ipcMain.handle("hide-window", () => mainWindow.hide());
ipcMain.handle("minimize-window", () => mainWindow.minimize());

// без явного AppUserModelID Windows часто молча не показывает toast-
// уведомления у Electron-приложений, запущенных не через NSIS-инсталлятор
// (у portable/packager-сборки нет ярлыка со своим AUMID) — проверено вживую,
// notify() отрабатывал без ошибок, но тост не появлялся
app.setAppUserModelId("kz.saq.guardian");

app.whenReady().then(async () => {
  createWindow();
  createTray();
  ocrWorker = await createWorker("rus+eng");
  tick();
});

app.on("window-all-closed", (e) => e.preventDefault());
