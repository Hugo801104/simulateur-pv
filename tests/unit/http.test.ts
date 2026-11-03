import { describe, expect, it, vi } from 'vitest';
import { fetchText, NetworkError } from '../../src/data/http';

const ok = (body: string) => new Response(body, { status: 200 });

describe('fetchText', () => {
  it('renvoie le corps de la réponse', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(ok('{"a":1}'));
    await expect(fetchText('https://x', { fetchImpl })).resolves.toBe('{"a":1}');
  });

  it('refuse immédiatement hors connexion', async () => {
    const fetchImpl = vi.fn();
    await expect(fetchText('https://x', { fetchImpl, isOnline: () => false })).rejects.toMatchObject({ kind: 'offline' });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('réessaie après une erreur réseau puis réussit', async () => {
    const fetchImpl = vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValue(ok('ok'));
    await expect(fetchText('https://x', { fetchImpl, retries: 1, retryDelayMs: 0 })).resolves.toBe('ok');
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('réessaie sur erreur serveur 5xx', async () => {
    const fetchImpl = vi.fn().mockResolvedValueOnce(new Response('', { status: 503 })).mockResolvedValue(ok('ok'));
    await expect(fetchText('https://x', { fetchImpl, retryDelayMs: 0 })).resolves.toBe('ok');
  });

  it('ne réessaie pas une erreur 400 et transmet la raison', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('{"error":true,"reason":"Latitude must be in range"}', { status: 400 }));
    const err = await fetchText('https://x', { fetchImpl, retryDelayMs: 0 }).catch((e) => e);
    expect(err).toBeInstanceOf(NetworkError);
    expect(err.kind).toBe('http');
    expect(err.message).toContain('Latitude must be in range');
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('signale la limite de requêtes (429)', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('', { status: 429 }));
    await expect(fetchText('https://x', { fetchImpl })).rejects.toMatchObject({ kind: 'rate_limit' });
  });

  it('abandonne après le délai maximal', async () => {
    const fetchImpl = vi.fn((_url: string, init?: RequestInit) =>
      new Promise<Response>((_, reject) => init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))),
    ) as unknown as typeof fetch;
    await expect(fetchText('https://x', { fetchImpl, timeoutMs: 10, retries: 0 })).rejects.toMatchObject({ kind: 'timeout' });
  });
});
