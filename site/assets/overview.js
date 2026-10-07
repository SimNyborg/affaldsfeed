// Affaldsfeed: AI-overblikket øverst (I dag, Ugen, Måneden, Året).
// Data kommer fra feed.json → overview.{dag,uge,maaned,aar} (KONTRAKTER §7–8).

import {
  el, icon, hidden, cph, fmtStamp, fmtShort, fmtLongYear, fmtNum, parseDate, shortName,
  load, store, OV_PERIODS,
} from './filters.js';

const LABELS = { dag: 'I dag', uge: 'Ugen', maaned: 'Måneden', aar: 'Året' };
const EMPTY = {
  dag: 'Dagens overblik kommer efter kl. 06.25.',
  uge: 'Ugens overblik kommer efter kl. 06.25.',
  maaned: 'Månedens overblik kommer efter kl. 06.25.',
  aar: 'Årets overblik kommer mandag efter kl. 06.25.',
};
// Hvor gammelt et overblik må være, før vi siger, at det ikke er opdateret som planlagt (timer)
const MAX_AGE_H = { uge: 18, maaned: 30, aar: 8 * 24 };
const KEY_HIDDEN = 'af.overviewHidden';

/**
 * createOverview(root, {data, now, getState, onPeriod, onStory})
 * - onPeriod(p): fanen er skiftet (app.js skriver ?overblik=)
 * - onStory(ids): "+N" er klikket (app.js sætter ?story=)
 * Returnerer {render, setFiltersActive}.
 */
