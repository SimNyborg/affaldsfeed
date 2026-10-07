// Affaldsfeed: hjælpere, URL-tilstand, filtrering, tællere og filterpanel.
// Ingen afhængigheder. Bruges af app.js og overview.js.

// ── Tid og formatering (Europe/Copenhagen) ─────────────────

export const TZ = 'Europe/Copenhagen';
export const DAY_MS = 864e5;

const MONTHS = ['januar', 'februar', 'marts', 'april', 'maj', 'juni', 'juli', 'august', 'september', 'oktober', 'november', 'december'];
const MONTHS_SHORT = ['jan.', 'feb.', 'mar.', 'apr.', 'maj', 'jun.', 'jul.', 'aug.', 'sep.', 'okt.', 'nov.', 'dec.'];
const WEEKDAYS = ['søndag', 'mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag', 'lørdag'];

const partsFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});
const numFmt = new Intl.NumberFormat('da-DK');

/** Kalenderdele for et tidspunkt i København. dayNum = dage siden 1970-01-01 (lokal dato). */
export function cph(date) {
  const p = {};
  for (const { type, value } of partsFmt.formatToParts(date)) p[type] = value;
  const y = +p.year, m = +p.month, d = +p.day;
  const hh = p.hour === '24' ? '00' : p.hour;
  return { y, m, d, hh, mm: p.minute, key: `${p.year}-${p.month}-${p.day}`, dayNum: Date.UTC(y, m - 1, d) / DAY_MS };
}

export const fmtNum = (n) => numFmt.format(n);
export const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);
export const parseDate = (s) => {
  if (!s) return null;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
};

export function weekdayOf(c) {
  return WEEKDAYS[new Date(c.dayNum * DAY_MS).getUTCDay()];
}
export const fmtShort = (c) => `${c.d}. ${MONTHS_SHORT[c.m - 1]}`;
export const fmtLong = (c) => `${c.d}. ${MONTHS[c.m - 1]}`;
export const fmtLongYear = (c) => `${c.d}. ${MONTHS[c.m - 1]} ${c.y}`;

/** "i dag kl. 08.14", "i går kl. 08.14", "tirsdag kl. 14.32" eller "5. okt. kl. 14.32". */
export function fmtWhen(date, now) {
  const c = cph(date);
  const diff = cph(now).dayNum - c.dayNum;
  const clock = `kl. ${c.hh}.${c.mm}`;
  if (diff <= 0) return `i dag ${clock}`;
  if (diff === 1) return `i går ${clock}`;
  if (diff < 7) return `${weekdayOf(c)} ${clock}`;
  return `${fmtShort(c)} ${clock}`;
}

/** "kl. 14.17" i dag, ellers "6. okt. kl. 14.17". */
export function fmtStamp(date, now) {
  const c = cph(date);
  const clock = `kl. ${c.hh}.${c.mm}`;
  return cph(now).dayNum === c.dayNum ? clock : `${fmtShort(c)} ${clock}`;
}

/** ISO-uge for en lokal dato (dayNum). */
export function isoWeek(dayNum) {
  const d = new Date(dayNum * DAY_MS);
  const wd = (d.getUTCDay() + 6) % 7; // mandag = 0
  const thursday = new Date(d.getTime() + (3 - wd) * DAY_MS);
  const yearStart = Date.UTC(thursday.getUTCFullYear(), 0, 1);
  const week = 1 + Math.floor((thursday.getTime() - yearStart) / DAY_MS / 7);
  return { year: thursday.getUTCFullYear(), week, monday: dayNum - wd };
}

export function fmtWeekRange(mondayNum) {
  const a = new Date(mondayNum * DAY_MS);
  const b = new Date((mondayNum + 6) * DAY_MS);
  const am = a.getUTCMonth(), bm = b.getUTCMonth();
  if (am === bm) return `${a.getUTCDate()}.–${b.getUTCDate()}. ${MONTHS[bm]}`;
  return `${a.getUTCDate()}. ${MONTHS[am]}–${b.getUTCDate()}. ${MONTHS[bm]}`;
}

