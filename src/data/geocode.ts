/**
 * Géocodage d'adresses françaises : service de l'IGN (Géoplateforme), gratuit,
 * sans clé, appelable depuis le navigateur (CORS vérifié). Remplace l'ancienne
 * API Adresse (api-adresse.data.gouv.fr), qui redirige désormais vers lui.
 */
import { fetchText, type FetchOptions } from './http';

export const GEOCODE_URL = 'https://data.geopf.fr/geocodage/search';

export interface AddressMatch {
  label: string;
  latitude: number;
  longitude: number;
  postcode?: string;
  city?: string;
  score: number;
}

export function buildGeocodeUrl(query: string, limit = 5): string {
  const q = new URLSearchParams({ q: query.trim(), limit: String(limit), index: 'address' });
  return `${GEOCODE_URL}?${q}`;
}

export function parseGeocode(text: string): AddressMatch[] {
  const doc = JSON.parse(text);
  if (!Array.isArray(doc.features)) return [];
  return doc.features
    .filter((f: any) => Array.isArray(f?.geometry?.coordinates) && f.properties?.label)
    .map((f: any) => ({
      label: String(f.properties.label),
      longitude: Number(f.geometry.coordinates[0]),
      latitude: Number(f.geometry.coordinates[1]),
      postcode: f.properties.postcode,
      city: f.properties.city,
      score: Number(f.properties.score ?? 0),
    }));
}

export async function searchAddress(query: string, options: FetchOptions = {}): Promise<AddressMatch[]> {
  if (query.trim().length < 3) return [];
  const text = await fetchText(buildGeocodeUrl(query), { timeoutMs: 8000, retries: 0, ...options });
  return parseGeocode(text);
}
