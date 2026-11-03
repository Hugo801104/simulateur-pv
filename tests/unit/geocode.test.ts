import { describe, expect, it, vi } from 'vitest';
import { buildGeocodeUrl, parseGeocode, searchAddress } from '../../src/data/geocode';
import { collectHouse } from '../../src/ui/form';

const SAMPLE = JSON.stringify({
  type: 'FeatureCollection',
  features: [
    { geometry: { coordinates: [4.833295, 45.758233] }, properties: { label: '10 Place Bellecour 69002 Lyon', score: 0.97, postcode: '69002', city: 'Lyon' } },
    { geometry: {}, properties: { label: 'sans coordonnées' } },
  ],
});

describe('géocodage', () => {
  it('construit l’URL de la Géoplateforme IGN', () => {
    const url = new URL(buildGeocodeUrl(' 10 place bellecour '));
    expect(url.origin + url.pathname).toBe('https://data.geopf.fr/geocodage/search');
    expect(url.searchParams.get('q')).toBe('10 place bellecour');
    expect(url.searchParams.get('index')).toBe('address');
  });

  it('lit les résultats et ignore les entrées incomplètes', () => {
    const r = parseGeocode(SAMPLE);
    expect(r).toHaveLength(1);
    expect(r[0]).toMatchObject({ latitude: 45.758233, longitude: 4.833295, city: 'Lyon' });
  });

  it('ne cherche pas en dessous de 3 caractères', async () => {
    const fetchImpl = vi.fn();
    expect(await searchAddress('ly', { fetchImpl: fetchImpl as unknown as typeof fetch })).toEqual([]);
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});

describe('collectHouse', () => {
  it('ne garde que les champs « house » non vides', () => {
    expect(
      collectHouse([
        ['house.roof_area_m2', ' 30 '],
        ['house.annual_kwh', ''],
        ['ui.address', '10 place Bellecour'],
        ['pv.tilt_deg', '30'],
      ]),
    ).toEqual({ roof_area_m2: '30' });
  });
});
