import { describe, expect, it, vi } from 'vitest';
import { memoryCache } from '../../src/data/cache';
import { buildUrl, fetchWeather, lastCompleteYear, validateRequest, WeatherUnavailableError } from '../../src/data/weather';

const REQ = { latitude: 45.7612, longitude: 4.8421, year: 2023 };
const opts = (fetchImpl: unknown) => ({ fetchImpl: fetchImpl as typeof fetch, retryDelayMs: 0, isOnline: () => true });

describe('buildUrl', () => {
  it('construit une requête Open-Meteo en UTC, vent en m/s, année complète', () => {
    const url = new URL(buildUrl('openmeteo', REQ));
    expect(url.host).toBe('archive-api.open-meteo.com');
    expect(url.searchParams.get('latitude')).toBe('45.76');
    expect(url.searchParams.get('timezone')).toBe('GMT');
    expect(url.searchParams.get('wind_speed_unit')).toBe('ms');
    expect(url.searchParams.get('start_date')).toBe('2023-01-01');
    expect(url.searchParams.get('end_date')).toBe('2023-12-31');
    expect(url.searchParams.get('hourly')).toContain('direct_normal_irradiance');
  });

  it('construit une requête NASA POWER en UTC', () => {
    const url = new URL(buildUrl('nasapower', REQ));
    expect(url.host).toBe('power.larc.nasa.gov');
    expect(url.searchParams.get('time-standard')).toBe('UTC');
    expect(url.searchParams.get('start')).toBe('20230101');
  });
});

describe('validateRequest', () => {
  it('borne l’année à la dernière année complète', () => {
    const now = new Date('2026-11-03T12:00:00Z');
    expect(lastCompleteYear(now)).toBe(2025);
    expect(lastCompleteYear(new Date('2026-01-05T00:00:00Z'))).toBe(2024);
    expect(validateRequest({ ...REQ, year: 2026 }, now)).toMatch(/Année/);
    expect(validateRequest({ ...REQ, latitude: 91 }, now)).toMatch(/Latitude/);
    expect(validateRequest(REQ, now)).toBeNull();
  });
});

describe('fetchWeather', () => {
  it('met en cache une réponse et la réutilise sans réseau', async () => {
    const cache = memoryCache();
    const fetchImpl = vi.fn().mockResolvedValue(new Response('{"hourly":{}}'));
    const first = await fetchWeather('openmeteo', REQ, cache, opts(fetchImpl));
    expect(first).toMatchObject({ source: 'openmeteo', fromCache: false });
    const second = await fetchWeather('openmeteo', REQ, cache, opts(vi.fn()));
    expect(second).toMatchObject({ source: 'openmeteo', fromCache: true, raw: '{"hourly":{}}' });
  });

  it('se replie sur NASA POWER en mode automatique', async () => {
    const fetchImpl = vi.fn(async (url: string) =>
      url.includes('open-meteo') ? new Response('', { status: 502 }) : new Response('{"properties":{}}'),
    );
    const res = await fetchWeather('auto', REQ, memoryCache(), opts(fetchImpl));
    expect(res.source).toBe('nasapower');
    expect(res.attempts).toHaveLength(1);
    expect(res.attempts[0].source).toBe('openmeteo');
  });

  it('échoue explicitement si toutes les sources sont indisponibles, sans rien mettre en cache', async () => {
    const cache = memoryCache();
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    const err = await fetchWeather('auto', REQ, cache, opts(fetchImpl)).catch((e) => e);
    expect(err).toBeInstanceOf(WeatherUnavailableError);
    expect(err.attempts.map((a: { source: string }) => a.source)).toEqual(['openmeteo', 'nasapower']);
    expect(cache.store.size).toBe(0);
  });

  it('n’interroge pas le réseau pour une requête invalide', async () => {
    const fetchImpl = vi.fn();
    await expect(fetchWeather('openmeteo', { ...REQ, year: 1990 }, memoryCache(), opts(fetchImpl))).rejects.toThrow(/Année/);
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
