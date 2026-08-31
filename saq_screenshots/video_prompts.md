# SAQ — промт для видео, сцена = скриншот

Формат под Higgsfield (image-to-video / "animate this photo"). Для каждой сцены — конкретный файл-скриншот как стартовый кадр + промт анимации. Плюс 3 "чистых" сцены без скриншота (хук, люди, лого) — их генерировать text-to-video с нуля.

Итого 9 сцен, 5 из них — image-to-video по реальным скриншотам SAQ.

Все файлы лежат в `D:\Новая папка\saq_screenshots\`.

---

## Сцена 1 — Хук (0:00–0:08) — БЕЗ скриншота, text-to-video
**Промт:**
"Extreme close-up on a smartphone screen at night, thumb scrolling a slick investment ad promising '300% monthly returns, guaranteed.' Red glitch warning glyphs flicker across the screen like a system detecting danger. Tense low synth pulse. City lights blurred in the background bokeh."

---

## Сцена 2 — Скриншот: `00_landing.png` (главная страница)
**Промт (image-to-video, анимация этого кадра):**
"Animate this landing page screenshot: the mascot icon top-right gently bobs and blinks once, the glowing dots around it drift slowly like a live radar. The search input types out a query letter by letter ('profit-guarantee.example'), then the Aqyl side-panel card fades and slides in from the right with a soft glow, its WHOIS / CRT.SH / РЕЕСТР / ТЕЛЕГРАМ rows appearing one-by-one top to bottom, finishing with the RISK SCORE bar filling up to 82 with a red pulse. Keep all UI text sharp and readable throughout. Slow, smooth camera push-in toward the score card. On-screen caption overlay: 'Domain, wallet or channel — Aqyl checks it against public sources.'"

---

## Сцена 3 — Скриншот: `01_multigraph.png` (общий граф Finiko/Qnet/Crowd1)
**Промт (image-to-video, анимация этого кадра):**
"Animate this dashboard screenshot: the graph nodes gently pulse with soft glowing light, the red 'bridge' connection lines between the three companies slowly draw themselves in with a subtle particle trail, as if the AI is actively tracing the shared entity in real time. Slow, smooth camera push-in toward the center node. Keep all UI text sharp and readable throughout. On-screen caption overlay: 'One AI agent. Every OSINT source. One graph.'"

---

## Сцена 4 — Скриншот: `02_dashboard.png` (личный кабинет)
**Промт (image-to-video):**
"Animate this dashboard screenshot: the risk-score numbers (60, 70, 60, 20...) count up from zero with a quick digital tick animation, the red score badges pulse once when they land, cards subtly lift with a soft shadow as if freshly loaded. Gentle camera drift downward revealing the investigation history list. On-screen caption: 'Every check, remembered. Every risk, scored.'"

---

## Сцена 5 — Скриншот: `03_watchlist.png` (реестр Watchlist)
**Промт (image-to-video):**
"Animate this watchlist screenshot: new entry cards slide in from the right one by one with a soft blue glow, the 'ПИРАМИД' / 'PONZI' tag chips fade in with a slight bounce, a live pulsing dot next to 'ЖИВАЯ ЛЕНТА' blinks steadily. Camera holds static, slight parallax on scroll. On-screen caption: 'A living registry — built from public data, shared by everyone who checks.'"

---

## Сцена 6 — Скриншот: `04_admin.png` (админ-панель)
**Промт (image-to-video):**
"Animate this admin panel screenshot: the big numbers (4, 745, 146, 4, 9, 0) count up rapidly like an odometer, the red '146' high-risk counter pulses with a warning glow once it lands. Subtle scan-line sweep passes once across the panel like a system health check completing. On-screen caption: '745 investigations. 146 high-risk. Zero manual work.'"

---

## Сцена 7 — Мобильное приложение — БЕЗ скриншота (продукта ещё нет как кадра), text-to-video
**Промт:**
"Split-screen: on one half, a phone showing an incoming video call from a 'financial advisor' with a faint deepfake shimmer artifact on their face; on the other half, a mobile app UI running a live scanning-line animation over the video feed, then a hard red stamp slams down: 'SCAM DETECTED — BLOCKED.' The call drops, caller ID greys out, a shield icon locks shut with a satisfying UI-click sound."

---

## Сцена 8 — Люди (0:50–0:58) — БЕЗ скриншота, text-to-video
**Промт:**
"Fast warm cuts: a student, an elderly woman, a young entrepreneur — each exhaling in relief, phone lowering, soft blue light on their faces, gentle smile. Music shifts from tense to uplifting major-key swell."

---

## Сцена 9 — Финал / лого — БЕЗ скриншота, text-to-video
**Промт:**
"Scattered graph nodes (echoing the shape from Scene 3) fly inward and snap together into a shield emblem with 'SAQ' lettering. Tagline types on letter by letter: 'SAQ — SEE THE SCAM BEFORE IT SEES YOU.' Closing card: web and mobile app icons side by side, small text 'AI-powered pyramid & fraud detection — web platform + mobile guardian app.'"

---

### Порядок сборки
1 (хук) → 2 (лендинг) → 3 (граф) → 4 (дашборд) → 5 (watchlist) → 6 (admin) → 7 (мобильное блокирует) → 8 (люди) → 9 (лого). Итого ≈80-90 сек.

### Для нового чата с Higgsfield
Скажи: "вот промты по сценам и скриншоты — сгенерируй видео по каждой сцене (image-to-video для сцен со скриншотом, text-to-video для остальных), потом склей в один ролик". Приложи все 5 PNG из `D:\Новая папка\saq_screenshots\` + этот файл.
