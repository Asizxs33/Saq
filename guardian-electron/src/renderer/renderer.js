/* Aqyl — тот же SVG-маскот, что на сайте (web/src/components/SaqMark.tsx). */
function aqylSVG(mood) {
  const NAVY = "#132a63", TONGUE = "#e0526d", BLUSH = "#7ba3f5";
  const eyes = (mood === "happy")
    ? `<path d="M15.4 28.4q3.2-3.2 6.4 0" stroke="${NAVY}" stroke-width="2" stroke-linecap="round" fill="none"/>
       <path d="M26.2 28.4q3.2-3.2 6.4 0" stroke="${NAVY}" stroke-width="2" stroke-linecap="round" fill="none"/>`
    : `<g class="aqyl-eyes"><g class="aqyl-look">
         <circle cx="18.6" cy="28" r="3.1" fill="${NAVY}"/><circle cx="29.4" cy="28" r="3.1" fill="${NAVY}"/>
         <g class="${mood === "thinking" ? "aqyl-scan" : ""}">
           <circle cx="19.7" cy="26.9" r="1" fill="#fff"/><circle cx="30.5" cy="26.9" r="1" fill="#fff"/>
         </g></g></g>`;
  const mouth = (mood === "happy")
    ? `<g><path d="M20.4 31.6h7.2c0 2.7-1.6 4.4-3.6 4.4s-3.6-1.7-3.6-4.4Z" fill="${NAVY}"/>
        <path d="M22 34.9c.5.7 1.2 1.1 2 1.1s1.5-.4 2-1.1c-.5-.9-1.2-1.4-2-1.4s-1.5.5-2 1.4Z" fill="${TONGUE}"/></g>`
    : (mood === "alert")
    ? `<path d="M21.2 34.4q2.8-2.2 5.6 0" stroke="${NAVY}" stroke-width="1.8" stroke-linecap="round" fill="none"/>`
    : `<path d="M21.4 33.2c1.7 1.5 3.5 1.5 5.2 0" stroke="${NAVY}" stroke-width="1.6" stroke-linecap="round" fill="none"/>`;
  const extras = (mood === "alert")
    ? `<g><path d="M14.6 23.4l6.2 1.9" stroke="${NAVY}" stroke-width="1.9" stroke-linecap="round"/>
        <path d="M33.4 23.4l-6.2 1.9" stroke="${NAVY}" stroke-width="1.9" stroke-linecap="round"/></g>`
    : (mood === "happy")
    ? `<g opacity=".5"><ellipse cx="14.4" cy="31.6" rx="2" ry="1.2" fill="${BLUSH}"/>
        <ellipse cx="33.6" cy="31.6" rx="2" ry="1.2" fill="${BLUSH}"/></g>` : "";
  return `<svg viewBox="0 0 48 48" fill="none"><defs>
    <linearGradient id="gh" x1="10" y1="8" x2="38" y2="44" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#5f94f9"/><stop offset=".55" stop-color="#2f6ae8"/><stop offset="1" stop-color="#1c4ecf"/></linearGradient>
    <linearGradient id="ge" x1="8" y1="4" x2="40" y2="18" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#4d83f2"/><stop offset="1" stop-color="#1e4dc4"/></linearGradient>
    <linearGradient id="gf" x1="24" y1="18" x2="24" y2="37" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#eef4ff"/></linearGradient></defs>
    <g class="aqyl-breathe">
      <g class="aqyl-ear">
        <ellipse cx="14" cy="11" rx="4.6" ry="6.4" transform="rotate(-24 14 11)" fill="url(#ge)"/>
        <ellipse cx="13.4" cy="9.6" rx="1.7" ry="2.6" transform="rotate(-24 13.4 9.6)" fill="#8db3fa" opacity=".55"/></g>
      <g class="aqyl-ear aqyl-ear-r">
        <ellipse cx="34" cy="11" rx="4.6" ry="6.4" transform="rotate(24 34 11)" fill="url(#ge)"/>
        <ellipse cx="34.6" cy="9.6" rx="1.7" ry="2.6" transform="rotate(24 34.6 9.6)" fill="#8db3fa" opacity=".55"/></g>
      <path d="M24 10c10.6 0 18 6.6 18 16.4C42 36.6 34.4 43 24 43S6 36.6 6 26.4C6 16.6 13.4 10 24 10Z" fill="url(#gh)"/>
      <ellipse cx="19" cy="14.6" rx="7.5" ry="3" transform="rotate(-12 19 14.6)" fill="#fff" opacity=".3"/>
      <path d="M24 18.2c-2.5 0-3.6 1.6-6.8 1.6-3.4 0-6.2 2.6-6.2 6.4 0 6 5.4 10.4 13 10.4s13-4.4 13-10.4c0-3.8-2.8-6.4-6.2-6.4-3.2 0-4.3-1.6-6.8-1.6Z" fill="url(#gf)"/>
      ${eyes}${mouth}${extras}
    </g></svg>`;
}

