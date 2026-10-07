// Affaldsfeed: søgefelt med forslag (WAI-ARIA combobox med flervalg) til Kilde og Sted.

import { el, icon, hidden, fmtNum } from './filters.js';

const MAX = 8;
let openOne = null; // kun én forslagsliste er åben ad gangen

// Klik udenfor lukker listen
document.addEventListener('pointerdown', (e) => {
  if (openOne && !openOne.root.contains(e.target)) openOne.close();
});

// To nøgler (å→aa, æ→ae, ø→oe og å→a, ø→o); uden accenter og tegn
export function searchKeys(text) {
  const s = String(text || '').toLowerCase();
  const fold = (t) => t.normalize('NFD').replace(/\p{M}/gu, '').replace(/[^a-z0-9]+/g, ' ').trim();
  const a = fold(s.replace(/å/g, 'aa').replace(/æ/g, 'ae').replace(/ø/g, 'oe'));
  const b = fold(s.replace(/å/g, 'a').replace(/æ/g, 'ae').replace(/ø/g, 'o'));
  return a === b ? [a] : [a, b];
}

// 1: navnet begynder med søgningen, 2: et ord gør, 0: intet træf
const rank = (keys, qs) => (keys.some((k) => qs.some((q) => k.startsWith(q))) ? 1
  : keys.some((k) => qs.some((q) => k.includes(` ${q}`))) ? 2 : 0);

