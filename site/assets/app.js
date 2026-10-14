// Affaldsfeed: forsiden (feed) og Højdepunkter (tidslinjen). Ingen build, ingen afhængigheder.

import {
  el, icon, hidden, catStyle, cap, truncate, cph, fmtNum, fmtShort, fmtLong, fmtWhen, fmtStamp,
  fmtLongYear, weekdayOf, parseDate, load, store, DAY_MS,
  readState, syncUrl, setData, defaultState, activeCount, sheetCount, activeFilters, removeFilter, resetFilters, shownSet, NATIONAL,
  prepare, applyFilters, computeCounts, computeDayCounts, buildPanel, renderActive,
  placeName, placeParents, rangeOf, setRange, fmtRange, validDay, dayNumOf,
} from './filters.js';
import { createOverview } from './overview.js';
import { createTimeline, demoizeTimeline } from './tidslinje.js';
import { createDatePicker } from './calendar.js';
import { setupInfo, setInfoStatus } from './info.js';

const PAGE = 60; // kort ad gangen; resten kommer med "Vis mere"
const TEASER_MAX = 240;
const TIME_KEYS = new Set(['generated', 'last_judgment', 'published', 'first_seen', 'start', 'end', 'last_attempt']);

const $ = (id) => document.getElementById(id);
const narrow = matchMedia('(max-width: 47.99em)');

// Siden følger enhedens farvetema (prefers-color-scheme). En gammel værdi fra den fjernede temavælger
// slettes, så ingen sidder fast i et tema uden en knap til at skifte (store kører i try/catch)
store('af.theme', null);
const page = document.body.dataset.page;
if (page === 'feed') initFeed();
else if (page === 'tidslinje') initTimeline();

// ── Data ─────────────────────────────────────────────────

