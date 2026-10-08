// Affaldsfeed: forsiden (feed), Tidslinje og "Om kilderne". Ingen build, ingen afhængigheder.

import {
  el, icon, hidden, catStyle, cap, truncate, cph, fmtNum, fmtShort, fmtLong, fmtWhen, fmtStamp,
  isoWeek, fmtDayRange, weekdayOf, parseDate, load, store, DAY_MS,
  readState, syncUrl, setData, defaultState, activeCount, sheetCount, activeFilters, removeFilter, resetFilters, shownSet, NATIONAL,
  prepare, applyFilters, computeCounts, computeDayCounts, buildPanel, renderActive,
  placeName, placeParents, rangeOf, setRange, fmtRange,
} from './filters.js';
import { createOverview } from './overview.js';
import { createTimeline, demoizeTimeline } from './tidslinje.js';
import { createDatePicker } from './calendar.js';

const CHUNK = 50; // kort pr. bid, når listen bygges, mens man scroller
const AHEAD_PX = 1500; // næste bid bygges, når listens ende er så tæt på skærmen
const IDLE_MAX = 300; // så mange kort bygges i forvejen i ledige stunder; resten, når man scroller
const STALE_HOURS = 6;
const TEASER_MAX = 240;
const TIME_KEYS = new Set(['generated', 'last_judgment', 'published', 'first_seen', 'start', 'end', 'last_attempt']);

const $ = (id) => document.getElementById(id);
const narrow = matchMedia('(max-width: 47.99em)');

