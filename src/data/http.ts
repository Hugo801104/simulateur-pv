/** Requêtes HTTP robustes : délai maximal, nouvelle tentative, messages d'erreur en français. */

export type NetworkErrorKind = 'offline' | 'timeout' | 'http' | 'rate_limit' | 'network';

export class NetworkError extends Error {
  constructor(
    readonly kind: NetworkErrorKind,
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = 'NetworkError';
  }
}

export interface FetchOptions {
  timeoutMs?: number;
  retries?: number;
  fetchImpl?: typeof fetch;
  /** Délai avant nouvelle tentative (ms), multiplié par le numéro de tentative. */
  retryDelayMs?: number;
  isOnline?: () => boolean;
}

const RETRYABLE = new Set<NetworkErrorKind>(['timeout', 'network']);

export async function fetchText(url: string, options: FetchOptions = {}): Promise<string> {
  const {
    timeoutMs = 45_000,
    retries = 1,
    fetchImpl = globalThis.fetch.bind(globalThis),
    retryDelayMs = 1500,
    isOnline = () => (typeof navigator === 'undefined' ? true : navigator.onLine !== false),
  } = options;

  if (!isOnline()) throw new NetworkError('offline', 'Pas de connexion Internet.');

  for (let attempt = 0; ; attempt++) {
    try {
      return await fetchOnce(url, timeoutMs, fetchImpl);
    } catch (err) {
      const e = err instanceof NetworkError ? err : new NetworkError('network', String(err));
      const retryable = RETRYABLE.has(e.kind) || (e.kind === 'http' && (e.status ?? 0) >= 500);
      if (!retryable || attempt >= retries) throw e;
      await new Promise((r) => setTimeout(r, retryDelayMs * (attempt + 1)));
    }
  }
}

async function fetchOnce(url: string, timeoutMs: number, fetchImpl: typeof fetch): Promise<string> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetchImpl(url, { signal: controller.signal });
  } catch (err) {
    if (controller.signal.aborted) {
      throw new NetworkError('timeout', `Le service n'a pas répondu en ${Math.round(timeoutMs / 1000)} s.`);
    }
    throw new NetworkError('network', 'Service injoignable (réseau, blocage CORS ou service indisponible).');
  } finally {
    clearTimeout(timer);
  }
  const body = await res.text();
  if (res.status === 429) {
    throw new NetworkError('rate_limit', 'Limite de requêtes du service atteinte : réessayez plus tard.', 429);
  }
  if (!res.ok) {
    throw new NetworkError('http', `Le service a répondu ${res.status}${extractReason(body)}.`, res.status);
  }
  return body;
}

/** Extrait un message d'erreur lisible d'une réponse JSON (Open-Meteo : reason, NASA POWER : messages). */
function extractReason(body: string): string {
  try {
    const doc = JSON.parse(body);
    const reason = doc.reason ?? (Array.isArray(doc.messages) ? doc.messages.join(' ') : undefined) ?? doc.message;
    return reason ? ` : ${String(reason).slice(0, 300)}` : '';
  } catch {
    return '';
  }
}
