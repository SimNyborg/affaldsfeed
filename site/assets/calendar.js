// Affaldsfeed: kalender til et tidsrum over listen.
// Mønstret er WAI-ARIA APG's "Date Picker Dialog" med to valg: første valg er første dag, andet valg
// sidste dag (samme dag to gange giver kun den dag). Dialogen er modal: under 768 px et bundark,
// derover en lille boks under knappen. Esc, "Luk" og klik udenfor lukker uden at ændre noget.

import { el, icon, cap, fmtNum, fmtLong, MONTHS, WEEKDAYS, DAY_MS } from './filters.js';

// Ugen begynder mandag
const WEEK = [...WEEKDAYS.slice(1), WEEKDAYS[0]];

/** Dele af en lokal dag (dayNum): år, måned (0-11), dag og ugedag (mandag = 0). */
function partsOf(n) {
  const t = new Date(n * DAY_MS);
  return { y: t.getUTCFullYear(), m: t.getUTCMonth(), d: t.getUTCDate(), wd: (t.getUTCDay() + 6) % 7 };
}
const dayOf = (y, m, d) => Date.UTC(y, m, d) / DAY_MS;
const daysIn = (y, m) => new Date(Date.UTC(y, m + 1, 0)).getUTCDate();

/** Samme dato en måned frem eller tilbage, højst månedens sidste dag. */
function addMonths(n, delta) {
  const c = partsOf(n);
  const t = new Date(Date.UTC(c.y, c.m + delta, 1));
  return dayOf(t.getUTCFullYear(), t.getUTCMonth(), Math.min(c.d, daysIn(t.getUTCFullYear(), t.getUTCMonth())));
}

const longDay = (n) => {
  const c = partsOf(n);
  return fmtLong({ d: c.d, m: c.m + 1 });
};

/**
 * createDatePicker({ button, minDay, maxDay, today, getRange, getCounts, onPick })
 * - button: knappen, der åbner kalenderen (aria-expanded styres her)
 * - minDay, maxDay: første og sidste dag, der kan vælges (dayNum)
 * - getRange(): det aktuelle tidsrum {lo, hi} (null i en ende = åben) eller null
 * - getCounts(): Map dayNum → antal kort med de øvrige filtre (prikker og skærmlæsertekst)
 * - onPick(lo, hi): nyt tidsrum; onPick(null) betyder alle datoer
 */
