// Affaldsfeed: forsiden (feed) og "Om kilderne". Ingen build, ingen afhængigheder.

import {
  el, icon, hidden, catStyle, cap, truncate, cph, fmtNum, fmtShort, fmtLong, fmtWhen, fmtStamp,
  isoWeek, fmtWeekRange, weekdayOf, parseDate, load, store, DAY_MS,
  readState, syncUrl, activeCount, activeFilters, removeFilter, resetFilters,
  prepare, applyFilters, computeCounts, buildPanel, renderActive, topicName,
} from './filters.js';
import { createOverview } from './overview.js';

const PAGE_SIZE = 50;
const STALE_HOURS = 6;
const TEASER_MAX = 240;
const TIME_KEYS = new Set(['generated', 'last_judgment', 'published', 'first_seen', 'start', 'end', 'last_attempt']);

const $ = (id) => document.getElementById(id);

initTheme();
const page = document.body.dataset.page;
if (page === 'feed') initFeed();
else if (page === 'kilder') initKilder();

// ── Tema: auto → lys → mørk ────────────────────────────────

function initTheme() {
  const btn = $('theme-btn');
  if (!btn) return;
  const order = ['auto', 'light', 'dark'];
  const names = { auto: 'Auto', light: 'Lys', dark: 'Mørk' };
  const icons = { auto: 'auto', light: 'sol', dark: 'maane' };
  const meta = document.querySelector('meta[name="color-scheme"]');
  let mode = load('af.theme');
  if (mode !== 'light' && mode !== 'dark') mode = 'auto';

  const apply = (save) => {
    const rootEl = document.documentElement;
    if (mode === 'auto') delete rootEl.dataset.theme;
    else rootEl.dataset.theme = mode;
    if (meta) meta.content = mode === 'auto' ? 'light dark' : mode;
    if (save) store('af.theme', mode === 'auto' ? null : mode);
    btn.replaceChildren(icon(icons[mode]), el('span', { class: 'lbl', text: names[mode] }));
    btn.setAttribute('aria-label', `Farvetema: ${names[mode]}. Skift tema`);
  };
  btn.addEventListener('click', () => {
    mode = order[(order.indexOf(mode) + 1) % order.length];
    apply(true);
  });
  apply(false);
}

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

/** Behold ?demo= på interne links. */
function keepDemo(demo) {
  if (!demo) return;
  for (const a of document.querySelectorAll('a[data-internal]')) {
    const url = new URL(a.getAttribute('href'), location.href);
    url.searchParams.set('demo', demo);
    a.href = url.pathname.split('/').pop() + url.search;
  }
}

function setSubtitle(feed, now) {
  const sub = $('subtitle');
  if (!sub) return;
  const gen = parseDate(feed.generated);
  const n = (feed.sources || []).length;
  sub.textContent = `Nyheder om affald fra ${fmtNum(n)} kilder${gen ? ` · opdateret ${fmtStamp(gen, now)}` : ''}`;
}

function bar(kind, iconName, ...content) {
  return el('div', { class: `bar ${kind}` }, icon(iconName), el('p', null, content));
}

function demoBar() {
  const url = new URL(location.href);
  url.searchParams.delete('demo');
  return bar('bar-demo', 'info',
    el('strong', { text: 'Demodata. ' }),
    'Indslagene er opdigtede eksempler, og links går til example.org. Tidspunkterne er rykket frem, så eksemplet ser aktuelt ud. ',
    el('a', { href: url.pathname.split('/').pop() + url.search || './' }, 'Vis det rigtige feed'));
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

  keepDemo(state.demo);
  const list = $('feed');

  const start = async () => {
    list.setAttribute('aria-busy', 'true');
    list.replaceChildren(el('p', { class: 'loading', text: 'Henter feedet …' }));
    let feed;
    try {
      feed = await loadFeed(state.demo);
      if (!feed || !Array.isArray(feed.items)) throw new Error('feed.json mangler items');
    } catch (err) {
      console.warn('Feedet kunne ikke indlæses:', err.message);
      list.removeAttribute('aria-busy');
      list.replaceChildren(el('div', { class: 'empty', role: 'alert' },
        el('p', { text: 'Feedet kunne ikke indlæses. Prøv igen om lidt.' }),
        el('div', { class: 'actions' }, el('button', { type: 'button', class: 'btn btn-primary', onclick: start }, 'Prøv igen'))));
      $('status-text').textContent = '';
      return;
    }
    list.removeAttribute('aria-busy');
    if (state.demo) demoize(feed, now);
    setupFeed(feed, state, now, lastVisit);
  };
  start();
}

