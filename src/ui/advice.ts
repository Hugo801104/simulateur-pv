/** Restitution du mode Conseil : recommandation, conseils, options, étapes, sources. */
import type { AdviceResult, AdviceRow } from '../engine/types';
import { monthlyChart, optimisationChart } from './charts';
import { escapeHtml, eur, kwh, num, pct, years } from './format';

const $ = (id: string) => document.getElementById(id) as HTMLElement;

const ORIENTATION: Record<string, string> = {
  '0': 'nord', '45': 'nord-est', '90': 'est', '135': 'sud-est', '180': 'sud', '225': 'sud-ouest', '270': 'ouest', '315': 'nord-ouest',
};

const LEVEL_LABEL = { conseil: 'Conseil', attention: 'À vérifier', info: 'Info' } as const;

function kpi(label: string, value: string, hint = '') {
  return `<div class="kpi"><div class="kpi-label">${label}</div><div class="kpi-value">${value}</div>${hint ? `<div class="kpi-hint">${hint}</div>` : ''}</div>`;
}

function batteryText(row: Pick<AdviceRow, 'battery_kwh'>) {
  return row.battery_kwh > 0 ? `${num(row.battery_kwh)} kWh` : 'sans';
}

function sourceLinks(keys: string[], sources: AdviceResult['sources']) {
  const links = keys
    .filter((k) => sources[k])
    .map((k) => `<a href="${escapeHtml(sources[k].url)}" target="_blank" rel="noopener">${escapeHtml(sources[k].title)}</a>`);
  return links.length ? `<div class="src">Source : ${links.join('')}</div>` : '';
}

export function renderAdvice(a: AdviceResult) {
  const r = a.recommendation;
  $('advice-empty').hidden = true;
  $('advice-results').hidden = false;

  const orient = r.azimuths_deg.map((d) => ORIENTATION[String(d)] ?? `${d}°`).join(' et ');
  $('reco-title').textContent =
    `${r.panels} panneaux de ${num(r.module.power_wc)} Wc, soit ${num(r.pv_kwc, 2)} kWc` +
    (r.battery_kwh > 0 ? `, avec une batterie de ${num(r.battery_kwh)} kWh` : ', sans batterie');
  $('reco-subtitle').textContent =
    `${r.module.label} · orientés ${orient}, inclinés à ${num(r.tilt_deg)}° · environ ${num(r.occupied_area_m2)} m² ` +
    `sur ${a.roof.max_panels} panneaux possibles au maximum.`;

  const t = r.totals;
  const yields = Object.values(a.production.yearly_yield);
  const yieldHint = yields.length > 1
    ? `moyenne de ${yields.length} ans : ${num(Math.min(...yields) * r.pv_kwc)} à ${num(Math.max(...yields) * r.pv_kwc)} kWh selon l'année`
    : `${num(a.production.specific_yield_kwh_per_kwc)} kWh/kWc par an`;
  const range = r.observed_price_range_eur;
  const pilot = r.water_heater_piloting;
  $('reco-kpis').innerHTML = [
    kpi('Production', kwh(t.pv_kwh), yieldHint),
    kpi('Autoconsommation', pct(t.self_consumption_rate),
      pilot ? `avec chauffe-eau piloté (${pct(pilot.self_consumption_without)} sans)` : `couvre ${pct(t.self_sufficiency_rate)} de vos besoins`),
    kpi('Investissement estimé', eur(r.capex_eur), range ? `prix publiés : ${eur(range[0])} à ${eur(range[1])}` : 'ordre de grandeur TTC'),
    kpi('Gain la 1re année', eur(r.year1_savings_eur), `facture ${eur(r.year1_bill_without_pv_eur)} → ${eur(r.year1_bill_with_pv_eur)}`),
    kpi('Temps de retour', years(r.payback_years)),
    kpi('VAN sur 25 ans', `<span class="${r.npv_eur >= 0 ? 'pos' : 'neg'}">${eur(r.npv_eur)}</span>`,
      r.break_even_capex_eur != null ? `rentable si devis < ${eur(Math.floor(r.break_even_capex_eur / 100) * 100)}` : ''),
  ].join('');
  $('reco-plateau').textContent =
    r.plateau.min_kwc < r.plateau.max_kwc
      ? `Entre ${num(r.plateau.min_kwc, 2)} et ${num(r.plateau.max_kwc, 2)} kWc, le résultat varie peu : une marge utile pour comparer les devis.`
      : '';

  $('advice-list').innerHTML = a.advice
    .map(
      (item) => `<article class="advice ${item.level}">
        <h3>${escapeHtml(item.title)} <span class="badge">${LEVEL_LABEL[item.level]}</span></h3>
        <p>${escapeHtml(item.text)}</p>${sourceLinks(item.sources, a.sources)}</article>`,
    )
    .join('');

  $('options-table').querySelector('tbody')!.innerHTML = a.options
    .map(
      (o) => `<tr class="${o.key === 'recommandee' ? 'best' : ''}">
        <td class="left">${escapeHtml(o.label ?? '')}</td><td>${o.panels}</td><td>${num(o.pv_kwc, 2)}</td><td>${batteryText(o)}</td>
        <td>${eur(o.capex_eur)}</td><td>${eur(o.year1_savings_eur)}</td><td>${years(o.payback_years)}</td>
        <td class="${o.npv_eur >= 0 ? 'pos' : 'neg'}">${eur(o.npv_eur)}</td><td>${pct(o.totals.self_consumption_rate)}</td></tr>`,
    )
    .join('');

  $('steps-list').innerHTML = a.steps
    .map((s) => `<li><strong>${escapeHtml(s.title)}</strong><p>${escapeHtml(s.text)}</p>${sourceLinks(s.sources, a.sources)}</li>`)
    .join('');

  $('assumptions-list').innerHTML = [`Consommation : ${num(a.consumption.annual_kwh)} kWh/an (${a.consumption.basis}).`, ...a.assumptions]
    .map((x) => `<li>${escapeHtml(x)}</li>`)
    .join('');
  $('sources-list').innerHTML = Object.values(a.sources)
    .map((s) => `<li><a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.title)}</a></li>`)
    .join('');
  const [y, m, d] = a.verified_on.split('-');
  $('advice-verified').textContent = `Tarifs, prix et règles vérifiés le ${d}/${m}/${y}. Ils évoluent : faites confirmer chaque point par l'installateur.`;

  drawAdviceCharts(a);
}

export function drawAdviceCharts(a: AdviceResult) {
  optimisationChart(a.grid, 'npv', 'chart-advice-grid');
  monthlyChart(a.monthly, 'chart-advice-monthly');
}
