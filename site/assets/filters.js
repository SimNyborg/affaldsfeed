// Affaldsfeed: hjælpere, URL-tilstand, filtrering, tællere og filterpanel.
// Ingen afhængigheder. Bruges af app.js, overview.js og combobox.js.

import { createCombobox } from './combobox.js';

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

const cphCache = new Map();

/**
 * Kalenderdele for et tidspunkt i København. dayNum = dage siden 1970-01-01 (lokal dato).
 * formatToParts er dyr, så resultatet gemmes pr. tidsstempel (og fryses, da det deles).
 */
export function cph(date) {
  const t = +date;
  const hit = cphCache.get(t);
  if (hit) return hit;
  const p = {};
  for (const { type, value } of partsFmt.formatToParts(date)) p[type] = value;
  const y = +p.year, m = +p.month, d = +p.day;
  const hh = p.hour === '24' ? '00' : p.hour;
  const c = Object.freeze({ y, m, d, hh, mm: p.minute, key: `${p.year}-${p.month}-${p.day}`, dayNum: Date.UTC(y, m - 1, d) / DAY_MS });
  if (cphCache.size > 20000) cphCache.clear();
  cphCache.set(t, c);
  return c;
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
// Hårde mellemrum (NBSP), så "5. okt." og "kl. 14.17" aldrig brydes over to linjer
const NB = '\u00A0';
export const fmtShort = (c) => `${c.d}.${NB}${MONTHS_SHORT[c.m - 1]}`;
export const fmtLong = (c) => `${c.d}.${NB}${MONTHS[c.m - 1]}`;
export const fmtLongYear = (c) => `${c.d}.${NB}${MONTHS[c.m - 1]} ${c.y}`;

/** "i dag kl. 08.14", "i går kl. 08.14", "tirsdag kl. 14.32" eller "5. okt. kl. 14.32". */
export function fmtWhen(date, now) {
  const c = cph(date);
  const diff = cph(now).dayNum - c.dayNum;
  const clock = `kl.${NB}${c.hh}.${c.mm}`;
  if (diff <= 0) return `i dag ${clock}`;
  if (diff === 1) return `i går ${clock}`;
  if (diff < 7) return `${weekdayOf(c)} ${clock}`;
  return `${fmtShort(c)} ${clock}`;
}

/** "kl. 14.17" i dag, ellers "6. okt. kl. 14.17". */
export function fmtStamp(date, now) {
  const c = cph(date);
  const clock = `kl.${NB}${c.hh}.${c.mm}`;
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

/** "28.–30. september", "29. september–3. oktober" eller "28. september". */
export function fmtDayRange(fromNum, toNum) {
  const a = new Date(fromNum * DAY_MS);
  const b = new Date(toNum * DAY_MS);
  const am = a.getUTCMonth(), bm = b.getUTCMonth();
  if (fromNum >= toNum) return `${b.getUTCDate()}.${NB}${MONTHS[bm]}`;
  if (am === bm) return `${a.getUTCDate()}.–${b.getUTCDate()}.${NB}${MONTHS[bm]}`;
  return `${a.getUTCDate()}.${NB}${MONTHS[am]}–${b.getUTCDate()}.${NB}${MONTHS[bm]}`;
}

/**
 * Søgenøgler til forslag og søgning: små bogstaver uden accenter, og andre tegn end bogstaver og tal
 * bliver mellemrum. To nøgler: å→aa, æ→ae, ø→oe og å→a, æ→ae, ø→o, så "århus" finder "Aarhus".
 */
export function foldKeys(text) {
  const s = String(text || '').normalize('NFC').toLowerCase();
  const fold = (t) => t.normalize('NFD').replace(/\p{M}/gu, '').replace(/[^a-z0-9]+/g, ' ').trim();
  const a = fold(s.replace(/å/g, 'aa').replace(/æ/g, 'ae').replace(/ø/g, 'oe'));
  const b = fold(s.replace(/å/g, 'a').replace(/æ/g, 'ae').replace(/ø/g, 'o'));
  return a === b ? [a] : [a, b];
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

/**
 * Tegnsætning kun til skærmlæsere. Står inline med nul bredde og højde, så navnet bliver
 * "Kommunal, 6 indslag" (en skjult span med position: absolute giver "Kommunal , 6 indslag").
 */
export const srPunct = (text = ',') => el('span', { class: 'sr-punct', text });

/**
 * Skilletegn: skjult komma, NBSP, "·" og mellemrum. Kommaet giver en pause i skærmlæseren,
 * og NBSP binder "·" til ordet før, så en brudt linje aldrig begynder med "·".
 */
export const sep = () => [srPunct(), '\u00A0', el('span', { class: 'sep', 'aria-hidden': 'true', text: '·' }), ' '];

/** Kategorifarver som custom properties (lys/mørk). */
export const catStyle = (cat) => `--cl:${cat.color};--cd:${cat.color_dark}`;

/** Kort navn til kildelinks: "European Environmental Bureau (EEB)" → "EEB". */
export function shortName(name) {
  const m = /^(.*?)\s*\(([^)]+)\)\s*$/.exec(name || '');
  if (!m) return name;
  return m[2].length <= 6 && m[2] === m[2].toUpperCase() ? m[2] : m[1];
}

/**
 * Tekstvalg: radioknapper vist som ord på række (style.css .seg). Med `legend` bliver det en fieldset
 * med skjult legend; uden er det en div i en gruppe, der selv har en legend.
 */
export function segmented({ name, legend = null, options, value, onSelect, cls = '' }) {
  const inputs = new Map();
  const labels = options.map((opt) => {
    const input = el('input', { type: 'radio', name, value: String(opt.value), onchange: () => onSelect(opt.value) });
    inputs.set(String(opt.value), input);
    return el('label', null, input, el('span', { text: opt.label }));
  });
  const root = legend
    ? el('fieldset', { class: `seg ${cls}`.trim() }, el('legend', { class: 'visually-hidden', text: legend }), labels)
    : el('div', { class: `seg ${cls}`.trim() }, labels);
  const set = (v) => { for (const [k, input] of inputs) input.checked = k === String(v); };
  set(value);
  return { root, set };
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

// Afkrydsningslister: alt er valgt fra start, og et fjernet flueben skjuler. I URL'en står de valgte
// (fx tema=gebyrer) eller med "-" foran de fravalgte (fx tema=-arbejdsmiljoe), alt efter hvad der er kortest.
export const GROUPS = ['afsender', 'tema', 'kilde', 'genre'];
export const PERIODS = [7, 30, 60];
export const OV_PERIODS = ['dag', 'uge', 'maaned', 'aar'];
export const NO_TOPIC = 'uden';
// Steder: ét felt `sted` med præfiksede nøgler internt (r:, k:, b: og l: for landsdækkende), fire
// parametre i URL'en. Uden `geo` i feed.json læses de og skrives uændret tilbage, men filtrerer ikke.
export const NATIONAL = 'l:landsdaekkende';
const PLACE_PARAMS = [['region', 'r'], ['kommune', 'k'], ['by', 'b']];
const MAX_CHIPS = 3; // højst så mange mærker pr. gruppe og retning, ellers ét samlet ("Uden 5 kilder")

export function defaultState() {
  return {
    afsender: [], tema: [], kilde: [], genre: [], sted: [],
    periode: 60, q: '', nye: false, vis: '',
    story: [], overblik: 'dag', demo: '',
  };
}

export function readState(search) {
  const p = new URLSearchParams(search);
  const list = (k) => [...new Set((p.get(k) || '').split(',').map((s) => s.trim()).filter(Boolean))];
  const s = defaultState();
  for (const g of GROUPS) s[g] = list(g);
  // Ældre links: uden=<kilder> er fravalgte kilder
  for (const v of list('uden')) if (!s.kilde.includes(`-${v}`)) s.kilde.push(`-${v}`);
  s.sted = PLACE_PARAMS.flatMap(([k, pre]) => list(k).map((v) => (v.startsWith('-') ? `-${pre}:${v.slice(1)}` : `${pre}:${v}`)));
  const land = p.get('landsdaekkende');
  if (land === '1') s.sted.push(NATIONAL);
  else if (land === '0') s.sted.push(`-${NATIONAL}`);
  const per = Number(p.get('periode'));
  s.periode = PERIODS.includes(per) ? per : 60;
  s.q = (p.get('q') || '').trim();
  s.nye = p.get('nye') === '1';
  // sprog= og saml= fra ældre links ignoreres; historierne er altid samlet
  s.vis = p.get('vis') === 'kompakt' ? 'kompakt' : '';
  s.story = list('story');
  s.overblik = OV_PERIODS.includes(p.get('overblik')) ? p.get('overblik') : 'dag';
  s.demo = p.get('demo') || '';
  return s;
}

// Konfigurationens rækkefølge (så samme valg altid giver samme link), alle mulige valg pr. gruppe og
// om stedfiltret er aktivt
let ORDER = {};
let UNIVERSE = {};
let GEO = false;
export function setData(data) {
  const idx = (ids) => new Map(ids.map((id, i) => [id, i]));
  UNIVERSE = {
    afsender: [...data.cats.keys()],
    tema: [...data.topics.keys(), NO_TOPIC],
    kilde: [...data.sources.keys()].sort(),
    genre: [...data.genres.keys()],
    sted: data.geo ? [...data.geo.regioner.map((r) => `r:${r.id}`), NATIONAL] : [],
  };
  ORDER = Object.fromEntries(Object.entries(UNIVERSE).map(([g, ids]) => [g, idx(ids)]));
  GEO = !!data.geo;
}

/** Valg ("-" foran = fravalgt) i konfigurationens rækkefølge, ukendte til sidst efter id. */
function canonical(values, order) {
  const id = (v) => v.replace(/^-/, '');
  const known = values.filter((v) => order?.has(id(v))).sort((a, b) => order.get(id(a)) - order.get(id(b)));
  return [...known, ...values.filter((v) => !order?.has(id(v))).sort((a, b) => (id(a) < id(b) ? -1 : id(a) > id(b) ? 1 : 0))];
}

/** De viste nøgler i en gruppe (også 'sted'), eller null når alt vises. */
export function shownSet(s, g) {
  const vals = s[g];
  if (!vals.length) return null;
  const exc = new Set(vals.filter((v) => v.startsWith('-')).map((v) => v.slice(1)));
  const inc = vals.filter((v) => !v.startsWith('-'));
  return new Set((inc.length ? inc : UNIVERSE[g] || []).filter((k) => !exc.has(k)));
}

export function isShown(s, g, key) {
  const set = shownSet(s, g);
  return !set || set.has(key);
}

/** Den korteste form af et sæt viste nøgler: [] = alt, ellers de valgte eller "-" + de fravalgte. */
function encodeShown(g, shown) {
  const all = UNIVERSE[g] || [];
  const extra = [...shown].filter((k) => !all.includes(k)); // fx valgte kommuner og byer under Sted
  const on = all.filter((k) => shown.has(k));
  if (on.length === all.length) return [];
  if (!extra.length && (!on.length || on.length > all.length - on.length)) return all.filter((k) => !shown.has(k)).map((k) => `-${k}`);
  return [...extra, ...on];
}

/** Flueben sat eller fjernet ved ét valg. */
export function toggleShown(s, g, key) {
  const cur = shownSet(s, g) || new Set(UNIVERSE[g]);
  if (cur.has(key)) cur.delete(key);
  else cur.add(key);
  s[g] = encodeShown(g, cur);
}

/** "Vælg alle" og "Fravælg alle". */
export function setAllShown(s, g, on) {
  s[g] = on ? [] : (UNIVERSE[g] || []).map((k) => `-${k}`);
}

/** Er alt i gruppen valgt? Så hedder gruppens knap "Fravælg alle", ellers "Vælg alle". */
export function allShown(s, g) {
  const set = shownSet(s, g);
  return !set || (UNIVERSE[g] || []).every((k) => set.has(k));
}

/**
 * En kommune eller by fra Steds søgefelt viser kun de valgte steder: det første sted erstatter
 * regionerne og "Landsdækkende", de næste lægges til, og et valgt sted fravælges. Regionerne og
 * "Landsdækkende" kan derefter sættes til igen med deres flueben.
 */
export function pickPlace(s, key) {
  const cur = shownSet(s, 'sted');
  const picks = cur ? [...cur].filter((k) => /^[kb]:/.test(k)) : [];
  if (!picks.length) { s.sted = [key]; return; }
  if (cur.has(key)) cur.delete(key);
  else cur.add(key);
  s.sted = encodeShown('sted', cur);
}

const enc = (v) => encodeURIComponent(v).replace(/%2C/gi, ',');

/** Rækkefølge: demo, afsender, tema, kilde, genre, region, kommune, by, landsdaekkende, periode, q, nye, vis, story, overblik. */
export function writeState(s) {
  const out = [];
  const add = (k, v) => out.push(`${k}=${enc(v)}`);
  const addList = (k, values) => { if (values.length) add(k, values.join(',')); };
  if (s.demo) add('demo', s.demo);
  for (const g of ['afsender', 'tema', 'kilde', 'genre']) addList(g, canonical(s[g], ORDER[g]));
  for (const [k, pre] of PLACE_PARAMS) {
    const vals = s.sted.filter((v) => v.replace(/^-/, '').startsWith(`${pre}:`))
      .map((v) => (v.startsWith('-') ? `-${v.slice(3)}` : v.slice(2)));
    // Uden geo skrives værdierne tilbage, præcis som de blev læst (samme rækkefølge)
    const order = pre === 'r' && GEO ? new Map([...ORDER.sted].filter(([key]) => key.startsWith('r:')).map(([key, i]) => [key.slice(2), i])) : null;
    addList(k, GEO ? canonical(vals, order) : vals);
  }
  if (s.sted.includes(NATIONAL)) add('landsdaekkende', '1');
  else if (s.sted.includes(`-${NATIONAL}`)) add('landsdaekkende', '0');
  if (s.periode !== 60) add('periode', s.periode);
  if (s.q) add('q', s.q);
  if (s.nye) add('nye', '1');
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

/** Antal mærker, en gruppe giver: højst 3 pr. retning (valgte og fravalgte), ellers ét samlet. */
function chipCount(values) {
  const exc = values.filter((v) => v.startsWith('-')).length;
  const inc = values.length - exc;
  return (inc > MAX_CHIPS ? 1 : inc) + (exc > MAX_CHIPS ? 1 : exc);
}
const groupsCount = (s) => GROUPS.reduce((n, g) => n + chipCount(s[g]), GEO ? chipCount(s.sted) : 0);

/** Er der noget, der indsnævrer feedet? (vis er en visning og tæller ikke) */
export function activeCount(s) {
  let n = groupsCount(s);
  if (s.periode !== 60) n += 1;
  if (s.q) n += 1;
  if (s.nye) n += 1;
  if (s.story.length) n += 1;
  return n;
}

/** Tallet på "Filtrér (n)": valg inde i arket. Søgning og periode tæller ikke, fordi de står over listen. */
export function sheetCount(s) {
  return groupsCount(s);
}

/** Nulstil: beholder vis og overblik (og steder, når feedet ikke har geo). */
export function resetFilters(s) {
  if (GEO) s.sted = [];
  for (const g of GROUPS) s[g] = [];
  s.periode = 60;
  s.q = '';
  s.nye = false;
  s.story = [];
}

// ── Data: indslag og historier ─────────────────────────────

const UNKNOWN_CAT = { id: 'ukendt', name: 'Ukendt afsender', short: 'Ukendt', color: '#565656', color_dark: '#A9B3AE', icon: 'avis', help: '' };

/**
 * `geo` fra feed.json som opslag pr. præfiks (r, k, b), eller null, så Sted ikke vises.
 * `dup` tæller bynavne, så to byer med samme navn kan skelnes: "Ejby (Køge)".
 */
function readGeo(geo) {
  if (!geo || !Array.isArray(geo.regioner) || !Array.isArray(geo.kommuner)) return null;
  const byer = Array.isArray(geo.byer) ? geo.byer : [];
  const dup = new Map();
  for (const b of byer) dup.set(b.navn, (dup.get(b.navn) || 0) + 1);
  const map = (list) => new Map(list.map((x) => [x.id, x]));
  return { regioner: geo.regioner, kommuner: geo.kommuner, byer, r: map(geo.regioner), k: map(geo.kommuner), b: map(byer), dup };
}

/**
 * Udvidet nøglesæt E: r:X giver r:X; k:Y giver k:Y og dens region; b:Z giver b:Z, byens primære
 * kommune (geo.byer[].kommune) og dennes region. En by tæller ikke under de øvrige kommuner i
 * `kommuner`. Ukendte id'er giver kun sig selv.
 */
function expandPlaces(geo, places) {
  const out = new Set(places);
  const addK = (id) => {
    out.add(`k:${id}`);
    const k = geo.k.get(id);
    if (k) out.add(`r:${k.region}`);
  };
  for (const p of places) {
    const id = p.slice(2);
    if (p.startsWith('k:') && geo.k.has(id)) addK(id);
    else if (p.startsWith('b:')) {
      const primary = geo.b.get(id)?.kommune;
      if (primary) addK(primary);
    }
  }
  return [...out];
}

/**
 * Gør feed.json klar til visning. Hvert indslag (også dem i `also`) bliver et "medlem",
 * og hvert hovedindslag med sine also-medlemmer bliver en "historie" (unit).
 */
export function prepare(feed, lastVisit) {
  const cats = new Map((feed.categories || []).map((c) => [c.id, c]));
  const sources = new Map((feed.sources || []).map((s) => [s.id, s]));
  const topics = new Map((feed.topics || []).map((t) => [t.id, t]));
  const genres = new Map((feed.genres || []).map((g) => [g.id, g]));
  const geo = readGeo(feed.geo);
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
      places: Array.isArray(it.places) ? it.places : [],
    });
    head.placeKeys = geo ? expandPlaces(geo, head.places) : [];
    unit.head = head;
    unit.members.push(head);
    for (const a of it.also || []) {
      const asrc = sourceOf(a.source);
      const m = finish({
        id: a.id, url: a.url, title: a.title, teaser: '', source: asrc, sourceId: asrc.id,
        published: parseDate(a.published) || head.published, firstSeen: null, dateQuality: 'kilde',
        baseline: head.baseline, topics: head.topics, genre: 'nyhed', lang: asrc.lang || 'da',
        summary: '', reviewed: head.reviewed, isHead: false, unit, places: head.places,
      });
      m.placeKeys = head.placeKeys; // also-indslag arver hovedindslagets steder
      unit.members.push(m);
    }
    units.push(unit);
  }
  return { feed, cats, sources, topics, genres, geo, units, members, byId };
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
  if (group === 'sted') return m.placeKeys.length ? m.placeKeys : [NATIONAL];
  if (group === 'afsender') return [m.catId];
  if (group === 'kilde') return [m.sourceId];
  if (group === 'genre') return [m.genre];
  return m.topics.length ? m.topics : [NO_TOPIC];
}

/** Prædikat for ét indslag. `skip` er grupper, der ses bort fra (til tællere). */
export function makePredicate(s, now, skip = new Set()) {
  const sets = GROUPS.map((g) => [g, skip.has(g) ? null : shownSet(s, g)]).filter(([, set]) => set);
  // Steder: indslaget passer, når dets steder (udvidet med kommune og region) eller "landsdækkende" er valgt
  const places = GEO && !skip.has('sted') ? shownSet(s, 'sted') : null;
  const minTime = now.getTime() - s.periode * DAY_MS;
  // Søgeord foldes som i forslagene (accenter, å/aa, æ/ae, ø/oe). Ord uden bogstaver og tal søges råt.
  const words = s.q.toLowerCase().split(/\s+/).filter(Boolean).map((raw) => ({ raw, keys: foldKeys(raw).filter(Boolean) }));
  const hasWord = (m, w) => {
    if (!w.keys.length) return m.text.includes(w.raw);
    m.fold ||= foldKeys(m.text); // første søgning folder teksten; resten genbruger den
    return w.keys.some((k) => m.fold.some((t) => t.includes(k)));
  };
  const stories = new Set(s.story);
  return (m) => {
    for (const [g, set] of sets) if (!optionKeys(g, m).some((k) => set.has(k))) return false;
    if (places && !optionKeys('sted', m).some((k) => places.has(k))) return false;
    if (m.time < minTime) return false;
    if (s.nye && !skip.has('nye') && !m.isNew) return false;
    if (stories.size && !stories.has(m.unit.id)) return false;
    if (words.length && !words.every((w) => hasWord(m, w))) return false;
    return true;
  };
}

/**
 * Kort til visning. Filtrene virker på enkelte indslag; samlingen i historier sker bagefter.
 * Historien vises med det første matchende medlem (helst hovedindslaget) øverst og resten under
 * "+N andre kilder". Et kort er nyt (`isNew`), når et af dets indslag, der passer på filtrene,
 * er nyt. Det er samme regel som "Vis N nye", så tal og markeringer stemmer.
 */
export function applyFilters(data, s, now, skip) {
  const pred = makePredicate(s, now, skip);
  const cards = [];
  for (const u of data.units) {
    const hits = u.members.filter(pred);
    if (!hits.length) continue;
    const primary = hits.includes(u.head) ? u.head : hits[0];
    cards.push({ primary, others: u.members.filter((m) => m !== primary), unit: u, isNew: hits.some((m) => m.isNew) });
  }
  cards.sort((a, b) => b.primary.sortKey - a.primary.sortKey || (a.primary.id < b.primary.id ? -1 : 1));
  return cards;
}

/** Tællere pr. valg med de øvrige filtre slået til. Enheden er det, der vises: historien. */
export function computeCounts(data, s, now) {
  const out = {};
  for (const g of data.geo ? ['sted', ...GROUPS] : GROUPS) {
    const pred = makePredicate(s, now, new Set([g]));
    const counts = new Map();
    for (const u of data.units) {
      const keys = new Set();
      for (const m of u.members) if (pred(m)) for (const k of optionKeys(g, m)) keys.add(k);
      for (const k of keys) counts.set(k, (counts.get(k) || 0) + 1);
    }
    out[g] = counts;
  }
  return out;
}

// ── Navne ─────────────────────────────────────────────────
// Panel, kort og aktive filtre bruger de samme korte navne.

export function catName(data, id) {
  const c = data.cats.get(id);
  return c ? c.short || c.name : id;
}

export function genreName(data, id) {
  if (id === 'nyhed') return 'Nyhed';
  const g = data.genres.get(id);
  return g && g.label ? cap(g.label.toLowerCase()) : cap(id);
}

/** Kort temanavn: `short`, ellers `name` (feltet `short` er valgfrit i feed.json). */
export function topicName(data, id) {
  if (id === NO_TOPIC) return 'Uden tema';
  const t = data.topics.get(id);
  return t ? t.short || t.name : id;
}

// ── Steder ────────────────────────────────────────────────

/** Stedets navn fra geo: "Region Syddanmark", "Nyborg Kommune", "Ullerslev". Ukendte id'er vises som id'et. */
export function placeName(data, key) {
  const geo = data.geo;
  const x = geo?.[key[0]]?.get(key.slice(2));
  if (!x) return key.slice(2);
  // To byer med samme navn får kommunens korte navn i parentes: "Ejby (Køge)"
  if (key[0] === 'b' && geo.dup.get(x.navn) > 1) return `${x.navn} (${geo.k.get(x.kommune)?.kort || x.kommune})`;
  return x.navn;
}

/** Til skærmlæser: "i Region Syddanmark" for en kommune og "by i Nyborg Kommune" for en by. */
export function placeContext(data, key) {
  const geo = data.geo;
  const x = geo?.[key[0]]?.get(key.slice(2));
  if (!x || key[0] === 'r') return '';
  if (key[0] === 'k') return `i ${geo.r.get(x.region)?.navn || x.region}`;
  return `by i ${geo.k.get(x.kommune)?.navn || x.kommune}`;
}

/**
 * De mest præcise steder på et indslag (til kortet): en region udelades, når en kommune i den eller en
 * by, hvis primære kommune ligger i den, står der; en kommune udelades, når den er primær kommune for
 * en by på indslaget. Id'er, der ikke er i geo, vises ikke.
 */
export function precisePlaces(data, places) {
  const geo = data.geo;
  if (!geo) return [];
  const known = places.filter((p) => geo[p[0]]?.has(p.slice(2)));
  const regionOf = (k) => geo.k.get(k)?.region;
  const townK = (p) => (p.startsWith('b:') ? geo.b.get(p.slice(2)).kommune : null);
  return known.filter((p) => {
    const id = p.slice(2);
    if (p.startsWith('r:')) return !known.some((q) => (q.startsWith('k:') && regionOf(q.slice(2)) === id) || (townK(q) && regionOf(townK(q)) === id));
    if (p.startsWith('k:')) return !known.some((q) => townK(q) === id);
    return true;
  });
}

/** Forældre til et sted, nærmeste først: by → primær kommune → region; kommune → region. */
export function placeParents(data, key) {
  const geo = data.geo;
  const id = key.slice(2);
  if (key.startsWith('b:')) {
    const b = geo?.b.get(id);
    const k = b && geo.k.get(b.kommune);
    return b ? [`k:${b.kommune}`, ...(k ? [`r:${k.region}`] : [])] : [];
  }
  const k = key.startsWith('k:') ? geo?.k.get(id) : null;
  return k ? [`r:${k.region}`] : [];
}

// ── Aktive filtre ─────────────────────────────────────────

// Navne i mærkerne: ental og flertal
const NOUNS = {
  sted: ['sted', 'steder'], afsender: ['afsendertype', 'afsendertyper'], tema: ['tema', 'temaer'],
  kilde: ['kilde', 'kilder'], genre: ['genre', 'genrer'],
};

/** Navnet på et valg i en gruppe, som panelet og mærkerne viser det. */
export function optionName(data, g, key) {
  if (g === 'sted') return key === NATIONAL ? 'Landsdækkende' : placeName(data, key);
  if (g === 'afsender') return catName(data, key);
  if (g === 'tema') return topicName(data, key);
  if (g === 'kilde') return data.sources.get(key)?.name || key;
  return genreName(data, key);
}

/** Mærker for én gruppe: de valgte og de fravalgte, højst 3 af hver, ellers ét samlet mærke. */
function groupChips(data, s, g) {
  const out = [];
  const name = (k) => optionName(data, g, k);
  const [, many] = NOUNS[g];
  const vals = g === 'sted' ? s.sted : canonical(s[g], ORDER[g]);
  const inc = vals.filter((v) => !v.startsWith('-'));
  const exc = vals.filter((v) => v.startsWith('-')).map((v) => v.slice(1));
  if (inc.length > MAX_CHIPS) out.push({ key: g, value: '+', label: `${fmtNum(inc.length)} ${many}`, undo: `Vis alle ${many}` });
  else for (const v of inc) out.push({ key: g, value: v, label: name(v) });
  if (exc.length > MAX_CHIPS) out.push({ key: g, value: '-', label: `Uden ${fmtNum(exc.length)} ${many}`, undo: `Vis alle ${many}` });
  else for (const v of exc) out.push({ key: g, value: `-${v}`, label: `Uden ${name(v)}`, undo: `Vis ${name(v)} igen` });
  return out;
}

/** Aktive filtre som {key, value, label, undo?} i panelets rækkefølge. Søgning og "Kun nye" får intet mærke. */
export function activeFilters(data, s) {
  const out = [];
  if (GEO) out.push(...groupChips(data, s, 'sted'));
  for (const g of GROUPS) out.push(...groupChips(data, s, g));
  if (s.story.length) {
    const head = data.units.find((u) => u.id === s.story[0])?.head;
    const more = s.story.length > 1 ? ` +${s.story.length - 1}` : '';
    out.push({ key: 'story', value: s.story.join(','), label: head ? `Historie: ${truncate(head.title, 48)}${more}` : 'Historie' });
  }
  return out;
}

/** Fjern ét filter fra en tilstand (muterer). "+" og "-" er de samlede mærker for valgte og fravalgte. */
export function removeFilter(s, f) {
  if (GROUPS.includes(f.key) || f.key === 'sted') {
    if (f.value === '+') s[f.key] = s[f.key].filter((v) => v.startsWith('-'));
    else if (f.value === '-') s[f.key] = s[f.key].filter((v) => !v.startsWith('-'));
    else s[f.key] = s[f.key].filter((v) => v !== f.value);
  } else if (f.key === 'periode') s.periode = 60;
  else if (f.key === 'q') s.q = '';
  else if (f.key === 'nye') s.nye = false;
  else if (f.key === 'story') s.story = [];
}

// ── Filterpanel ───────────────────────────────────────────

const MAX_OFF_ROWS = 6; // fravalgte rækker, der bliver stående

/**
 * Filterrække: ægte afkrydsning, evt. ikon, navn på én linje og tallet i en fast kolonne.
 * Skærmlæseren hører fx "Nyborg Kommune, i Region Syddanmark, 12 indslag" (`sr` er den skjulte kontekst).
 */
function frow({ name, title = null, iconName, style = null, onchange, sr = '' }) {
  const input = el('input', { type: 'checkbox', onchange });
  const num = document.createTextNode('');
  const withIcon = iconName !== undefined;
  const label = el('label', { class: `frow${withIcon ? ' has-icon' : ''}${style ? ' cat' : ''}`, style, title },
    input,
    withIcon ? (iconName ? icon(iconName) : el('span', { class: 'i' })) : null,
    // Kommaet står inline lige efter navnet, så navnet bliver "Kommunal, 6 indslag" uden mellemrum før kommaet
    el('span', { class: 'name' }, name, srPunct(), sr ? hidden(` ${sr},`) : null),
    el('span', { class: 'n' }, num, hidden(' indslag')));
  return {
    label, input,
    set(on, n = 0) {
      input.checked = on;
      num.data = fmtNum(n);
      label.classList.toggle('is-zero', n === 0);
    },
  };
}

/**
 * Valgte kommuner og byer under Steds søgefelt i den rækkefølge, de blev valgt; ved indlæsning i URL'ens
 * rækkefølge. En fravalgt række bliver stående uden flueben resten af besøget, så et fejlklik kan
 * fortrydes. Højst 6 fravalgte rækker; den ældste forsvinder først. Vises alt (intet sted valgt), er
 * der ingen rækker, fordi et valgt sted altid indsnævrer.
 */
function pickedRows(picks, isOn, makeRow) {
  const made = new Map();
  const shown = [];
  const off = [];
  const box = el('div', { class: 'opts' });
  const rowOf = (key) => {
    if (!made.has(key)) made.set(key, makeRow(key));
    return made.get(key);
  };
  function sync(s, counts, all) {
    if (all) { shown.length = 0; off.length = 0; }
    for (const key of picks(s)) if (!shown.includes(key)) shown.push(key);
    for (const key of shown) {
      const on = isOn(s, key);
      const i = off.indexOf(key);
      if (!on && i < 0) off.push(key);
      if (on && i >= 0) off.splice(i, 1);
    }
    while (off.length > MAX_OFF_ROWS) shown.splice(shown.indexOf(off.shift()), 1);
    // Kun beskårne rækker fjernes og kun nye sættes ind. De øvrige bliver i DOM'en, så fokus bliver,
    // hvor det var, også når en ældre fravalgt række forsvinder
    const nodes = shown.map((key) => rowOf(key).label);
    for (const child of [...box.children]) if (!nodes.includes(child)) child.remove();
    nodes.forEach((n, i) => { if (box.children[i] !== n) box.insertBefore(n, box.children[i] || null); });
    for (const key of shown) rowOf(key).set(isOn(s, key), counts.get(key) || 0);
  }
  return { box, sync };
}

/** Sammenfoldelig gruppe: navnet og en kort status i <summary>, indholdet nedenunder. */
function foldGroup(name, ...body) {
  const status = el('span', { class: 'fg-state' });
  const root = el('details', { class: 'fg' },
    el('summary', null, el('span', { class: 'fg-name' }, name, srPunct()), status, icon('pil-ned')),
    el('div', { class: 'fg-body' }, body));
  return { root, status };
}

/** Afkrydsningsliste. Legend er skjult, fordi gruppens navn står i <summary> lige over. */
const fset = (legend, ...rows) => el('fieldset', { class: 'fset' }, el('legend', { class: 'visually-hidden', text: legend }), rows);

/**
 * Bygger filterpanelet én gang. `update(state, counts)` opdaterer tal, flueben og status uden at
 * genopbygge noget, så fokus, fold og scroll bevares. `onChange(mutator)` anvender en ændring.
 *
 * Hver gruppe er foldet sammen fra start (åben, hvis den har et valg) og viser sin status ("Alle",
 * "5 af 8"). I alle lister er alt valgt fra start, og et fjernet flueben skjuler (KONTRAKTER §9).
 */
export function buildPanel(data, state, onChange, { onReset } = {}) {
  let cur = state;
  let counts = null;
  const rows = []; // { g, key, row }
  const groups = []; // { fg, text(s), active(s) }
  const addRow = (g, key, opts) => {
    const row = frow({ ...opts, onchange: () => onChange((s) => toggleShown(s, g, key)) });
    rows.push({ g, key, row });
    return row.label;
  };
  // Én knap pr. gruppe: "Fravælg alle", når alt er valgt, ellers "Vælg alle". update() sætter teksten.
  const toggles = []; // { g, btn }
  const tools = (g) => {
    const btn = el('button', { type: 'button', class: 'btn-text', onclick: () => onChange((s) => setAllShown(s, g, !allShown(s, g))) }, 'Fravælg alle');
    toggles.push({ g, btn });
    return el('p', { class: 'fg-tools' }, btn);
  };
  /** "Alle", "Ingen", op til to navne eller "5 af 8" ("3 steder", når kommuner eller byer er valgt). */
  const statusOf = (g) => (s) => {
    const set = shownSet(s, g);
    if (!set) return 'Alle';
    const all = UNIVERSE[g];
    const extra = [...set].filter((k) => !all.includes(k));
    const on = [...extra, ...all.filter((k) => set.has(k))];
    if (!on.length) return 'Ingen';
    if (on.length <= 2) return on.map((k) => optionName(data, g, k)).join(', ');
    return extra.length ? `${fmtNum(on.length)} ${NOUNS[g][1]}` : `${fmtNum(on.length)} af ${fmtNum(all.length)}`;
  };
  const addGroup = (fg, text, active) => { groups.push({ fg, text, active }); return fg; };

  // Sted (kun når feedet har geo): søgefelt, valgte kommuner og byer, regionerne og "Landsdækkende"
  let sted = null;
  if (data.geo) {
    const geo = data.geo;
    const regionRows = geo.regioner.map((r) => addRow('sted', `r:${r.id}`, { name: placeName(data, `r:${r.id}`) }));
    const nationalRow = addRow('sted', NATIONAL, { name: 'Landsdækkende' });
    const isPick = (s, key) => !!shownSet(s, 'sted')?.has(key);
    const picked = pickedRows((s) => s.sted.filter((v) => /^[kb]:/.test(v)), isPick, (key) => frow({
      name: placeName(data, key), sr: placeContext(data, key), onchange: () => onChange((s) => pickPlace(s, key)),
    }));
    const kort = (id) => geo.k.get(id)?.kort || id;
    const cbx = createCombobox({
      id: 'f-sted', label: 'Find kommune eller by', placeholder: 'Kommune eller by', fieldIcon: 'sted', listLabel: 'Steder',
      // Type: kommune, by, region (bruges ved lige rang)
      // Kun kommuner og byer; regionerne står som rækker under feltet
      items: [
        ...geo.kommuner.map((k) => ({ key: `k:${k.id}`, name: k.navn, order: 0 })),
        ...geo.byer.map((b) => ({ key: `b:${b.id}`, name: placeName(data, `b:${b.id}`), ctx: `by i ${kort(b.kommune)}`, order: 1 })),
      ],
      getCount: (key) => counts?.sted.get(key) || 0,
      isSelected: (key) => isPick(cur, key),
      // Det første sted erstatter regionerne og "Landsdækkende"; de næste lægges til
      onToggle: (key) => onChange((s) => pickPlace(s, key)),
      emptyCaption: 'Flest indslag lige nu',
      emptyNone: 'Ingen steder har indslag lige nu.',
      noMatch: (q) => `Ingen kommune eller by passer til "${q}". Byer kommer med, når de er nævnt i et indslag.`,
      // Kontekst i forslagets navn: "Ullerslev, by i Nyborg Kommune, 3 indslag"
      describe: (it) => placeContext(data, it.key),
    });
    const fg = addGroup(foldGroup('Sted', cbx.root,
      fset('Sted', picked.box, el('div', { class: 'opts regions' }, regionRows), nationalRow)), statusOf('sted'), (s) => s.sted.length > 0);
    sted = { cbx, picked, fg };
  }

  // Afsender: korte navne, fuldt navn i title
  const catRows = [...data.cats.values()].map((c) => {
    const name = c.short || c.name;
    return addRow('afsender', c.id, { name, title: c.name !== name ? c.name : null, iconName: c.icon, style: catStyle(c) });
  });
  addGroup(foldGroup('Afsender', tools('afsender'), fset('Afsender', catRows)), statusOf('afsender'), (s) => s.afsender.length > 0);

  // Tema: `short` hvis feedet har det; title, når navnet afviger eller kan blive afkortet
  const topicRow = (id) => {
    const name = topicName(data, id);
    const full = id === NO_TOPIC ? name : data.topics.get(id)?.name || name;
    return addRow('tema', id, { name, title: full !== name || name.length > 24 ? full : null });
  };
  addGroup(foldGroup('Tema', tools('tema'), fset('Tema', [...data.topics.keys()].map(topicRow),
    el('div', { class: 'fsep', 'aria-hidden': 'true' }), topicRow(NO_TOPIC))), statusOf('tema'), (s) => s.tema.length > 0);

  // Kilde: alle kilder grupperet efter afsendertype; feltet øverst indsnævrer listen
  const srcIds = [...data.sources.keys()];
  const srcRows = new Map();
  const srcSections = [...data.cats.values()].map((c) => {
    const ids = srcIds.filter((id) => data.sources.get(id).category === c.id)
      .sort((a, b) => data.sources.get(a).name.localeCompare(data.sources.get(b).name, 'da'));
    if (!ids.length) return null;
    const list = ids.map((id) => {
      const src = data.sources.get(id);
      const label = addRow('kilde', id, { name: src.name, title: src.name.length > 26 ? src.name : null });
      srcRows.set(id, { label, keys: foldKeys(src.name) });
      return label;
    });
    const sub = el('p', { class: 'fsub cat', style: catStyle(c), 'aria-hidden': 'true' }, icon(c.icon), c.short || c.name);
    return { el: el('div', { class: 'fsrc-cat' }, sub, el('div', { class: 'opts' }, list)), ids };
  }).filter(Boolean);
  const srcFind = el('input', {
    id: 'f-kilde', class: 'field', type: 'search', autocomplete: 'off', spellcheck: 'false', placeholder: 'Find kilde',
    oninput: () => filterSrc(),
    onkeydown: (e) => { if (e.key === 'Escape' && srcFind.value) { e.preventDefault(); e.stopPropagation(); srcFind.value = ''; filterSrc(); } },
  });
  const srcNone = el('p', { class: 'fnote', role: 'status' });
  addGroup(foldGroup('Kilde',
    el('div', { class: 'fsrc' },
      el('label', { for: 'f-kilde', class: 'visually-hidden', text: 'Find kilde' }),
      el('div', { class: 'cbx-field' }, icon('soeg'), srcFind)),
    tools('kilde'),
    fset('Kilde', srcSections.map((x) => x.el)), srcNone), statusOf('kilde'), (s) => s.kilde.length > 0);

  /** Feltet skjuler kilder, der ikke passer, og typer uden kilder tilbage. */
  function filterSrc() {
    const qs = foldKeys(srcFind.value).filter(Boolean);
    let n = 0;
    for (const sec of srcSections) {
      let any = false;
      for (const id of sec.ids) {
        const { label, keys } = srcRows.get(id);
        // Feltets to stavemåder (å→aa og å→a) er alternativer; én skal passe
        const hit = !qs.length || qs.some((q) => keys.some((k) => k.includes(q)));
        label.hidden = !hit;
        if (hit) { any = true; n += 1; }
      }
      sec.el.hidden = !any;
    }
    srcNone.textContent = qs.length && !n ? `Ingen kilde passer til "${srcFind.value.trim()}".` : '';
  }

  // Genre
  addGroup(foldGroup('Genre', tools('genre'), fset('Genre', [...data.genres.keys()].map((id) => addRow('genre', id, { name: genreName(data, id) })))),
    statusOf('genre'), (s) => s.genre.length > 0);

  // Åben ved indlæsning, hvis gruppen har et valg. Brugerens egne fold huskes ikke.
  for (const x of groups) x.fg.root.open = x.active(state);

  const resetBtn = el('button', { type: 'button', class: 'btn-text', hidden: true, onclick: () => onReset?.() }, 'Nulstil');

  const root = el('search', { class: 'filters', 'aria-labelledby': 'filters-title' },
    el('div', { class: 'filters-head' }, el('h2', { id: 'filters-title', text: 'Filtre' }), resetBtn),
    el('div', { class: 'fgs' }, groups.map((x) => x.fg.root)));

  function update(s, c) {
    cur = s;
    counts = c;
    for (const { g, key, row } of rows) row.set(isShown(s, g, key), c[g]?.get(key) || 0);
    for (const x of groups) x.fg.status.textContent = x.text(s);
    for (const { g, btn } of toggles) btn.textContent = allShown(s, g) ? 'Fravælg alle' : 'Vælg alle';
    resetBtn.hidden = activeCount(s) === 0;
    if (sted) {
      sted.picked.sync(s, c.sted, !s.sted.length);
      sted.cbx.refresh();
    }
  }

  return {
    root, update,
    /** Lukker en åben forslagsliste. Returnerer true, hvis der var en. */
    closeSuggestions() {
      const open = [sted?.cbx].find((x) => x?.isOpen());
      open?.close();
      return !!open;
    },
  };
}

export function renderActive(container, data, s, onChange, onReset) {
  const list = activeFilters(data, s);
  const before = [...container.querySelectorAll('.chip-x')];
  const prevIndex = before.indexOf(document.activeElement);
  container.replaceChildren(
    ...list.map((f) => el('li', null, el('button', {
      type: 'button', class: 'chip-x', 'aria-label': `Fjern filter: ${f.label}`, title: f.label.length > 32 ? f.label : null,
      onclick: () => onChange((st) => removeFilter(st, f)),
    }, el('span', { class: 'label', text: f.label }), el('span', { class: 'x', 'aria-hidden': 'true' }, icon('luk'))))),
    // replaceChildren skriver null som teksten "null"; derfor en tom liste i stedet
    ...(list.length ? [el('li', null, el('button', { type: 'button', class: 'btn-text', onclick: onReset }, 'Nulstil'))] : []));
  container.hidden = list.length === 0;
  if (prevIndex < 0) return false;
  // Fokus: næste mærke, ellers forrige, ellers statuslinjen (app.js)
  const chips = container.querySelectorAll('.chip-x');
  if (!chips.length) return true;
  chips[Math.min(prevIndex, chips.length - 1)].focus();
  return false;
}
