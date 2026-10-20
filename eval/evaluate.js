/* Измерение точности детектора сообщений на размеченной выборке.
 *
 * Детектор возвращает кандидатов видов: domain, phone, phrase, casino.
 * Риском считаются 'phrase' и 'casino'. Домен или номер сами по себе ничего
 * не доказывают — в обычной переписке они встречаются постоянно.
 *
 * Запуск:  node eval/evaluate.js
 */
const fs = require('fs');
const path = require('path');
const { extractCandidates } = require(path.join(__dirname, '..', 'guardian-electron', 'src', 'detect.js'));

const data = JSON.parse(fs.readFileSync(path.join(__dirname, 'dataset.json'), 'utf8'));
const items = data.items;

const RISK_KINDS = new Set(['phrase', 'casino']);
const flagged = (text) => extractCandidates(text).filter((c) => RISK_KINDS.has(c.kind));

/* ── прогон ───────────────────────────────────────────────── */
const rows = items.map((it) => {
  const hits = flagged(it.text);
  return {
    ...it,
    predicted: hits.length > 0,
    actual: it.label !== 'clean',
    hits: hits.map((h) => h.value),
  };
});

/* ── метрики ──────────────────────────────────────────────── */
function metrics(subset) {
  const tp = subset.filter((r) => r.actual && r.predicted).length;
  const fp = subset.filter((r) => !r.actual && r.predicted).length;
  const fn = subset.filter((r) => r.actual && !r.predicted).length;
  const tn = subset.filter((r) => !r.actual && !r.predicted).length;
  const precision = tp + fp ? tp / (tp + fp) : null;
  const recall = tp + fn ? tp / (tp + fn) : null;
  const f1 = precision && recall ? (2 * precision * recall) / (precision + recall) : null;
  const fpr = fp + tn ? fp / (fp + tn) : null;   // доля ложных срабатываний
  return { tp, fp, fn, tn, precision, recall, f1, fpr, n: subset.length };
}

const pct = (v) => (v === null ? '  н/д ' : (v * 100).toFixed(1).padStart(5) + '%');

function line(name, m) {
  return `${name.padEnd(26)} ${String(m.n).padStart(3)}  ` +
    `${pct(m.precision)}  ${pct(m.recall)}  ${pct(m.f1)}  ${pct(m.fpr)}   ` +
    `TP=${m.tp} FP=${m.fp} FN=${m.fn} TN=${m.tn}`;
}

const out = [];
out.push('═'.repeat(100));
out.push('ТОЧНОСТЬ ДЕТЕКТОРА СООБЩЕНИЙ — SAQ Guardian');
out.push('Выборка: ' + items.length + ' сообщений · ' + new Date().toISOString().slice(0, 10));
out.push('═'.repeat(100));
out.push('');
out.push('срез'.padEnd(26) + '  N  precision  recall      F1     FPR');
out.push('─'.repeat(100));

const all = metrics(rows);
out.push(line('ВСЯ ВЫБОРКА', all));
out.push('');

out.push('— по языку —');
for (const lang of ['ru', 'kz', 'mixed', 'translit']) {
  const sub = rows.filter((r) => r.lang === lang);
  if (sub.length) out.push(line('  ' + lang, metrics(sub)));
}
out.push('');

out.push('— по сложности —');
for (const d of ['easy', 'hard']) {
  out.push(line('  ' + d, metrics(rows.filter((r) => r.difficulty === d))));
}
out.push('');

out.push('— по типу схемы (recall) —');
for (const lab of ['pyramid', 'casino']) {
  const sub = rows.filter((r) => r.label === lab);
  const hit = sub.filter((r) => r.predicted).length;
  out.push(`  ${lab.padEnd(24)} ${String(sub.length).padStart(3)}  найдено ${hit}/${sub.length}` +
    `  (${((hit / sub.length) * 100).toFixed(1)}%)`);
}
out.push('');

/* ── ошибки поимённо ──────────────────────────────────────── */
const fns = rows.filter((r) => r.actual && !r.predicted);
const fps = rows.filter((r) => !r.actual && r.predicted);

out.push('─'.repeat(100));
out.push(`ПРОПУЩЕННЫЕ СХЕМЫ (false negatives): ${fns.length}`);
out.push('─'.repeat(100));
if (!fns.length) out.push('  нет');
fns.forEach((r) => {
  out.push(`  [${r.id}] ${r.lang}/${r.difficulty}`);
  out.push(`      ${r.text.slice(0, 95)}`);
});
out.push('');

out.push('─'.repeat(100));
out.push(`ЛОЖНЫЕ СРАБАТЫВАНИЯ (false positives): ${fps.length}`);
out.push('─'.repeat(100));
if (!fps.length) out.push('  нет');
fps.forEach((r) => {
  out.push(`  [${r.id}] ${r.lang}/${r.difficulty}`);
  out.push(`      ${r.text.slice(0, 95)}`);
  out.push(`      сработало: ${r.hits.join(' | ').slice(0, 150)}`);
});
out.push('');
out.push('═'.repeat(100));

const report = out.join('\n');
fs.writeFileSync(path.join(__dirname, 'report.txt'), report, 'utf8');
fs.writeFileSync(path.join(__dirname, 'results.json'), JSON.stringify({
  generated: new Date().toISOString(),
  total: items.length,
  overall: all,
  by_language: Object.fromEntries(['ru', 'kz', 'mixed', 'translit']
    .map((l) => [l, metrics(rows.filter((r) => r.lang === l))])),
  by_difficulty: Object.fromEntries(['easy', 'hard']
    .map((d) => [d, metrics(rows.filter((r) => r.difficulty === d))])),
  false_negatives: fns.map((r) => ({ id: r.id, lang: r.lang, text: r.text })),
  false_positives: fps.map((r) => ({ id: r.id, lang: r.lang, text: r.text, hits: r.hits })),
}, null, 2), 'utf8');

console.log(report);