async function fetchJson(url) {
  const r = await fetch(url, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

/** data/<name>.json, eller eksempeldata ved ?demo=1 (lokalt ../examples/, på Pages data/). */
async function loadData(name, demo) {
  if (!demo) return fetchJson(`data/${name}.json`);
  const local = location.pathname.includes('/site/');
  const urls = local
    ? [`../examples/${name}.sample.json`, `data/${name}.sample.json`]
    : [`data/${name}.sample.json`, `../examples/${name}.sample.json`];
  let err = null;
  for (const u of urls) {
    try { return await fetchJson(u); } catch (e) { err = e; }
  }
  throw err;
}

function loadFeed(demo) {
  return loadData('feed', demo);
}

/** Demodata: ryk alle tidspunkter frem, så eksemplet ser aktuelt ud. */
function shiftTimes(obj, delta) {
  if (Array.isArray(obj)) { for (const o of obj) shiftTimes(o, delta); return; }
  if (!obj || typeof obj !== 'object') return;
  for (const [k, v] of Object.entries(obj)) {
    if (typeof v === 'string' && TIME_KEYS.has(k)) {
      const d = parseDate(v);
      if (d) obj[k] = new Date(d.getTime() + delta).toISOString().replace('.000Z', 'Z');
    } else if ((k === 'since' || k === 'window_start') && typeof v === 'string') {  // datoer: hele dage
      const [y, m, d] = v.split('-').map(Number);
      if (y && m && d) obj[k] = new Date(Date.UTC(y, m - 1, d) + Math.round(delta / DAY_MS) * DAY_MS).toISOString().slice(0, 10);
    } else if (v && typeof v === 'object') {
      shiftTimes(v, delta);
    }
  }
}

function demoize(feed, now) {
  const gen = parseDate(feed.generated);
  if (gen) shiftTimes(feed, Math.floor((now - gen) / 6e4) * 6e4);
}

/** Demo-strimlen over headeren, og ?demo= på interne links. */
function initDemo(demo) {
  if (!demo) return;
  for (const a of document.querySelectorAll('a[data-internal]')) {
    const url = new URL(a.getAttribute('href'), location.href);
    url.searchParams.set('demo', demo);
    // "./" har intet filnavn; uden "index.html" ville linket pege på siden selv (tidslinje.html?demo=1)
    a.href = (url.pathname.split('/').pop() || 'index.html') + url.search + url.hash;
  }
  const strip = $('demo-strip');
  const real = $('demo-real');
  if (!strip || !real) return;
  // "Vis det rigtige feed": samme side og filtre uden demo
  const update = () => {
    const url = new URL(location.href);
    url.searchParams.delete('demo');
    real.href = (url.pathname.split('/').pop() || './') + url.search;
  };
  for (const ev of ['pointerenter', 'focus', 'click']) real.addEventListener(ev, update);
  update();
  strip.hidden = false;
}

/** Klassiske scrollbarer tager plads fra indholdet; deres bredde trækkes fra højre polstring (--sbw). */
function fitScrollbar(box) {
  box.style.setProperty('--sbw', `${Math.max(0, box.offsetWidth - box.clientWidth)}px`);
}

// ── Forsiden ─────────────────────────────────────────────

function initFeed() {
  const state = readState(location.search);
  const now = new Date();
  const lastVisit = parseDate(load('af.lastVisit'));

  // "Nyt siden sidst": ny værdi skrives først, når siden forlades eller skjules
  const saveVisit = () => store('af.lastVisit', new Date().toISOString());
  addEventListener('pagehide', saveVisit);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') saveVisit(); });

  initDemo(state.demo);
  setupInfo();
  const list = $('feed');
  const slot = $('sidebar-slot');
  const head = $('list-head');
  if (state.q) $('q').value = state.q;

  const start = async () => {
    list.setAttribute('aria-busy', 'true');
    list.replaceChildren();
    slot.hidden = false;
    head.hidden = false;
    $('status-text').textContent = 'Henter feedet …';
    let loaded = false;
    try {
      const feed = await loadFeed(state.demo);
      if (!feed || !Array.isArray(feed.items)) throw new Error('feed.json mangler items');
      if (state.demo) demoize(feed, now);
      loaded = true;
      list.removeAttribute('aria-busy');
      // Data uden for kontrakten (fx places: null eller et indslag uden titel) giver fejltilstanden
      // i stedet for en side, der bliver ved med at hente
      setupFeed(feed, state, now, lastVisit);
    } catch (err) {
      console.warn('Feedet kunne ikke indlæses:', err.message);
      list.removeAttribute('aria-busy');
      // Fejlen står i læsekolonnen uden sidepanel og listens hoved (søgning, Filtrér og visning)
      slot.hidden = true;
      head.hidden = true;
      $('overview').hidden = true;
      $('status-text').textContent = '';
      // Fejlede opbygningen, genindlæses siden, så intet bindes to gange
      const retry = loaded ? () => location.reload() : start;
      list.replaceChildren(el('div', { class: 'empty', role: 'alert' },
        el('p', { text: 'Feedet kunne ikke indlæses. Prøv igen om lidt.' }),
        el('div', { class: 'actions' }, el('button', { type: 'button', class: 'btn btn-primary', onclick: retry }, 'Prøv igen'))));
    }
  };
  start();
}

/**
 * Kildens eget logo (16 px, KONTRAKTER §6.4), ellers afsendertypens ikon (cat) eller intet. Logoet er pynt
 * (alt=""), fordi navnet står lige efter det. Kan billedet ikke vises, står ikonet i stedet.
 */
function srcIcon(logo, cat) {
  if (!logo) return cat ? icon(cat.icon) : null;
  return el('img', {
    class: 'logo', src: logo, alt: '', width: 16, height: 16, loading: 'lazy', decoding: 'async',
    onerror: (e) => { if (cat) e.currentTarget.replaceWith(icon(cat.icon)); else e.currentTarget.remove(); },
  });
}

function setupFeed(feed, state, now, lastVisit) {
  const data = prepare(feed, lastVisit);
  setData(data);
  const ui = {
    overview: $('overview'), slot: $('sidebar-slot'),
    sheet: $('filter-sheet'), sheetTitle: $('sheet-title'), sheetBody: $('sheet-body'), sheetShow: $('sheet-show'),
    sheetClose: $('sheet-close'), sheetReset: $('sheet-reset'), sheetLive: $('sheet-live'),
    filterBtn: $('filter-btn'), filterCount: $('filter-count'), filterComma: $('filter-comma'), filterCountSr: $('filter-count-sr'),
    head: $('list-head'), q: $('q'), qClear: $('q-clear'), active: $('active-filters'),
    status: $('status'), statusUnit: $('status-unit'), statusText: $('status-text'), statusSep: $('status-sep'),
    statusAction: $('status-action'), view: $('view-seg'), list: $('feed'),
    more: $('feed-more'), moreBtn: $('feed-more-btn'), moreN: $('feed-more-n'),
    dateBtn: $('date-btn'), dateText: $('date-text'), dateClear: $('date-clear'),
  };
  const todayNum = cph(now).dayNum;
  // Feedets første dag: window_start (ellers window_days tilbage) eller det ældste indslag, hvis det er ældre.
  // Kalenderen kan vælge dage herfra til i dag.
  const windowStart = validDay(feed.window_start) ? dayNumOf(feed.window_start)
    : cph(new Date(now.getTime() - (Number(feed.window_days) || 60) * DAY_MS)).dayNum;
  const firstDay = data.members.reduce((d, m) => Math.min(d, m.day.dayNum), windowStart);
  let total = null; // antal kort uden filtre
  let cards = [];
  let fill = null; // byggeriet af den aktuelle liste (renderList)
  const gen = parseDate(feed.generated);
  setInfoStatus(feed, now);

  // ── Ændringer ──
  let qTimer = 0; // søgning, der venter på de 180 ms
  function change(mutate, { scroll = true } = {}) {
    // En ventende søgning anvendes først, så et filterklik lige efter en tast ikke overskriver teksten
    if (qTimer) { clearTimeout(qTimer); qTimer = 0; state.q = ui.q.value.trim(); }
    // Stod listens hoved over skærmens top, rulles det i syne. Det måles, før DOM'en ændres (layoutet er
    // rent, så målingen er gratis), og rulningen sker i næste billede uden et ekstra, tvunget layout
    const above = scroll && ui.head.getBoundingClientRect().top < 0;
    mutate(state);
    render();
    if (above) requestAnimationFrame(() => scrollToHead(true));
  }
  function reset() {
    change(resetFilters);
    if (ui.sheet.open) ui.sheetTitle.focus();
    else ui.status.focus();
  }

  // Filterpanelet (flyttes ind i arket under 1024 px)
  const panel = buildPanel(data, state, change, { onReset: reset });
  ui.slot.replaceChildren(panel.root);
  fitScrollbar(ui.slot);
  addEventListener('resize', () => fitScrollbar(ui.slot));

  const overview = createOverview(ui.overview, {
    data, now, getState: () => state,
    onPeriod: (p) => { state.overblik = p; syncUrl(state); },
    onStory: (ids) => { change((s) => { s.story = ids; }, { scroll: false }); toList(); },
  });
  ui.overview.hidden = false;
  overview.render();

  // ── Søgefeltet over listen ──
  const applyQ = () => {
    clearTimeout(qTimer);
    qTimer = 0;
    const v = ui.q.value.trim();
    if (v !== state.q) change((s) => { s.q = v; });
  };
  const showClear = () => { ui.qClear.hidden = !ui.q.value; };
  ui.q.addEventListener('input', () => { showClear(); clearTimeout(qTimer); qTimer = setTimeout(applyQ, 180); });
  ui.q.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); applyQ(); }
    if (e.key === 'Escape' && ui.q.value) { e.preventDefault(); ui.q.value = ''; showClear(); applyQ(); }
  });
  ui.qClear.addEventListener('click', () => { ui.q.value = ''; showClear(); applyQ(); ui.q.focus(); });
  showClear();
  applyQ(); // tekst skrevet, mens feedet blev hentet

  // ── Visning: Normal | Kompakt ──
  for (const input of ui.view.querySelectorAll('input')) {
    input.addEventListener('change', () => change((s) => { s.vis = input.value; }, { scroll: false }));
  }

  // ── Kalenderen: et tidsrum inden for feedets vindue ──
  createDatePicker({
    button: ui.dateBtn, minDay: firstDay, maxDay: todayNum, today: todayNum,
    getRange: () => rangeOf(state),
    getCounts: () => computeDayCounts(data, state, now),
    onPick: (lo, hi) => change((s) => setRange(s, lo, hi), { scroll: false }),
  });
  ui.dateClear.addEventListener('click', () => {
    change((s) => setRange(s, null), { scroll: false });
    ui.dateBtn.focus();
  });

  // ── "Vis mere": de næste PAGE kort, og fokus til det første af dem ──
  ui.moreBtn.addEventListener('click', () => {
    const first = fill.i;
    appendCards(PAGE);
    updateMore();
    ui.list.querySelectorAll('.cards > li')[first]?.querySelector('a')?.focus();
  });

  // ── Statuslinjen ──
  ui.statusAction.addEventListener('click', () => {
    change((s) => { s.nye = !s.nye; });
    ui.status.focus();
  });

  // ── Filterarket: bundark under 768 px, skuffe fra højre til 1023 px ──
  const sheetMq = matchMedia('(max-width: 63.99em)');
  let closeReason = '';
  let liveTimer = 0;
  ui.filterBtn.addEventListener('click', () => {
    if (ui.sheet.open) return;
    ui.sheetBody.append(panel.root);
    // Klassisk rullebjælke: dens bredde bliver polstring, mens arket låser scroll (style.css)
    const root = document.documentElement;
    root.style.setProperty('--page-sbw', `${Math.max(0, innerWidth - root.clientWidth)}px`);
    ui.sheet.showModal();
    fitScrollbar(ui.sheetBody);
    ui.sheetTitle.focus();
  });
  ui.sheetClose.addEventListener('click', () => ui.sheet.close());
  ui.sheetReset.addEventListener('click', reset);
  ui.sheetShow.addEventListener('click', () => { closeReason = 'show'; ui.sheet.close(); });
  // Esc: en åben forslagsliste lukkes først (komponenten stopper selv tasten; dette er reserven)
  ui.sheet.addEventListener('cancel', (e) => { if (panel.closeSuggestions()) e.preventDefault(); });
  // Når arket lukkes (×, Esc, klik udenfor, "Vis N indslag"): panelet tilbage i sidepanelet.
  // Lytter både på close og på open-attributten, da close-hændelsen ikke kommer i alle browsere.
  const afterClose = () => {
    if (ui.sheet.open || panel.root.parentElement === ui.slot) return;
    panel.closeSuggestions();
    ui.slot.append(panel.root);
    fitScrollbar(ui.slot);
    const reason = closeReason;
    closeReason = '';
    if (reason === 'show') toList();
    else if (reason === 'wide') ui.status.focus({ preventScroll: true });
    else ui.filterBtn.focus();
  };
  ui.sheet.addEventListener('close', afterClose);
  new MutationObserver(afterClose).observe(ui.sheet, { attributes: true, attributeFilter: ['open'] });
  if (!('closedBy' in HTMLDialogElement.prototype)) {
    // Klik på baggrunden lukker i browsere uden closedby, men kun når både pointerdown og klik var på
    // baggrunden (et træk, der begynder i arket og slutter udenfor, lukker ikke)
    const onBackdrop = (e) => {
      if (e.target !== ui.sheet) return false;
      const r = ui.sheet.getBoundingClientRect();
      return !(r.top <= e.clientY && e.clientY <= r.bottom && r.left <= e.clientX && e.clientX <= r.right);
    };
    let downOnBackdrop = false;
    ui.sheet.addEventListener('pointerdown', (e) => { downOnBackdrop = onBackdrop(e); });
    ui.sheet.addEventListener('click', (e) => {
      const close = downOnBackdrop && onBackdrop(e);
      downOnBackdrop = false;
      if (close) ui.sheet.close();
    });
  }
  sheetMq.addEventListener('change', () => {
    if (!sheetMq.matches && ui.sheet.open) { closeReason = 'wide'; ui.sheet.close(); }
    fitScrollbar(ui.slot);
  });

  render();

  // ── Rendering ──

  function render() {
    const counts = computeCounts(data, state, now);
    panel.update(state, counts);
    const lostFocus = renderActive(ui.active, data, state, change, reset);
    const n = activeCount(state);
    const sc = sheetCount(state);
    // Synligt "Filtrér (2)", til skærmlæser "Filtrér, 2 valgt" (kommaet står inline uden mellemrum før)
    ui.filterCount.textContent = sc ? ` (${sc})` : '';
    ui.filterComma.hidden = !sc;
    ui.filterCountSr.textContent = sc ? ` ${sc} valgt` : '';
    ui.sheetReset.hidden = n === 0;
    if (document.activeElement !== ui.q && ui.q.value.trim() !== state.q) { ui.q.value = state.q; showClear(); }
    for (const input of ui.view.querySelectorAll('input')) input.checked = input.value === state.vis;
    const range = rangeOf(state);
    ui.dateText.textContent = range ? cap(fmtRange(range, true)) : 'Alle datoer';
    ui.dateBtn.classList.toggle('is-set', !!range);
    ui.dateClear.hidden = !range;
    cards = applyFilters(data, state, now);
    ui.sheetShow.textContent = `Vis ${fmtNum(cards.length)} indslag`;
    if (ui.sheet.open) {
      // Statuslinjen bag arket er inert; arket har sin egen besked
      clearTimeout(liveTimer);
      liveTimer = setTimeout(() => { ui.sheetLive.textContent = `${fmtNum(cards.length)} indslag`; }, 500);
    }
    renderStatus();
    renderList();
    overview.setFiltersActive(n > 0);
    syncUrl(state);
    if (lostFocus) ui.status.focus();
  }

  function totalAll() {
    total ??= applyFilters(data, defaultState(), now).length;
    return total;
  }

  function renderStatus() {
    const n = cards.length;
    let action = null;
    let tail = '';
    let text;
    if (state.nye) {
      text = n === 1 ? '1 nyt indslag' : `${fmtNum(n)} nye indslag`;
      action = 'Vis alle';
    } else {
      text = activeCount(state) ? `${fmtNum(n)} af ${fmtNum(totalAll())} indslag` : `${fmtNum(n)} indslag`;
      if (lastVisit) {
        // Nye kort er de markerede (card.isNew), så tallet og markeringerne altid stemmer
        let newCount = 0;
        for (const c of cards) if (c.isNew) newCount += 1;
        if (newCount) { action = newCount === 1 ? 'Vis 1 ny' : `Vis ${fmtNum(newCount)} nye`; tail = ` siden ${fmtWhen(lastVisit, now)}`; }
      }
    }
    ui.statusText.textContent = text;
    // Antallet står kun synligt i "Kun nye". Ellers står kalenderknappen i stedet, og antallet læses op (style.css)
    ui.statusUnit.classList.toggle('st-quiet', !state.nye);
    ui.status.classList.toggle('is-empty', !state.nye && !action);
    ui.statusSep.hidden = !action;
    ui.statusAction.hidden = !action;
    // replaceChildren skriver null som teksten "null" ("Vis allenull"); derfor kun de dele, der findes
    if (action) ui.statusAction.replaceChildren(action, ...(tail ? [hidden(tail)] : []));
  }

  // Grupper: I dag, I går og derefter én dag ad gangen hele vejen tilbage ("Mandag 28. september").
  // Dage fra et andet år får årstallet med.
  function grouper() {
    const thisYear = cph(now).y;
    return (day) => {
      const diff = todayNum - day.dayNum;
      if (diff <= 0) return { key: 'i-dag', label: 'I dag' };
      if (diff === 1) return { key: 'i-gaar', label: 'I går' };
      const date = day.y === thisYear ? fmtLong(day) : fmtLongYear(day);
      return { key: `d${day.dayNum}`, label: `${cap(weekdayOf(day))} ${date}` };
    };
  }

  // ── Listen viser PAGE kort ad gangen. "Vis mere" under listen viser de næste. ──
  function updateMore() {
    const shown = fill ? fill.i : 0;
    ui.more.hidden = shown >= cards.length;
    ui.moreN.textContent = `Viser ${fmtNum(shown)} af ${fmtNum(cards.length)} indslag`;
  }

  function renderList() {
    fill = null;
    ui.list.classList.toggle('is-compact', state.vis === 'kompakt');
    if (!data.members.length) {
      ui.list.replaceChildren(el('div', { class: 'empty' }, el('p', { text: 'Der er ingen indslag i feedet endnu.' })));
      updateMore();
      return;
    }
    if (!cards.length) { ui.list.replaceChildren(renderEmpty()); updateMore(); return; }

    const groupOf = grouper();
    const groupCount = new Map();
    for (const c of cards) {
      const k = groupOf(c.primary.day).key;
      groupCount.set(k, (groupCount.get(k) || 0) + 1);
    }
    const out = [];
    // Intet i dag (kun uden filtre)
    if (activeCount(state) === 0 && groupOf(cards[0].primary.day).key !== 'i-dag') {
      out.push(el('div', { class: 'day' },
        el('h2', { class: 'day-head', id: 'day-i-dag' }, el('span', { text: 'I dag' })),
        el('p', { class: 'day-empty', text: `Intet nyt endnu i dag.${gen ? ` Sidst opdateret ${fmtStamp(gen, now)}.` : ''}` })));
    }
    ui.list.replaceChildren(...out);
    fill = { i: 0, group: null, ul: null, groupOf, groupCount, compact: state.vis === 'kompakt' };
    appendCards(PAGE);
    updateMore();
  }

  /** De næste n kort i rækkefølge, med dagsoverskrifter. */
  function appendCards(n) {
    const f = fill;
    const end = Math.min(cards.length, f.i + n);
    for (; f.i < end; f.i += 1) {
      const card = cards[f.i];
      const g = f.groupOf(card.primary.day);
      if (!f.group || f.group.key !== g.key) {
        f.group = g;
        f.ul = el('ul', { class: 'cards' });
        ui.list.append(el('div', { class: 'day' },
          el('h2', { class: 'day-head', id: `day-${g.key}` },
            el('span', { text: g.label }),
            el('span', { class: 'n' }, fmtNum(f.groupCount.get(g.key) || 0), hidden(' indslag'))),
          f.ul));
      }
      f.ul.append(el('li', null, f.compact ? renderRow(card) : renderCard(card)));
    }
  }

  // ── Kortet ──

  /** Tid efter datokvalitet. Under sin egen dags overskrift kun klokkeslæt; ellers datoen (fx et andet indslag
   *  i historien fra en anden dag). */
  function timeEl(m, headDay) {
    const c = m.day;
    const dateOnly = m.dateQuality === 'url' || m.dateQuality === 'liste';
    const pre = m.dateQuality === 'fundet' ? 'fundet ' : '';
    let text = '';
    let sr = null;
    if (c.dayNum === headDay) {
      if (dateOnly) sr = 'uden klokkeslæt';
      else text = `${pre}${c.hh}.${c.mm}`;
    } else {
      text = `${pre}${fmtShort(c)}`;
    }
    return el('time', { datetime: new Date(m.time).toISOString() }, text || null, sr ? hidden(sr) : null);
  }

  function langAttr(m) {
    return m.lang && m.lang !== 'da' ? m.lang : null;
  }

  function titleLink(m) {
    return el('a', { href: m.url, target: '_blank', rel: 'noopener' },
      el('span', { lang: langAttr(m) }, m.title), hidden(' (åbner i nyt vindue)'));
  }

  /**
   * Afsenderlinjen: kategoriikon og kildens navn, intet andet. Afsendertype og genre kan vælges i menuen.
   */
  function who(m) {
    return el('p', { class: 'who' }, srcIcon(m.logo, m.cat), el('b', { text: m.source.name }));
  }

  function renderCard(card) {
    const m = card.primary;
    const others = card.others;
    const titleId = `t-${m.id}`;
    const headDay = m.day.dayNum;

    // Previewet er resuméet med egne ord (KONTRAKTER §6.2a); kildens egen teaser vises aldrig
    const teaser = m.summary ? el('p', { class: 'teaser' }, truncate(m.summary, TEASER_MAX)) : null;

    // Fodlinjen har kun "+N andre kilder"; sted og temaer står ikke på kortet (de kan vælges i menuen)
    let also = null;
    if (others.length) {
      const fresh = others.filter((o) => o.isNew).length;
      const ids = others.map((o) => o.sourceId);
      // "+4 andre kilder" kun, når de øvrige er fra hver sin anden kilde; ellers "+4 flere" (fx Folketingets dagsbundt)
      const distinct = !ids.includes(m.sourceId) && new Set(ids).size === ids.length;
      // Samme kilde og dag som kortet: afsenderlinjen og tiden står allerede øverst, så kun titlerne vises
      const bare = others.every((o) => o.sourceId === m.sourceId && o.day.dayNum === headDay);
      const noun = distinct ? (others.length === 1 ? 'anden kilde' : 'andre kilder') : (others.length === 1 ? 'mere' : 'flere');
      also = el('details', { class: 'also' },
        el('summary', null,
          `+${others.length} ${noun}${fresh ? `, ${fresh} ${fresh === 1 ? 'ny' : 'nye'}` : ''}`,
          icon('pil-ned')),
        el('ul', { class: bare ? 'bare' : null }, others.map((o) => el('li', { class: 'cat', style: catStyle(o.cat) },
          bare ? null : el('div', { class: 'meta' }, who(o), timeEl(o, headDay)),
          el('p', { class: 'mtitle' }, o.isNew ? hidden('Ny: ') : null, titleLink(o))))));
    }

    // Kortet er nyt, når et af dets indslag, der passer på filtrene, er nyt (samme regel som "Vis N nye")
    return el('article', { class: `card cat${card.isNew ? ' is-new' : ''}`, style: catStyle(m.cat), 'aria-labelledby': titleId },
      el('div', { class: 'meta' }, who(m), timeEl(m, headDay)),
      el('h3', { class: 'title', id: titleId }, card.isNew ? hidden('Ny: ') : null, titleLink(m)),
      teaser,
      also ? el('div', { class: 'foot' }, also) : null);
  }

  /** Kompakt: ikon, kilde (fast kolonne), titel og tid. */
  function renderRow(card) {
    const m = card.primary;
    const titleId = `t-${m.id}`;
    return el('article', { class: `row cat${card.isNew ? ' is-new' : ''}`, style: catStyle(m.cat), 'aria-labelledby': titleId },
      srcIcon(m.logo, m.cat),
      el('span', { class: 'src', text: m.source.name, title: m.source.name.length > 18 ? m.source.name : null }),
      el('div', { class: 'tcell' },
        el('h3', { class: 'title', id: titleId }, card.isNew ? hidden('Ny: ') : null, titleLink(m))),
      timeEl(m, m.day.dayNum));
  }

  /** Efter "+N" i overblikket eller "Vis N indslag": listens hoved i syne og fokus på statuslinjen. */
  function toList() {
    scrollToHead(true);
    ui.status.focus({ preventScroll: true });
  }

  function scrollToHead(force) {
    const r = ui.head.getBoundingClientRect();
    if (!force && r.top >= 0) return;
    window.scrollTo({ top: window.scrollY + r.top - (narrow.matches ? 0 : 16), behavior: 'auto' });
  }

  // ── Tom-tilstande ──

  function renderEmpty() {
    const box = el('div', { class: 'empty' });
    const actions = el('div', { class: 'actions' });
    const act = (text, mutate, primary) => el('button', {
      type: 'button', class: primary ? 'btn btn-primary' : 'btn',
      onclick: () => { change(mutate); ui.status.focus(); },
    }, text);
    if (state.nye) {
      box.append(el('p', {
        text: lastVisit
          ? `Intet nyt siden dit sidste besøg ${fmtWhen(lastVisit, now)}.`
          : 'Intet er markeret som nyt, fordi siden ikke kender dit sidste besøg på denne enhed.',
      }));
      actions.append(act('Vis alle', (s) => { s.nye = false; }, true));
      box.append(actions);
      return box;
    }
    const chips = activeFilters(data, state);
    const named = chips.map((f) => f.label);
    // Tidsrummet: " den 7. oktober", " i perioden 7.–12. oktober" eller " fra 7. oktober"
    const r = rangeOf(state);
    let span = '';
    if (r) span = r.lo !== null && r.lo === r.hi ? ` den ${fmtRange(r)}` : r.lo === null || r.hi === null ? ` ${fmtRange(r)}` : ` i perioden ${fmtRange(r)}`;
    let msg;
    if (!named.length && state.q) msg = `Intet om "${state.q}"${span}.`;
    else if (named.length) msg = `Ingen indslag passer til ${[...named, ...(state.q ? [`"${state.q}"`] : [])].join(' + ')}${span}.`;
    else msg = `Ingen indslag${span}.`;
    const places = data.geo ? shownSet(state, 'sted') : null;
    if (places && !places.has(NATIONAL)) msg += ' Landsdækkende nyheder er ikke valgt under Sted.';
    box.append(el('p', { text: msg }));

    // Den ene ændring, der giver flest indslag: et filter fjernet, søgningen ryddet eller et sted udvidet
    // (by → primær kommune → region). Et sted, der kan udvides med indslag til følge, udvides frem for at fjernes.
    const count = (mutate) => {
      const trial = structuredClone(state);
      mutate(trial);
      return applyFilters(data, trial, now).length;
    };
    const widen = (from, to) => (s) => { s.sted = [...new Set(s.sted.map((v) => (v === from ? to : v)))]; };
    const options = [];
    for (const f of chips) {
      // Kun et valgt sted kan udvides (by → kommune → region); regioner og fravalg fjernes
      const parent = f.key === 'sted' && /^[kb]:/.test(f.value) ? placeParents(data, f.value).find((p) => count(widen(f.value, p)) > 0) : null;
      if (parent) options.push({ text: `Udvid til ${placeName(data, parent)}`, mutate: widen(f.value, parent) });
      // Historien får den korte tekst; dens mærke kan være 60 tegn langt
      else options.push({ text: f.undo || (f.key === 'story' ? 'Fjern historien' : `Fjern ${f.label}`), mutate: (s) => removeFilter(s, f) });
    }
    // Tidsrummet har intet mærke, fordi det står over listen
    if (r) options.push({ text: 'Vis alle datoer', mutate: (s) => setRange(s, null) });
    if (state.q) options.push({ text: 'Ryd søgning', mutate: (s) => { s.q = ''; } });
    let best = null;
    for (const o of options) {
      const n = count(o.mutate);
      if (n > 0 && (!best || n > best.n)) best = { ...o, n };
    }
    if (best) actions.append(act(`${best.text} (viser ${fmtNum(best.n)})`, best.mutate, true));
    if (options.length) actions.append(act('Nulstil filtre', resetFilters, false));
    box.append(actions);
    return box;
  }
}

// ── Tidslinje ────────────────────────────────────────────

async function initTimeline() {
  const state = readState(location.search);
  const now = new Date();
  initDemo(state.demo);
  setupInfo();
  const root = $('tidslinje-root');
  let tl;
  try {
    tl = await loadData('timeline', state.demo);
  } catch (err) {
    console.warn('Højdepunkterne kunne ikke indlæses:', err.message);
    root.replaceChildren(el('div', { class: 'panel', role: 'alert' },
      el('p', { text: 'Højdepunkterne kunne ikke indlæses. Prøv igen om lidt.' }),
      el('p', { class: 'actions' }, el('button', { type: 'button', class: 'btn', onclick: () => location.reload() }, 'Prøv igen'))));
    return;
  }
  if (state.demo) demoizeTimeline(tl, now);
  // Link til historien i feedet; demo står først som i resten af URL'en
  const feedHref = (story) => {
    const q = new URLSearchParams();
    if (state.demo) q.set('demo', state.demo);
    if (story) q.set('story', story);
    const qs = q.toString();
    return qs ? `index.html?${qs}` : './';
  };
  createTimeline(root, tl, { feedHref });
}
