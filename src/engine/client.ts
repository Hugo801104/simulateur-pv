/** Client du moteur : envoie des appels au Web Worker et renvoie des promesses typées. */
import type { EngineApi, EngineInfo, EngineMethod, EngineResult, WorkerMessage } from './types';

type Pending = { resolve: (v: string) => void; reject: (e: Error) => void };

export interface EngineEvents {
  onProgress?: (detail: string) => void;
  onReady?: (info: EngineInfo, totalBytes: number) => void;
  onBootError?: (message: string) => void;
}

export class EngineClient {
  private worker: Worker;
  private nextId = 1;
  private pending = new Map<number, Pending>();
  readonly ready: Promise<EngineInfo>;

  constructor(pyodideIndexURL: string, events: EngineEvents = {}) {
    this.worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module', name: pyodideIndexURL });
    let markReady!: (info: EngineInfo) => void;
    let markFailed!: (err: Error) => void;
    this.ready = new Promise((res, rej) => {
      markReady = res;
      markFailed = rej;
    });
    this.ready.catch(() => {});

    this.worker.onmessage = (event: MessageEvent<WorkerMessage>) => {
      const msg = event.data;
      switch (msg.type) {
        case 'progress':
          events.onProgress?.(msg.detail);
          break;
        case 'ready':
          events.onReady?.(msg.info, msg.totalBytes);
          markReady(msg.info);
          break;
        case 'boot-error':
          events.onBootError?.(msg.message);
          markFailed(new Error(msg.message));
          this.rejectAll(new Error(msg.message));
          break;
        case 'result':
          this.pending.get(msg.id)?.resolve(msg.result);
          this.pending.delete(msg.id);
          break;
        case 'error':
          this.pending.get(msg.id)?.reject(new Error(msg.message));
          this.pending.delete(msg.id);
          break;
      }
    };
    this.worker.onerror = (event) => {
      const err = new Error(event.message || 'Le moteur de calcul s’est arrêté.');
      events.onBootError?.(err.message);
      markFailed(err);
      this.rejectAll(err);
    };
  }

  call<M extends EngineMethod>(method: M, ...args: Parameters<EngineApi[M]>): Promise<ReturnType<EngineApi[M]>> {
    const id = this.nextId++;
    return new Promise<string>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.worker.postMessage({ id, method, args });
    }).then((text) => JSON.parse(text) as ReturnType<EngineApi[M]>);
  }

  private rejectAll(err: Error) {
    for (const p of this.pending.values()) p.reject(err);
    this.pending.clear();
  }
}

export function isOk<T>(r: EngineResult<T>): r is { ok: true } & T {
  return r.ok;
}
