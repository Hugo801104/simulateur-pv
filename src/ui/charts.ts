/** Graphiques (Chart.js). Les couleurs viennent des variables CSS pour suivre le thème clair/sombre. */
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
  type ChartConfiguration,
} from 'chart.js';
import type { OptimisationRow, SimulationResult } from '../engine/types';
import { MONTHS, num } from './format';

Chart.register(BarController, BarElement, CategoryScale, LinearScale, LineController, LineElement, PointElement, Tooltip, Legend, Filler);

const charts = new Map<string, Chart>();

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function render(id: string, config: ChartConfiguration) {
  charts.get(id)?.destroy();
  const canvas = document.getElementById(id) as HTMLCanvasElement | null;
  if (!canvas) return;
  Chart.defaults.color = token('--text-muted');
  Chart.defaults.borderColor = token('--grid');
  Chart.defaults.font.family = token('--font-sans');
  charts.set(id, new Chart(canvas, config));
}

const baseOptions = (yTitle: string) => ({
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index' as const, intersect: false },
  plugins: {
    legend: { position: 'bottom' as const, labels: { boxWidth: 12, boxHeight: 12 } },
    tooltip: {
      callbacks: {
        label: (ctx: { dataset: { label?: string }; parsed: { y: number | null } }) =>
          `${ctx.dataset.label} : ${num(ctx.parsed.y, Math.abs(ctx.parsed.y ?? 0) < 10 ? 2 : 0)}`,
      },
    },
  },
  scales: { y: { title: { display: true, text: yTitle }, beginAtZero: true } },
});

export function monthlyChart(m: SimulationResult['monthly'], canvasId = 'chart-monthly') {
  const labels = m.month.map((i) => MONTHS[i - 1]);
  render(canvasId, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { type: 'bar', label: 'Autoconsommé direct', data: m.direct_kwh, backgroundColor: token('--c-self'), stack: 'pv' },
        { type: 'bar', label: 'Via la batterie', data: m.battery_discharge_kwh, backgroundColor: token('--c-battery'), stack: 'pv' },
        { type: 'bar', label: 'Injecté sur le réseau', data: m.export_kwh, backgroundColor: token('--c-export'), stack: 'pv' },
        { type: 'line', label: 'Consommation', data: m.load_kwh, borderColor: token('--c-load'), backgroundColor: token('--c-load'), pointRadius: 3, borderWidth: 2 },
      ],
    },
    options: { ...baseOptions('kWh'), scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true, title: { display: true, text: 'kWh' } } } },
  } as ChartConfiguration);
}

export function dailyChart(r: SimulationResult) {
  const d = r.daily_profile;
  render('chart-daily', {
    type: 'line',
    data: {
      labels: d.hour.map((h) => `${h} h`),
      datasets: [
        { label: 'Production PV', data: d.pv_kwh, borderColor: token('--c-pv'), backgroundColor: token('--c-pv-fill'), fill: true, pointRadius: 0, borderWidth: 2, tension: 0.3 },
        { label: 'Consommation', data: d.load_kwh, borderColor: token('--c-load'), pointRadius: 0, borderWidth: 2, tension: 0.3 },
        { label: 'Soutirage réseau', data: d.import_kwh, borderColor: token('--c-import'), borderDash: [5, 4], pointRadius: 0, borderWidth: 2, tension: 0.3 },
      ],
    },
    options: baseOptions('kWh par heure (moyenne annuelle)'),
  } as ChartConfiguration);
}

export function cashflowChart(r: SimulationResult) {
  const y = r.economics.yearly;
  render('chart-cash', {
    type: 'line',
    data: {
      labels: [0, ...y.year].map(String),
      datasets: [
        { label: 'Trésorerie cumulée', data: [-r.economics.capex_eur, ...y.cumulative_eur], borderColor: token('--c-self'), pointRadius: 0, borderWidth: 2 },
        { label: 'Cumul actualisé', data: [-r.economics.capex_eur, ...y.cumulative_discounted_eur], borderColor: token('--c-export'), borderDash: [5, 4], pointRadius: 0, borderWidth: 2 },
      ],
    },
    options: { ...baseOptions('€'), scales: { x: { title: { display: true, text: 'Année' } }, y: { title: { display: true, text: '€' } } } },
  } as ChartConfiguration);
}

type GridRow = Pick<OptimisationRow, 'pv_kwc' | 'battery_kwh' | 'npv_eur'> & { irr?: number | null };

export function optimisationChart(rows: GridRow[], objective: 'npv' | 'irr', canvasId = 'chart-opt') {
  const sizes = [...new Set(rows.map((r) => r.pv_kwc))].sort((a, b) => a - b);
  const batteries = [...new Set(rows.map((r) => r.battery_kwh))].sort((a, b) => a - b);
  const palette = ['--c-self', '--c-battery', '--c-export', '--c-pv', '--c-import', '--c-load'];
  render(canvasId, {
    type: 'line',
    data: {
      labels: sizes.map((s) => num(s, s % 1 ? 1 : 0)),
      datasets: batteries.map((b, i) => ({
        label: b === 0 ? 'Sans batterie' : `Batterie ${num(b, b % 1 ? 1 : 0)} kWh`,
        data: sizes.map((s) => {
          const row = rows.find((r) => r.pv_kwc === s && r.battery_kwh === b);
          if (!row) return null;
          return objective === 'irr' ? (row.irr == null ? null : row.irr * 100) : row.npv_eur;
        }),
        borderColor: token(palette[i % palette.length]),
        backgroundColor: token(palette[i % palette.length]),
        pointRadius: 2,
        borderWidth: 2,
      })),
    },
    options: {
      ...baseOptions(objective === 'irr' ? 'TRI (%)' : 'VAN (€)'),
      scales: {
        x: { title: { display: true, text: 'Puissance crête (kWc)' } },
        y: { title: { display: true, text: objective === 'irr' ? 'TRI (%)' : 'VAN (€)' } },
      },
    },
  } as ChartConfiguration);
}

/** Redessine les graphiques existants après un changement de thème. */
export function onThemeChange(redraw: () => void) {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', redraw);
}
