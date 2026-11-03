/**
 * Orchestration de l'interface : formulaire -> données météo -> moteur -> résultats.
 * Aucun calcul scientifique ici : tout passe par le moteur Python (src/engine).
 */
import { browserCache } from './data/cache';
import { searchAddress, type AddressMatch } from './data/geocode';
import { fetchWeather, lastCompleteYear, SOURCE_LABELS, type SourceChoice } from './data/weather';
import { EngineClient } from './engine/client';
import type { AdviceResult, EngineResult, FieldError, OptimisationRow, SimulationResult, OptimisationResult } from './engine/types';
import { drawAdviceCharts, renderAdvice } from './ui/advice';
import { cashflowChart, dailyChart, monthlyChart, onThemeChange, optimisationChart } from './ui/charts';
import { clearSavedForm, collectHouse, collectParams, formEntries, groupErrors, readUi, restoreForm, saveForm, showFieldErrors } from './ui/form';
import { escapeHtml, num } from './ui/format';
import { renderOptimisation, renderSimulation, showMessages, type MessageLevel } from './ui/results';

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const form = $<HTMLFormElement>('params');
const field = <T extends HTMLInputElement | HTMLSelectElement = HTMLInputElement>(name: string) => form.elements.namedItem(name) as T;

const btnSimulate = $<HTMLButtonElement>('btn-simulate');
const btnOptimise = $<HTMLButtonElement>('btn-optimise');
const weatherCache = browserCache();

// --- Démarrage du moteur -----------------------------------------------------
const statusBox = $('engine-status');
const statusText = $('engine-status-text');
let engineReady = false;

const engine = new EngineClient(new URL('pyodide/', document.baseURI).href, {
  onProgress: (detail) => (statusText.textContent = `${detail}…`),
  onReady: (info, totalBytes) => {
    engineReady = true;
    statusBox.classList.add('ready');
    statusText.textContent = 'Moteur de calcul prêt';
    $('engine-versions').textContent =
      `Moteur ${info.engine_version} · pvlib ${info.pvlib} · NumPy ${info.numpy} · pandas ${info.pandas} · SciPy ${info.scipy} · ` +
      `${num(totalBytes / 1e6)} Mo téléchargés une fois puis mis en cache.`;
    setBusy(false);
  },
  onBootError: (message) => {
    statusBox.classList.add('error');
    statusText.textContent = 'Moteur indisponible';
    const text = `Le moteur de calcul n'a pas pu démarrer : ${message}. Rechargez la page ; si le problème persiste, votre navigateur ne prend peut-être pas en charge WebAssembly.`;
    showMessages([{ level: 'error', text }]);
    showMessages([{ level: 'error', text }], 'advice-messages');
  },
});

// --- Formulaire : valeurs initiales et affichage conditionnel ---------------
function setInitialValues() {
  field('ui.weather_year').value = String(lastCompleteYear());
  field('ui.weather_year').max = String(lastCompleteYear());
  try {
    field('site.timezone').value = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Paris';
  } catch {
    // valeur par défaut du HTML
  }
}

function updateVisibility() {
  const ui = readUi(form);
  form.querySelectorAll<HTMLElement>('[data-show-battery]').forEach((el) => (el.hidden = !ui.batteryEnabled));
  const loadMode = (form.querySelector<HTMLInputElement>('[name="load.mode"]:checked')?.value ?? 'profile');
  form.querySelectorAll<HTMLElement>('[data-show-load]').forEach((el) => (el.hidden = el.dataset.showLoad !== loadMode));
  const pvgis = ui.weatherSource === 'pvgis';
  form.querySelectorAll<HTMLElement>('[data-show-weather]').forEach((el) => (el.hidden = (el.dataset.showWeather === 'pvgis') !== pvgis));
}

setInitialValues();
restoreForm(form);
updateVisibility();
form.addEventListener('change', () => {
  updateVisibility();
  saveForm(form);
});

function setBusy(busy: boolean, label?: string) {
  btnSimulate.disabled = busy || !engineReady;
  btnOptimise.disabled = busy || !engineReady;
  $<HTMLButtonElement>('btn-advise').disabled = busy || !engineReady;
  if (busy && label) statusText.textContent = label;
  else if (engineReady) statusText.textContent = 'Moteur de calcul prêt';
}

