/// <reference lib="webworker" />
/**
 * Web Worker hébergeant Python (Pyodide) et le moteur pvsim.
 * Le calcul ne bloque jamais l'interface. Le worker reçoit l'URL du dossier
 * Pyodide dans son nom (voir client.ts), calculée à partir de l'URL de la page.
 */
import { bootEngine } from './bootstrap.js';
import type { EngineMethod, WorkerMessage, WorkerRequest } from './types';

declare const self: DedicatedWorkerGlobalScope;

// Sources Python du moteur, intégrées au bundle au moment du build.
const modules = import.meta.glob('../../engine/pvsim/*.py', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
const engineFiles = Object.fromEntries(Object.entries(modules).map(([path, src]) => [path.split('/').pop()!, src]));

const ALLOWED: EngineMethod[] = ['info', 'set_weather', 'set_load_csv', 'clear_load_csv', 'simulate', 'optimise', 'hourly_csv'];

const post = (msg: WorkerMessage) => self.postMessage(msg);

async function fetchBytes(url: string): Promise<Uint8Array> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} : HTTP ${res.status}`);
  return new Uint8Array(await res.arrayBuffer());
}

const indexURL = self.name;

const ready = (async () => {
  const { loadPyodide } = await import(/* @vite-ignore */ indexURL + 'pyodide.mjs');
  const booted = await bootEngine({
    indexURL,
    loadPyodide,
    fetchBytes,
    engineFiles,
    onProgress: (step, detail = '') => post({ type: 'progress', step, detail }),
  });
  const info = JSON.parse(booted.engine.info());
  post({ type: 'ready', info, totalBytes: booted.manifest.totalBytes });
  return booted.engine;
})();

ready.catch((err: unknown) => {
  post({ type: 'boot-error', message: err instanceof Error ? err.message : String(err) });
});

self.onmessage = async (event: MessageEvent<WorkerRequest>) => {
  const { id, method, args } = event.data;
  try {
    if (!ALLOWED.includes(method)) throw new Error(`Méthode inconnue : ${method}`);
    const engine = await ready;
    const result: string = engine[method](...args);
    post({ type: 'result', id, result });
  } catch (err) {
    post({ type: 'error', id, message: err instanceof Error ? err.message : String(err) });
  }
};
