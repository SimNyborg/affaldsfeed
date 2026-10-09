// Affaldsfeed: Tidslinjen med de vigtigste begivenheder på affaldsområdet (KONTRAKTER §7.3).
// Data: data/timeline.json, ved ?demo=1 eksempelfilen. Claude vælger og skriver begivenhederne.

import { el, icon, hidden, sep, cph, fmtShort, fmtNum, parseDate, DAY_MS } from './filters.js';

const MONTHS = ['Januar', 'Februar', 'Marts', 'April', 'Maj', 'Juni', 'Juli', 'August', 'September', 'Oktober',
  'November', 'December'];
const PAGE = 12; // måneder med begivenheder ad gangen

/** "2026-10-07" → kalenderdele som cph() (y, m, d, dayNum). */
function dayOf(s) {
  const [y, m, d] = String(s || '').split('-').map(Number);
  if (!y || !m || !d) return null;
  return { y, m, d, dayNum: Date.UTC(y, m - 1, d) / DAY_MS };
}

const monthKey = (d) => `${d.y}-${String(d.m).padStart(2, '0')}`;

/** Demodata: ryk datoer og tider lige så mange hele dage frem, som eksemplet er gammelt. */
export function demoizeTimeline(tl, now) {
  const gen = parseDate(tl.generated);
  if (!gen) return;
  const days = cph(now).dayNum - cph(gen).dayNum;
  if (!days) return;
  const shiftIso = (s) => {
    const d = parseDate(s);
    return d ? new Date(d.getTime() + days * DAY_MS).toISOString().replace('.000Z', 'Z') : s;
  };
  const shiftDay = (s) => {
    const d = dayOf(s);
    return d ? new Date((d.dayNum + days) * DAY_MS).toISOString().slice(0, 10) : s;
  };
  tl.generated = shiftIso(tl.generated);
  for (const e of tl.events || []) {
    e.date = shiftDay(e.date);
    e.updated = shiftIso(e.updated);
    for (const r of e.items || []) r.published = shiftIso(r.published);
  }
}

/**
 * Tegner tidslinjen i root. `feedHref(story)` giver linket til historien i feedet.
 * Måneder har ankre (#2026-10). niveau= fra ældre links fjernes fra URL'en.
 */