// --- Données météo -----------------------------------------------------------
let weatherKey: string | null = null; // météo actuellement chargée dans le moteur
const weatherStatus = $('weather-status');

function setStatus(el: HTMLElement, text: string, state: 'ok' | 'bad' | '' = '') {
  el.textContent = text;
  el.className = `status-line ${state}`;
}

/** Météo du mode expert : fichier PVGIS déjà chargé, ou source en ligne choisie. */
async function ensureWeather(): Promise<string[]> {
  const ui = readUi(form);
  if (ui.weatherSource === 'pvgis') {
    if (weatherKey !== 'pvgis') throw new UserError('Importez un fichier TMY PVGIS, ou choisissez une source en ligne.');
    return [];
  }
  return ensureRemoteWeather(
    ui.weatherSource as SourceChoice,
    Number(field('site.latitude').value),
    Number(field('site.longitude').value),
    ui.weatherYear,
    weatherStatus,
  );
}

/**
 * Télécharge (ou relit en cache) une année de météo et la charge dans le moteur.
 * Renvoie les messages de repli éventuels. Partagé par les modes Conseil et expert.
 */
async function ensureRemoteWeather(
  choice: SourceChoice,
  latitude: number,
  longitude: number,
  year: number,
  statusEl: HTMLElement,
): Promise<string[]> {
  const key = `${choice}|${latitude.toFixed(2)}|${longitude.toFixed(2)}|${year}`;
  if (key === weatherKey) return [];

  setBusy(true, 'Téléchargement des données météo…');
  setStatus(statusEl, 'Téléchargement des données météo…');
  let response;
  try {
    response = await fetchWeather(choice, { latitude, longitude, year }, weatherCache);
  } catch (err) {
    setStatus(statusEl, 'Données météo indisponibles.', 'bad');
    throw new UserError(
      `${err instanceof Error ? err.message : String(err)} Réessayez plus tard ; en mode expert, vous pouvez aussi importer un fichier PVGIS.`,
    );
  }
  const res = await engine.call('set_weather', response.source, response.raw);
  if (!res.ok) {
    setStatus(statusEl, 'Données météo inutilisables.', 'bad');
    throw new EngineErrors(res.errors);
  }
  weatherKey = key;
  const w = res.weather;
  setStatus(
    statusEl,
    `Météo ${SOURCE_LABELS[response.source]} ${year}${response.fromCache ? ' (cache local)' : ''} · point ${num(w.latitude, 2)}, ${num(w.longitude, 2)} · ` +
      `${num(w.ghi_kwh_m2)} kWh/m²/an`,
    'ok',
  );
  return response.attempts.map((a) => `${SOURCE_LABELS[a.source]} indisponible (${a.error}) : repli sur ${SOURCE_LABELS[response.source]}.`);
}

$<HTMLInputElement>('pvgis-file').addEventListener('change', async (event) => {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  setStatus(weatherStatus, 'Lecture du fichier PVGIS…');
  try {
    await engine.ready;
    const res = await engine.call('set_weather', 'pvgis_tmy', await file.text());
    if (!res.ok) throw new EngineErrors(res.errors);
    weatherKey = 'pvgis';
    const w = res.weather;
    field('site.latitude').value = String(w.latitude);
    field('site.longitude').value = String(w.longitude);
    saveForm(form);
    setStatus(weatherStatus, `PVGIS (année type) · ${num(w.latitude, 3)}, ${num(w.longitude, 3)} · ${num(w.ghi_kwh_m2)} kWh/m²/an · coordonnées du site reprises du fichier`, 'ok');
  } catch (err) {
    weatherKey = null;
    setStatus(weatherStatus, errorText(err), 'bad');
  }
});

// --- Courbe de charge --------------------------------------------------------
const loadStatus = $('load-status');
let loadFile: File | null = null;