/** Afkort ved et ord og tilføj "…". */
export function truncate(s, max) {
  if (!s || s.length <= max) return s || '';
  const cut = s.slice(0, max);
  const sp = cut.lastIndexOf(' ');
  return `${(sp > max * 0.6 ? cut.slice(0, sp) : cut).replace(/[\s,.;:–-]+$/, '')}…`;
}

// ── DOM ────────────────────────────────────────────────────

export const ICONS = 'assets/ikoner.svg';
const SVG_NS = 'http://www.w3.org/2000/svg';

/** el('a', {class: 'x', href: '…', onclick: fn}, 'tekst', child, [flere]) */
export function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') node.className = v;
      else if (k === 'text') node.textContent = v;
      else if (k === 'style') node.style.cssText = v;
      else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
      else if (k === 'dataset') Object.assign(node.dataset, v);
      else node.setAttribute(k, v === true ? '' : v);
    }
  }
  append(node, children);
  return node;
}

function append(node, children) {
  for (const c of children) {
    if (c === null || c === undefined || c === false) continue;
    if (Array.isArray(c)) append(node, c);
    else node.append(c instanceof Node ? c : String(c));
  }
}

export function icon(name, cls = '') {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', `i ${cls}`.trim());
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const use = document.createElementNS(SVG_NS, 'use');
  use.setAttribute('href', `${ICONS}#${name}`);
  svg.append(use);
  return svg;
}

export const hidden = (text) => el('span', { class: 'visually-hidden', text });

/** Kategorifarver som custom properties (lys/mørk). */
export const catStyle = (cat) => `--cl:${cat.color};--cd:${cat.color_dark}`;

/** Kort navn til kildelinks: "European Environmental Bureau (EEB)" → "EEB". */
export function shortName(name) {
  const m = /^(.*?)\s*\(([^)]+)\)\s*$/.exec(name || '');
  if (!m) return name;
  return m[2].length <= 6 && m[2] === m[2].toUpperCase() ? m[2] : m[1];
}

// ── Lokal lagring (altid i try/catch) ──────────────────────

