import { describe, expect, it } from 'vitest';
import { collectParams, groupErrors } from '../../src/ui/form';
import { escapeHtml, eur, pct, years } from '../../src/ui/format';

describe('collectParams', () => {
  const entries: [string, string][] = [
    ['site.latitude', '45.76'],
    ['site.altitude', ''],
    ['pv.peak_power_kwc', ' 6 '],
    ['battery.capacity_kwh', '5'],
    ['battery.power_kw', '2.5'],
    ['ui.weather_source', 'auto'],
    ['optimisation.battery_sizes_kwh', '0 5 10'],
    ['bizarre', 'x'],
  ];

  it('regroupe les champs, ignore les vides et les champs d’interface', () => {
    const p = collectParams(entries, { batteryEnabled: true });
    expect(p.site).toEqual({ latitude: '45.76' });
    expect(p.pv).toEqual({ peak_power_kwc: '6' });
    expect(p.battery).toEqual({ capacity_kwh: '5', power_kw: '2.5' });
    expect(p.optimisation).toEqual({ battery_sizes_kwh: '0 5 10' });
    expect(Object.keys(p)).toEqual(['site', 'pv', 'battery', 'load', 'economics', 'optimisation']);
  });

  it('met la batterie à zéro quand elle est désactivée', () => {
    const p = collectParams(entries, { batteryEnabled: false });
    expect(p.battery).toEqual({ capacity_kwh: 0, power_kw: 0 });
  });
});

describe('groupErrors', () => {
  it('sépare erreurs de champ et erreurs générales', () => {
    const { byField, general } = groupErrors([
      { field: 'pv.tilt_deg', message: 'trop grand' },
      { field: '', message: 'Aucune donnée météo' },
      { field: 'autre', message: 'groupe inconnu' },
    ]);
    expect([...byField]).toEqual([['pv.tilt_deg', 'trop grand']]);
    expect(general).toEqual(['Aucune donnée météo', 'autre : groupe inconnu']);
  });
});

describe('format', () => {
  it('met en forme à la française', () => {
    expect(eur(1234.5).replace(/\s/g, ' ')).toBe('1 235 €');
    expect(pct(0.4258, 1).replace(/\s/g, ' ')).toBe('42,6 %');
    expect(years(null)).toBe('non atteint');
    expect(escapeHtml('<b>"x"</b>')).toBe('&lt;b&gt;&quot;x&quot;&lt;/b&gt;');
  });
});