async function loadCsv() {
  if (!loadFile) return;
  setStatus(loadStatus, 'Lecture de la courbe de charge…');
  try {
    await engine.ready;
    const res = await engine.call('set_load_csv', await loadFile.text(), field('site.timezone').value, readUi(form).loadUnit);
    if (!res.ok) throw new EngineErrors(res.errors);
    const l = res.load;
    const day = (iso: string) => new Date(iso).toLocaleDateString('fr-FR');
    setStatus(loadStatus, `${num(l.hours)} heures, du ${day(l.start)} au ${day(l.end)} · ${num(l.total_kwh)} kWh`, 'ok');
  } catch (err) {
    setStatus(loadStatus, errorText(err), 'bad');
    await engine.call('clear_load_csv').catch(() => {});
  }
}

$<HTMLInputElement>('load-file').addEventListener('change', (event) => {
  loadFile = (event.target as HTMLInputElement).files?.[0] ?? null;
  void loadCsv();
});
field<HTMLSelectElement>('ui.load_unit').addEventListener('change', () => void loadCsv());

// --- Calculs -----------------------------------------------------------------
class UserError extends Error {}
class EngineErrors extends Error {
  constructor(readonly errors: FieldError[]) {
    super(errors.map((e) => e.message).join(' ; '));
  }
}

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function currentParams() {
  return JSON.stringify(collectParams(formEntries(form), readUi(form)));
}

let lastSimulation: SimulationResult | null = null;
let lastAdvice: AdviceResult | null = null;
let lastOptimisation: OptimisationResult | null = null;

function engineMessages(warnings: string[], notes: string[]): { level: MessageLevel; text: string }[] {
  return [
    ...warnings.map((text) => ({ level: 'warning' as const, text })),
    ...notes.map((text) => ({ level: 'info' as const, text })),
  ];
}

async function run<T>(label: string, task: () => Promise<EngineResult<T>>, onSuccess: (r: { ok: true } & T, notes: string[]) => void) {
  showFieldErrors(form, new Map());
  setBusy(true, label);
  try {
    const notes = await ensureWeather();
    setBusy(true, label);
    const res = await task();
    if (!res.ok) throw new EngineErrors(res.errors);
    onSuccess(res, notes);
  } catch (err) {
    if (err instanceof EngineErrors) {
      const { byField, general } = groupErrors(err.errors);
      showFieldErrors(form, byField);
      const items = general.map((text) => ({ level: 'error' as const, text }));
      if (byField.size) items.unshift({ level: 'error', text: 'Certaines valeurs sont invalides : voir les champs signalés.' });
      showMessages(items);
    } else {
      showMessages([{ level: 'error', text: errorText(err) }]);
    }
  } finally {
    setBusy(false);
  }
}

function drawSimulation(r: SimulationResult) {
  renderSimulation(r);
  monthlyChart(r.monthly);
  dailyChart(r);
  cashflowChart(r);
}

function simulate() {
  saveForm(form);
  return run('Simulation en cours…', () => engine.call('simulate', currentParams()), (r, notes) => {
    lastSimulation = r;
    showMessages(engineMessages([...notes, ...r.warnings], r.notes));
    drawSimulation(r);
  });
}

function applyRow(row: OptimisationRow) {
  field('pv.peak_power_kwc').value = String(row.pv_kwc);
  const battery = field('ui.battery_enabled');
  battery.checked = row.battery_kwh > 0;
  if (row.battery_kwh > 0) {
    field('battery.capacity_kwh').value = String(row.battery_kwh);
    field('battery.power_kw').value = String(row.battery_kw);
  }
  updateVisibility();
  void simulate().then(() => $('sim-results').scrollIntoView({ behavior: 'smooth', block: 'start' }));
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  void simulate();
});

