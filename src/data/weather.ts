/**
 * Récupération des données météo depuis les API publiques.
 *
 * Sources appelables depuis le navigateur (en-têtes CORS vérifiés) :
 *   - Open-Meteo, archive historique (réanalyse ERA5), source principale ;
 *   - NASA POWER, source de secours.
 * L'API PVGIS n'autorise pas les appels depuis un navigateur (pas d'en-tête
 * CORS) : ses données s'importent sous forme de fichier (voir l'interface).
 *
 * En cas d'échec, aucune donnée n'est inventée : l'erreur est remontée avec la
 * liste des tentatives, et l'utilisateur peut importer un fichier PVGIS.
 */
import { fetchText, NetworkError, type FetchOptions } from './http';
import type { TextCache } from './cache';

export type RemoteSource = 'openmeteo' | 'nasapower';
export type SourceChoice = RemoteSource | 'auto';

export interface WeatherRequest {
  latitude: number;
  longitude: number;
  /** Dernière année demandée. */
  year: number;
  /** Première année (plusieurs années d'un coup) ; par défaut `year`. */
  startYear?: number;
}

export interface WeatherResponse {
  source: RemoteSource;
  raw: string;
  fromCache: boolean;
  attempts: { source: RemoteSource; error: string }[];
}

export const SOURCE_LABELS: Record<RemoteSource, string> = {
  openmeteo: 'Open-Meteo',
  nasapower: 'NASA POWER',
};

export const AUTO_ORDER: RemoteSource[] = ['openmeteo', 'nasapower'];

/** Coordonnées arrondies à 0,01° (~1 km) : meilleure réutilisation du cache, précision suffisante. */
const round2 = (x: number) => (Math.round(x * 100) / 100).toFixed(2);

export function buildUrl(source: RemoteSource, { latitude, longitude, year, startYear }: WeatherRequest): string {
  const lat = round2(latitude);
  const lon = round2(longitude);
  // NASA POWER refuse les longues périodes horaires (erreur 422 vérifiée pour 10 ans) :
  // en secours, on se limite à la dernière année.
  const first = source === 'nasapower' ? year : (startYear ?? year);
  if (source === 'openmeteo') {
    const q = new URLSearchParams({
      latitude: lat,
      longitude: lon,
      start_date: `${first}-01-01`,
      end_date: `${year}-12-31`,
      hourly: 'shortwave_radiation,direct_normal_irradiance,diffuse_radiation,temperature_2m,wind_speed_10m',
      wind_speed_unit: 'ms',
      timezone: 'GMT',
    });
    return `https://archive-api.open-meteo.com/v1/archive?${q}`;
  }
  const q = new URLSearchParams({
    parameters: 'ALLSKY_SFC_SW_DWN,ALLSKY_SFC_SW_DNI,ALLSKY_SFC_SW_DIFF,T2M,WS10M',
    community: 'RE',
    latitude: lat,
    longitude: lon,
    start: `${first}0101`,
    end: `${year}1231`,
    format: 'JSON',
    'time-standard': 'UTC',
  });
  return `https://power.larc.nasa.gov/api/temporal/hourly/point?${q}`;
}

/** Dernière année complète disponible dans les archives (délai de publication de quelques jours). */
export function lastCompleteYear(now = new Date()): number {
  return now.getUTCMonth() === 0 && now.getUTCDate() < 10 ? now.getUTCFullYear() - 2 : now.getUTCFullYear() - 1;
}

export function validateRequest(req: WeatherRequest, now = new Date()): string | null {
  if (!Number.isFinite(req.latitude) || Math.abs(req.latitude) > 90) return 'Latitude invalide.';
  if (!Number.isFinite(req.longitude) || Math.abs(req.longitude) > 180) return 'Longitude invalide.';
  const max = lastCompleteYear(now);
  if (!Number.isInteger(req.year) || req.year < 2001 || req.year > max) return `Année attendue entre 2001 et ${max}.`;
  if (req.startYear !== undefined && (!Number.isInteger(req.startYear) || req.startYear < 2001 || req.startYear > req.year)) {
    return `Première année attendue entre 2001 et ${req.year}.`;
  }
  return null;
}

export async function fetchWeather(
  choice: SourceChoice,
  req: WeatherRequest,
  cache: TextCache,
  options: FetchOptions = {},
): Promise<WeatherResponse> {
  const invalid = validateRequest(req);
  if (invalid) throw new NetworkError('http', invalid);

  const order = choice === 'auto' ? AUTO_ORDER : [choice];
  const attempts: WeatherResponse['attempts'] = [];

  // 1. Cache local (fonctionne hors connexion).
  for (const source of order) {
    const cached = await cache.get(buildUrl(source, req));
    if (cached) return { source, raw: cached, fromCache: true, attempts };
  }

  // 2. Réseau, avec repli sur la source suivante en mode automatique.
  for (const source of order) {
    const url = buildUrl(source, req);
    try {
      const raw = await fetchText(url, options);
      await cache.set(url, raw);
      return { source, raw, fromCache: false, attempts };
    } catch (err) {
      attempts.push({ source, error: err instanceof Error ? err.message : String(err) });
      if (err instanceof NetworkError && err.kind === 'offline') break;
    }
  }

  const detail = attempts.map((a) => `${SOURCE_LABELS[a.source]} : ${a.error}`).join(' — ');
  throw new WeatherUnavailableError(attempts, detail);
}

export class WeatherUnavailableError extends Error {
  constructor(
    readonly attempts: WeatherResponse['attempts'],
    detail: string,
  ) {
    super(`Données météo indisponibles. ${detail}`);
    this.name = 'WeatherUnavailableError';
  }
}