export function createDatePicker({ button, minDay, maxDay, today, getRange, getCounts, onPick }) {
  let view = null; // { y, m } for den viste måned
  let focusDay = maxDay;
  let pending = null; // første dag, mens sidste dag vælges
  let hoverDay = null; // forhåndsvisning med mus
  let counts = new Map();

  const month = el('p', { class: 'dp-month', id: 'dp-month', 'aria-live': 'polite' });
  const prev = el('button', { type: 'button', class: 'icon-btn dp-nav dp-prev', 'aria-label': 'Forrige måned', onclick: () => shiftMonth(-1) }, icon('pil-ned'));
  const next = el('button', { type: 'button', class: 'icon-btn dp-nav dp-next', 'aria-label': 'Næste måned', onclick: () => shiftMonth(1) }, icon('pil-ned'));
  const body = el('tbody');
  const grid = el('table', { class: 'dp-grid', role: 'grid', 'aria-labelledby': 'dp-month', 'aria-multiselectable': 'true' },
    el('thead', null, el('tr', null, WEEK.map((w) => el('th', { scope: 'col', abbr: w }, w.slice(0, 2))))),
    body);
  const hint = el('p', { class: 'dp-hint', role: 'status' });
  const dlg = el('dialog', { class: 'dp', id: 'date-dialog', 'aria-label': 'Vælg datoer' },
    el('div', { class: 'dp-head' }, prev, month, next),
    grid,
    hint,
    el('div', { class: 'dp-foot' },
      el('button', { type: 'button', class: 'btn-text', onclick: () => finish(null) }, 'Alle datoer'),
      el('button', { type: 'button', class: 'btn-text', onclick: () => dlg.close() }, 'Luk')));
  // Klik udenfor lukker (closedby); browsere uden closedby får reserven nederst
  dlg.setAttribute('closedby', 'any');
  document.body.append(dlg);
  button.setAttribute('aria-controls', dlg.id);

  const wide = matchMedia('(min-width: 48em)');

  // ── Måneden ──

  function cell(n) {
    const c = partsOf(n);
    const out = n < minDay || n > maxDay;
    const k = counts.get(n) || 0;
    const label = `${WEEK[c.wd]} ${longDay(n)}${out ? '' : `, ${k ? `${fmtNum(k)} indslag` : 'ingen indslag'}`}`;
    return el('td', {
      class: `dp-day${!out && k ? ' has-news' : ''}`, 'data-day': n, tabindex: '-1', 'aria-label': label,
      'aria-disabled': out ? 'true' : null, 'aria-current': n === today ? 'date' : null,
    }, el('span', { class: 'dp-n', 'aria-hidden': 'true', text: String(c.d) }));
  }

  function renderMonth() {
    const { y, m } = view;
    month.textContent = `${cap(MONTHS[m])} ${y}`;
    const first = dayOf(y, m, 1);
    const n = daysIn(y, m);
    const lead = partsOf(first).wd;
    const rows = [];
    let tr = null;
    for (let i = 0; i < Math.ceil((lead + n) / 7) * 7; i++) {
      if (i % 7 === 0) { tr = el('tr'); rows.push(tr); }
      const d = i - lead + 1;
      tr.append(d >= 1 && d <= n ? cell(first + d - 1) : el('td', { class: 'dp-pad' }));
    }
    body.replaceChildren(...rows);
    // Pilene er altid i tabulatorrækken; uden for grænserne gør de intet (aria-disabled, ikke disabled,
    // så fokus ikke forsvinder, når man når grænsen)
    prev.setAttribute('aria-disabled', String(first <= minDay));
    next.setAttribute('aria-disabled', String(first + n - 1 >= maxDay));
    paint();
  }

  /** Tidsrum, valg og fokus: det valgte eller, mens man vælger, fra første dag til musen eller fokus. */
  function paint() {
    let lo = null;
    let hi = null;
    if (pending !== null) {
      const end = hoverDay ?? focusDay;
      lo = Math.min(pending, end);
      hi = Math.max(pending, end);
    } else {
      const r = getRange();
      if (r) { lo = r.lo ?? minDay; hi = r.hi ?? maxDay; }
    }
    for (const td of body.querySelectorAll('td[data-day]')) {
      const n = +td.dataset.day;
      const inside = lo !== null && n >= lo && n <= hi;
      td.classList.toggle('in-range', inside && lo !== hi);
      td.classList.toggle('is-start', inside && n === lo);
      td.classList.toggle('is-end', inside && n === hi);
      // Valgt er det, der faktisk er valgt; forhåndsvisningen er kun visuel. Som i APG's eksempel har
      // kun de valgte dage aria-selected, så skærmlæseren ikke siger "ikke valgt" ved hver dag.
      if (pending !== null ? n === pending : inside) td.setAttribute('aria-selected', 'true');
      else td.removeAttribute('aria-selected');
      td.tabIndex = n === focusDay ? 0 : -1;
    }
  }

  const cellOf = (n) => body.querySelector(`td[data-day="${n}"]`);

  function moveTo(n) {
    focusDay = Math.min(maxDay, Math.max(minDay, n));
    const c = partsOf(focusDay);
    if (c.y !== view.y || c.m !== view.m) {
      view = { y: c.y, m: c.m };
      renderMonth();
    } else {
      paint();
    }
    cellOf(focusDay)?.focus();
  }

  function shiftMonth(delta) {
    const btn = delta < 0 ? prev : next;
    if (btn.getAttribute('aria-disabled') === 'true') return;
    const t = new Date(Date.UTC(view.y, view.m + delta, 1));
    view = { y: t.getUTCFullYear(), m: t.getUTCMonth() };
    // Fokusdagen følger med til samme dato i den nye måned, inden for grænserne
    focusDay = Math.min(maxDay, Math.max(minDay, addMonths(focusDay, delta)));
    const c = partsOf(focusDay);
    if (c.y !== view.y || c.m !== view.m) view = { y: c.y, m: c.m };
    renderMonth();
  }

  // ── Valg ──

  function pick(n) {
    if (n < minDay || n > maxDay) return;
    focusDay = n;
    if (pending === null) {
      pending = n;
      hoverDay = null;
      hint.textContent = `Fra ${longDay(n)}. Vælg sidste dag.`;
      paint();
      cellOf(n)?.focus();
      return;
    }
    const lo = Math.min(pending, n);
    const hi = Math.max(pending, n);
    finish({ lo, hi });
  }

  function finish(range) {
    pending = null;
    dlg.close();
    if (range) onPick(range.lo, range.hi);
    else onPick(null);
  }

  body.addEventListener('click', (e) => {
    const td = e.target.closest('td[data-day]');
    if (td && td.getAttribute('aria-disabled') !== 'true') pick(+td.dataset.day);
  });
  body.addEventListener('pointerover', (e) => {
    if (pending === null) return;
    const td = e.target.closest('td[data-day]');
    if (!td || td.getAttribute('aria-disabled') === 'true' || +td.dataset.day === hoverDay) return;
    hoverDay = +td.dataset.day;
    paint();
  });
  body.addEventListener('pointerleave', () => {
    if (hoverDay === null) return;
    hoverDay = null;
    paint();
  });

  grid.addEventListener('keydown', (e) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const wd = partsOf(focusDay).wd;
    const moves = {
      ArrowRight: 1, ArrowLeft: -1, ArrowDown: 7, ArrowUp: -7, Home: -wd, End: 6 - wd,
    };
    let to = null;
    if (e.key in moves) to = focusDay + moves[e.key];
    else if (e.key === 'PageUp') to = addMonths(focusDay, -1);
    else if (e.key === 'PageDown') to = addMonths(focusDay, 1);
    else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      pick(focusDay);
      return;
    } else return;
    e.preventDefault();
    hoverDay = null;
    moveTo(to);
  });

  // ── Åbn og luk ──

  /** Fra 768 px: under knappen (over den, hvis der ikke er plads), altid inden for vinduet. */
  function place() {
    if (!wide.matches) {
      dlg.style.removeProperty('top');
      dlg.style.removeProperty('left');
      return;
    }
    const r = button.getBoundingClientRect();
    const w = dlg.offsetWidth;
    const h = dlg.offsetHeight;
    let top = r.bottom + 8;
    if (top + h > innerHeight - 8 && r.top - 8 - h >= 8) top = r.top - 8 - h;
    dlg.style.top = `${Math.max(8, top)}px`;
    dlg.style.left = `${Math.max(8, Math.min(r.left - 12, innerWidth - w - 8))}px`;
  }

  function open() {
    if (dlg.open) return;
    counts = getCounts();
    const r = getRange();
    pending = null;
    hoverDay = null;
    focusDay = Math.min(maxDay, Math.max(minDay, r ? (r.lo ?? r.hi) : maxDay));
    const c = partsOf(focusDay);
    view = { y: c.y, m: c.m };
    hint.textContent = 'Vælg første dag.';
    renderMonth();
    // Siden låses, mens kalenderen er åben; en klassisk rullebjælkes bredde bliver polstring (style.css)
    const root = document.documentElement;
    root.style.setProperty('--page-sbw', `${Math.max(0, innerWidth - root.clientWidth)}px`);
    dlg.showModal();
    place();
    button.setAttribute('aria-expanded', 'true');
    cellOf(focusDay)?.focus();
  }

  // Lukket (Esc, "Luk", klik udenfor eller et valg): et påbegyndt valg glemmes, og fokus går til knappen.
  // Lytter også på open-attributten, da close-hændelsen ikke kommer i alle browsere.
  let wasOpen = false;
  const afterClose = () => {
    if (dlg.open || !wasOpen) return;
    wasOpen = false;
    pending = null;
    hoverDay = null;
    button.setAttribute('aria-expanded', 'false');
    button.focus();
  };
  dlg.addEventListener('close', afterClose);
  new MutationObserver(() => { if (dlg.open) wasOpen = true; else afterClose(); })
    .observe(dlg, { attributes: true, attributeFilter: ['open'] });
  addEventListener('resize', () => { if (dlg.open) place(); });

  if (!('closedBy' in HTMLDialogElement.prototype)) {
    // Klik på baggrunden lukker, men kun når både pointerdown og klik var uden for boksen
    const outside = (e) => {
      if (e.target !== dlg) return false;
      const r = dlg.getBoundingClientRect();
      return !(r.top <= e.clientY && e.clientY <= r.bottom && r.left <= e.clientX && e.clientX <= r.right);
    };
    let downOutside = false;
    dlg.addEventListener('pointerdown', (e) => { downOutside = outside(e); });
    dlg.addEventListener('click', (e) => {
      const close = downOutside && outside(e);
      downOutside = false;
      if (close) dlg.close();
    });
  }

  button.setAttribute('aria-haspopup', 'dialog');
  button.setAttribute('aria-expanded', 'false');
  button.addEventListener('click', open);

  return { open, isOpen: () => dlg.open, close: () => dlg.close() };
}
