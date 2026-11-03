/**
 * Orchestration de l'interface : formulaire -> données météo -> moteur -> résultats.
 * Aucun calcul scientifique ici : tout passe par le moteur Python (src/engine).
 */
import { browserCache } from './data/cache';
import { fetchWeather, lastCompleteYear, SOURCE_LABELS, type SourceChoice } from './data/weather';
import { EngineClient } from './engine/client';
import type { EngineResult, FieldError, OptimisationRow, SimulationResult, OptimisationResult } from './engine/types';
import { cashflowChart, dailyChart, monthlyChart, onThemeChange, optimisationChart } from './ui/charts';
import { clearSavedForm, collectParams, formEntries, groupErrors, readUi, restoreForm, saveForm, showFieldErrors } from './ui/form';
import { num } from './ui/format';
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
    showMessages([{ level: 'error', text: `Le moteur de calcul n'a pas pu démarrer : ${message}. Rechargez la page ; si le problème persiste, votre navigateur ne prend peut-être pas en charge WebAssembly.` }]);
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

async function ensureWeather(): Promise<string[]> {
  const ui = readUi(form);
  if (ui.weatherSource === 'pvgis') {
    if (weatherKey !== 'pvgis') throw new UserError('Importez un fichier TMY PVGIS, ou choisissez une source en ligne.');
    return [];
  }
  const latitude = Number(field('site.latitude').value);
  const longitude = Number(field('site.longitude').value);
  const year = ui.weatherYear;
  const key = `${ui.weatherSource}|${latitude.toFixed(2)}|${longitude.toFixed(2)}|${year}`;
  if (key === weatherKey) return [];

  setBusy(true, 'Téléchargement des données météo…');
  setStatus(weatherStatus, 'Téléchargement des données météo…');
  let response;
  try {
    response = await fetchWeather(ui.weatherSource as SourceChoice, { latitude, longitude, year }, weatherCache);
  } catch (err) {
    setStatus(weatherStatus, 'Données météo indisponibles.', 'bad');
    throw new UserError(
      `${err instanceof Error ? err.message : String(err)} Vous pouvez réessayer plus tard, choisir une autre source ou importer un fichier PVGIS.`,
    );
  }
  const res = await engine.call('set_weather', response.source, response.raw);
  if (!res.ok) {
    setStatus(weatherStatus, 'Données météo inutilisables.', 'bad');
    throw new EngineErrors(res.errors);
  }
  weatherKey = key;
  const w = res.weather;
  setStatus(
    weatherStatus,
    `${SOURCE_LABELS[response.source]} ${year}${response.fromCache ? ' (cache local)' : ''} · point ${num(w.latitude, 2)}, ${num(w.longitude, 2)} · ` +
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
  monthlyChart(r);
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

onThemeChange(() => {
  if (lastSimulation) drawSimulation(lastSimulation);
  if (lastOptimisation) optimisationChart(lastOptimisation.optimisation.rows, lastOptimisation.optimisation.objective);
});

// --- Service worker : cache de Pyodide et fonctionnement hors connexion -----
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js').catch(() => {
    // Sans service worker, le cache HTTP du navigateur prend le relais.
  });
}