// o: { id, label, placeholder, fieldIcon, listLabel, items: [{ key, name, ctx?, icon?, style?, order? }],
//      getCount, isSelected, onToggle, emptyCaption, emptyNone, noMatch, describe?, inTop? }
// describe(item): skjult tekst efter navnet; så skjules ctx for skærmlæsere
export function createCombobox(o) {
  const items = o.items.map((it) => ({ ...it, keys: it.keys || searchKeys(it.name) }));
  const input = el('input', {
    id: o.id, class: 'field', type: 'text', role: 'combobox', autocomplete: 'off', autocapitalize: 'off',
    spellcheck: 'false', 'aria-autocomplete': 'list', 'aria-expanded': 'false', 'aria-controls': `${o.id}-list`,
    placeholder: o.placeholder,
  });
  const cap = el('p', { class: 'cbx-cap', 'aria-hidden': 'true', text: o.emptyCaption });
  const list = el('ul', { id: `${o.id}-list`, role: 'listbox', 'aria-label': o.listLabel, 'aria-multiselectable': 'true' });
  const more = el('p', { class: 'cbx-more', 'aria-hidden': 'true' });
  const pop = el('div', { class: 'cbx-pop', hidden: true }, cap, list, more);
  const msg = el('p', { class: 'cbx-msg visually-hidden', id: `${o.id}-msg`, role: 'status' });
  const root = el('div', { class: 'cbx' },
    el('label', { for: o.id, class: 'visually-hidden', text: o.label }),
    el('div', { class: 'cbx-field' }, icon(o.fieldIcon), input), pop, msg);
  let shown = [];
  let active = -1;
  let timer = 0;
  const api = { root, input, close, refresh, isOpen: () => !pop.hidden };

  // Besked i role="status" (synlig eller skjult)
  function say(text, visible = false, delay = 0) {
    clearTimeout(timer);
    const put = () => { msg.textContent = text; msg.classList.toggle('visually-hidden', !visible); };
    if (delay) { msg.textContent = ''; timer = setTimeout(put, delay); } else put();
  }

  // Tomt felt: flest indslag. Ellers rang, type og navn
  function compute() {
    const qs = searchKeys(input.value).filter(Boolean);
    const top = !qs.length;
    const hits = top
      ? items.filter((it) => !o.inTop || o.inTop(it)).map((it) => [-o.getCount(it.key), it]).filter(([n]) => n < 0)
      : items.map((it) => [rank(it.keys, qs) * 100 + (it.order || 0), it]).filter(([r]) => r >= 100);
    hits.sort((a, b) => a[0] - b[0] || a[1].name.localeCompare(b[1].name, 'da'));
    return { top, list: hits.slice(0, MAX).map(([, it]) => it), total: hits.length };
  }

  // Navn fra indholdet, fx "Altinget, Fagmedie, 5 indslag"
  function option(it, i) {
    const n = o.getCount(it.key);
    const extra = o.describe ? o.describe(it) : '';
    const ico = it.icon === undefined ? null : it.icon ? icon(it.icon) : el('span');
    return el('li', {
      id: `${o.id}-o-${String(it.key).replace(/[^\w-]/g, '-')}`, role: 'option', 'data-i': i,
      'aria-selected': String(o.isSelected(it.key)), style: it.style || null,
      class: `cbx-opt${ico ? ' has-icon' : ''}${it.style ? ' cat' : ''}${n ? '' : ' is-zero'}`,
    }, icon('flueben', 'ck'), ico,
    el('span', { class: 'name' }, it.name, it.ctx ? [' ', el('span', { class: 'ctx', 'aria-hidden': extra ? 'true' : null, text: it.ctx })] : null,
      extra ? hidden(extra) : null), el('span', { class: 'n' }, fmtNum(n), hidden(' indslag')));
  }

  function update(pref, announce = true) {
    const r = compute();
    if (!r.total) { close(); say(r.top ? o.emptyNone : o.noMatch(input.value.trim()), true); return; }
    shown = r.list;
    list.replaceChildren(...shown.map(option));
    cap.hidden = !r.top;
    const cut = !r.top && r.total > MAX;
    more.textContent = `Viser ${MAX} af ${fmtNum(r.total)}. Skriv mere for at indsnævre.`;
    more.hidden = !cut;
    if (openOne && openOne !== api) openOne.close();
    openOne = api;
    pop.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    setActive(pref === 'first' ? 0 : pref === 'last' ? shown.length - 1 : -1);
    for (const nm of list.querySelectorAll('.name')) if (nm.scrollWidth > nm.clientWidth) nm.parentNode.title = nm.firstChild.data;
    pop.scrollIntoView({ block: 'nearest' });
    if (!announce) return;
    const count = cut ? `Viser ${MAX} af ${fmtNum(r.total)} forslag` : `${shown.length} forslag`;
    say(r.top ? `${o.emptyCaption}, ${count}` : count, false, 300);
  }

  function setActive(i) {
    list.querySelector('.is-active')?.classList.remove('is-active');
    active = shown[i] ? i : -1;
    if (active < 0) { input.removeAttribute('aria-activedescendant'); return; }
    const li = list.children[active];
    li.classList.add('is-active');
    input.setAttribute('aria-activedescendant', li.id);
    li.scrollIntoView({ block: 'nearest' });
  }

  function refresh() {
    if (pop.hidden) return;
    const a = active;
    update('none', false);
    if (a >= 0) setActive(Math.min(a, shown.length - 1));
  }

  function close() {
    pop.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    setActive(-1);
    if (openOne === api) openOne = null;
  }

  function choose(it) {
    const was = o.isSelected(it.key);
    input.value = '';
    close();
    o.onToggle(it.key);
    say(`${it.name} er ${was ? 'fravalgt' : 'valgt'}.`);
  }

  input.addEventListener('input', () => {
    if (input.value.trim()) update('first');
    else { close(); say(''); }
  });
  input.addEventListener('click', () => { if (pop.hidden) update('first'); });
  input.addEventListener('keydown', (e) => {
    if (e.isComposing) return;
    const isOpen = !pop.hidden;
    const k = e.key;
    const down = k === 'ArrowDown';
    if (down || k === 'ArrowUp') {
      const n = shown.length;
      if (e.altKey && down === isOpen) return; // Alt + ↓ åbner uden aktivt forslag, Alt + ↑ lukker
      e.preventDefault();
      if (e.altKey) { if (down) update('none'); else close(); }
      else if (!isOpen) update(down ? 'first' : 'last');
      else setActive(active < 0 ? (down ? 0 : n - 1) : (active + (down ? 1 : n - 1)) % n);
    } else if (k === 'Enter' && isOpen) {
      e.preventDefault();
      if (active >= 0) choose(shown[active]);
    } else if (k === 'Escape' && (isOpen || input.value)) {
      // Inderst først: listen, så teksten; ellers lukker tasten arket
      e.preventDefault();
      e.stopPropagation();
      if (isOpen) close();
      else { input.value = ''; say(''); }
    } else if (k === 'Tab') {
      close();
    } else if (isOpen && ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(k)) {
      setActive(-1);
    }
  });
  input.addEventListener('blur', close);
  // Berøring i arket: feltet øverst over tastaturet
  input.addEventListener('focus', () => { if (matchMedia('(pointer: coarse)').matches && root.closest('dialog')) root.scrollIntoView({ block: 'start' }); });
  pop.addEventListener('pointerdown', (e) => e.preventDefault()); // fokus bliver i feltet
  list.addEventListener('click', (e) => {
    const li = e.target.closest('[role="option"]');
    if (li) choose(shown[Number(li.dataset.i)]);
  });
  return api;
}