btnOptimise.addEventListener('click', () => {
  saveForm(form);
  void run('Optimisation en cours…', () => engine.call('optimise', currentParams()), (r, notes) => {
    lastOptimisation = r;
    showMessages(engineMessages([...notes, ...r.warnings], r.notes));
    renderOptimisation(r, applyRow);
    optimisationChart(r.optimisation.rows, r.optimisation.objective);
    $('opt-results').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
});

$('btn-export').addEventListener('click', async () => {
  const res = await engine.call('hourly_csv');
  if (!res.ok) return showMessages([{ level: 'error', text: res.errors[0].message }]);
  const url = URL.createObjectURL(new Blob(['﻿' + res.csv], { type: 'text/csv;charset=utf-8' }));
  const a = Object.assign(document.createElement('a'), { href: url, download: 'simulation-horaire.csv' });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

$('geolocate').addEventListener('click', () => {
  if (!('geolocation' in navigator)) return showMessages([{ level: 'warning', text: 'Géolocalisation non disponible dans ce navigateur.' }]);
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      field('site.latitude').value = pos.coords.latitude.toFixed(4);
      field('site.longitude').value = pos.coords.longitude.toFixed(4);
      saveForm(form);
    },
    (err) => showMessages([{ level: 'warning', text: `Position non obtenue : ${err.message}` }]),
    { timeout: 10_000 },
  );
});

$('btn-reset').addEventListener('click', () => {
  clearSavedForm();
  form.reset();
  setInitialValues();
  updateVisibility();
  showFieldErrors(form, new Map());
});

// --- Onglets -----------------------------------------------------------------
const tabs = { conseil: $('tab-conseil'), expert: $('tab-expert') };
function showTab(name: keyof typeof tabs) {
  for (const [key, tab] of Object.entries(tabs)) {
    const active = key === name;
    tab.setAttribute('aria-selected', String(active));
    $(`view-${key}`).hidden = !active;
  }
  // Les graphiques d'une vue masquée n'ont pas de taille : on les redessine.
  if (name === 'expert' && lastSimulation) drawSimulation(lastSimulation);
  if (name === 'conseil' && lastAdvice) drawAdviceCharts(lastAdvice);
  try {
    localStorage.setItem('pvsim-tab', name);
  } catch {
    // ignoré
  }
}
tabs.conseil.addEventListener('click', () => showTab('conseil'));
tabs.expert.addEventListener('click', () => showTab('expert'));
try {
  if (localStorage.getItem('pvsim-tab') === 'expert') showTab('expert');
} catch {
  // ignoré
}

// --- Mode Conseil --------------------------------------------------------------
const houseForm = $<HTMLFormElement>('house');
const HOUSE_KEY = 'pvsim-house-v1';
const houseField = (name: string) => houseForm.elements.namedItem(name) as HTMLInputElement;
const addressInput = $<HTMLInputElement>('address');
const addressStatus = $('address-status');
let addressMatches: AddressMatch[] = [];

try {
  houseField('house.timezone').value = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Paris';
} catch {
  // valeur par défaut du HTML
}
restoreForm(houseForm, HOUSE_KEY);
houseForm.addEventListener('change', () => saveForm(houseForm, HOUSE_KEY));
if (houseField('house.latitude').value) {
  setStatus(addressStatus, `Position : ${num(Number(houseField('house.latitude').value), 4)}, ${num(Number(houseField('house.longitude').value), 4)}`, 'ok');
}

function setLocation(match: AddressMatch) {
  houseField('house.latitude').value = match.latitude.toFixed(5);
  houseField('house.longitude').value = match.longitude.toFixed(5);
  addressInput.value = match.label;
  setStatus(addressStatus, `${match.label} · ${num(match.latitude, 4)}, ${num(match.longitude, 4)}`, 'ok');
  saveForm(houseForm, HOUSE_KEY);
}

let suggestTimer: ReturnType<typeof setTimeout> | undefined;
addressInput.addEventListener('input', () => {
  houseField('house.latitude').value = '';
  houseField('house.longitude').value = '';
  const exact = addressMatches.find((m) => m.label === addressInput.value);
  if (exact) return setLocation(exact);
  clearTimeout(suggestTimer);
  suggestTimer = setTimeout(async () => {
    try {
      addressMatches = await searchAddress(addressInput.value);
      $('address-list').innerHTML = addressMatches.map((m) => `<option value="${escapeHtml(m.label)}"></option>`).join('');
      setStatus(addressStatus, addressMatches.length ? 'Choisissez votre adresse dans la liste.' : '');
    } catch {
      setStatus(addressStatus, 'Recherche d’adresse indisponible pour le moment.', 'bad');
    }
  }, 300);
});

/** Localise l'adresse saisie si l'utilisateur n'a pas choisi de suggestion. */
async function ensureLocation(): Promise<void> {
  if (houseField('house.latitude').value && houseField('house.longitude').value) return;
  if (addressInput.value.trim().length < 3) throw new EngineErrors([{ field: 'house.latitude', message: 'Indiquez l’adresse de la maison.' }]);
  let matches: AddressMatch[];
  try {
    matches = await searchAddress(addressInput.value);
  } catch (err) {
    throw new UserError(`Recherche d'adresse impossible : ${errorText(err)}`);
  }
  if (!matches.length) throw new EngineErrors([{ field: 'house.latitude', message: 'Adresse introuvable : vérifiez-la ou choisissez une suggestion.' }]);
  setLocation(matches[0]);
}

houseForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  showFieldErrors(houseForm, new Map());
  showMessages([], 'advice-messages');
  setBusy(true, 'Préparation des conseils…');
  try {
    await ensureLocation();
    const lat = Number(houseField('house.latitude').value);
    const lon = Number(houseField('house.longitude').value);
    const notes = await ensureRemoteWeather('auto', lat, lon, lastCompleteYear(), addressStatus);
    setBusy(true, 'Comparaison des configurations…');
    const res = await engine.call('advise', JSON.stringify(collectHouse(formEntries(houseForm))));
    if (!res.ok) throw new EngineErrors(res.errors);
    lastAdvice = res.advice;
    showMessages([...notes, ...res.advice.notes].map((text) => ({ level: 'info' as const, text })), 'advice-messages');
    renderAdvice(res.advice);
    $('advice-results').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (err) {
    if (err instanceof EngineErrors) {
      const { byField, general } = groupErrors(err.errors);
      showFieldErrors(houseForm, byField);
      const items = general.map((text) => ({ level: 'error' as const, text }));
      if (byField.size) items.unshift({ level: 'error', text: 'Certaines informations sont manquantes ou invalides : voir les champs signalés.' });
      showMessages(items, 'advice-messages');
    } else {
      showMessages([{ level: 'error', text: errorText(err) }], 'advice-messages');
    }
  } finally {
    setBusy(false);
  }
});

/** Reporte la recommandation dans le mode expert pour l'affiner. */
$('btn-to-expert').addEventListener('click', () => {
  if (!lastAdvice) return;
  const r = lastAdvice.recommendation;
  const set = (name: string, value: string | number) => (field(name).value = String(value));
  set('site.latitude', houseField('house.latitude').value);
  set('site.longitude', houseField('house.longitude').value);
  set('site.timezone', houseField('house.timezone').value);
  set('pv.peak_power_kwc', r.pv_kwc);
  set('pv.tilt_deg', r.tilt_deg);
  set('pv.azimuth_deg', r.azimuths_deg[0]);
  set('pv.gamma_pdc_pct_per_c', -0.29);
  field('ui.battery_enabled').checked = r.battery_kwh > 0;
  if (r.battery_kwh > 0) {
    set('battery.capacity_kwh', r.battery_kwh);
    set('battery.power_kw', r.battery_kw);
  }
  form.querySelector<HTMLInputElement>('[name="load.mode"][value="profile"]')!.checked = true;
  set('load.annual_kwh', Math.round(lastAdvice.consumption.annual_kwh));
  field('ui.weather_source').value = 'auto';
  updateVisibility();
  saveForm(form);
  showTab('expert');
  showMessages(
    r.azimuths_deg.length > 1
      ? [{ level: 'warning', text: 'Le mode expert ne gère qu’une orientation : le pan est a été retenu. Le résultat diffère donc du conseil est + ouest.' }]
      : [{ level: 'info', text: 'Recommandation reportée : ajustez les paramètres puis lancez « Simuler ».' }],
  );
});

onThemeChange(() => {
  if (lastAdvice) drawAdviceCharts(lastAdvice);
  if (lastSimulation) drawSimulation(lastSimulation);
  if (lastOptimisation) optimisationChart(lastOptimisation.optimisation.rows, lastOptimisation.optimisation.objective);
});

// --- Service worker : cache de Pyodide et fonctionnement hors connexion -----
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js').catch(() => {
    // Sans service worker, le cache HTTP du navigateur prend le relais.
  });
}
