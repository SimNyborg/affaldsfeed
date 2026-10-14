// Affaldsfeed: nyhedsoverblikket øverst (I dag, Ugen, Måneden, Året).
// Data kommer fra feed.json → overview.{dag,uge,maaned,aar} (KONTRAKTER §7–8).
// Foldet viser kun "Kort sagt"-linjen; "Vis hele" folder ud. af.overviewHidden = "0" betyder udfoldet.

import {
  el, icon, hidden, srPunct, cph, fmtWhen, fmtLongYear, parseDate, shortName,
  load, store, OV_PERIODS,
} from './filters.js';

const LABELS = { dag: 'I dag', uge: 'Ugen', maaned: 'Måneden', aar: 'Året' };
// Foldet står perioden i første linje, når den ikke er I dag: "Nyhedsoverblik for ugen senest opdateret ..."
const FOR = { uge: 'for ugen', maaned: 'for måneden', aar: 'for året' };
const EMPTY = {
  dag: 'Dagens overblik kommer efter kl. 07.25.',
  uge: 'Ugens overblik kommer efter kl. 07.25.',
  maaned: 'Månedens overblik kommer efter kl. 07.25.',
  aar: 'Årets overblik kommer mandag efter kl. 07.25.',
};
const KEY = 'af.overviewHidden';

/**
 * createOverview(root, {data, now, getState, onPeriod, onStory})
 * - onPeriod(p): fanen er skiftet (app.js skriver ?overblik=)
 * - onStory(ids): "+N" er klikket (app.js sætter ?story=)
 * Returnerer {render, setFiltersActive}.
 */