export function store(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch { /* privat vindue o.l. */ }
}
export function load(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

// ── URL-tilstand (KONTRAKTER §9) ───────────────────────────

export const GROUPS = ['afsender', 'tema', 'kilde', 'genre'];
export const PERIODS = [7, 30, 60];
export const OV_PERIODS = ['dag', 'uge', 'maaned', 'aar'];
export const NO_TOPIC = 'uden';

export function defaultState() {
  return {
    afsender: [], tema: [], kilde: [], genre: [],
    periode: 60, sprog: '', q: '', nye: false, saml: true, vis: '',
    story: [], overblik: 'dag', demo: '',
  };
}

export function readState(search) {
  const p = new URLSearchParams(search);
  const list = (k) => [...new Set((p.get(k) || '').split(',').map((s) => s.trim()).filter(Boolean))];
  const s = defaultState();
  for (const g of GROUPS) s[g] = list(g);
  const per = Number(p.get('periode'));
  s.periode = PERIODS.includes(per) ? per : 60;
  s.sprog = p.get('sprog') === 'da' ? 'da' : '';
  s.q = (p.get('q') || '').trim();
  s.nye = p.get('nye') === '1';
  s.saml = p.get('saml') !== '0';
  s.vis = p.get('vis') === 'kompakt' ? 'kompakt' : '';
  s.story = list('story');
  s.overblik = OV_PERIODS.includes(p.get('overblik')) ? p.get('overblik') : 'dag';
  s.demo = p.get('demo') || '';
  return s;
}

const enc = (v) => encodeURIComponent(v).replace(/%2C/gi, ',');

export function writeState(s) {
  const out = [];
  const add = (k, v) => out.push(`${k}=${enc(v)}`);
  if (s.demo) add('demo', s.demo);
  for (const g of GROUPS) if (s[g].length) add(g, s[g].join(','));
  if (s.periode !== 60) add('periode', s.periode);
  if (s.sprog) add('sprog', s.sprog);
  if (s.q) add('q', s.q);
  if (s.nye) add('nye', '1');
  if (!s.saml) add('saml', '0');
  if (s.vis) add('vis', s.vis);
  if (s.story.length) add('story', s.story.join(','));
  if (s.overblik !== 'dag') add('overblik', s.overblik);
  return out.join('&');
}

export function syncUrl(s) {
  const qs = writeState(s);
  const url = `${location.pathname}${qs ? `?${qs}` : ''}${location.hash}`;
  if (url !== `${location.pathname}${location.search}${location.hash}`) history.replaceState(null, '', url);
}

/** Er der filtre, der indsnævrer feedet? (visning som saml/vis tæller ikke) */
export function activeCount(s) {
  let n = 0;
  for (const g of GROUPS) n += s[g].length;
  if (s.periode !== 60) n += 1;
  if (s.sprog) n += 1;
  if (s.q) n += 1;
  if (s.nye) n += 1;
  if (s.story.length) n += 1;
  return n;
}

export function resetFilters(s) {
  for (const g of GROUPS) s[g] = [];
  s.periode = 60;
  s.sprog = '';
  s.q = '';
  s.nye = false;
  s.story = [];
}

// ── Data: indslag og historier ─────────────────────────────

const UNKNOWN_CAT = { id: 'ukendt', name: 'Ukendt afsender', short: 'Ukendt', color: '#565656', color_dark: '#A9B3AE', icon: 'avis', help: '' };

/**
 * Gør feed.json klar til visning. Hvert indslag (også dem i `also`) bliver et "medlem",
 * og hvert hovedindslag med sine also-medlemmer bliver en "historie" (unit).
 */
export function prepare(feed, lastVisit) {
  const cats = new Map((feed.categories || []).map((c) => [c.id, c]));
  const sources = new Map((feed.sources || []).map((s) => [s.id, s]));
  const topics = new Map((feed.topics || []).map((t) => [t.id, t]));
  const genres = new Map((feed.genres || []).map((g) => [g.id, g]));
  const units = [];
  const members = [];
  const byId = new Map();

  const sourceOf = (id) => {
    if (!sources.has(id)) sources.set(id, { id, name: id, category: null, lang: 'da', paywall: 'nej', owner: null, status: 'aktiv', health: 'graa', via_search: false });
    return sources.get(id);
  };

  const finish = (m) => {
    m.cat = cats.get(m.source.category) || UNKNOWN_CAT;
    m.catId = m.cat.id;
    m.time = (m.published || m.firstSeen || new Date(0)).getTime();
    m.text = [m.title, m.teaser, m.summary, m.source.name, m.source.owner].filter(Boolean).join(' ').toLowerCase();
    m.isNew = isNewMember(m, lastVisit);
    m.sortKey = sortKey(m);
    m.day = cph(new Date(m.time));
    members.push(m);
    byId.set(m.id, m);
    return m;
  };

  for (const it of feed.items || []) {
    const src = sourceOf(it.source);
    const unit = { id: it.story || it.id, members: [] };
    const head = finish({
      id: it.id, url: it.url, title: it.title, teaser: it.teaser || '', source: src, sourceId: src.id,
      published: parseDate(it.published), firstSeen: parseDate(it.first_seen), dateQuality: it.date_quality,
      baseline: !!it.baseline, topics: it.topics || [], genre: it.genre || 'nyhed', lang: it.lang || src.lang || 'da',
      summary: it.summary_da || '', reviewed: it.reviewed !== false, isHead: true, unit,
    });
    unit.head = head;
    unit.members.push(head);
    for (const a of it.also || []) {
      const asrc = sourceOf(a.source);
      const m = finish({
        id: a.id, url: a.url, title: a.title, teaser: '', source: asrc, sourceId: asrc.id,
        published: parseDate(a.published) || head.published, firstSeen: null, dateQuality: 'kilde',
        baseline: head.baseline, topics: head.topics, genre: 'nyhed', lang: asrc.lang || 'da',
        summary: '', reviewed: head.reviewed, isHead: false, unit,
      });
      unit.members.push(m);
    }
    units.push(unit);
  }
  return { feed, cats, sources, topics, genres, units, members, byId };
}

function isNewMember(m, lastVisit) {
  if (!lastVisit || m.baseline) return false;
  const found = m.firstSeen || m.published;
  if (!found || found <= lastVisit) return false;
  if (m.published && found - m.published > 3 * DAY_MS) return false;
  return true;
}

/** Sortering inden for en dag: lokal klokketid; kun-dato nederst, medmindre fundet samme dag. */
function sortKey(m) {
  const base = m.published || m.firstSeen;
  if (!base) return 0;
  const c = cph(base);
  if (m.dateQuality === 'url' || m.dateQuality === 'liste') {
    if (m.firstSeen) {
      const f = cph(m.firstSeen);
      if (f.dayNum === c.dayNum) return f.dayNum * DAY_MS + (+f.hh * 60 + +f.mm) * 6e4;
    }
    return c.dayNum * DAY_MS;
  }
  return c.dayNum * DAY_MS + (+c.hh * 60 + +c.mm) * 6e4 + base.getUTCSeconds() * 1e3;
}

function optionKeys(group, m) {
  if (group === 'afsender') return [m.catId];
  if (group === 'kilde') return [m.sourceId];
  if (group === 'genre') return [m.genre];
  return m.topics.length ? m.topics : [NO_TOPIC];
}

/** Predikat for ét indslag. `skip` er grupper, der ses bort fra (til tællere). */
export function makePredicate(s, now, skip = new Set()) {
  const sets = Object.fromEntries(GROUPS.map((g) => [g, new Set(s[g])]));
  const minTime = now.getTime() - s.periode * DAY_MS;
  const words = s.q.toLowerCase().split(/\s+/).filter(Boolean);
  const stories = new Set(s.story);
  return (m) => {
    for (const g of GROUPS) {
      if (skip.has(g) || !sets[g].size) continue;
      if (!optionKeys(g, m).some((k) => sets[g].has(k))) return false;
    }
    if (m.time < minTime) return false;
    if (s.sprog === 'da' && m.lang !== 'da') return false;
    if (s.nye && !skip.has('nye') && !m.isNew) return false;
    if (stories.size && !stories.has(m.unit.id)) return false;
    if (words.length && !words.every((w) => m.text.includes(w))) return false;
    return true;
  };
}

/**
 * Kort til visning. Filtrene virker på enkelte indslag; samlingen i historier sker bagefter.
 * Med saml slået til vises historien med det første matchende medlem (helst hovedindslaget)
 * øverst og resten under "+N andre kilder".
 */
export function applyFilters(data, s, now, skip) {
  const pred = makePredicate(s, now, skip);
  const cards = [];
  if (s.saml) {
    for (const u of data.units) {
      const hits = u.members.filter(pred);
      if (!hits.length) continue;
      const primary = hits.includes(u.head) ? u.head : hits[0];
      cards.push({ primary, others: u.members.filter((m) => m !== primary), unit: u });
    }
  } else {
    for (const m of data.members) if (pred(m)) cards.push({ primary: m, others: [], unit: m.unit });
  }
  cards.sort((a, b) => b.primary.sortKey - a.primary.sortKey || (a.primary.id < b.primary.id ? -1 : 1));
  return cards;
}

/** Tællere pr. valg med de øvrige filtre slået til. Enheden er det, der vises (historie eller indslag). */
export function computeCounts(data, s, now) {
  const out = {};
  for (const g of GROUPS) {
    const pred = makePredicate(s, now, new Set([g]));
    const counts = new Map();
    const bump = (keys) => { for (const k of keys) counts.set(k, (counts.get(k) || 0) + 1); };
    if (s.saml) {
      for (const u of data.units) {
        const keys = new Set();
        for (const m of u.members) if (pred(m)) for (const k of optionKeys(g, m)) keys.add(k);
        bump(keys);
      }
    } else {
      for (const m of data.members) if (pred(m)) bump(optionKeys(g, m));
    }
    out[g] = counts;
  }
  return out;
}

// ── Etiketter ─────────────────────────────────────────────

export function genreName(data, id) {
  if (id === 'nyhed') return 'Nyhed';
  const g = data.genres.get(id);
  return g && g.label ? cap(g.label.toLowerCase()) : cap(id);
}

export function topicName(data, id) {
  if (id === NO_TOPIC) return 'Uden tema';
  return data.topics.get(id)?.name || id;
}

/** Alle aktive filtre som {key, value, label}. */
export function activeFilters(data, s) {
  const out = [];
  for (const v of s.afsender) out.push({ key: 'afsender', value: v, label: data.cats.get(v)?.name || v });
  for (const v of s.tema) out.push({ key: 'tema', value: v, label: topicName(data, v) });
  for (const v of s.kilde) out.push({ key: 'kilde', value: v, label: data.sources.get(v)?.name || v });
  for (const v of s.genre) out.push({ key: 'genre', value: v, label: genreName(data, v) });
  if (s.periode !== 60) out.push({ key: 'periode', value: s.periode, label: `Seneste ${s.periode} dage` });
  if (s.sprog) out.push({ key: 'sprog', value: s.sprog, label: 'Kun dansk' });
  if (s.q) out.push({ key: 'q', value: s.q, label: `Søgning: "${s.q}"` });
  if (s.nye) out.push({ key: 'nye', value: '1', label: 'Kun nye' });
  if (s.story.length) {
    const head = data.units.find((u) => u.id === s.story[0])?.head;
    const more = s.story.length > 1 ? ` +${s.story.length - 1}` : '';
    out.push({ key: 'story', value: s.story.join(','), label: head ? `Historie: ${truncate(head.title, 48)}${more}` : 'Udvalgt historie' });
  }
  return out;
}

/** Fjern ét aktivt filter fra en tilstand (muterer). */
export function removeFilter(s, f) {
  if (GROUPS.includes(f.key)) s[f.key] = s[f.key].filter((v) => v !== f.value);
  else if (f.key === 'periode') s.periode = 60;
  else if (f.key === 'sprog') s.sprog = '';
  else if (f.key === 'q') s.q = '';
  else if (f.key === 'nye') s.nye = false;
  else if (f.key === 'story') s.story = [];
}

// ── Filterpanel ───────────────────────────────────────────

/**
 * Bygger filterpanelet én gang. `update(state, counts)` opdaterer tællere og valg uden
 * at genopbygge felterne, så fokus og scroll bevares.
 * `onChange(mutator)` kaldes ved ændringer; app.js anvender mutatoren på tilstanden.
 */
export function buildPanel(data, state, onChange) {
  let current = state;
  const toggle = (group, value) => onChange((s) => {
    s[group] = s[group].includes(value) ? s[group].filter((v) => v !== value) : [...s[group], value];
  });

  // Søgning
  const searchInput = el('input', {
    type: 'search', id: 'f-q', name: 'q', placeholder: 'Søg i titler og kilder', autocomplete: 'off',
    'aria-keyshortcuts': '/', value: state.q, enterkeyhint: 'search',
  });
  let timer = 0;
  searchInput.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => onChange((s) => { s.q = searchInput.value.trim(); }), 180);
  });
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { clearTimeout(timer); onChange((s) => { s.q = searchInput.value.trim(); }); }
  });

  // Afsender
  const catChips = [...data.cats.values()].map((c) => chip({
    group: 'afsender', value: c.id, label: c.name,
    lead: [el('span', { class: 'dot', 'aria-hidden': 'true' }), icon(c.icon)],
    cls: 'cat', style: catStyle(c), onclick: () => toggle('afsender', c.id),
  }));

  // Tema
  const topicIds = [...data.topics.keys(), NO_TOPIC];
  const topicChips = topicIds.map((id) => chip({
    group: 'tema', value: id, label: topicName(data, id), onclick: () => toggle('tema', id),
  }));

  // Kilder (søgbar liste grupperet pr. kategori)
  const srcFind = el('input', { type: 'search', class: 'src-find', id: 'f-src', placeholder: 'Find kilde', autocomplete: 'off' });
  const srcList = el('div', { class: 'src-list', id: 'f-src-list' });
  const srcRows = [];
  const srcGroups = [];
  for (const c of data.cats.values()) {
    const list = [...data.sources.values()]
      .filter((s) => s.category === c.id)
      .sort((a, b) => a.name.localeCompare(b.name, 'da'));
    if (!list.length) continue;
    const rows = list.map((src) => {
      const input = el('input', { type: 'checkbox', value: src.id, onchange: () => toggle('kilde', src.id) });
      const n = el('span', { class: 'n' });
      const label = el('label', { class: 'src-opt' }, input, el('span', { class: 'name', text: src.name }), n);
      const row = { src, input, n, label, cat: c.id, name: src.name.toLowerCase() };
      srcRows.push(row);
      return label;
    });
    const group = el('div', { class: 'src-group cat', style: catStyle(c), role: 'group', 'aria-label': c.name },
      el('div', { class: 'src-group-title', 'aria-hidden': 'true' }, el('span', { class: 'dot' }), c.short),
      rows);
    srcGroups.push({ cat: c.id, node: group });
    srcList.append(group);
  }
  const srcNone = el('p', { class: 'src-none', hidden: true, text: 'Ingen kilder passer.' });
  srcList.append(srcNone);
  srcFind.addEventListener('input', () => filterSources());

  // Flere filtre
  const genreChips = [...data.genres.keys()].map((id) => chip({
    group: 'genre', value: id, label: genreName(data, id), onclick: () => toggle('genre', id),
  }));
  const periodInputs = PERIODS.map((d) => {
    const input = el('input', { type: 'radio', name: 'periode', value: d, onchange: () => onChange((s) => { s.periode = d; }) });
    return { d, input, label: el('label', null, input, el('span', { text: `${d} dage` })) };
  });
  const cbDa = el('input', { type: 'checkbox', id: 'f-da', onchange: (e) => onChange((s) => { s.sprog = e.target.checked ? 'da' : ''; }) });
  const cbSaml = el('input', { type: 'checkbox', id: 'f-saml', onchange: (e) => onChange((s) => { s.saml = e.target.checked; }) });
  const cbKompakt = el('input', { type: 'checkbox', id: 'f-kompakt', onchange: (e) => onChange((s) => { s.vis = e.target.checked ? 'kompakt' : ''; }) });
  const more = el('details', { class: 'more' },
    el('summary', null, 'Flere filtre', icon('pil-ned')),
    el('fieldset', { class: 'fgroup' }, el('legend', { text: 'Genre' }), el('div', { class: 'chips' }, genreChips.map((c) => c.node))),
    el('fieldset', { class: 'fgroup' }, el('legend', { text: 'Periode' }), el('div', { class: 'seg-radio' }, periodInputs.map((p) => p.label))),
    el('fieldset', { class: 'fgroup' }, el('legend', { text: 'Visning' }),
      el('label', { class: 'check-opt' }, cbDa, 'Kun dansk'),
      el('label', { class: 'check-opt' }, cbSaml, 'Saml historier'),
      el('label', { class: 'check-opt' }, cbKompakt, 'Kompakt visning')),
  );

  const resetBtn = el('button', { type: 'button', class: 'btn panel-reset', onclick: () => onChange((s) => resetFilters(s)) }, 'Nulstil filtre');

  const root = el('search', { class: 'filters', 'aria-labelledby': 'filters-title' },
    el('h2', { id: 'filters-title', text: 'Filtre' }),
    el('div', { class: 'search-field' },
      el('label', { for: 'f-q' }, 'Søg', el('span', { class: 'kbd-hint' }, 'Tast ', el('kbd', { text: '/' }))),
      searchInput),
    el('fieldset', { class: 'fgroup' }, el('legend', { text: 'Afsender' }), el('div', { class: 'chips' }, catChips.map((c) => c.node))),
    el('fieldset', { class: 'fgroup' }, el('legend', { text: 'Tema' }), el('div', { class: 'chips' }, topicChips.map((c) => c.node))),
    el('fieldset', { class: 'fgroup' }, el('legend', { text: 'Kilde' }),
      el('label', { for: 'f-src', class: 'visually-hidden', text: 'Find kilde' }), srcFind, srcList),
    more,
    resetBtn,
  );

  function filterSources() {
    const q = srcFind.value.trim().toLowerCase();
    const cats = new Set(current.afsender);
    let visible = 0;
    for (const r of srcRows) {
      const show = (!cats.size || cats.has(r.cat) || r.input.checked) && (!q || r.name.includes(q));
      r.label.hidden = !show;
      if (show) visible += 1;
    }
    for (const g of srcGroups) g.node.hidden = ![...g.node.querySelectorAll('.src-opt')].some((l) => !l.hidden);
    srcNone.hidden = visible > 0;
  }

  function update(s, counts) {
    current = s;
    if (document.activeElement !== searchInput && searchInput.value.trim() !== s.q) searchInput.value = s.q;
    for (const c of [...catChips, ...topicChips, ...genreChips]) c.update(s, counts[c.group]);
    for (const r of srcRows) {
      const n = counts.kilde.get(r.src.id) || 0;
      r.input.checked = s.kilde.includes(r.src.id);
      r.n.textContent = `(${fmtNum(n)})`;
      r.label.classList.toggle('is-zero', n === 0);
    }
    for (const p of periodInputs) p.input.checked = s.periode === p.d;
    cbDa.checked = s.sprog === 'da';
    cbSaml.checked = s.saml;
    cbKompakt.checked = s.vis === 'kompakt';
    if (s.genre.length || s.periode !== 60 || s.sprog || !s.saml || s.vis) more.open = true;
    resetBtn.hidden = activeCount(s) === 0;
    filterSources();
  }

  return { root, update, searchInput };
}

