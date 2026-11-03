/** Restitution des résultats (indicateurs, messages, tableau d'optimisation). */
import type { OptimisationResult, OptimisationRow, SimulationResult } from '../engine/types';
import { escapeHtml, eur, kwh, num, pct, years } from './format';

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

export type MessageLevel = 'error' | 'warning' | 'info';

export function showMessages(items: { level: MessageLevel; text: string }[], target = 'messages') {
  const box = $(target);
  box.innerHTML = items
    .map(({ level, text }) => `<div class="msg msg-${level}" role="${level === 'error' ? 'alert' : 'status'}">${escapeHtml(text)}</div>`)
    .join('');
}

function kpi(label: string, value: string, hint = '') {
  return `<div class="kpi"><div class="kpi-label">${label}</div><div class="kpi-value">${value}</div>${hint ? `<div class="kpi-hint">${hint}</div>` : ''}</div>`;
}

export function renderSimulation(r: SimulationResult) {
  const t = r.totals;
  const e = r.economics;
  $('results-empty').hidden = true;
  $('sim-results').hidden = false;

  $('kpis-energy').innerHTML = [
    kpi('Production annuelle', kwh(t.pv_kwh), `${num(r.specific_yield_kwh_per_kwc)} kWh/kWc`),
    kpi('Autoconsommation', pct(t.self_consumption_rate), 'part de la production consommée sur place'),
    kpi('Autoproduction', pct(t.self_sufficiency_rate), 'part de la consommation couverte'),
    kpi('Injection réseau', kwh(t.export_kwh)),
    kpi('Soutirage réseau', kwh(t.import_kwh), `sur ${kwh(t.load_kwh)} consommés`),
  ].join('');

  $('kpis-eco').innerHTML = [
    kpi('Investissement', eur(e.capex_eur), 'net des aides'),
    kpi('Gain année 1', eur(e.year1_savings_eur), `facture ${eur(e.year1_bill_without_pv_eur)} → ${eur(e.year1_bill_with_pv_eur)}`),
    kpi('Temps de retour', years(e.payback_years), `actualisé : ${years(e.discounted_payback_years)}`),
    kpi('VAN', `<span class="${e.npv_eur >= 0 ? 'pos' : 'neg'}">${eur(e.npv_eur)}</span>`, 'valeur actuelle nette'),
    kpi('TRI', e.irr == null ? '—' : pct(e.irr, 1), 'taux de rentabilité interne'),
    kpi('LCOE', e.lcoe_eur_per_kwh == null ? '—' : `${num(e.lcoe_eur_per_kwh * 100, 1)} c€/kWh`, 'coût actualisé du kWh produit'),
  ].join('');

  const w = r.weather;
  // Dates affichées en heure locale (les horodatages du moteur sont en UTC).
  const day = (iso: string) => new Date(iso).toLocaleDateString('fr-FR');
  const period = w.source === 'pvgis_tmy' ? 'année type' : `${day(w.start)} → ${day(w.end)}`;
  $('sim-context').textContent =
    `Météo : ${w.source_label}, ${period} · ` +
    `irradiation horizontale ${num(w.ghi_kwh_m2)} kWh/m² · dans le plan ${num(r.poa_kwh_m2)} kWh/m²`;
}

export function renderOptimisation(r: OptimisationResult, onApply: (row: OptimisationRow) => void) {
  const { rows, best, objective } = r.optimisation;
  $('results-empty').hidden = true;
  $('opt-results').hidden = false;

  $('opt-best').innerHTML = best
    ? `Meilleure combinaison (${objective === 'irr' ? 'TRI' : 'VAN'} maximale) : <strong>${num(best.pv_kwc, 1)} kWc</strong>` +
      `${best.battery_kwh > 0 ? ` avec <strong>${num(best.battery_kwh, 1)} kWh</strong> de batterie` : ' sans batterie'}` +
      ` — VAN ${eur(best.npv_eur)}, TRI ${best.irr == null ? '—' : pct(best.irr, 1)}, retour ${years(best.payback_years)}.`
    : 'Aucune combinaison rentable sur la grille testée.';

  const sorted = [...rows].sort((a, b) =>
    objective === 'irr' ? (b.irr ?? -Infinity) - (a.irr ?? -Infinity) : b.npv_eur - a.npv_eur,
  );
  const body = sorted
    .slice(0, 15)
    .map((row, i) => {
      const isBest = best && row.pv_kwc === best.pv_kwc && row.battery_kwh === best.battery_kwh;
      return `<tr class="${isBest ? 'best' : ''}">
        <td>${num(row.pv_kwc, 1)}</td><td>${num(row.battery_kwh, 1)}</td>
        <td>${eur(row.capex_eur)}</td><td class="${row.npv_eur >= 0 ? 'pos' : 'neg'}">${eur(row.npv_eur)}</td>
        <td>${row.irr == null ? '—' : pct(row.irr, 1)}</td><td>${years(row.payback_years)}</td>
        <td>${pct(row.self_consumption_rate)}</td><td>${pct(row.self_sufficiency_rate)}</td>
        <td><button type="button" class="btn-link" data-apply="${i}">Appliquer</button></td></tr>`;
    })
    .join('');
  $('opt-table').querySelector('tbody')!.innerHTML = body;
  $('opt-count').textContent = `${rows.length} combinaisons évaluées${rows.length > 15 ? ' (15 meilleures affichées)' : ''}.`;
  for (const btn of Array.from($('opt-table').querySelectorAll<HTMLButtonElement>('[data-apply]'))) {
    btn.addEventListener('click', () => onApply(sorted[Number(btn.dataset.apply)]));
  }
}
