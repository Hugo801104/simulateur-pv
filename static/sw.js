/**
 * Service worker : met en cache Pyodide et les paquets Python (≈ 57 Mo) au
 * premier chargement, et permet d'utiliser l'application hors connexion avec
 * les données météo déjà téléchargées ou un fichier PVGIS.
 *
 * - pyodide/ : « cache d'abord ». Le nom du cache contient les versions lues
 *   dans pyodide/manifest.json : une mise à jour de Pyodide ou de pvlib crée
 *   un nouveau cache et l'ancien est supprimé, sans modifier ce fichier.
 * - application : « réseau d'abord », repli sur le cache hors connexion.
 * - Les API météo ne passent pas par ici (cache dédié dans src/data/cache.ts).
 */
const APP_CACHE = 'pvsim-app-v1';
const PYODIDE_PREFIX = 'pvsim-pyodide-';
let pyodideCacheName = null;

async function currentPyodideCacheName() {
  if (pyodideCacheName) return pyodideCacheName;
  const res = await fetch(new URL('pyodide/manifest.json', self.registration.scope), { cache: 'no-store' });
  const m = await res.json();
  pyodideCacheName = PYODIDE_PREFIX + [m.pyodideVersion, ...m.wheels.map((w) => `${w.name}-${w.version}`)].join('_');
  return pyodideCacheName;
}

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      let keep = null;
      try {
        keep = await currentPyodideCacheName();
      } catch {
        // Hors connexion : on ne supprime rien.
      }
      if (keep) {
        for (const name of await caches.keys()) {
          if (name.startsWith(PYODIDE_PREFIX) && name !== keep) await caches.delete(name);
        }
      }
      await self.clients.claim();
    })(),
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const scope = new URL(self.registration.scope);
  if (!url.pathname.startsWith(scope.pathname)) return;

  if (url.pathname.includes('/pyodide/') && !url.pathname.endsWith('/manifest.json')) {
    event.respondWith(cacheFirst(req));
  } else {
    event.respondWith(networkFirst(req));
  }
});

async function cacheFirst(req) {
  let cache = null;
  try {
    cache = await caches.open(await currentPyodideCacheName());
  } catch {
    // Manifeste illisible : on passe par le réseau sans mettre en cache.
  }
  const hit = cache && (await cache.match(req));
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok && cache) await cache.put(req, res.clone());
  return res;
}

async function networkFirst(req) {
  const cache = await caches.open(APP_CACHE);
  try {
    // Revalidation systématique : une nouvelle version déployée s'affiche
    // immédiatement, malgré le cache HTTP de 10 min de GitLab Pages.
    const res = await fetch(req, { cache: 'no-cache' });
    if (res.ok) await cache.put(req, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(req, { ignoreSearch: true });
    if (hit) return hit;
    throw err;
  }
}