function chip({ group, value, label, lead = null, cls = '', style = null, onclick }) {
  const n = el('span', { class: 'n' });
  // Fluebenet gør, at et valg ikke kun vises med farve
  const node = el('button', { type: 'button', class: `chip ${cls}`.trim(), style, 'aria-pressed': 'false', onclick },
    el('span', { class: 'check', 'aria-hidden': 'true', text: '✓' }), lead, el('span', { class: 'label', text: label }), n);
  return {
    group, node,
    update(s, counts) {
      const count = counts.get(value) || 0;
      const on = s[group].includes(value);
      node.setAttribute('aria-pressed', on ? 'true' : 'false');
      n.textContent = fmtNum(count);
      node.classList.toggle('is-zero', count === 0);
    },
  };
}

/** Aktive filter-chips med × over listen. */
export function renderActive(container, data, s, onChange) {
  const list = activeFilters(data, s);
  const prevIndex = [...container.querySelectorAll('button')].indexOf(document.activeElement);
  container.replaceChildren(...list.map((f) => el('li', null,
    el('button', {
      type: 'button', class: 'active-chip', 'aria-label': `Fjern filter ${f.label}`,
      onclick: () => onChange((st) => removeFilter(st, f)),
    }, el('span', { class: 'label', text: f.label }), el('span', { class: 'x', 'aria-hidden': 'true' }, icon('luk'))))));
  container.hidden = list.length === 0;
  // Bevar fokus i rækken, når en chip fjernes
  if (prevIndex >= 0) {
    const btns = container.querySelectorAll('button');
    if (btns.length) { btns[Math.min(prevIndex, btns.length - 1)].focus(); return false; }
    return true; // fokus mistet; app.js flytter det
  }
  return false;
}
