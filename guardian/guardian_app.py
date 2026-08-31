"""
SAQ Guardian — десктоп-защита в стиле сайта SAQ.

Окно на чистом Tkinter, но БЕЗ стоковых ttk-виджетов — все карточки,
кнопки и слайдер отрисованы вручную через PIL (скругления, градиенты
как в CSS-карточках сайта, тот же маскот Aqyl) и вставлены как картинки.
Пробовали pywebview/WebView2 для честного HTML/CSS-рендера — на этой
машине evaluate_js стабильно намертво виснет из фонового потока (COM-
апартаменты WebView2 конфликтуют с threading), так что это надёжный
путь: без браузерного движка, но и без стокового «сырого» вида.

Как работает защита:
1. Раз в CHECK_INTERVAL секунд снимает скриншот АКТИВНОГО окна (то, что
   ты реально сейчас читаешь: Telegram, Chrome, почта и т.д.).
2. Распознаёт текст встроенным OCR-движком Windows (Windows.Media.Ocr) —
   сторонний Tesseract не нужен.
3. Достаёт домены, телефоны (СНГ-формат) и фразы-маркеры пирамид.
4. Каждое новое значение прогоняет через тот же backend SAQ, что и сайт
   (POST /investigate) — те же источники, тот же risk-score.
5. При risk-score выше порога — Windows-уведомление + запись в лог окна.

Крестик сворачивает в трей, программа завершается только через «Выход»
в меню трея. Иконка в трее видна всегда — это инструмент собственной
защиты, а не скрытая слежка.
"""

import asyncio
import io
import os
import re
import sys
import threading
import time
import tkinter as tk
from datetime import datetime

import requests
import win32gui
from PIL import Image, ImageGrab, ImageTk
from pystray import Icon, Menu, MenuItem
from win11toast import toast

from aqyl_art import render_aqyl, render_shield, rounded_button, rounded_card, dot as draw_dot

# та же палитра, что в web/src/app/globals.css (тёмная тема сайта)
BG = "#090e1c"
BG_CARD = "#141f36"
INK = "#f1f5f9"
INK_MUTED = "#94a3b8"
INK_FAINT = "#64748b"
ACCENT = "#3b82f6"
ACCENT_BRIGHT = "#60a5fa"
DANGER = "#ef4444"
SAFE = "#10b981"
BORDER = "#1e293b"
BORDER_STRONG = "#334155"
CARD_W = 430
SANS = "Segoe UI"
DISPLAY = "Segoe UI Semibold"
MONO = "Consolas"

# ------------------------------------------------------------ детекторы
DOMAIN_RE = re.compile(r"\b([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\-\s()]{7,16}\d)(?!\d)")
PYRAMID_KEYWORDS = [
    "гарантированный доход",
    "гарантированная прибыль",
    "x2 за неделю",
    "удвоим ваш",
    "пассивный доход от",
    "инвестируй сегодня",
    "приведи друга и получи",
    "быстрый заработок без вложений",
]
# точные фразы ловят мало — проверено на реальном сообщении мошенника
# («Вложите 50 000 тг, через неделю получите 300% прибыли, не рассказывайте
# никому») ни одна из PYRAMID_KEYWORDS не сработала. Паттерны ловят СТРУКТУРУ
# развода, а не конкретную формулировку: обещание % прибыли за срок,
# давление срочностью/эксклюзивностью, просьба хранить в тайне.
PYRAMID_PATTERNS = [
    (re.compile(r"\d{2,4}\s?%.{0,25}(прибыл|доход|дней|недел|месяц)", re.I),
     "обещание конкретного % прибыли за срок"),
    (re.compile(r"(вложите?|инвестируй|переведите).{0,40}(получите|заработа|прибыл)", re.I),
     "схема «вложи сейчас → получи потом»"),
    (re.compile(r"(количество мест|осталось \d+ мест|только сегодня|акция закан)", re.I),
     "искусственная срочность/ограниченность"),
    (re.compile(r"(не рассказывайте|никому не говор|держите в тайне)", re.I),
     "просьба скрывать предложение от других"),
    (re.compile(r"(вы (были )?выбраны|эксклюзивн(ая|ое) (программ|предложени|возможност)|избранн)", re.I),
     "фальшивая эксклюзивность «вас выбрали»"),
    (re.compile(r"приведи? друга.{0,20}(получ|бонус|%)", re.I), "реферальная вербовка"),
]
DOMAIN_IGNORE_SUFFIXES = (
    "microsoft.com", "windows.com", "google.com", "gstatic.com",
    "localhost", "vercel.app",
)
# Без этого списка «домен» ловится в любом имени файла (ui.html, test.txt,
# report.pdf) и в мусоре OCR — проверено вживую, реестр забивался хламом.
# Берём только реально существующие зоны: общие + СНГ/популярные страновые.
VALID_TLDS = {
    "com", "net", "org", "info", "biz", "io", "co", "app", "dev", "ai", "me",
    "shop", "site", "online", "store", "club", "top", "xyz", "pro", "cc", "tv",
    "kz", "ru", "ua", "by", "uz", "kg", "tj", "az", "ge", "am", "md",
    "tr", "cn", "in", "de", "fr", "uk", "eu", "pl", "cz", "lv", "lt", "ee",
    "su", "рф", "қаз", "onion",
}
SEEN_CACHE_LIMIT = 500