export function createOverview(root, { data, now, getState, onPeriod, onStory }) {
  let filtersActive = false;
  const overviews = data.feed.overview || {};
  // Foldningen holdes i en variabel; lagringen er kun en bekvemmelighed (localStorage kan kaste)
  let open = load(KEY) === '0';
  const isOpen = () => open;

  const per = el('span', { class: 'ov-per' });
  const upd = el('span', { class: 'ov-upd' });
  const toggleText = el('span');
  const toggle = el('button', {
    type: 'button', class: 'btn-text ov-toggle', 'aria-expanded': 'false', 'aria-controls': 'ov-body',
    onclick: () => { open = !open; store(KEY, open ? '0' : '1'); render(); },
  }, toggleText, hidden(' overblikket'), icon('pil-ned'));
  const short = el('p', { class: 'ov-short' });

  const tabs = OV_PERIODS.map((p) => el('button', {
    type: 'button', role: 'tab', id: `ov-tab-${p}`, 'aria-controls': 'ov-panel', onclick: () => select(p, false),
  }, LABELS[p]));
  const tablist = el('div', { class: 'seg seg-tabs', role: 'tablist', 'aria-label': 'Periode for overblikket' }, tabs);
  tablist.addEventListener('keydown', (e) => {
    const i = OV_PERIODS.indexOf(getState().overblik);
    const n = OV_PERIODS.length;
    const next = { ArrowRight: (i + 1) % n, ArrowLeft: (i + n - 1) % n, Home: 0, End: n - 1 }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    select(OV_PERIODS[next], true);
  });
  const panel = el('div', { class: 'ov-panel', id: 'ov-panel', role: 'tabpanel', tabindex: '0' });
  const body = el('div', { class: 'ov-body', id: 'ov-body' }, tablist, panel);

  root.replaceChildren(
    el('div', { class: 'ov-head' },
      el('div', { class: 'ov-label' }, el('h2', { id: 'ov-title', text: 'Nyhedsoverblik' }), per, upd),
      toggle),
    short, body);
  root.setAttribute('aria-labelledby', 'ov-title');

  function select(p, focusTab) {
    if (p !== getState().overblik) onPeriod(p);
    render();
    if (focusTab) tabs[OV_PERIODS.indexOf(p)].focus();
  }

  function current(period) {
    const ov = overviews[period];
    return ov && Array.isArray(ov.bullets) ? ov : null;
  }

  function render() {
    const period = getState().overblik;
    const ov = current(period);
    const open = isOpen();
    const generated = ov ? parseDate(ov.generated) || now : null;

    // "Nyhedsoverblik senest opdateret fredag kl. 23.28". Foldet står en anden periode end I dag med
    // ("for ugen"); udfoldet viser fanerne perioden
    per.textContent = !open && FOR[period] ? ` ${FOR[period]}` : '';
    upd.textContent = ov ? ` senest opdateret ${fmtWhen(generated, now)}` : '';
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    toggleText.textContent = open ? 'Vis mindre' : 'Vis hele';
    root.classList.toggle('is-open', open);

    // Foldet: hovedlinjen, afkortet
    short.hidden = open;
    short.classList.toggle('is-empty', !ov);
    short.replaceChildren(...(ov ? headline(ov.headline) : [emptyText(period)]));

    // Udfoldet: faner, meta, hovedlinje, punkter og bund
    body.hidden = !open;
    tabs.forEach((t, i) => {
      const on = OV_PERIODS[i] === period;
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      t.tabIndex = on ? 0 : -1;
    });
    panel.setAttribute('aria-labelledby', `ov-tab-${period}`);
    panel.replaceChildren(...panelContent(period, ov));
  }

  /** "Kort sagt:" i fed, resten almindelig. */
  function headline(text) {
    const m = /^(Kort sagt:)\s*/.exec(text || '');
    return m ? [el('b', { text: m[1] }), ' ', text.slice(m[0].length)] : [text || ''];
  }

  function emptyText(period) {
    // Før kl. 08 venter vi på morgenkørslen; senere på dagen er overblikket bare ikke skrevet endnu
    return Number(cph(now).hh) < 8 ? EMPTY[period] : 'Overblikket er ikke skrevet endnu. Det kommer ved en af de næste opdateringer.';
  }

  function panelContent(period, ov) {
    if (!ov) return [el('p', { class: 'ov-empty', text: emptyText(period) }), foot()];
    const out = [];
    if (ov.since) {
      // Perioden står allerede i fanerne; "Siden" siger, at data først begynder senere
      const [y, m, d] = String(ov.since).split('-').map(Number);
      if (y && m && d) out.push(el('p', { class: 'ov-meta', text: `Siden ${fmtLongYear({ y, m, d })}` }));
    }
    out.push(el('p', { class: 'ov-headline', text: ov.headline }));
    out.push(el('ul', { class: 'ov-bullets' }, ov.bullets.map((b) => el('li', null, el('p', { text: b.text }), refsLine(b)))));
    out.push(foot());
    return out;
  }

  /** Bunden har kun noten om filtre, når der er aktive filtre. Uden noten er den tom og skjult af CSS
   *  (.ov-foot:empty). Den skal altid findes: replaceChildren skriver null som teksten "null", og
   *  setFiltersActive sætter noten ind i den. */
  function foot() {
    return el('div', { class: 'ov-foot' }, filtersActive ? filterNote() : null);
  }

  function filterNote() {
    return el('p', { class: 'ov-note' }, icon('info'), el('span', { text: 'Overblikket dækker hele feedet, ikke kun dine filtre.' }));
  }

  // "Altinget, KEFM +2": de to første kilder linker til artiklerne; +N filtrerer feedet til historien
  function refsLine(bullet) {
    const seen = new Set();
    const refs = [];
    for (const id of bullet.item_ids || []) {
      const m = data.byId.get(id);
      if (m && !seen.has(m.id)) { seen.add(m.id); refs.push(m); }
    }
    if (!refs.length) return null;
    const units = [...new Set(refs.map((m) => m.unit))];
    let extra = 0;
    for (const u of units) for (const m of u.members) if (!seen.has(m.id)) { seen.add(m.id); extra += 1; }

    const shown = [refs[0]];
    const second = refs.find((m) => m.sourceId !== refs[0].sourceId) || refs[1];
    if (second) shown.push(second);
    const rest = refs.length - shown.length + extra;

    const links = [];
    shown.forEach((m, i) => {
      if (i) links.push(', ');
      // Kolonet står inline (intet mellemrum før det i navnet), og titler på engelsk og svensk har lang
      links.push(el('a', { href: m.url, target: '_blank', rel: 'noopener' },
        shortName(m.source.name), srPunct(':'),
        el('span', { class: 'visually-hidden' }, ' ', el('span', { lang: m.lang && m.lang !== 'da' ? m.lang : null }, m.title), ' (åbner i nyt vindue)')));
    });
    const more = rest > 0
      ? el('button', {
        type: 'button', class: 'btn-text ov-more', 'aria-label': `+${rest}: vis historien i feedet`,
        onclick: () => onStory(units.map((u) => u.id)),
      }, `+${rest}`)
      : null;
    return el('p', { class: 'ov-refs' }, hidden('Kilder: '), links, more ? ' ' : null, more);
  }

  return {
    render,
    setFiltersActive(v) {
      if (v === filtersActive) return;
      filtersActive = v;
      const f = panel.querySelector('.ov-foot');
      if (!f) return;
      const note = f.querySelector('.ov-note');
      if (v && !note) f.append(filterNote());
      if (!v && note) note.remove();
    },
  };
}
