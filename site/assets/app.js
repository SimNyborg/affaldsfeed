// Affaldsfeed: forsiden (feed) og "Om kilderne". Ingen build, ingen afhængigheder.

import {
  el, icon, hidden, sep, catStyle, cap, truncate, cph, fmtNum, fmtShort, fmtLong, fmtWhen, fmtStamp,
  isoWeek, fmtDayRange, weekdayOf, parseDate, load, store, DAY_MS,
  readState, syncUrl, setData, defaultState, activeCount, sheetCount, activeFilters, removeFilter, resetFilters,
  prepare, applyFilters, computeCounts, buildPanel, renderActive, topicName, genreName,
  placeName, placeParents, precisePlaces,
} from './filters.js';
import { createOverview } from './overview.js';

const PAGE_SIZE = 50;
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

// ── Data ─────────────────────────────────────────────────

async function fetchJson(url) {
  const r = await fetch(url, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

/** feed.json, eller eksempeldata ved ?demo=1 (lokalt ../examples/, på Pages data/). */
async function loadFeed(demo) {
  if (!demo) return fetchJson('data/feed.json');
  const local = location.pathname.includes('/site/');
  const urls = local
    ? ['../examples/feed.sample.json', 'data/feed.sample.json']
    : ['data/feed.sample.json', '../examples/feed.sample.json'];
  let err = null;
  for (const u of urls) {
    try { return await fetchJson(u); } catch (e) { err = e; }
  }
  throw err;
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

function setSubtitle(feed, now) {
  const sub = $('subtitle');
  if (!sub) return;
  const gen = parseDate(feed.generated);
  const n = (feed.sources || []).length;
  sub.replaceChildren(el('span', { class: 'sub-lang', text: 'Nyheder om affald fra ' }),
    `${fmtNum(n)} kilder${gen ? ` · opdateret ${fmtStamp(gen, now)}` : ''}`);
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
      for (const id of ['overview', 'msgs', 'more-wrap']) $(id).hidden = true;
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
    status: $('status'), statusText: $('status-text'), statusSep: $('status-sep'), statusAction: $('status-action'),
    view: $('view-seg'), list: $('feed'), more: $('more-wrap'),
  };
  const todayNum = cph(now).dayNum;
  const totals = new Map(); // antal kort uden filtre, pr. "Saml historier"
  let limit = PAGE_SIZE;
  let cards = [];

  setSubtitle(feed, now);

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
    msgs.push(message('msg-info', 'info', 'Claudes vurdering er forsinket. Nye indslag vises efter faste regler og er mærket "Ikke vurderet".'));
  }
  ui.msgs.replaceChildren(...msgs);
  ui.msgs.hidden = !msgs.length;

  // ── Ændringer ──
  let qTimer = 0; // søgning, der venter på de 180 ms
  function change(mutate, { keepLimit = false, scroll = true } = {}) {
    // En ventende søgning anvendes først, så et filterklik lige efter en tast ikke overskriver teksten
    if (qTimer) { clearTimeout(qTimer); qTimer = 0; state.q = ui.q.value.trim(); }
    // Stod listens hoved over skærmens top, rulles det i syne. Det måles, før DOM'en ændres (layoutet er
    // rent, så målingen er gratis), og rulningen sker i næste billede uden et ekstra, tvunget layout
    const above = scroll && ui.head.getBoundingClientRect().top < 0;
    mutate(state);
    if (!keepLimit) limit = PAGE_SIZE;
    render();
    if (above) requestAnimationFrame(() => scrollToHead(true));
  }
  function reset() {
    change(resetFilters);
    if (ui.sheet.open) ui.sheetTitle.focus();
    else ui.status.focus();
  }

  // Filterpanelet (flyttes ind i arket under 1024 px)
  const panel = buildPanel(data, state, change, { typesHref: withDemo('kilder.html#typer', state.demo), onReset: reset });
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
    input.addEventListener('change', () => change((s) => { s.vis = input.value; }, { keepLimit: true, scroll: false }));
  }

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

  function totalFor(saml) {
    if (!totals.has(saml)) totals.set(saml, applyFilters(data, { ...defaultState(), saml }, now).length);
    return totals.get(saml);
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
      text = activeCount(state) ? `${fmtNum(n)} af ${fmtNum(totalFor(state.saml))} indslag` : `${fmtNum(n)} indslag`;
      if (lastVisit) {
        // Nye kort er de markerede (card.isNew), så tallet og markeringerne altid stemmer
        let newCount = 0;
        for (const c of cards) if (c.isNew) newCount += 1;
        if (newCount) { action = newCount === 1 ? 'Vis 1 ny' : `Vis ${fmtNum(newCount)} nye`; tail = ` siden ${fmtWhen(lastVisit, now)}`; }
      }
    }
    ui.statusText.textContent = text;
    ui.statusSep.hidden = !action;
    ui.statusAction.hidden = !action;
    // replaceChildren skriver null som teksten "null" ("Vis allenull"); derfor kun de dele, der findes
    if (action) ui.statusAction.replaceChildren(action, ...(tail ? [hidden(tail)] : []));
  }

  // Grupper: I dag, I går, ugedage til 6 dage tilbage, derefter uger med kun de dage, gruppen dækker
  function grouper() {
    const firstDay = cph(new Date(now.getTime() - state.periode * DAY_MS)).dayNum;
    return (day) => {
      const diff = todayNum - day.dayNum;
      if (diff <= 0) return { key: 'i-dag', label: 'I dag', week: false };
      if (diff === 1) return { key: 'i-gaar', label: 'I går', week: false };
      if (diff < 7) return { key: `d${day.dayNum}`, label: `${cap(weekdayOf(day))} ${fmtLong(day)}`, week: false };
      const w = isoWeek(day.dayNum);
      const from = Math.max(w.monday, firstDay);
      const to = Math.min(w.monday + 6, todayNum - 7);
      return { key: `w${w.year}-${w.week}`, label: `Uge ${w.week} · ${fmtDayRange(from, to)}`, week: true };
    };
  }

  function renderList() {
    ui.more.replaceChildren();
    ui.more.hidden = true;
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
    const visible = cards.slice(0, limit);

    // Intet i dag (kun uden filtre)
    if (activeCount(state) === 0 && groupOf(visible[0].primary.day).key !== 'i-dag') {
      out.push(el('div', { class: 'day' },
        el('h2', { class: 'day-head', id: 'day-i-dag' }, el('span', { text: 'I dag' })),
        el('p', { class: 'day-empty', text: `Intet nyt endnu i dag.${gen ? ` Sidst opdateret ${fmtStamp(gen, now)}.` : ''}` })));
    }

    let group = null;
    let ul = null;
    let dividerDone = !lastVisit || state.nye;
    let seenNew = false;
    const compact = state.vis === 'kompakt';
    for (const card of visible) {
      const g = groupOf(card.primary.day);
      if (!group || group.key !== g.key) {
        group = g;
        ul = el('ul', { class: 'cards' });
        out.push(el('div', { class: 'day' },
          el('h2', { class: 'day-head', id: `day-${g.key}` },
            el('span', { text: g.label }),
            el('span', { class: 'n' }, fmtNum(groupCount.get(g.key) || 0), hidden(' indslag'))),
          ul));
      }
      const isNew = card.isNew;
      if (!dividerDone && seenNew && !isNew) {
        ul.append(el('li', { class: 'lastvisit' }, `Her slap du sidst · ${fmtWhen(lastVisit, now)}`));
        dividerDone = true;
      }
      if (isNew) seenNew = true;
      ul.append(el('li', null, compact ? renderRow(card, g) : renderCard(card, g)));
    }
    ui.list.replaceChildren(...out);

    if (cards.length > limit) {
      const next = Math.min(PAGE_SIZE, cards.length - limit);
      ui.more.append(el('button', {
        type: 'button', class: 'btn',
        onclick: () => {
          const first = limit;
          limit += PAGE_SIZE;
          renderList();
          ui.list.querySelectorAll('article .title a')[first]?.focus();
        },
      }, `Vis flere (${fmtNum(next)})`));
      ui.more.hidden = false;
    }
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
   * Titel i kompakt visning. Titlens sidste ord, låsen og den skjulte tekst står i ét span uden
   * ombrydning, så låsen aldrig står alene på en linje, og "· Ikke vurderet" aldrig begynder en linje.
   */
  function compactTitleLink(m, pay) {
    const lang = langAttr(m);
    const t = String(m.title || '').trim();
    const cut = t.lastIndexOf(' ') + 1;
    return el('a', { href: m.url, target: '_blank', rel: 'noopener' },
      cut ? el('span', { lang }, t.slice(0, cut)) : null,
      el('span', { class: 'nw' }, el('span', { lang }, t.slice(cut)), pay ? icon('laas', 'lock') : null, hidden(' (åbner i nyt vindue)')));
  }

  function paywallText(src) {
    return src.paywall === 'ja' ? 'Betalingsmur' : src.paywall === 'delvis' ? 'Delvis betalingsmur' : '';
  }

  /** Genre, men ikke når titlen selv siger den ("Debat: …"). */
  function genreText(m) {
    if (!m.isHead || m.genre === 'nyhed') return '';
    const g = genreName(data, m.genre);
    const word = g.split(' ')[0].toLowerCase();
    return m.title.toLowerCase().startsWith(`${word}:`) ? '' : g;
  }

  /** Afsenderlinjen: ikon, kilde, kategori (", udgivet af X"), genre, betalingsmur, "Ikke vurderet". */
  function who(m, { genre = true, review = true } = {}) {
    const parts = [];
    if (genre) parts.push(genreText(m));
    parts.push(paywallText(m.source));
    if (review && !m.reviewed) parts.push('Ikke vurderet');
    return el('p', { class: 'who' }, icon(m.cat.icon), el('b', { text: m.source.name }),
      sep(), `${m.cat.short || m.cat.name}${m.source.owner ? `, udgivet af ${m.source.owner}` : ''}`,
      // Genre, betalingsmur og "Ikke vurderet" brydes aldrig midt i ("Delvis betalingsmur" står samlet)
      parts.filter(Boolean).map((t) => [sep(), el('span', { class: 'nw', text: t })]));
  }

  function renderCard(card, group) {
    const m = card.primary;
    const others = state.saml ? card.others : [];
    const titleId = `t-${m.id}`;
    const headDay = m.day.dayNum;

    let teaser = null;
    if (m.lang !== 'da' && m.summary) {
      teaser = el('p', { class: 'teaser' }, el('b', { class: 'auto', text: 'Auto-resumé:' }), ' ', m.summary);
    } else if (m.teaser) {
      teaser = el('p', { class: 'teaser', lang: langAttr(m) }, truncate(m.teaser, TEASER_MAX));
    }

    // Fodlinje: sted (de mest præcise, højst to navne og "+N"), temaer og "+N andre kilder"
    const places = precisePlaces(data, m.places).map((p) => placeName(data, p));
    const topics = m.topics.slice(0, 2).map((t) => topicName(data, t));
    const rest = places.length - 2;
    const placeText = places.length ? [
      icon('sted', 'pin'), hidden('Sted: '), places.slice(0, 2).join(', '),
      rest > 0 ? [' ', el('span', { 'aria-hidden': 'true', text: `+${rest}` }), hidden(rest === 1 ? 'og 1 andet sted' : `og ${rest} andre steder`)] : null,
    ] : null;
    const topicText = topics.length ? [hidden(topics.length > 1 ? 'Temaer: ' : 'Tema: '), topics.map((t, i) => (i ? [sep(), t] : t))] : null;
    const facets = placeText || topicText
      ? el('p', { class: 'facets' }, placeText, placeText && topicText ? sep() : null, topicText)
      : null;
    let also = null;
    if (others.length) {
      const fresh = others.filter((o) => o.isNew).length;
      also = el('details', { class: 'also' },
        el('summary', null,
          `+${others.length} ${others.length === 1 ? 'anden kilde' : 'andre kilder'}${fresh ? `, ${fresh} ${fresh === 1 ? 'ny' : 'nye'}` : ''}`,
          icon('pil-ned')),
        el('ul', null, others.map((o) => el('li', { class: 'cat', style: catStyle(o.cat) },
          el('div', { class: 'meta' }, who(o, { genre: false, review: false }), timeEl(o, group, headDay)),
          el('p', { class: 'mtitle' }, o.isNew ? hidden('Ny: ') : null, titleLink(o))))));
    }

    // Kortet er nyt, når et af dets indslag, der passer på filtrene, er nyt (samme regel som "Vis N nye")
    return el('article', { class: `card cat${card.isNew ? ' is-new' : ''}`, style: catStyle(m.cat), 'aria-labelledby': titleId },
      el('div', { class: 'meta' }, who(m), timeEl(m, group, headDay)),
      el('h3', { class: 'title', id: titleId }, card.isNew ? hidden('Ny: ') : null, titleLink(m)),
      teaser,
      facets || also ? el('div', { class: 'foot' }, facets, also) : null);
  }

  /** Kompakt: ikon, kilde (fast kolonne), titel og tid. */
  function renderRow(card, group) {
    const m = card.primary;
    const titleId = `t-${m.id}`;
    const pay = paywallText(m.source);
    return el('article', { class: `row cat${card.isNew ? ' is-new' : ''}`, style: catStyle(m.cat), 'aria-labelledby': titleId },
      icon(m.cat.icon),
      el('span', { class: 'src', text: m.source.name, title: m.source.name.length > 18 ? m.source.name : null }),
      el('div', { class: 'tcell' },
        el('h3', { class: 'title', id: titleId }, card.isNew ? hidden('Ny: ') : null, compactTitleLink(m, pay)),
        m.reviewed ? null : el('span', { class: 'nr' }, sep(), 'Ikke vurderet'),
        pay ? hidden(` (${pay.toLowerCase()})`) : null),
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
    const named = chips.filter((f) => f.key !== 'periode').map((f) => f.label);
    const span = `de seneste ${state.periode} dage`;
    let msg;
    if (!named.length && state.q) msg = `Intet om "${state.q}" ${span}.`;
    else if (named.length) msg = `Ingen indslag passer til ${[...named, ...(state.q ? [`"${state.q}"`] : [])].join(' + ')} ${span}.`;
    else msg = `Ingen indslag ${span}.`;
    if (chips.some((f) => f.key === 'sted')) msg += ' Landsdækkende nyheder vises ikke, når et sted er valgt.';
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
      const parent = f.key === 'sted' ? placeParents(data, f.value).find((p) => count(widen(f.value, p)) > 0) : null;
      if (parent) options.push({ text: `Udvid til ${placeName(data, parent)}`, mutate: widen(f.value, parent) });
      // Historien får den korte tekst; dens mærke kan være 60 tegn langt
      else options.push({ text: f.key === 'periode' ? 'Udvid til 60 dage' : f.key === 'story' ? 'Fjern historien' : `Fjern ${f.label}`, mutate: (s) => removeFilter(s, f) });
    }
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
  setSubtitle(feed, now);

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
      lastJ ? `Claude vurderede sidst indslag ${fmtWhen(lastJ, now)}. ` : '',
      feed.mode === 'fallback' ? 'Lige nu vises nye indslag efter faste regler og er mærket "Ikke vurderet".' : ''),
    el('ul', { class: 'legend', 'aria-label': 'Kildernes sundhed' },
      Object.keys(HEALTH).map((h) => el('li', null, healthBadge(h), ` ${fmtNum(healthCount[h])}`)))));

  // Afsendertyperne som rækker; filterpanelets link "Om afsendertyperne" peger hertil
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
      el('a', { href: s.homepage, target: '_blank', rel: 'noopener' }, s.name, hidden(' (åbner i nyt vindue)')),
      facts.length ? el('p', { class: 'facts', text: facts.join(' · ') }) : null,
      st?.last_error && s.health === 'roed' ? el('p', { class: 'facts', text: `Seneste fejl: ${truncate(st.last_error, 120)}` }) : null),
    healthBadge(s.health));
}
