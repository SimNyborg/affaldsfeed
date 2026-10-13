// Affaldsfeed: "Om Affaldsfeed" bag i-knappen i headeren. Al småtekst samles her: AI, opdatering og
// klager og sletning. Dialogen bygges første gang, knappen bruges.

import { el, icon, fmtWhen, parseDate } from './filters.js';

// Kontakt til klager og sletning. Adressen samles først i browseren.
const MAIL = ['jhn', 'jhn.dk'].join('@');

let dialog = null;
let statusEl = null;
let status = null; // {generated, mode, now}
let opts = { demo: '' };

/** Kobler i-knappen (#info-btn) til dialogen. demo: links til andre sider beholder ?demo=. */
export function setupInfo({ demo = '' } = {}) {
  opts = { demo };
  const btn = document.getElementById('info-btn');
  if (!btn) return;
  btn.addEventListener('click', () => {
    if (!dialog) build(btn);
    renderStatus();
    dialog.showModal();
    dialog.querySelector('h2').focus();
  });
}

/** Feedets tidspunkt og tilstand til linjen om opdatering. Kaldes, når feed.json er hentet. */
export function setInfoStatus(feed, now) {
  status = { generated: parseDate(feed?.generated), mode: feed?.mode, now };
  renderStatus();
}

function renderStatus() {
  if (!statusEl) return;
  const parts = [];
  if (status?.generated) parts.push(`Siden blev sidst opdateret ${fmtWhen(status.generated, status.now)}.`);
  if (status?.mode === 'fallback') parts.push('Vurderingen er forsinket lige nu, så nye nyheder vises efter faste regler.');
  statusEl.textContent = parts.join(' ');
  statusEl.hidden = !parts.length;
}

function link(href, text) {
  const internal = !/^[a-z]+:/i.test(href);
  const url = internal && opts.demo ? `${href}?demo=${encodeURIComponent(opts.demo)}` : href;
  return el('a', { href: url, 'data-internal': internal ? '' : null }, text);
}

function build(btn) {
  statusEl = el('p', { class: 'info-status', hidden: '' });
  const close = el('button', { type: 'button', class: 'icon-btn', 'aria-label': 'Luk' }, icon('luk'));
  dialog = el('dialog', { class: 'info', id: 'info-dialog', closedby: 'any', 'aria-labelledby': 'info-title' },
    el('div', { class: 'sheet-head' },
      el('h2', { id: 'info-title', tabindex: '-1' }, 'Om Affaldsfeed'),
      close),
    el('div', { class: 'info-body prose' },
      el('p', null, 'Affaldsfeed samler nyheder om affaldsområdet i Danmark fra kommuner, affaldsselskaber, '
        + 'myndigheder, medier, organisationer og forskning. Alle overskrifter linker til den oprindelige artikel. '
        + 'Under ', link('kilder.html', 'Om kilderne'), ' kan du se, hvilke kilder feedet bruger.'),
      el('h3', null, 'Udvalgt af AI'),
      el('p', null, 'En AI-model vurderer, hvilke nyheder der er relevante for kommunernes arbejde med affald. '
        + 'Den skriver også nyhedsoverblikket og højdepunkterne. Modellen ser kun titlen og kildens egen korte '
        + 'beskrivelse. Teksterne kan indeholde fejl, så tjek altid den oprindelige artikel.'),
      el('h3', null, 'Opdatering'),
      el('p', null, 'Nyhederne hentes flere gange i døgnet og vurderes om morgenen, om formiddagen og om '
        + 'eftermiddagen. Der kan derfor gå nogle timer, før en ny artikel kommer med.'),
      statusEl,
      el('h3', null, 'Klager og sletning'),
      el('p', null, 'Skriv til ', el('a', { href: `mailto:${MAIL}` }, MAIL), ', hvis du vil klage over noget på '
        + 'siden, have fjernet et opslag eller have din side taget af listen over kilder. Opslag og kilder '
        + 'fjernes inden for 24 timer.')));
  close.addEventListener('click', () => dialog.close());
  // Fokus tilbage til knappen, også i browsere, der ikke selv gør det
  dialog.addEventListener('close', () => { if (!dialog.contains(document.activeElement)) btn.focus(); });
  // Klik på baggrunden lukker i browsere uden closedby (både pointerdown og klik skal ramme baggrunden)
  if (!('closedBy' in HTMLDialogElement.prototype)) {
    let down = null;
    dialog.addEventListener('pointerdown', (e) => { down = e.target; });
    dialog.addEventListener('click', (e) => { if (e.target === dialog && down === dialog) dialog.close(); });
  }
  document.body.append(dialog);
}