// Siden følger enhedens farvetema (prefers-color-scheme). En gammel værdi fra den fjernede temavælger
// slettes, så ingen sidder fast i et tema uden en knap til at skifte (store kører i try/catch)
store('af.theme', null);
const page = document.body.dataset.page;
if (page === 'feed') initFeed();
else if (page === 'kilder') initKilder();
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
    } else if (k === 'since' && typeof v === 'string') {
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

const withDemo = (href, demo) => {
  if (!demo) return href;
  const [path, hash] = href.split('#');
  return `${path}?demo=${encodeURIComponent(demo)}${hash ? `#${hash}` : ''}`;
};

/** Demo-strimlen over headeren, og ?demo= på interne links. */
function initDemo(demo) {
  if (!demo) return;
  for (const a of document.querySelectorAll('a[data-internal]')) {
    const url = new URL(a.getAttribute('href'), location.href);
    url.searchParams.set('demo', demo);
    // "./" har intet filnavn; uden "index.html" ville linket pege på siden selv (kilder.html?demo=1)
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
      for (const id of ['overview', 'msgs']) $(id).hidden = true;
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

function message(kind, iconName, ...content) {
  return el('div', { class: `msg ${kind}`.trim() }, icon(iconName), el('p', null, content));
}

function setupFeed(feed, state, now, lastVisit) {
  const data = prepare(feed, lastVisit);
  setData(data);
  const ui = {
    msgs: $('msgs'), overview: $('overview'), slot: $('sidebar-slot'),
    sheet: $('filter-sheet'), sheetTitle: $('sheet-title'), sheetBody: $('sheet-body'), sheetShow: $('sheet-show'),
    sheetClose: $('sheet-close'), sheetReset: $('sheet-reset'), sheetLive: $('sheet-live'),
    filterBtn: $('filter-btn'), filterCount: $('filter-count'), filterComma: $('filter-comma'), filterCountSr: $('filter-count-sr'),
    head: $('list-head'), q: $('q'), qClear: $('q-clear'), active: $('active-filters'),
    status: $('status'), statusUnit: $('status-unit'), statusText: $('status-text'), statusSep: $('status-sep'),
    statusAction: $('status-action'), view: $('view-seg'), list: $('feed'), end: $('feed-end'),
    dateBtn: $('date-btn'), dateText: $('date-text'), dateClear: $('date-clear'),
  };
  const todayNum = cph(now).dayNum;
  // Feedets første dag: vinduets start (som standard 60 dage) eller det ældste indslag, hvis det er ældre.
  // Kalenderen kan vælge dage herfra til i dag.
  const firstDay = data.members.reduce((d, m) => Math.min(d, m.day.dayNum),
    cph(new Date(now.getTime() - (Number(feed.window_days) || 60) * DAY_MS)).dayNum);
  let total = null; // antal kort uden filtre
  let cards = [];
  let fill = null; // byggeriet af den aktuelle liste (renderList)
  let fillId = 0;
  let pumping = false;

  // Meddelelser: forældet feed og regelvisning
  const msgs = [];
  const gen = parseDate(feed.generated);
  if (gen) {
    const hours = Math.floor((now - gen) / 36e5);
    if (hours > STALE_HOURS) {
      const ago = hours < 48 ? `${hours} timer` : `${Math.floor(hours / 24)} dage`;
      msgs.push(message('', 'advarsel', `Feedet blev sidst opdateret for ${ago} siden. Indsamlingen kører måske ikke. `,
        el('a', { href: withDemo('kilder.html', state.demo) }, 'Se kildernes status')));
    }
  }
  if (feed.mode === 'fallback') {
    msgs.push(message('msg-info', 'info', 'Vurderingen af nye indslag er forsinket, så de vises efter faste regler indtil videre.'));
  }
  ui.msgs.replaceChildren(...msgs);
  ui.msgs.hidden = !msgs.length;

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

  // ── Listens ende: nærmer den sig skærmen, bygges de næste kort (renderList) ──
  new IntersectionObserver((entries) => { if (entries.some((e) => e.isIntersecting)) pump(); },
    { rootMargin: `0px 0px ${AHEAD_PX}px 0px` }).observe(ui.end);

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

  // Grupper: I dag, I går, ugedage til 6 dage tilbage, derefter uger med kun de dage, gruppen dækker
  // (inden for feedets vindue og et valgt tidsrum)
  function grouper() {
    const r = rangeOf(state);
    const lo = r?.lo ?? firstDay;
    const hi = r?.hi ?? todayNum;
    return (day) => {
      const diff = todayNum - day.dayNum;
      if (diff <= 0) return { key: 'i-dag', label: 'I dag', week: false };
      if (diff === 1) return { key: 'i-gaar', label: 'I går', week: false };
      if (diff < 7) return { key: `d${day.dayNum}`, label: `${cap(weekdayOf(day))} ${fmtLong(day)}`, week: false };
      const w = isoWeek(day.dayNum);
      const from = Math.max(w.monday, lo);
      const to = Math.min(w.monday + 6, todayNum - 7, hi);
      return { key: `w${w.year}-${w.week}`, label: `Uge ${w.week} · ${fmtDayRange(from, to)}`, week: true };
    };
  }

  // ── Listen bygges i bidder: den første med det samme, de næste, når listens ende nærmer sig skærmen.
  // I ledige stunder bygges op til IDLE_MAX kort i forvejen, så en normal liste kort efter står helt i
  // siden (søgning i siden og footeren virker), mens et meget langt feed ikke gør hvert filterklik tungt. ──
  function done() {
    return !fill || fill.i >= cards.length;
  }
  function near() {
    return ui.end.getBoundingClientRect().top < innerHeight + AHEAD_PX;
  }

  function renderList() {
    fillId += 1;
    fill = null;
    ui.list.classList.toggle('is-compact', state.vis === 'kompakt');
    if (!data.members.length) {
      ui.list.replaceChildren(el('div', { class: 'empty' }, el('p', { text: 'Der er ingen indslag i feedet endnu.' })));
      return;
    }
    if (!cards.length) { ui.list.replaceChildren(renderEmpty()); return; }

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
    fill = {
      id: fillId, i: 0, group: null, ul: null, groupOf, groupCount,
      dividerDone: !lastVisit || state.nye, seenNew: false, compact: state.vis === 'kompakt',
    };
    appendCards(CHUNK);
    pump();
    idleFill();
  }

  /** De næste n kort i rækkefølge, med dagsoverskrifter og "Her slap du sidst". */
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
      if (!f.dividerDone && f.seenNew && !card.isNew) {
        f.ul.append(el('li', { class: 'lastvisit' }, `Her slap du sidst · ${fmtWhen(lastVisit, now)}`));
        f.dividerDone = true;
      }
      if (card.isNew) f.seenNew = true;
      f.ul.append(el('li', null, f.compact ? renderRow(card, g) : renderCard(card, g)));
    }
  }

  // Tæt på listens ende: ét bid pr. billede, til enden er langt nok væk igen
  function pump() {
    if (pumping || done()) return;
    pumping = true;
    requestAnimationFrame(() => {
      pumping = false;
      if (done() || !near()) return;
      appendCards(CHUNK);
      pump();
    });
  }

  // Op til IDLE_MAX kort bygges i ledige stunder (højst 1 s mellem bidderne, også når siden har travlt)
  function whenIdle(fn) {
    if (window.requestIdleCallback) requestIdleCallback(fn, { timeout: 1000 });
    else setTimeout(() => fn({ timeRemaining: () => 8 }), 50);
  }
  function idleFill() {
    const id = fillId;
    const full = () => done() || fill.i >= IDLE_MAX;
    // Små bidder på 2 kort, kun mens der er god tid tilbage, så en langsom telefon ikke får lange opgaver
    whenIdle((deadline) => {
      if (id !== fillId || full()) return;
      appendCards(2);
      while (!full() && deadline.timeRemaining() > 20) appendCards(2);
      idleFill();
    });
  }

  // ── Kortet ──

  /** Tid efter datokvalitet. Under en dagsoverskrift kun klokkeslæt; ellers datoen. */
  function timeEl(m, group, headDay) {
    const c = m.day;
    const dateOnly = m.dateQuality === 'url' || m.dateQuality === 'liste';
    const pre = m.dateQuality === 'fundet' ? 'fundet ' : '';
    let text = '';
    let sr = null;
    if (!group.week && c.dayNum === headDay) {
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
   * Afsenderlinjen: kategoriikon og kildens navn, intet andet. Afsendertype og genre kan vælges i menuen,
   * og betalingsmur og ejer står på Om kilderne.
   */
  function who(m) {
    return el('p', { class: 'who' }, srcIcon(m.logo, m.cat), el('b', { text: m.source.name }));
  }

  function renderCard(card, group) {
    const m = card.primary;
    const others = card.others;
    const titleId = `t-${m.id}`;
    const headDay = m.day.dayNum;

    let teaser = null;
    if (m.lang !== 'da' && m.summary) {
      teaser = el('p', { class: 'teaser' }, el('b', { class: 'auto', text: 'Auto-resumé:' }), ' ', m.summary);
    } else if (m.teaser) {
      teaser = el('p', { class: 'teaser', lang: langAttr(m) }, truncate(m.teaser, TEASER_MAX));
    }

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
          bare ? null : el('div', { class: 'meta' }, who(o), timeEl(o, group, headDay)),
          el('p', { class: 'mtitle' }, o.isNew ? hidden('Ny: ') : null, titleLink(o))))));
    }

    // Kortet er nyt, når et af dets indslag, der passer på filtrene, er nyt (samme regel som "Vis N nye")
    return el('article', { class: `card cat${card.isNew ? ' is-new' : ''}`, style: catStyle(m.cat), 'aria-labelledby': titleId },
      el('div', { class: 'meta' }, who(m), timeEl(m, group, headDay)),
      el('h3', { class: 'title', id: titleId }, card.isNew ? hidden('Ny: ') : null, titleLink(m)),
      teaser,
      also ? el('div', { class: 'foot' }, also) : null);
  }

  /** Kompakt: ikon, kilde (fast kolonne), titel og tid. */
  function renderRow(card, group) {
    const m = card.primary;
    const titleId = `t-${m.id}`;
    return el('article', { class: `row cat${card.isNew ? ' is-new' : ''}`, style: catStyle(m.cat), 'aria-labelledby': titleId },
      srcIcon(m.logo, m.cat),
      el('span', { class: 'src', text: m.source.name, title: m.source.name.length > 18 ? m.source.name : null }),
      el('div', { class: 'tcell' },
        el('h3', { class: 'title', id: titleId }, card.isNew ? hidden('Ny: ') : null, titleLink(m))),
      timeEl(m, group, m.day.dayNum));
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

// ── Om kilderne ──────────────────────────────────────────

const HEALTH = {
  groen: { label: 'Kører', sym: '●' },
  gul: { label: 'Ustabil', sym: '▲' },
  roed: { label: 'Fejler', sym: '■' },
  graa: { label: 'Ingen data endnu', sym: '○' },
};

function healthBadge(h) {
  const x = HEALTH[h] || HEALTH.graa;
  return el('span', { class: `health health-${HEALTH[h] ? h : 'graa'}` },
    el('span', { class: 'sym', 'aria-hidden': 'true', text: x.sym }), x.label);
}

async function initKilder() {
  const state = readState(location.search);
  const now = new Date();
  initDemo(state.demo);
  const root = $('kilder-root');

  let feed;
  try {
    feed = await loadFeed(state.demo);
  } catch (err) {
    console.warn('Kilderne kunne ikke indlæses:', err.message);
    root.replaceChildren(el('div', { class: 'panel', role: 'alert' },
      el('p', { text: 'Kildelisten kunne ikke indlæses. Prøv igen om lidt.' }),
      el('p', { class: 'actions' }, el('button', { type: 'button', class: 'btn', onclick: () => location.reload() }, 'Prøv igen'))));
    return;
  }
  if (state.demo) demoize(feed, now);

  let status = null;
  if (!state.demo) {
    try { status = await fetchJson('data/status.json'); } catch { status = null; }
  }

  const cats = feed.categories || [];
  const stat = new Map((status?.sources || []).map((s) => [s.id, s]));
  const sources = (feed.sources || []).map((s) => ({ ...s, ...(stat.get(s.id) ? { health: stat.get(s.id).health } : {}), st: stat.get(s.id) || null }));
  const direct = sources.filter((s) => !s.via_search);
  const viaSearch = sources.filter((s) => s.via_search);

  const healthCount = { groen: 0, gul: 0, roed: 0, graa: 0 };
  for (const s of direct) healthCount[HEALTH[s.health] ? s.health : 'graa'] += 1;

  const out = [];

  // Overblik over sundhed
  const gen = parseDate(feed.generated);
  const lastJ = parseDate(feed.last_judgment);
  out.push(el('section', { class: 'panel', 'aria-labelledby': 'h-status' },
    el('h2', { id: 'h-status', text: 'Status lige nu' }),
    el('p', { class: 'help', text: 'Mærket ud for hver kilde viser, om indsamlingen virker. En kilde, der svarer, men ikke leverer nogen indslag, tæller som en fejl.' }),
    el('ul', { class: 'stats' },
      el('li', null, el('strong', { text: fmtNum(direct.length) }), el('span', { text: 'aktive kilder' })),
      el('li', null, el('strong', { text: fmtNum(viaSearch.length) }), el('span', { text: 'udgivere fundet via søgning' })),
      status?.counts ? [
        el('li', null, el('strong', { text: fmtNum(status.counts.shown_60d ?? 0) }), el('span', { text: 'viste indslag (60 dage)' })),
        el('li', null, el('strong', { text: fmtNum(status.counts.candidates_60d ?? 0) }), el('span', { text: 'fundne kandidater (60 dage)' })),
      ] : null),
    el('p', { class: 'facts status-note' },
      gen ? `Feedet er opdateret ${fmtWhen(gen, now)}. ` : '',
      lastJ ? `Indslagene blev sidst vurderet ${fmtWhen(lastJ, now)}. ` : '',
      feed.mode === 'fallback' ? 'Lige nu vises nye indslag efter faste regler.' : ''),
    el('ul', { class: 'legend', 'aria-label': 'Kildernes sundhed' },
      Object.keys(HEALTH).map((h) => el('li', null, healthBadge(h), ` ${fmtNum(healthCount[h])}`)))));

  // Afsendertyperne som rækker med spring til hver type
  out.push(el('nav', { class: 'panel', id: 'typer', 'aria-labelledby': 'h-typer' },
    el('h2', { id: 'h-typer', text: 'Afsendertyper' }),
    el('ul', { class: 'types' }, cats.map((c) => {
      const n = direct.filter((s) => s.category === c.id).length;
      return el('li', null, el('a', { class: 'trow cat', style: catStyle(c), href: `#kat-${c.id}` },
        icon(c.icon), el('span', { class: 'name', text: c.name }),
        el('span', { class: 'n' }, fmtNum(n), hidden(n === 1 ? ' kilde' : ' kilder'))));
    }))));

  for (const c of cats) {
    const list = direct.filter((s) => s.category === c.id).sort((a, b) => a.name.localeCompare(b.name, 'da'));
    out.push(el('section', { class: 'panel cat-section cat', id: `kat-${c.id}`, style: catStyle(c), 'aria-labelledby': `h-${c.id}` },
      el('h2', { id: `h-${c.id}` }, icon(c.icon), el('span', { text: c.name })),
      el('p', { class: 'help', text: c.help }),
      list.length
        ? el('ul', { class: 'src-rows' }, list.map((s) => sourceRow(s, now)))
        : el('p', { class: 'facts', text: 'Ingen aktive kilder i denne kategori endnu.' })));
  }

  out.push(el('section', { class: 'panel', 'aria-labelledby': 'h-search' },
    el('h2', { id: 'h-search', text: 'Fundet via søgning' }),
    el('p', { class: 'help', text: 'Disse udgivere har ikke et feed, som Affaldsfeed henter direkte. Deres artikler bliver fundet via nyhedssøgninger, men krediteres altid udgiveren. Kun udgivere på listen over troværdige medier kommer med.' }),
    viaSearch.length
      ? el('ul', { class: 'src-rows' }, viaSearch.sort((a, b) => a.name.localeCompare(b.name, 'da')).map((s) => sourceRow(s, now, cats)))
      : el('p', { class: 'facts', text: 'Ingen artikler fra søgning i perioden.' })));

  root.replaceChildren(...out);
  if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
}

function sourceRow(s, now, cats = null) {
  const facts = [];
  if (cats) {
    const c = cats.find((x) => x.id === s.category);
    if (c) facts.push(c.short);
  }
  if (s.owner) facts.push(`udgivet af ${s.owner}`);
  if (s.lang && s.lang !== 'da') facts.push(s.lang === 'en' ? 'engelsk' : 'svensk');
  if (s.paywall === 'ja') facts.push('betalingsmur');
  if (s.paywall === 'delvis') facts.push('delvis betalingsmur');
  const st = s.st;
  if (st) {
    const ok = parseDate(st.last_ok);
    if (ok) facts.push(`sidst hentet ${fmtShort(cph(ok))}`);
    if (typeof st.items_30d === 'number') facts.push(`${fmtNum(st.items_30d)} indslag på 30 dage`);
    if (st.silent) facts.push('tavs i lang tid');
    if (st.fails) facts.push(`${fmtNum(st.fails)} fejl i træk`);
  }
  return el('li', { class: 'src-row' },
    el('div', { class: 'src-who' },
      el('a', { href: s.homepage, target: '_blank', rel: 'noopener' }, srcIcon(s.logo, null), s.name, hidden(' (åbner i nyt vindue)')),
      facts.length ? el('p', { class: 'facts', text: facts.join(' · ') }) : null,
      st?.last_error && s.health === 'roed' ? el('p', { class: 'facts', text: `Seneste fejl: ${truncate(st.last_error, 120)}` }) : null),
    healthBadge(s.health));
}

// ── Tidslinje ────────────────────────────────────────────

async function initTimeline() {
  const state = readState(location.search);
  const now = new Date();
  initDemo(state.demo);
  const root = $('tidslinje-root');
  let tl;
  try {
    tl = await loadData('timeline', state.demo);
  } catch (err) {
    console.warn('Tidslinjen kunne ikke indlæses:', err.message);
    root.replaceChildren(el('div', { class: 'panel', role: 'alert' },
      el('p', { text: 'Tidslinjen kunne ikke indlæses. Prøv igen om lidt.' }),
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
