/**
 * Collecte des paramètres saisis.
 *
 * Les champs du formulaire portent un nom « groupe.champ » identique aux
 * paramètres du moteur (engine/pvsim/params.py). La validation fait foi côté
 * Python ; ce module se contente de rassembler les valeurs. Les fonctions
 * pures ci-dessous sont testées sans navigateur (tests/unit/form.test.ts).
 */
import type { FieldError, ParamGroups } from '../engine/types';

export const PARAM_GROUPS = ['site', 'pv', 'battery', 'load', 'economics', 'optimisation'] as const;
const STORAGE_KEY = 'pvsim-form-v1';

/** Champs propres à l'interface (non transmis tels quels au moteur). */
export interface UiFields {
  batteryEnabled: boolean;
  weatherSource: 'auto' | 'openmeteo' | 'nasapower' | 'pvgis';
  weatherYear: number;
  loadUnit: 'kwh' | 'kw' | 'w';
}

export function collectParams(entries: Iterable<[string, string]>, ui: Pick<UiFields, 'batteryEnabled'>): ParamGroups {
  const params: ParamGroups = Object.fromEntries(PARAM_GROUPS.map((g) => [g, {}]));
  for (const [name, rawValue] of entries) {
    const [group, field, ...rest] = name.split('.');
    if (rest.length || !field || !(PARAM_GROUPS as readonly string[]).includes(group)) continue;
    const value = rawValue.trim();
    if (value === '') continue; // valeur par défaut du moteur
    params[group][field] = value;
  }
  if (!ui.batteryEnabled) {
    params.battery.capacity_kwh = 0;
    params.battery.power_kw = 0;
  }
  return params;
}

/**
 * Données « maison » du mode Conseil : champs nommés « house.champ »
 * (identiques à engine/pvsim/advisor.py, classe House). Les valeurs vides sont omises.
 */
export function collectHouse(entries: Iterable<[string, string]>): Record<string, string> {
  const house: Record<string, string> = {};
  for (const [name, rawValue] of entries) {
    const [group, field, ...rest] = name.split('.');
    if (group !== 'house' || !field || rest.length) continue;
    const value = rawValue.trim();
    if (value !== '') house[field] = value;
  }
  return house;
}

/** Regroupe les erreurs par champ ; les erreurs sans champ sont des erreurs générales. */
export function groupErrors(errors: FieldError[]): { byField: Map<string, string>; general: string[] } {
  const byField = new Map<string, string>();
  const general: string[] = [];
  for (const e of errors) {
    if (e.field && e.field.includes('.')) byField.set(e.field, e.message);
    else general.push(e.field ? `${e.field} : ${e.message}` : e.message);
  }
  return { byField, general };
}

// --- Liaison avec le DOM ---------------------------------------------------

export function formEntries(form: HTMLFormElement): [string, string][] {
  const out: [string, string][] = [];
  for (const el of Array.from(form.elements)) {
    if (!(el instanceof HTMLInputElement || el instanceof HTMLSelectElement) || !el.name || el.disabled) continue;
    if (el instanceof HTMLInputElement && (el.type === 'file' || el.type === 'button')) continue;
    if (el instanceof HTMLInputElement && (el.type === 'radio' || el.type === 'checkbox') && !el.checked) continue;
    out.push([el.name, el instanceof HTMLInputElement && el.type === 'checkbox' ? 'on' : el.value]);
  }
  return out;
}

export function readUi(form: HTMLFormElement): UiFields {
  const get = (name: string) => (form.elements.namedItem(name) as HTMLInputElement | HTMLSelectElement | null)?.value ?? '';
  const battery = form.elements.namedItem('ui.battery_enabled') as HTMLInputElement | null;
  return {
    batteryEnabled: !!battery?.checked,
    weatherSource: get('ui.weather_source') as UiFields['weatherSource'],
    weatherYear: Number(get('ui.weather_year')),
    loadUnit: get('ui.load_unit') as UiFields['loadUnit'],
  };
}

export function showFieldErrors(form: HTMLFormElement, byField: Map<string, string>): void {
  for (const el of Array.from(form.querySelectorAll<HTMLElement>('[data-error-for]'))) {
    el.textContent = '';
  }
  for (const el of Array.from(form.querySelectorAll('[aria-invalid="true"]'))) {
    el.removeAttribute('aria-invalid');
  }
  let first: HTMLElement | null = null;
  for (const [field, message] of byField) {
    const input = form.querySelector<HTMLElement>(`[name="${CSS.escape(field)}"]`);
    const slot = form.querySelector<HTMLElement>(`[data-error-for="${CSS.escape(field)}"]`);
    if (input) {
      input.setAttribute('aria-invalid', 'true');
      input.closest('details')?.setAttribute('open', '');
      first ??= input;
    }
    if (slot) slot.textContent = message;
  }
  first?.focus();
}

export function saveForm(form: HTMLFormElement, key = STORAGE_KEY): void {
  const state: Record<string, string | boolean> = {};
  for (const el of Array.from(form.elements)) {
    if (!(el instanceof HTMLInputElement || el instanceof HTMLSelectElement) || !el.name) continue;
    if (el instanceof HTMLInputElement && el.type === 'file') continue;
    if (el instanceof HTMLInputElement && el.type === 'radio') {
      if (el.checked) state[el.name] = el.value;
    } else if (el instanceof HTMLInputElement && el.type === 'checkbox') {
      state[el.name] = el.checked;
    } else {
      state[el.name] = el.value;
    }
  }
  try {
    localStorage.setItem(key, JSON.stringify(state));
  } catch {
    // Stockage indisponible : la saisie n'est simplement pas mémorisée.
  }
}

export function restoreForm(form: HTMLFormElement, key = STORAGE_KEY): void {
  let state: Record<string, string | boolean>;
  try {
    state = JSON.parse(localStorage.getItem(key) ?? '{}');
  } catch {
    return;
  }
  for (const el of Array.from(form.elements)) {
    if (!(el instanceof HTMLInputElement || el instanceof HTMLSelectElement) || !(el.name in state)) continue;
    const value = state[el.name];
    if (el instanceof HTMLInputElement && el.type === 'radio') el.checked = el.value === value;
    else if (el instanceof HTMLInputElement && el.type === 'checkbox') el.checked = value === true;
    else if (el instanceof HTMLInputElement && el.type === 'file') continue;
    else el.value = String(value);
  }
}

export function clearSavedForm(key = STORAGE_KEY): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // ignoré
  }
}