export function createTimeline(root, tl, { feedHref }) {
  const events = (tl.events || [])
    .map((e) => ({ ...e, day: dayOf(e.date) }))
    .filter((e) => e.day)
    .sort((a, b) => b.day.dayNum - a.day.dayNum || (a.id < b.id ? -1 : 1));

  let shown = PAGE;
  dropLevelParam();

  const years = el('p', { class: 'tl-years' });
  const list = el('div', { class: 'tl-months' });
  const moreBtn = el('button', { type: 'button', class: 'btn', onclick: showMore }, 'Vis ældre');
  const more = el('div', { class: 'more-wrap', hidden: true }, moreBtn);

  root.replaceChildren(
    el('section', { class: 'panel tl-head', 'aria-labelledby': 'h-tl' },
      el('h1', { id: 'h-tl', text: 'Tidslinje' }),
      el('p', { class: 'lead', text: 'De store linjer på affaldsområdet: love, politiske aftaler, EU-regler og andre beslutninger med betydning for hele landet. Udvalgt af AI ud fra nyhederne i feedet. Kan indeholde fejl.' }),
      years),
    list, more);

  function groups(evs) {
    const out = [];
    for (const e of evs) {
      const key = monthKey(e.day);
      if (!out.length || out[out.length - 1].key !== key) out.push({ key, y: e.day.y, m: e.day.m, events: [] });
      out[out.length - 1].events.push(e);
    }
    return out;
  }

  // Valget "Kun milepæle" er fjernet; et gammelt link med niveau= viser alle begivenheder
  function dropLevelParam() {
    const url = new URL(location.href);
    if (!url.searchParams.has('niveau')) return;
    url.searchParams.delete('niveau');
    history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
  }

  function render(focusKey = null) {
    const all = groups(events);
    const part = all.slice(0, shown);

    if (!events.length) {
      list.replaceChildren(el('section', { class: 'panel tl-empty' },
        el('p', { text: 'Tidslinjen er tom endnu. De vigtigste begivenheder bliver tilføjet, efterhånden som nyhederne kommer.' }),
        el('p', null, el('a', { href: feedHref(null) }, 'Gå til feedet'))));
      years.replaceChildren();
      more.hidden = true;
      return;
    }
    // Spring til et år, når der er mere end ét
    const ys = [...new Set(all.map((g) => g.y))];
    const links = ys.length > 1 ? ys.map((y) => {
      const key = all.find((g) => g.y === y).key;
      return el('a', { href: `#${key}`, onclick: (ev) => { ev.preventDefault(); jump(key); } }, String(y));
    }) : [];
    years.replaceChildren(...(links.length
      ? [el('span', { class: 'tl-years-label', text: 'Spring til' }), ...links.flatMap((a, i) => (i ? [el('span', { class: 'sep', 'aria-hidden': 'true', text: '·' }), a] : [a]))]
      : []));

    list.replaceChildren(el('div', { class: 'panel list-panel tl-panel' }, part.map(monthEl)));
    more.hidden = all.length <= shown;
    if (focusKey) document.getElementById(`h-${focusKey}`)?.focus();
  }

  function monthEl(g) {
    return el('section', { class: 'tl-month', id: g.key, 'aria-labelledby': `h-${g.key}` },
      el('h2', { class: 'day-head tl-mhead', id: `h-${g.key}`, tabindex: '-1' },
        el('span', { text: `${MONTHS[g.m - 1]} ${g.y}` }),
        el('span', { class: 'n' }, fmtNum(g.events.length), hidden(g.events.length === 1 ? ' begivenhed' : ' begivenheder'))),
      el('ol', { class: 'tl-list' }, g.events.map(eventEl)));
  }

  function itemEl(r, e) {
    const p = parseDate(r.published);
    const c = p ? cph(p) : null;
    const when = c ? `${fmtShort(c)}${c.y !== e.day.y ? ` ${c.y}` : ''}` : null;
    return el('li', null,
      el('p', { class: 'who' }, el('b', { text: r.source_name }),
        when ? [sep(), el('time', { datetime: r.published }, when)] : null),
      el('p', { class: 'mtitle' },
        el('a', { href: r.url, target: '_blank', rel: 'noopener' }, r.title, hidden(' (åbner i nyt vindue)'))));
  }

  /**
   * Kompakt begivenhed: dato, markør, titel, resumé og "Læs 3 nyheder". En milepæl har en udfyldt
   * markør, og skærmlæseren hører "Milepæl:" før titlen.
   */
  function eventEl(e) {
    const titleId = `ev-${e.id}`;
    const n = (e.items || []).length;
    const milestone = e.level === 'milepael';
    return el('li', { class: `tl-ev${milestone ? ' is-milestone' : ''}` },
      el('article', { 'aria-labelledby': titleId },
        el('span', { class: 'tl-dot', 'aria-hidden': 'true' }),
        el('p', { class: 'tl-date' }, el('time', { datetime: e.date }, fmtShort(e.day))),
        el('div', { class: 'tl-body' },
          el('h3', { class: 'tl-title', id: titleId }, milestone ? hidden('Milepæl: ') : null, e.title),
          el('p', { class: 'tl-sum', text: e.summary }),
          n ? el('details', { class: 'tl-news' },
            el('summary', null, n === 1 ? 'Læs nyheden' : `Læs ${fmtNum(n)} nyheder`, icon('pil-ned')),
            el('ul', null, e.items.map((r) => itemEl(r, e))),
            e.story ? el('p', { class: 'tl-feed' }, el('a', { href: feedHref(e.story) }, 'Vis i feedet')) : null) : null)));
  }

  function showMore() {
    const all = groups(events);
    const next = all[shown]?.key;
    shown += PAGE;
    render(next);
  }

  /** Viser måneden (indlæser ældre efter behov), ruller til den og sætter ankeret. */
  function jump(key) {
    const all = groups(events);
    const i = all.findIndex((g) => g.key === key);
    if (i < 0) return;
    if (i >= shown) { shown = Math.ceil((i + 1) / PAGE) * PAGE; render(); }
    history.replaceState(null, '', `${location.pathname}${location.search}#${key}`);
    const h = document.getElementById(`h-${key}`);
    h?.scrollIntoView();
    h?.focus({ preventScroll: true });
  }

  render();
  const hash = location.hash.slice(1);
  if (/^\d{4}-\d{2}$/.test(hash)) jump(hash);
  addEventListener('hashchange', () => {
    const h = location.hash.slice(1);
    if (/^\d{4}-\d{2}$/.test(h)) jump(h);
  });
}
