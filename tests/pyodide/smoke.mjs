#!/usr/bin/env node
/**
 * Test d'intégration : exécute le moteur Python dans Pyodide (WebAssembly),
 * avec les fichiers réellement servis par le site (static/pyodide/), et compare
 * les résultats au cas de référence calculé sous CPython.
 *
 *   node scripts/fetch-pyodide.mjs   (une fois)
 *   node tests/pyodide/smoke.mjs
 */
import { readdir, readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { bootEngine } from '../../src/engine/bootstrap.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const indexURL = join(root, 'static', 'pyodide') + '/';
const REL_TOL = 1e-6;

const t0 = performance.now();
const elapsed = () => `${((performance.now() - t0) / 1000).toFixed(1)} s`;

const { loadPyodide } = await import(pathToFileURL(join(indexURL, 'pyodide.mjs')).href);
const engineDir = join(root, 'engine', 'pvsim');
const engineFiles = {};
for (const f of (await readdir(engineDir)).filter((f) => f.endsWith('.py'))) {
  engineFiles[f] = await readFile(join(engineDir, f), 'utf8');
}

const { engine } = await bootEngine({
  indexURL,
  loadPyodide,
  fetchBytes: async (p) => new Uint8Array(await readFile(p)),
  engineFiles,
  onProgress: (step, detail) => console.log(`[${elapsed()}] ${detail}`),
});

const info = JSON.parse(engine.info());
console.log(`[${elapsed()}] Moteur prêt : pvlib ${info.pvlib}, numpy ${info.numpy}, pandas ${info.pandas}, scipy ${info.scipy}`);

const ref = JSON.parse(await readFile(join(root, 'engine', 'tests', 'reference_case.json'), 'utf8'));
const raw = await readFile(join(root, 'engine', 'tests', 'fixtures', ref.weather_fixture), 'utf8');

const check = (label, res) => {
  if (!res.ok) throw new Error(`${label} : ${JSON.stringify(res.errors)}`);
  return res;
};
check('météo', JSON.parse(engine.set_weather(ref.weather_source, raw)));

let t = performance.now();
const sim = check('simulation', JSON.parse(engine.simulate(JSON.stringify(ref.params))));
console.log(`[${elapsed()}] Simulation : ${(performance.now() - t).toFixed(0)} ms`);
t = performance.now();
const opt = check('optimisation', JSON.parse(engine.optimise(JSON.stringify(ref.params))));
console.log(`[${elapsed()}] Optimisation (${opt.optimisation.rows.length} combinaisons) : ${(performance.now() - t).toFixed(0)} ms`);

t = performance.now();
const house = { latitude: 45.76, longitude: 4.84, annual_kwh: 4500, roof_area_m2: 30 };
const advice = check('conseil', JSON.parse(engine.advise(JSON.stringify(house))));
const rec = advice.advice.recommendation;
console.log(`[${elapsed()}] Conseil (${advice.advice.grid.length} configurations) : ${(performance.now() - t).toFixed(0)} ms — ` +
  `${rec.panels} panneaux, ${rec.pv_kwc} kWc, batterie ${rec.battery_kwh} kWh`);

// Conseil sur plusieurs années de météo (année représentative) : temps de calcul réaliste.
check('météo pluriannuelle', JSON.parse(engine.set_weather('openmeteo',
  await readFile(join(root, 'engine', 'tests', 'fixtures', 'openmeteo_lyon_2021_2023.json'), 'utf8'))));
t = performance.now();
const multi = check('conseil pluriannuel', JSON.parse(engine.advise(JSON.stringify({ ...house, electric_water_heater: 'oui' }))));
const years = Object.keys(multi.advice.production.yearly_yield).length;
console.log(`[${elapsed()}] Conseil sur ${years} ans de météo : ${(performance.now() - t).toFixed(0)} ms ` +
  `(≈ ${((performance.now() - t) * 10 / years / 1000).toFixed(1)} s pour 10 ans)`);

const get = (obj, path) => path.split('.').reduce((o, k) => o[k], obj);
let failures = 0;
for (const [key, expected] of Object.entries(ref.expected)) {
  const actual = key.startsWith('optimisation.') ? get(opt, key) : get(sim, key);
  const ok = Math.abs(actual - expected) <= REL_TOL * Math.max(Math.abs(expected), 1e-12);
  if (!ok) failures++;
  console.log(`${ok ? 'OK ' : 'ÉCHEC'} ${key} : Pyodide ${actual} / CPython ${expected}`);
}

if (failures) {
  console.error(`\n${failures} écart(s) entre Pyodide et CPython.`);
  process.exit(1);
}
console.log(`\nPyodide et CPython donnent les mêmes résultats (tolérance relative ${REL_TOL}).`);
process.exit(0);