settings = {
    "backend_url": "http://127.0.0.1:8000",
    "interval": 8,
    "threshold": 60,
    "running": True,
}
state = {"window": "", "checked": 0, "flagged": 0}
findings: list[dict] = []
_seen_values: list[str] = []
_lock = threading.Lock()


def resource_path(name: str) -> str:
    """Путь к файлу и в обычном запуске, и внутри onefile-сборки."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def _remember(key: str) -> bool:
    with _lock:
        if key in _seen_values:
            return False
        _seen_values.append(key)
        if len(_seen_values) > SEEN_CACHE_LIMIT:
            del _seen_values[: len(_seen_values) - SEEN_CACHE_LIMIT]
        return True


def get_foreground_window_title() -> str:
    return win32gui.GetWindowText(win32gui.GetForegroundWindow()) or ""


def grab_foreground_screenshot() -> Image.Image | None:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    rect = win32gui.GetWindowRect(hwnd)
    if rect[2] <= rect[0] or rect[3] <= rect[1]:
        return None
    try:
        return ImageGrab.grab(bbox=rect)
    except Exception:
        return None


async def ocr_image(img: Image.Image) -> str:
    from winsdk.windows.globalization import Language
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.storage.streams import InMemoryRandomAccessStream, DataWriter

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(bytearray(buf.getvalue()))
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()

    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        engine = OcrEngine.try_create_from_language(Language("ru"))
    if engine is None:
        return ""
    result = await engine.recognize_async(bitmap)
    return result.text or ""


def extract_candidates(text: str) -> list[tuple[str, str]]:
    """Возвращает (значение, вид), вид ∈ {domain, phone, phrase}.
    domain/phone идут на проверку через backend (POST /investigate),
    phrase — сразу уведомление, backend такое не проверяет."""
    lower = text.lower()
    out: list[tuple[str, str]] = []
    for m in DOMAIN_RE.finditer(text):
        d = m.group(0).lower()
        if d.rsplit(".", 1)[-1] not in VALID_TLDS:
            continue  # имя файла или мусор OCR, а не домен
        if not any(d == s or d.endswith("." + s) for s in DOMAIN_IGNORE_SUFFIXES):
            out.append((d, "domain"))
    for m in PHONE_RE.finditer(text):
        raw = m.group(0).strip()
        digits = re.sub(r"\D", "", raw)
        # настоящий номер: 10-13 цифр и ведущая 7/8 — иначе это случайный
        # забег цифр вроде risk-score, попавшего в кадр
        if 10 <= len(digits) <= 13 and digits[:1] in ("7", "8"):
            out.append((raw, "phone"))
    for kw in PYRAMID_KEYWORDS:
        if kw in lower:
            out.append((kw, "phrase"))
    for rex, label in PYRAMID_PATTERNS:
        m = rex.search(text)
        if m:
            snippet = m.group(0).strip()
            if len(snippet) > 80:
                snippet = snippet[:80] + "…"
            out.append((f"{snippet} ({label})", "phrase"))
    return out


def check_backend(query: str) -> dict | None:
    try:
        r = requests.post(
            f"{settings['backend_url']}/investigate",
            json={"query": query, "synthesize": False},
            timeout=15,
        )
        if r.ok:
            return r.json()
    except requests.RequestException:
        pass
    return None


def notify(title: str, message: str):
    """win11toast регистрирует свой AppUserModelID на лету — в отличие от
    plyer, тост реально показывается для непакетированного .exe (проверено:
    plyer молча проглатывал уведомление, ни разу не появилось на экране).
    toast() блокирует до закрытия/таймаута тоста, поэтому — в отдельном
    потоке, чтобы не подвешивать цикл сканирования."""

    def _fire():
        try:
            toast(title, message[:250], app_id="SAQ Guardian", duration="short")
        except Exception:
            pass

    threading.Thread(target=_fire, daemon=True).start()


def add_finding(value, window, score, flags="", flag_list=None, kind="", sources=0):
    with _lock:
        findings.append(
            {
                "value": value,
                "window": window,
                "score": score,
                "flags": flags,
                # полный список сигналов — по нему окно строит объяснение
                "flag_list": flag_list or [],
                "kind": kind,
                "sources": sources,
                "at": datetime.now().strftime("%H:%M:%S"),
            }
        )
        state["flagged"] += 1


def worker_loop():
    while True:
        if not settings["running"]:
            time.sleep(1)
            continue
        try:
            title = get_foreground_window_title()
            state["window"] = title
            img = grab_foreground_screenshot()
            if img is not None:
                text = asyncio.run(ocr_image(img))
                for cand, ckind in extract_candidates(text):
                    key = cand.lower().strip()
                    if not key or not _remember(key):
                        continue
                    state["checked"] += 1

                    if ckind == "phrase":
                        add_finding(cand, title, None, kind="phrase")
                        notify(
                            "SAQ Guardian — подозрительная формулировка",
                            f"В окне «{title}» встретилась фраза: «{cand}».",
                        )
                        continue

                    res = check_backend(cand)
                    score = res.get("risk_score") if res else None
                    if score is not None and score >= settings["threshold"]:
                        all_flags = (res or {}).get("risk_flags", [])
                        fl = ", ".join(all_flags[:3])
                        add_finding(
                            cand, title, score, fl,
                            flag_list=all_flags,
                            kind=(res or {}).get("detected_type", ""),
                            sources=len((res or {}).get("connectors_run", [])),
                        )
                        notify(
                            "SAQ Guardian — обнаружен риск",
                            f"«{cand}» в окне «{title}»: risk-score {score}/100. {fl}",
                        )
        except Exception:
            pass
        time.sleep(settings["interval"])


# ── расшифровка сигналов риска человеческим языком (окно-объяснение) ──
FLAG_INFO = [
    (re.compile(r"свежерегистрирован|дн\. назад", re.I), "Домен создан совсем недавно",
     "Пирамиды живут месяцами: сайт поднимают, собирают деньги и бросают. Если «компания работает 5 лет», "
     "а домен зарегистрирован недавно — вам врут."),
    (re.compile(r"дешёвая TLD|TLD-зона", re.I), "Дешёвая доменная зона",
     "Зоны вроде .top/.xyz/.online стоят копейки и не требуют проверки владельца — их берут, когда сайт "
     "планируют бросить."),
    (re.compile(r"маркер-приманка|приманк", re.I), "Слова-приманки в адресе сайта",
     "В имени домена зашиты обещания дохода (profit, invest, x2, bonus). Настоящие финкомпании так не "
     "называются."),
    (re.compile(r"веб-архив|архив", re.I), "Сайта нет в веб-архиве",
     "У реальной компании остаётся след в интернете за прошлые годы. Пустая история = сайт появился "
     "только что."),
    (re.compile(r"санкцион|PEP", re.I), "Есть в санкционных списках",
     "Объект найден в международных санкционных списках или среди политически значимых лиц. Это очень "
     "серьёзный сигнал."),
    (re.compile(r"кошельк|сборщик", re.I), "Криптокошелёк ведёт себя как сборщик",
     "Деньги приходят от множества разных людей и уходят одним потоком — типичная схема сбора средств "
     "пирамиды."),
    (re.compile(r"ponzi|пирамид|pyramid", re.I), "Упоминания пирамиды в открытых источниках",
     "В поиске, СМИ или жалобах этот объект уже связывают со схемой Понци или финансовой пирамидой."),
    (re.compile(r"блэклист|blacklist|АФМ", re.I), "Числится в чёрном списке регулятора",
     "Объект попал в официальный перечень подозрительных организаций."),
]


def explain_flags(flag_list: list[str]) -> list[tuple[str, str]]:
    out, seen_t = [], set()
    for f in flag_list:
        hit = next((x for x in FLAG_INFO if x[0].search(f)), None)
        title, desc = (hit[1], hit[2]) if hit else (f, "Сигнал риска, зафиксированный источниками SAQ.")
        if title not in seen_t:
            seen_t.add(title)
            out.append((title, desc))
    return out


class ExplainSheet(tk.Toplevel):
    """Окно-объяснение находки: что нашли, почему это опасно, что делать."""

    def __init__(self, master, finding: dict):
        super().__init__(master)
        self.overrideredirect(True)
        self.configure(bg=BORDER_STRONG)
        w, h = 460, 560
        mx, my = master.winfo_x(), master.winfo_y()
        self.geometry(f"{w}x{h}+{mx + 10}+{my + 60}")
        self.attributes("-topmost", True)

        outer = tk.Frame(self, bg=BORDER_STRONG)
        outer.pack(fill="both", expand=True, padx=1, pady=1)
        body = tk.Frame(outer, bg=BG)
        body.pack(fill="both", expand=True)

        bar = tk.Frame(body, bg=BG, height=34)
        bar.pack(fill="x")
        tk.Label(bar, text="ОБЪЯСНЕНИЕ", bg=BG, fg=INK_FAINT, font=(MONO, 9)).pack(side="left", padx=14)
        tk.Button(
            bar, text="✕", bg=BG, fg=INK_FAINT, bd=0, activebackground=DANGER, activeforeground="white",
            font=(SANS, 10), command=self.destroy, cursor="hand2",
        ).pack(side="right", padx=6, pady=4)
        bar.bind("<B1-Motion>", self._drag)
        bar.bind("<Button-1>", self._start_drag)

        canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        scroll = tk.Scrollbar(body, orient="vertical", command=canvas.yview, bg=BG)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw", width=w - 20)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(14, 0))
        scroll.pack(side="right", fill="y")

        self._build(inner, finding, w - 40)

    def _start_drag(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag(self, e):
        self.geometry(f"+{self.winfo_pointerx() - self._dx}+{self.winfo_pointery() - self._dy}")

    def _build(self, root, f, cw):
        is_phrase = f["score"] is None
        score = f["score"]
        tone = DANGER if is_phrase or (score is not None and score >= 60) else \
            ACCENT_BRIGHT if score >= 30 else SAFE
        verdict = "Формулировка мошенника" if is_phrase else \
            "Высокий риск" if score >= 60 else "Требует внимания" if score >= 30 else "Низкий риск"

        top = tk.Frame(root, bg=BG)
        top.pack(fill="x", pady=(18, 14))
        gauge = tk.Canvas(top, width=60, height=60, bg=BG, highlightthickness=0)
        gauge.pack(side="left")
        gauge.create_oval(3, 3, 57, 57, outline=tone, width=2)
        gauge.create_text(30, 30, text=("!" if is_phrase else str(score)), fill=tone,
                           font=(DISPLAY, 18, "bold"))
        txt = tk.Frame(top, bg=BG)
        txt.pack(side="left", padx=12, fill="x", expand=True)
        tk.Label(txt, text=f["value"], bg=BG, fg=INK, font=(MONO, 11, "bold"),
                 wraplength=cw - 90, justify="left").pack(anchor="w")
        sub = verdict + ("" if is_phrase else f" · {f['sources']} источников") + f" · окно «{f['window']}»"
        tk.Label(txt, text=sub, bg=BG, fg=INK_FAINT, font=(SANS, 9), wraplength=cw - 90,
                 justify="left").pack(anchor="w", pady=(3, 0))

        self._section(root, "ЧТО ЭТО ЗНАЧИТ", cw)
        expl = ("На экране встретилась фраза, которой пользуются организаторы финансовых пирамид. Сама "
                "по себе она не доказывает мошенничество, но это повод насторожиться.") if is_phrase else \
            (f"SAQ прогнал этот объект через {f['sources']} открытых источника — реестры компаний, "
             f"санкционные списки, судебные базы, чёрные списки регулятора и поиск. Итоговая оценка "
             f"риска — {score} из 100.")
        tk.Label(root, text=expl, bg=BG, fg=INK_MUTED, font=(SANS, 10), wraplength=cw,
                 justify="left").pack(anchor="w", pady=(0, 14))

        self._section(root, "ПОЧЕМУ ЭТО ПОДОЗРИТЕЛЬНО", cw)
        items = [("Обещание гарантированного дохода",
                   "Ни один законный финансовый инструмент не может гарантировать доходность — это "
                   "запрещено. Такой формулировкой отключают критическое мышление.")] if is_phrase \
            else (explain_flags(f["flag_list"]) or
                  [("Совокупная оценка источников", f"Отдельные признаки слабые, но вместе дали {score}/100.")])
        for title, desc in items:
            card = tk.Frame(root, bg="#2a1618", bd=0)
            card.pack(fill="x", pady=(0, 7))
            inner = tk.Frame(card, bg="#2a1618")
            inner.pack(fill="x", padx=12, pady=9)
            tk.Label(inner, text="▲", bg="#2a1618", fg=DANGER, font=(SANS, 10)).pack(side="left", anchor="n")
            box = tk.Frame(inner, bg="#2a1618")
            box.pack(side="left", padx=(9, 0), fill="x", expand=True)
            tk.Label(box, text=title, bg="#2a1618", fg=INK, font=(SANS, 10, "bold"),
                     wraplength=cw - 50, justify="left").pack(anchor="w")
            tk.Label(box, text=desc, bg="#2a1618", fg=INK_MUTED, font=(SANS, 9), wraplength=cw - 50,
                     justify="left").pack(anchor="w", pady=(2, 0))

        self._section(root, "ЧТО ДЕЛАТЬ", cw)
        steps = [
            "Не переводите деньги и не вводите данные карты.",
            "Не пересылайте ссылку/сообщение знакомым — так схема и распространяется.",
            "Проверьте объект целиком через Aqyl на сайте SAQ — там полное досье и граф связей.",
            "Если уже пострадали — обратитесь в АФМ РК и в банк как можно быстрее.",
        ]
        for i, s in enumerate(steps, 1):
            row = tk.Frame(root, bg=BG)
            row.pack(fill="x", pady=5)
            n = tk.Canvas(row, width=20, height=20, bg=BG, highlightthickness=0)
            n.pack(side="left", anchor="n")
            n.create_oval(0, 0, 20, 20, fill="#1e3a8a", outline="")
            n.create_text(10, 10, text=str(i), fill=ACCENT_BRIGHT, font=(MONO, 8, "bold"))
            tk.Label(row, text=s, bg=BG, fg=INK_MUTED, font=(SANS, 10), wraplength=cw - 34,
                     justify="left").pack(side="left", padx=8, fill="x", expand=True)

        tk.Frame(root, bg=BG, height=16).pack()
        btn = tk.Button(
            root, text="Понятно", bg=ACCENT, fg="white", activebackground=ACCENT_BRIGHT,
            activeforeground="white", bd=0, font=(SANS, 10, "bold"), command=self.destroy,
            cursor="hand2", pady=8,
        )
        btn.pack(fill="x", pady=(4, 20))

    def _section(self, root, title, cw):
        tk.Label(root, text=title, bg=BG, fg=INK_FAINT, font=(MONO, 8, "bold")).pack(anchor="w", pady=(2, 8))


class GuardianWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.overrideredirect(True)
        self.geometry("470x720+120+120")
        self.configure(bg=BG)
        self.attributes("-alpha", 1.0)

        self.tray_icon: Icon | None = None
        self._seen_count = 0
        self._mood_imgs = {
            m: ImageTk.PhotoImage(render_aqyl(58, mood=m)) for m in ("happy", "alert")
        }
        self._app_icon_img = ImageTk.PhotoImage(render_shield(32, "happy"))
        self.iconphoto(True, self._app_icon_img)

        self._build_titlebar()
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)
        self._build_header(outer)
        self._build_status_card(outer)
        self._build_settings_card(outer)
        self._build_log(outer)

        self.after(400, self._poll)

    # ---- титульная строка (окно без рамки — рисуем сами) --------------
    def _build_titlebar(self):
        bar = tk.Frame(self, bg=BG, height=36)
        bar.pack(fill="x")
        tk.Label(bar, text="SAQ GUARDIAN", bg=BG, fg=INK_FAINT, font=(MONO, 9)).pack(side="left", padx=16)
        tk.Button(
            bar, text="✕", bg=BG, fg=INK_FAINT, bd=0, activebackground=DANGER, activeforeground="white",
            font=(SANS, 10), command=self.hide_to_tray, cursor="hand2", width=3,
        ).pack(side="right")
        tk.Button(
            bar, text="–", bg=BG, fg=INK_FAINT, bd=0, activebackground=BG_CARD, activeforeground=INK,
            font=(SANS, 12), command=lambda: self.overrideredirect(False) or self.iconify(), cursor="hand2",
            width=3,
        ).pack(side="right")
        bar.bind("<Button-1>", self._start_drag)
        bar.bind("<B1-Motion>", self._drag)

    def _start_drag(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag(self, e):
        self.geometry(f"+{self.winfo_pointerx() - self._dx}+{self.winfo_pointery() - self._dy}")

    # ---- шапка: Aqyl + заголовок ---------------------------------------
    def _build_header(self, root):
        row = tk.Frame(root, bg=BG)
        row.pack(fill="x", padx=22, pady=(14, 16))
        self.aqyl_label = tk.Label(row, image=self._mood_imgs["happy"], bg=BG, bd=0)
        self.aqyl_label.pack(side="left")
        txt = tk.Frame(row, bg=BG)
        txt.pack(side="left", padx=(14, 0))
        tk.Label(txt, text="SAQ Guardian", bg=BG, fg=INK, font=(DISPLAY, 19, "bold")).pack(anchor="w")
        tk.Label(txt, text="Қаржы қорғаушысы · защита в реальном времени", bg=BG, fg=INK_FAINT,
                 font=(SANS, 10)).pack(anchor="w", pady=(2, 0))

    def _set_mood(self, mood):
        self.aqyl_label.configure(image=self._mood_imgs[mood])

    # ---- карточка статуса ----------------------------------------------
    # Tkinter не умеет накладывать виджеты с прозрачным фоном поверх картинки —
    # решение: сама Label с картинкой служит родителем для содержимого.
    # Дочерние виджеты пакуются с отступом (padx/pady), поэтому скруглённая
    # рамка и градиент карточки остаются видны по краям, а не перекрываются
    # полностью, как было бы с отдельным непрозрачным оверлеем во весь размер.
    def _build_status_card(self, root):
        self._status_bg = ImageTk.PhotoImage(rounded_card(CARD_W, 168))
        card = tk.Label(root, image=self._status_bg, bg=BG, bd=0)
        card.pack(padx=20, pady=6)

        top = tk.Frame(card, bg=BG_CARD)
        top.pack(fill="x", padx=18, pady=(16, 6))
        self._dot_safe = ImageTk.PhotoImage(draw_dot(10, (16, 185, 129, 255)))
        self._dot_off = ImageTk.PhotoImage(draw_dot(10, (100, 116, 139, 255)))
        self.dot_lbl = tk.Label(top, image=self._dot_safe, bg=BG_CARD, bd=0)
        self.dot_lbl.pack(side="left")
        self.status_lbl = tk.Label(top, text="Активен", bg=BG_CARD, fg=INK, font=(SANS, 12, "bold"))
        self.status_lbl.pack(side="left", padx=(8, 0))

        self._sw_on = ImageTk.PhotoImage(self._switch_img(True))
        self._sw_off = ImageTk.PhotoImage(self._switch_img(False))
        self.switch_btn = tk.Label(top, image=self._sw_on, bg=BG_CARD, bd=0, cursor="hand2")
        self.switch_btn.pack(side="right")
        self.switch_btn.bind("<Button-1>", lambda e: self._toggle())

        self.watching_lbl = tk.Label(card, text="Слежу за: —", bg=BG_CARD, fg=INK_MUTED,
                                      font=(SANS, 10), anchor="w")
        self.watching_lbl.pack(fill="x", padx=18, pady=(0, 12))

        tiles = tk.Frame(card, bg=BG_CARD)
        tiles.pack(fill="x", padx=18, pady=(0, 16))
        self.checked_val = self._tile(tiles, "Проверено", INK)
        self.flagged_val = self._tile(tiles, "Найдено рисков", DANGER)

    def _tile(self, parent, label, color):
        tile_bg = ImageTk.PhotoImage(rounded_card(190, 62, radius=11, top=(9, 14, 28), bottom=(9, 14, 28)))
        holder = tk.Label(parent, image=tile_bg, bg=BG_CARD, bd=0)
        holder.image = tile_bg
        holder.pack(side="left", expand=True, fill="x", padx=(0, 8))
        tk.Label(holder, text=label.upper(), bg="#0d1424", fg=INK_FAINT, font=(MONO, 8)).pack(
            anchor="w", padx=10, pady=(8, 0))
        val = tk.Label(holder, text="0", bg="#0d1424", fg=color, font=(DISPLAY, 19, "bold"))
        val.pack(anchor="w", padx=10, pady=(0, 6))
        return val

    def _switch_img(self, on: bool) -> Image.Image:
        pill = rounded_button(44, 24, ACCENT if on else (51, 65, 85, 255))
        thumb = draw_dot(18, (255, 255, 255, 255))
        pill.paste(thumb, (22 if on else 2, 3), thumb)
        return pill

    def _toggle(self):
        settings["running"] = not settings["running"]
        on = settings["running"]
        self.switch_btn.configure(image=self._sw_on if on else self._sw_off)
        self.status_lbl.configure(text="Активен" if on else "На паузе")
        self.dot_lbl.configure(image=self._dot_safe if on else self._dot_off)
        self._set_mood("happy")

    # ---- настройки -------------------------------------------------------
    def _build_settings_card(self, root):
        self._settings_bg = ImageTk.PhotoImage(rounded_card(CARD_W, 150))
        card = tk.Label(root, image=self._settings_bg, bg=BG, bd=0)
        card.pack(padx=20, pady=6)

        tk.Label(card, text="НАСТРОЙКИ", bg=BG_CARD, fg=INK_FAINT, font=(MONO, 8, "bold")).pack(
            anchor="w", padx=18, pady=(14, 4))

        row = tk.Frame(card, bg=BG_CARD)
        row.pack(fill="x", padx=18)
        tk.Label(row, text="Порог риска", bg=BG_CARD, fg=INK_MUTED, font=(SANS, 10)).pack(side="left")
        self.threshold_lbl = tk.Label(row, text=str(settings["threshold"]), bg=BG_CARD, fg=ACCENT_BRIGHT,
                                       font=(MONO, 10, "bold"))
        self.threshold_lbl.pack(side="right")

        self.threshold_scale = tk.Scale(
            card, from_=10, to=100, orient="horizontal", showvalue=0, bg=BG_CARD,
            troughcolor=BORDER, fg=INK, bd=0, highlightthickness=0, sliderrelief="flat",
            activebackground=ACCENT, command=self._on_threshold,
        )
        self.threshold_scale.set(settings["threshold"])
        self.threshold_scale.pack(fill="x", padx=16, pady=(2, 10))

        row2 = tk.Frame(card, bg=BG_CARD)
        row2.pack(fill="x", padx=18, pady=(4, 16))
        tk.Label(row2, text="Backend URL", bg=BG_CARD, fg=INK_MUTED, font=(SANS, 10)).pack(side="left")
        self.backend_entry = tk.Entry(
            row2, bg=BG, fg=INK, insertbackground=ACCENT, relief="flat", font=(MONO, 9),
            highlightthickness=1, highlightbackground=BORDER_STRONG, highlightcolor=ACCENT, width=22,
        )
        self.backend_entry.insert(0, settings["backend_url"])
        self.backend_entry.pack(side="right", ipady=4)
        self.backend_entry.bind("<FocusOut>", self._on_backend)
        self.backend_entry.bind("<Return>", self._on_backend)

    def _on_threshold(self, v):
        settings["threshold"] = int(float(v))
        self.threshold_lbl.configure(text=str(int(float(v))))

    def _on_backend(self, _e=None):
        v = self.backend_entry.get().strip()
        if v:
            settings["backend_url"] = v

    # ---- лог находок -----------------------------------------------------
    def _build_log(self, root):
        head = tk.Frame(root, bg=BG)
        head.pack(fill="x", padx=24, pady=(8, 6))
        tk.Label(head, text="ЛОГ НАХОДОК", bg=BG, fg=INK_FAINT, font=(MONO, 8, "bold")).pack(side="left")

        wrap = tk.Frame(root, bg=BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        self._log_canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(wrap, orient="vertical", command=self._log_canvas.yview)
        self.log_inner = tk.Frame(self._log_canvas, bg=BG)
        self.log_inner.bind(
            "<Configure>", lambda e: self._log_canvas.configure(scrollregion=self._log_canvas.bbox("all"))
        )
        self._log_canvas.create_window((0, 0), window=self.log_inner, anchor="nw", width=CARD_W)
        self._log_canvas.configure(yscrollcommand=sb.set)
        self._log_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        empty_img = ImageTk.PhotoImage(render_aqyl(64, "happy"))
        self._empty_holder = tk.Frame(self.log_inner, bg=BG)
        self._empty_holder.pack(pady=24)
        tk.Label(self._empty_holder, image=empty_img, bg=BG, bd=0).pack()
        self._empty_holder._img = empty_img
        tk.Label(
            self._empty_holder, text="Пока чисто.\nAqyl присматривает за экраном — находки появятся здесь.",
            bg=BG, fg=INK_FAINT, font=(SANS, 10), justify="center",
        ).pack(pady=(8, 0))

    def _add_entry(self, f: dict):
        if self._empty_holder.winfo_ismapped():
            self._empty_holder.pack_forget()

        high = f["score"] is None or f["score"] >= 60
        bg_img = ImageTk.PhotoImage(rounded_card(CARD_W, 58, radius=11))
        holder = tk.Label(self.log_inner, image=bg_img, bg=BG, bd=0, cursor="hand2")
        holder.image = bg_img
        holder.pack(fill="x", pady=4)
        # левая цветная полоска — как border-left на сайте
        stripe = tk.Frame(holder, bg=(DANGER if high else ACCENT), width=3)
        stripe.place(x=0, y=0, relheight=1)

        row = tk.Frame(holder, bg="#141f36")
        row.pack(fill="both", expand=True, padx=(14, 12), pady=8)
        left = tk.Frame(row, bg="#141f36")
        left.pack(side="left", fill="both", expand=True)
        val = f["value"] if len(f["value"]) < 46 else f["value"][:46] + "…"
        tk.Label(left, text=val, bg="#141f36", fg=INK, font=(MONO, 10, "bold"), anchor="w").pack(
            fill="x", anchor="w")
        meta = f"{f['at']} · окно «{f['window']}»" + (f" · {f['flags']}" if f.get("flags") else "")
        tk.Label(left, text=meta[:70], bg="#141f36", fg=INK_FAINT, font=(SANS, 8), anchor="w").pack(
            fill="x", anchor="w")

        if f["score"] is None:
            tk.Label(row, text="ФРАЗА", bg="#3a1a1a", fg=DANGER, font=(MONO, 7, "bold")).pack(
                side="right", padx=4)
        else:
            tone = DANGER if f["score"] >= 60 else ACCENT_BRIGHT if f["score"] >= 30 else SAFE
            tk.Label(row, text=str(f["score"]), bg="#141f36", fg=tone, font=(DISPLAY, 16, "bold")).pack(
                side="right")

        for w in (holder, row, left):
            w.bind("<Button-1>", lambda e, ff=f: ExplainSheet(self, ff))

    # ---- опрос состояния (тот же поток, что раньше опрашивал пул событий) --
    def _poll(self):
        with _lock:
            win = state["window"]
            checked = state["checked"]
            flagged = state["flagged"]
            new = list(findings[self._seen_count:])
            self._seen_count = len(findings)

        self.watching_lbl.configure(text=f"Слежу за: {win or '—'}")
        self.checked_val.configure(text=str(checked))
        self.flagged_val.configure(text=str(flagged))
        if new:
            for f in new:
                self._add_entry(f)
            if settings["running"]:
                self._set_mood("alert")
                self.after(6000, lambda: self._set_mood("happy"))

        self.after(600, self._poll)

    # ---- трей ---------------------------------------------------------
    def hide_to_tray(self):
        self.withdraw()

    def show_from_tray(self):
        self.deiconify()
        self.overrideredirect(True)
        self.lift()
        self.focus_force()


def run_tray(app: "GuardianWindow", icon_image: Image.Image):
    def show(icon, item):
        app.after(0, app.show_from_tray)

    def quit_app(icon, item):
        icon.stop()
        app.after(0, app.destroy)

    app.tray_icon = Icon(
        "SAQ Guardian",
        icon_image,
        "SAQ Guardian — активен",
        menu=Menu(MenuItem("Открыть", show, default=True), MenuItem("Выход", quit_app)),
    )
    app.tray_icon.run()


def main():
    threading.Thread(target=worker_loop, daemon=True).start()
    app = GuardianWindow()
    threading.Thread(target=run_tray, args=(app, render_shield(64, "happy", ss=3)), daemon=True).start()
    app.mainloop()


if __name__ == "__main__":
    main()
