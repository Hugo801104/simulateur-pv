/**
 * Cache local des réponses météo (Cache API du navigateur).
 * Les données historiques ne changent pas : une réponse valide est conservée
 * sans date d'expiration. Le cache est facultatif : s'il est indisponible
 * (navigation privée, contexte non sécurisé), l'application fonctionne sans.
 */

export interface TextCache {
  get(key: string): Promise<string | undefined>;
  set(key: string, value: string): Promise<void>;
}

export const WEATHER_CACHE_NAME = 'pvsim-weather-v1';

export function browserCache(name = WEATHER_CACHE_NAME): TextCache {
  const available = typeof caches !== 'undefined';
  return {
    async get(key) {
      if (!available) return undefined;
      try {
        const res = await (await caches.open(name)).match(key);
        return res ? await res.text() : undefined;
      } catch {
        return undefined;
      }
    },
    async set(key, value) {
      if (!available) return;
      try {
        await (await caches.open(name)).put(key, new Response(value, { headers: { 'Content-Type': 'application/json' } }));
      } catch {
        // Quota dépassé ou cache indisponible : on continue sans.
      }
    },
  };
}

export function memoryCache(): TextCache & { store: Map<string, string> } {
  const store = new Map<string, string>();
  return {
    store,
    async get(key) {
      return store.get(key);
    },
    async set(key, value) {
      store.set(key, value);
    },
  };
}