const FLAG_INFO = [
  [/свежерегистрирован|дн\. назад/i, "Домен создан совсем недавно",
    "Пирамиды живут месяцами: сайт поднимают, собирают деньги и бросают. Если «компания работает 5 лет», а домен зарегистрирован недавно — вам врут."],
  [/дешёвая TLD|TLD-зона/i, "Дешёвая доменная зона",
    "Зоны вроде .top/.xyz/.online стоят копейки и не требуют проверки владельца — их берут, когда сайт планируют бросить."],
  [/маркер-приманка|приманк/i, "Слова-приманки в адресе сайта",
    "В имени домена зашиты обещания дохода (profit, invest, x2, bonus). Настоящие финкомпании так не называются."],
  [/веб-архив|архив/i, "Сайта нет в веб-архиве",
    "У реальной компании остаётся след в интернете за прошлые годы. Пустая история = сайт появился только что."],
  [/санкцион|PEP/i, "Есть в санкционных списках",
    "Объект найден в международных санкционных списках или среди политически значимых лиц. Это очень серьёзный сигнал."],
  [/кошельк|сборщик/i, "Криптокошелёк ведёт себя как сборщик",
    "Деньги приходят от множества разных людей и уходят одним потоком — типичная схема сбора средств пирамиды."],
  [/ponzi|пирамид|pyramid/i, "Упоминания пирамиды в открытых источниках",
    "В поиске, СМИ или жалобах этот объект уже связывают со схемой Понци или финансовой пирамидой."],
  [/блэклист|blacklist|АФМ/i, "Числится в чёрном списке регулятора",
    "Объект попал в официальный перечень подозрительных организаций."],
];

function explainFlags(list) {
  if (!list || !list.length) return [];
  const out = [];
  list.forEach((f) => {
    const hit = FLAG_INFO.find(([re]) => re.test(f));
    out.push(hit ? { t: hit[1], d: hit[2] } : { t: f, d: "Сигнал риска, зафиксированный источниками SAQ." });
  });
  return out.filter((v, i, a) => a.findIndex((x) => x.t === v.t) === i);
}

let mood = "thinking", seen = 0, paused = false, moodTimer = null;
const $ = (id) => document.getElementById(id);
$("mascot").innerHTML = aqylSVG(mood);
$("empty-mascot").innerHTML = aqylSVG("happy");
function setMood(m) { if (m !== mood) { mood = m; $("mascot").innerHTML = aqylSVG(m); } }

$("btnMin").onclick = () => window.guardianAPI.minimize();
$("btnClose").onclick = () => window.guardianAPI.hide();

$("toggle").onclick = async () => {
  paused = !paused;
  document.body.classList.toggle("paused", paused);
  $("status").textContent = paused ? "На паузе" : "Активен";
  setMood(paused ? "neutral" : "thinking");
  await window.guardianAPI.setRunning(!paused);
};

const th = $("threshold");
function paintRange() { th.style.setProperty("--pct", ((th.value - 10) / 90 * 100) + "%"); }
th.oninput = () => { $("thval").textContent = th.value; paintRange(); window.guardianAPI.setThreshold(+th.value); };
paintRange();