function setupFeed(feed, state, now, lastVisit) {
  const data = prepare(feed, lastVisit);
  const ui = {
    bars: $('bars'), overview: $('overview'), slot: $('sidebar-slot'), sheet: $('filter-sheet'),
    sheetBody: $('sheet-body'), sheetShow: $('sheet-show'), sheetClose: $('sheet-close'),
    filterBtn: $('filter-btn'), filterCount: $('filter-count'), active: $('active-filters'),
    resetTop: $('reset-top'), toolbar: $('toolbar'), status: $('status'), statusText: $('status-text'),
    statusAction: $('status-action'), intro: $('intro'), list: $('feed'), more: $('more-wrap'),
  };
  const todayNum = cph(now).dayNum;
  let limit = PAGE_SIZE;
  let cards = [];

  setSubtitle(feed, now);

  // Bjælker: demo, forældet feed, regelbaseret visning
  const bars = [];
  if (state.demo) bars.push(demoBar());
  const gen = parseDate(feed.generated);
  if (gen) {
    const hours = Math.floor((now - gen) / 36e5);
    if (hours > STALE_HOURS) {
      const ago = hours < 48 ? `${hours} timer` : `${Math.floor(hours / 24)} dage`;
      bars.push(bar('', 'advarsel', `Feedet blev sidst opdateret for ${ago} siden. Indsamlingen kører måske ikke. `,
        el('a', { href: `kilder.html${state.demo ? `?demo=${encodeURIComponent(state.demo)}` : ''}` }, 'Se kildernes status')));
    }
  }
  if (feed.mode === 'fallback') {
    bars.push(bar('bar-info', 'info', 'Claudes vurdering er forsinket. Nye indslag vises lige nu ud fra regler og er mærket "ikke vurderet".'));
  }
  ui.bars.replaceChildren(...bars);
  ui.bars.hidden = !bars.length;

  // Introlinje ved første besøg
  if (!lastVisit && load('af.introClosed') !== '1') {
    ui.intro.hidden = false;
    $('intro-close').addEventListener('click', () => {
      store('af.introClosed', '1');
      ui.intro.hidden = true;
      ui.status.focus();
    });
  }

  // Filterpanel (flyttes ind i bundarket på smalle skærme)
  const change = (mutate) => { mutate(state); limit = PAGE_SIZE; render(); };
  const panel = buildPanel(data, state, change);
  ui.slot.append(panel.root);

  const overview = createOverview(ui.overview, {
    data, now, getState: () => state,
    onPeriod: (p) => { state.overblik = p; syncUrl(state); },
    onStory: (ids) => { change((s) => { s.story = ids; }); toList(); },
  });
  ui.overview.hidden = false;
  overview.render();

  const mq = matchMedia('(max-width: 1023px)');
  const openSheet = () => { ui.sheetBody.append(panel.root); ui.sheet.showModal(); };
  ui.filterBtn.addEventListener('click', openSheet);
  ui.sheetClose.addEventListener('click', () => ui.sheet.close());
  ui.sheetShow.addEventListener('click', () => ui.sheet.close());
  // Når arket lukkes (knap, Esc, klik udenfor): flyt panelet tilbage og giv fokus til knappen.
  // Lytter både på close og på open-attributten, da close-hændelsen ikke kommer i alle browsere.
  const afterClose = () => {
    if (ui.sheet.open || panel.root.parentElement === ui.slot) return;
    ui.slot.append(panel.root);
    if (mq.matches) ui.filterBtn.focus();
  };
  ui.sheet.addEventListener('close', afterClose);
  new MutationObserver(afterClose).observe(ui.sheet, { attributes: true, attributeFilter: ['open'] });
  if (!('closedBy' in HTMLDialogElement.prototype)) {
    // Light dismiss i browsere uden closedby
    ui.sheet.addEventListener('click', (e) => {
      if (e.target !== ui.sheet) return;
      const r = ui.sheet.getBoundingClientRect();
      const inside = r.top <= e.clientY && e.clientY <= r.bottom && r.left <= e.clientX && e.clientX <= r.right;
      if (!inside) ui.sheet.close();
    });
  }
  mq.addEventListener('change', () => { if (!mq.matches && ui.sheet.open) ui.sheet.close(); });

  // "/" giver fokus i søgefeltet
  document.addEventListener('keydown', (e) => {
    if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.target.closest?.('input, textarea, select, [contenteditable="true"]')) return;
    e.preventDefault();
    if (mq.matches && !ui.sheet.open) openSheet();
    panel.searchInput.focus();
    panel.searchInput.select();
  });

  ui.resetTop.addEventListener('click', () => { change(resetFilters); ui.status.focus(); });
  ui.statusAction.addEventListener('click', () => {
    change((s) => { s.nye = !s.nye; });
    ui.status.focus();
  });

  render();

  // ── Rendering ──

  function render() {
    const counts = computeCounts(data, state, now);
    panel.update(state, counts);
    const lostFocus = renderActive(ui.active, data, state, change);
    const n = activeCount(state);
    ui.resetTop.hidden = n === 0;
    ui.filterCount.textContent = n ? ` (${n})` : '';
    cards = applyFilters(data, state, now);
    ui.sheetShow.textContent = `Vis ${fmtNum(cards.length)} indslag`;
    renderStatus();
    renderList();
    overview.setFiltersActive(n > 0);
    syncUrl(state);
    if (lostFocus) ui.status.focus();
  }

  function renderStatus() {
    const total = cards.length;
    const shown = Math.min(limit, total);
    let text = total ? `Viser ${fmtNum(shown)} af ${fmtNum(total)} indslag` : 'Ingen indslag';
    let newCount = 0;
    if (lastVisit) {
      newCount = state.nye ? total : applyFilters(data, { ...state, nye: true }, now).length;
      if (newCount) text += ` · ${fmtNum(newCount)} nye siden ${fmtWhen(lastVisit, now)}`;
    }
    ui.statusText.textContent = text;
    if (state.nye) { ui.statusAction.textContent = 'Vis alle'; ui.statusAction.hidden = false; }
    else if (newCount) { ui.statusAction.textContent = 'Vis kun nye'; ui.statusAction.hidden = false; }
    else ui.statusAction.hidden = true;
  }

  function groupOf(day) {
    const diff = todayNum - day.dayNum;
    if (diff <= 0) return { key: 'i-dag', label: 'I dag' };
    if (diff === 1) return { key: 'i-gaar', label: 'I går' };
    if (diff < 7) return { key: `d${day.dayNum}`, label: `${cap(weekdayOf(day))} ${fmtLong(day)}` };
    const w = isoWeek(day.dayNum);
    return { key: `w${w.year}-${w.week}`, label: `Uge ${w.week} · ${fmtWeekRange(w.monday)}` };
  }

  function renderList() {
    ui.more.replaceChildren();
    if (!data.members.length) {
      ui.list.replaceChildren(el('div', { class: 'empty' }, el('p', { text: 'Der er ingen indslag i feedet endnu.' })));
      return;
    }
    if (!cards.length) { ui.list.replaceChildren(renderEmpty()); return; }

    const groupCount = new Map();
    for (const c of cards) {
      const k = groupOf(c.primary.day).key;
      groupCount.set(k, (groupCount.get(k) || 0) + 1);
    }
    const out = [];
    const visible = cards.slice(0, limit);

    // Intet i dag (kun uden filtre)
    if (activeCount(state) === 0 && groupOf(visible[0].primary.day).key !== 'i-dag') {
      const gen = parseDate(data.feed.generated);
      out.push(el('section', { class: 'day', 'aria-labelledby': 'day-i-dag' },
        el('h2', { class: 'day-head', id: 'day-i-dag' }, 'I dag'),
        el('p', { class: 'day-empty', text: `Intet nyt endnu i dag.${gen ? ` Sidst opdateret ${fmtStamp(gen, now)}.` : ''}` })));
    }

    let group = null;
    let ul = null;
    let dividerDone = !lastVisit || state.nye;
    let seenNew = false;
    for (const card of visible) {
      const g = groupOf(card.primary.day);
      if (!group || group.key !== g.key) {
        group = g;
        const count = groupCount.get(g.key) || 0;
        ul = el('ul', { class: 'cards' });
        out.push(el('section', { class: 'day', 'aria-labelledby': `day-${g.key}` },
          el('h2', { class: 'day-head', id: `day-${g.key}` },
            el('span', { text: g.label }),
            el('span', { class: 'n' }, fmtNum(count), hidden(' indslag'))),
          ul));
      }
      const isNew = card.primary.isNew;
      if (!dividerDone && seenNew && !isNew) {
        ul.append(el('li', { class: 'lastvisit' }, `Her slap du sidst · ${fmtWhen(lastVisit, now)}`));
        dividerDone = true;
      }
      if (isNew) seenNew = true;
      ul.append(el('li', null, state.vis === 'kompakt' ? renderRow(card) : renderCard(card)));
    }
    ui.list.classList.toggle('is-compact', state.vis === 'kompakt');
    ui.list.replaceChildren(...out);

    if (cards.length > limit) {
      const next = Math.min(PAGE_SIZE, cards.length - limit);
      ui.more.append(el('button', {
        type: 'button', class: 'btn',
        onclick: () => {
          const first = limit;
          limit += PAGE_SIZE;
          renderStatus();
          renderList();
          ui.list.querySelectorAll('article .title a')[first]?.focus();
        },
      }, `Vis flere (${fmtNum(next)})`));
    }
  }

  function timeLabel(m) {
    const c = m.day;
    const diff = todayNum - c.dayNum;
    const clock = `kl. ${c.hh}.${c.mm}`;
    if (m.dateQuality === 'url' || m.dateQuality === 'liste') return diff <= 0 ? 'i dag' : diff === 1 ? 'i går' : fmtShort(c);
    if (m.dateQuality === 'fundet') return diff <= 1 ? `fundet ${clock}` : `fundet ${fmtShort(c)}`;
    return diff <= 1 ? clock : fmtShort(c);
  }

  function timeEl(m) {
    return el('time', { datetime: new Date(m.time).toISOString() }, timeLabel(m));
  }
  function sep() {
    return el('span', { class: 'sep', 'aria-hidden': 'true', text: '·' });
  }
  function langAttr(m) {
    return m.lang && m.lang !== 'da' ? m.lang : null;
  }

  function titleLink(m) {
    return el('a', { href: m.url, target: '_blank', rel: 'noopener' },
      el('span', { lang: langAttr(m) }, m.title),
      el('span', { class: 'ext', 'aria-hidden': 'true', text: ' ↗' }),
      hidden(' (åbner i nyt vindue)'));
  }

  function srcButton(src) {
    return el('button', {
      type: 'button', class: 'src',
      onclick: () => { addFilter('kilde', src.id); },
    }, hidden('Filtrér på kilden '), src.name);
  }

  function renderCard(card) {
    const m = card.primary;
    const src = m.source;
    const others = state.saml ? card.others : [];
    const newOthers = others.filter((o) => o.isNew).length;
    const titleId = `t-${m.id}`;

    const badges = [];
    if (src.paywall === 'ja' || src.paywall === 'delvis') badges.push(el('span', { class: 'badge' }, icon('laas'), 'Betalingsmur'));
    if (m.lang === 'en' || m.lang === 'sv') {
      badges.push(el('span', { class: 'badge' }, m.lang.toUpperCase(), hidden(m.lang === 'en' ? ' (på engelsk)' : ' (på svensk)')));
    }
    if (!m.reviewed) badges.push(el('span', { class: 'badge badge-warn' }, 'ikke vurderet'));
    if (newOthers) badges.push(el('span', { class: 'badge badge-new' }, `+${newOthers} ${newOthers === 1 ? 'ny' : 'nye'}`));

    const meta = el('div', { class: 'meta' },
      el('span', { class: 'dot', 'aria-hidden': 'true' }), icon(m.cat.icon),
      srcButton(src), sep(), el('span', { text: m.cat.short }),
      src.owner ? [sep(), el('span', { text: `udgivet af ${src.owner}` })] : null,
      sep(), timeEl(m),
      badges.length ? el('span', { class: 'badges' }, badges) : null);

    const genre = m.isHead && m.genre !== 'nyhed' ? data.genres.get(m.genre)?.label : '';

    let body = null;
    if (m.lang !== 'da' && m.summary) {
      body = [
        el('p', { class: 'teaser summary' }, el('span', { class: 'badge badge-auto' }, 'Auto-resumé'), m.summary),
        m.teaser ? el('details', { class: 'orig' },
          el('summary', null, `Original tekst (${m.lang === 'sv' ? 'svensk' : 'engelsk'})`),
          el('p', { lang: m.lang }, truncate(m.teaser, TEASER_MAX))) : null,
      ];
    } else if (m.teaser) {
      body = el('p', { class: 'teaser', lang: langAttr(m) }, truncate(m.teaser, TEASER_MAX));
    }

    const topics = m.topics.slice(0, 2).map((t) => el('button', {
      type: 'button', class: 'topic', onclick: () => addFilter('tema', t),
    }, hidden('Filtrér på tema: '), topicName(data, t)));

    const also = others.length ? el('details', { class: 'also' },
      el('summary', null, `+${others.length} ${others.length === 1 ? 'anden kilde' : 'andre kilder'}`, icon('pil-ned')),
      el('ul', null, others.map((o) => el('li', { class: 'cat', style: catStyle(o.cat) },
        el('div', { class: 'meta' },
          el('span', { class: 'dot', 'aria-hidden': 'true' }), icon(o.cat.icon),
          el('strong', { text: o.source.name }), sep(), el('span', { text: o.cat.short }), sep(), timeEl(o),
          o.isNew ? el('span', { class: 'badges' }, el('span', { class: 'badge badge-new' }, 'ny')) : null),
        titleLink(o))))) : null;

    return el('article', { class: `card cat${m.isNew ? ' is-new' : ''}`, style: catStyle(m.cat), 'aria-labelledby': titleId },
      meta,
      genre ? el('p', { class: 'genre', text: genre }) : null,
      el('h3', { class: 'title', id: titleId }, m.isNew ? hidden('Ny: ') : null, titleLink(m)),
      body,
      topics.length || also ? el('div', { class: 'foot' }, topics, also) : null);
  }

  function renderRow(card) {
    const m = card.primary;
    const titleId = `t-${m.id}`;
    return el('article', { class: `row cat${m.isNew ? ' is-new' : ''}`, style: catStyle(m.cat), 'aria-labelledby': titleId },
      timeEl(m),
      el('span', { class: 'dot', 'aria-hidden': 'true' }),
      srcButton(m.source),
      el('h3', { class: 'title', id: titleId }, m.isNew ? hidden('Ny: ') : null, titleLink(m)));
  }

  function addFilter(group, value) {
    change((s) => { if (!s[group].includes(value)) s[group] = [...s[group], value]; });
    toList();
  }

  /** Efter et klik i listen eller overblikket: vis toppen af listen og flyt fokus til statuslinjen. */
  function toList() {
    if (ui.toolbar.getBoundingClientRect().top < 0) ui.toolbar.scrollIntoView({ block: 'start' });
    ui.status.focus({ preventScroll: true });
  }

  function renderEmpty() {
    const box = el('div', { class: 'empty' });
    const actions = el('div', { class: 'actions' });
    if (state.nye) {
      box.append(el('p', {
        text: lastVisit
          ? `Intet nyt siden dit sidste besøg ${fmtWhen(lastVisit, now)}.`
          : 'Intet er markeret som nyt, fordi siden ikke kender dit sidste besøg på denne enhed.',
      }));
      actions.append(el('button', { type: 'button', class: 'btn btn-primary', onclick: () => change((s) => { s.nye = false; }) }, 'Vis alle'));
      box.append(actions);
      return box;
    }
    const filters = activeFilters(data, state);
    const named = filters.filter((f) => f.key !== 'periode');
    const span = `de seneste ${state.periode} dage`;
    let msg;
    if (named.length === 1 && named[0].key === 'q') msg = `Intet om "${state.q}" ${span}.`;
    else if (named.length) msg = `Ingen indslag passer til ${named.map((f) => f.label).join(' + ')} ${span}.`;
    else msg = `Ingen indslag ${span}.`;
    box.append(el('p', { text: msg }));

    // Foreslå det filter, der giver flest indslag, når det fjernes
    let best = null;
    for (const f of filters) {
      const trial = structuredClone(state);
      removeFilter(trial, f);
      const n = applyFilters(data, trial, now).length;
      if (n > 0 && (!best || n > best.n)) best = { f, n };
    }
    if (best) {
      actions.append(el('button', {
        type: 'button', class: 'btn btn-primary',
        onclick: () => { change((s) => removeFilter(s, best.f)); ui.status.focus(); },
      }, `Fjern ${best.f.label} (viser ${fmtNum(best.n)})`));
    }
    if (filters.length) {
      actions.append(el('button', { type: 'button', class: 'btn', onclick: () => { change(resetFilters); ui.status.focus(); } }, 'Nulstil filtre'));
    }
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
  keepDemo(state.demo);
  const root = $('kilder-root');
  const bars = $('bars');

  let feed;
  try {
    feed = await loadFeed(state.demo);
  } catch (err) {
    console.warn('Kilderne kunne ikke indlæses:', err.message);
    root.replaceChildren(el('div', { class: 'panel', role: 'alert' },
      el('p', { text: 'Kildelisten kunne ikke indlæses. Prøv igen om lidt.' }),
      el('p', null, el('button', { type: 'button', class: 'btn', onclick: () => location.reload() }, 'Prøv igen'))));
    return;
  }
  if (state.demo) {
    demoize(feed, now);
    bars.replaceChildren(demoBar());
    bars.hidden = false;
  }

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
      feed.mode === 'fallback' ? 'Lige nu vises nye indslag ud fra regler og er mærket "ikke vurderet".' : ''),
    el('ul', { class: 'legend', 'aria-label': 'Kildernes sundhed' },
      Object.keys(HEALTH).map((h) => el('li', null, healthBadge(h), ` ${fmtNum(healthCount[h])}`)))));

  // Indholdsfortegnelse
  out.push(el('nav', { class: 'panel', 'aria-label': 'Kategorier' },
    el('ul', { class: 'toc' }, cats.map((c) => el('li', { class: 'cat', style: catStyle(c) },
      el('a', { href: `#kat-${c.id}` }, el('span', { class: 'dot', 'aria-hidden': 'true' }), c.name))))));

  for (const c of cats) {
    const list = direct.filter((s) => s.category === c.id).sort((a, b) => a.name.localeCompare(b.name, 'da'));
    out.push(el('section', { class: 'panel cat-section cat', id: `kat-${c.id}`, style: catStyle(c), 'aria-labelledby': `h-${c.id}` },
      el('h2', { id: `h-${c.id}` }, icon(c.icon), c.name),
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
    el('div', { class: 'who' },
      el('a', { href: s.homepage, target: '_blank', rel: 'noopener' }, s.name, hidden(' (åbner i nyt vindue)')),
      facts.length ? el('p', { class: 'facts', text: facts.join(' · ') }) : null,
      st?.last_error && s.health === 'roed' ? el('p', { class: 'facts', text: `Seneste fejl: ${truncate(st.last_error, 120)}` }) : null),
    healthBadge(s.health));
}