export function createOverview(root, { data, now, getState, onPeriod, onStory }) {
  let filtersActive = false;
  const overviews = data.feed.overview || {};

  function render({ focusTab = false, focusToggle = false } = {}) {
    const period = getState().overblik;
    root.replaceChildren();

    if (load(KEY_HIDDEN) === '1') {
      root.className = 'panel overview is-collapsed';
      const show = el('button', {
        type: 'button', class: 'btn-text', 'aria-expanded': 'false',
        onclick: () => { store(KEY_HIDDEN, null); render({ focusToggle: true }); },
      }, 'Vis overblik');
      root.append(el('p', { text: 'AI-overblikket er skjult.' }), show);
      if (focusToggle) show.focus();
      return;
    }

    root.className = 'panel overview';
    const hide = el('button', {
      type: 'button', class: 'btn-text', 'aria-expanded': 'true', 'aria-controls': 'ov-body',
      onclick: () => { store(KEY_HIDDEN, '1'); render({ focusToggle: true }); },
    }, 'Skjul overblik');

    const tabs = OV_PERIODS.map((p) => el('button', {
      type: 'button', role: 'tab', id: `ov-tab-${p}`, 'aria-controls': 'ov-body',
      'aria-selected': p === period ? 'true' : 'false', tabindex: p === period ? '0' : '-1',
      onclick: () => select(p, false),
    }, LABELS[p]));

    const tablist = el('div', { class: 'seg', role: 'tablist', 'aria-label': 'Periode for overblikket' }, tabs);
    tablist.addEventListener('keydown', (e) => {
      const i = OV_PERIODS.indexOf(period);
      let next = null;
      if (e.key === 'ArrowRight') next = OV_PERIODS[(i + 1) % OV_PERIODS.length];
      else if (e.key === 'ArrowLeft') next = OV_PERIODS[(i + OV_PERIODS.length - 1) % OV_PERIODS.length];
      else if (e.key === 'Home') next = OV_PERIODS[0];
      else if (e.key === 'End') next = OV_PERIODS[OV_PERIODS.length - 1];
      if (next) { e.preventDefault(); select(next, true); }
    });

    const body = el('div', { class: 'ov-body', id: 'ov-body', role: 'tabpanel', tabindex: '0', 'aria-labelledby': `ov-tab-${period}` },
      panelContent(period));

    root.append(
      el('div', { class: 'ov-head' }, el('h2', { id: 'ov-title', text: 'Overblik' }), hide),
      tablist,
      body,
    );
    root.setAttribute('aria-labelledby', 'ov-title');
    if (focusTab) tabs[OV_PERIODS.indexOf(period)].focus();
    if (focusToggle) hide.focus();
  }

  function select(p, focusTab) {
    if (p !== getState().overblik) onPeriod(p);
    render({ focusTab });
  }

  function panelContent(period) {
    const ov = overviews[period] || null;
    const out = [];
    if (!ov || !Array.isArray(ov.bullets)) {
      // Før kl. 07 venter vi på morgenkørslen; senere på dagen er overblikket bare ikke skrevet endnu
      const early = Number(cph(now).hh) < 7;
      const text = early ? EMPTY[period] : 'Overblikket er ikke skrevet endnu. Det kommer ved en af de næste opdateringer.';
      out.push(el('p', { class: 'ov-empty', text }));
      if (filtersActive) out.push(filterNote());
      return out;
    }
    const generated = parseDate(ov.generated) || now;

    // Forældet overblik: vis tidspunktet tydeligt
    const stale = staleText(period, ov, generated);
    if (stale) out.push(el('p', { class: 'ov-note ov-stale' }, icon('advarsel'), el('span', { text: stale })));

    if (ov.since) {
      const [y, m, d] = String(ov.since).split('-').map(Number);
      if (y && m && d) out.push(el('p', { class: 'ov-period', text: `${LABELS[period]} (siden ${fmtLongYear({ y, m, d })})` }));
    }
    out.push(el('p', { class: 'ov-headline', text: ov.headline }));
    out.push(el('ul', { class: 'ov-bullets' }, ov.bullets.map((b) => el('li', null,
      el('p', { text: b.text }),
      refsLine(b),
    ))));
    out.push(el('p', { class: 'ov-meta' },
      `Opdateret ${fmtStamp(generated, now)} · bygget på ${fmtNum(ov.based_on || 0)} indslag · `,
      'Skrevet af Claude ud fra kilderne nedenfor. Kan indeholde fejl.'));
    if (filtersActive) out.push(filterNote());
    return out;
  }

  function staleText(period, ov, generated) {
    const end = parseDate(ov.window?.end) || generated;
    const early = Number(cph(now).hh) < 7;
    if (period === 'dag') {
      const diff = cph(now).dayNum - cph(end).dayNum;
      if (diff <= 0) return '';
      const from = diff === 1 ? 'Dette er gårsdagens overblik' : `Dette overblik er fra ${fmtShort(cph(end))}`;
      return `${from} (opdateret ${fmtStamp(generated, now)}). ${early ? 'Dagens overblik kommer efter kl. 06.25.' : 'Dagens overblik er forsinket.'}`;
    }
    const ageH = (now - generated) / 36e5;
    if (ageH > MAX_AGE_H[period]) {
      return `Overblikket blev sidst opdateret ${fmtStamp(generated, now)} og er ikke blevet opdateret som planlagt.`;
    }
    return '';
  }

  function filterNote() {
    return el('p', { class: 'ov-note' }, icon('info'),
      el('span', { text: 'Overblikket dækker hele feedet og tager ikke højde for dine filtre.' }));
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
      links.push(el('a', { href: m.url, target: '_blank', rel: 'noopener' },
        shortName(m.source.name), hidden(`: ${m.title} (åbner i nyt vindue)`)));
    });
    const more = rest > 0
      ? el('button', {
        type: 'button', class: 'ov-more', 'aria-label': `+${rest}: vis historien i feedet`,
        onclick: () => onStory(units.map((u) => u.id)),
      }, `+${rest}`)
      : null;
    return el('p', { class: 'ov-refs' }, hidden('Kilder: '), links, more);
  }

  return {
    render,
    setFiltersActive(v) {
      if (v === filtersActive) return;
      filtersActive = v;
      const body = root.querySelector('#ov-body');
      if (!body) return;
      const note = body.querySelector('.ov-note:not(.ov-stale)');
      if (v && !note) body.append(filterNote());
      if (!v && note) note.remove();
    },
  };
}