$("backend").onchange = (e) => window.guardianAPI.setBackend(e.target.value.trim());

function addEntry(f) {
  $("empty").style.display = "none";
  const isCasino = f.kind === "casino";
  const high = f.score === null || f.score >= 60;
  const tone = f.score === null ? "" : f.score >= 60 ? "high" : f.score >= 30 ? "mid" : "low";
  const badge = isCasino ? `<div class="kind" style="background:rgba(96,165,250,.14);color:var(--accent-bright)">казино</div>`
    : f.score === null ? `<div class="kind">фраза</div>`
    : `<div class="score ${tone}">${f.score}</div>`;
  const el = document.createElement("div");
  el.className = "entry" + (high ? " high" : "") + (isCasino ? " casino" : "");
  if (isCasino) el.style.borderLeftColor = "var(--accent)";
  el.innerHTML = `<div class="body">
      <div class="val">${f.value}</div>
      <div class="meta">${f.at} · окно «${f.window}»${f.flags ? " · " + f.flags : ""}</div>
    </div>` + badge;
  el.onclick = () => openSheet(f);
  el.title = "Нажмите — объясню, что это и что делать";
  $("log").prepend(el);
}

function openSheet(f) {
  if (f.kind === "casino") { openCasinoSheet(f); return; }
  const isPhrase = f.score === null;
  const score = f.score;
  const tone = isPhrase ? "var(--danger)" : score >= 60 ? "var(--danger)" : score >= 30 ? "var(--accent-bright)" : "var(--safe)";
  const verdict = isPhrase ? "Формулировка мошенника" : score >= 60 ? "Высокий риск" : score >= 30 ? "Требует внимания" : "Низкий риск";

  const whyHtml = isPhrase
    ? `<div class="why"><div class="ic">▲</div><div><b>Обещание гарантированного дохода</b>
        <small>Ни один законный финансовый инструмент не может гарантировать доходность — это запрещено.
        Такую формулировку используют, чтобы отключить у человека критическое мышление.</small></div></div>`
    : (explainFlags(f.flagList).map((x) =>
        `<div class="why"><div class="ic">▲</div><div><b>${x.t}</b><small>${x.d}</small></div></div>`
      ).join("") || `<div class="why"><div class="ic">▲</div><div><b>Совокупная оценка источников</b>
        <small>Отдельные признаки по одиночке слабые, но вместе дали оценку ${score}/100.</small></div></div>`);

  const steps = isPhrase
    ? ["Не переводите деньги и не вводите данные карты.",
       "Спросите, откуда берётся доход. У пирамиды ответ всегда размытый.",
       "Проверьте организацию в реестре SAQ или через Aqyl на сайте.",
       "Если уже перевели деньги — обратитесь в АФМ РК и в банк как можно быстрее."]
    : ["Не переводите деньги и не вводите данные карты на этом ресурсе.",
       "Не пересылайте ссылку знакомым — так схема и распространяется.",
       "Проверьте объект целиком через Aqyl на сайте SAQ — там будет полное досье и граф связей.",
       "Если уже пострадали — зафиксируйте переписку и обратитесь в АФМ РК."];

  $("sheet").innerHTML = `
    <div class="grab"></div>
    <div class="verdict">
      <div class="gauge" style="background:radial-gradient(circle,${tone}22,transparent 70%);border:2px solid ${tone};color:${tone}">
        <span>${isPhrase ? "!" : score}</span>
      </div>
      <div style="min-width:0">
        <h3>${f.value}</h3>
        <div class="sub">${verdict}${isPhrase ? "" : " · " + f.sources + " источников проверено"} · окно «${f.window}»</div>
      </div>
    </div>
    <div class="sect"><div class="t">Что это значит</div>
      <p>${isPhrase
        ? "На экране встретилась фраза, которой пользуются организаторы финансовых пирамид. Сама по себе она не доказывает мошенничество, но это повод насторожиться и проверить, с кем вы имеете дело."
        : `SAQ прогнал этот объект через ${f.sources} открытых источника — реестры компаний, санкционные списки, судебные базы, чёрные списки регулятора и поиск. Итоговая оценка риска — <b style="color:${tone}">${score} из 100</b>.`}</p>
    </div>
    <div class="sect"><div class="t">Почему это подозрительно</div>${whyHtml}</div>
    <div class="sect"><div class="t">Что делать</div>
      ${steps.map((s, i) => `<div class="todo"><div class="n">${i + 1}</div><div>${s}</div></div>`).join("")}
    </div>
    <button class="close" onclick="closeSheet()">Понятно</button>`;
  $("overlay").classList.add("open");
}
function openCasinoSheet(f) {
  const tone = "var(--accent-bright)";
  $("sheet").innerHTML = `
    <div class="grab"></div>
    <div class="verdict">
      <div class="gauge" style="background:radial-gradient(circle,${tone}22,transparent 70%);border:2px solid ${tone};color:${tone}">
        <span>🎰</span>
      </div>
      <div style="min-width:0">
        <h3>${f.value}</h3>
        <div class="sub">Азартный контент · окно «${f.window}»</div>
      </div>
    </div>
    <div class="sect"><div class="t">Что это значит</div>
      <p>На экране контент, связанный с онлайн-казино или ставками — реклама, стрим с демонстрацией «выигрышей» или промо-код. Это не обязательно мошенничество в смысле пирамиды, но отдельная категория финансового риска: такие ролики специально показывают крупные выигрыши, чтобы создать иллюзию лёгких денег.</p>
    </div>
    <div class="sect"><div class="t">Почему это подозрительно</div>
      <div class="why"><div class="ic">▲</div><div><b>Выборочная демонстрация выигрышей</b>
        <small>Стримеры показывают удачные заносы и почти никогда — суммарный проигрыш за сессию. Математика казино устроена так, что казино всегда в плюсе в долгую.</small></div></div>
      <div class="why"><div class="ic">▲</div><div><b>Целевая аудитория — часто подростки</b>
        <small>Такой контент массово идёт на YouTube/стримах, куда заходят несовершеннолетние, хотя азартные игры для них запрещены законом.</small></div></div>
    </div>
    <div class="sect"><div class="t">Что делать</div>
      <div class="todo"><div class="n">1</div><div>Не переходите по промокодам и ссылкам на казино из видео.</div></div>
      <div class="todo"><div class="n">2</div><div>Если это видит ребёнок — стоит включить родительский контроль на платформе.</div></div>
      <div class="todo"><div class="n">3</div><div>Помните: демонстрация выигрыша — это реклама, а не статистика вашего будущего результата.</div></div>
    </div>
    <button class="close" onclick="closeSheet()">Понятно</button>`;
  $("overlay").classList.add("open");
}
function closeSheet() { $("overlay").classList.remove("open"); }
$("overlay").onclick = (e) => { if (e.target.id === "overlay") closeSheet(); };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSheet(); });

window.guardianAPI.onStateUpdate((s) => {
  $("window").textContent = s.window || "—";
  $("checked").textContent = s.checked;
  $("flagged").textContent = s.flagged;
  if (s.findings.length > seen) {
    s.findings.slice(seen).forEach(addEntry);
    seen = s.findings.length;
    $("count").textContent = seen;
    if (!paused) {
      setMood("alert");
      clearTimeout(moodTimer);
      moodTimer = setTimeout(() => { if (!paused) setMood("thinking"); }, 6000);
    }
  }
});

window.guardianAPI.getState().then((s) => {
  $("window").textContent = s.window || "—";
  $("checked").textContent = s.checked;
  $("flagged").textContent = s.flagged;
  seen = s.findings.length;
  $("count").textContent = seen;
  s.findings.forEach(addEntry);
  // поле раньше показывало статичное значение из HTML, а не реальный
  // backendUrl из main.js — синхронизируем с тем, что реально используется
  if (s.settings) {
    $("backend").value = s.settings.backendUrl;
    $("threshold").value = s.settings.threshold;
    $("thval").textContent = s.settings.threshold;
    paintRange();
  }
});
