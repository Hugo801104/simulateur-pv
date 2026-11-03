#!/usr/bin/env node
/**
 * Sert le site construit (dist/) sous un sous-chemin, comme GitLab Pages :
 *   http://localhost:8090/simulateur-pv/
 *
 *   npm run build && npm run preview:pages
 *
 * Options : --port 8090 --base /simulateur-pv/ --dir dist
 * Types MIME explicites (.mjs, .wasm) : certains serveurs locaux les servent
 * en text/plain, ce que les navigateurs refusent pour les modules JavaScript.
 */
import { createReadStream, existsSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname, join, normalize, resolve } from 'node:path';

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith('--') ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
);
const port = Number(args.port ?? 8090);
const base = ('/' + (args.base ?? 'simulateur-pv') + '/').replace(/\/+/g, '/');
const dir = resolve(args.dir ?? 'dist');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.wasm': 'application/wasm',
  '.svg': 'image/svg+xml',
  '.zip': 'application/zip',
  '.whl': 'application/zip',
  '.csv': 'text/csv; charset=utf-8',
};

if (!existsSync(join(dir, 'index.html'))) {
  console.error(`${dir}/index.html introuvable : lancez d'abord « npm run build ».`);
  process.exit(1);
}

createServer((req, res) => {
  const url = new URL(req.url ?? '/', 'http://localhost');
  if (url.pathname === '/' || url.pathname === base.slice(0, -1)) {
    res.writeHead(302, { Location: base }).end();
    return;
  }
  if (!url.pathname.startsWith(base)) {
    res.writeHead(404).end('Hors du sous-chemin ' + base);
    return;
  }
  let rel = decodeURIComponent(url.pathname.slice(base.length)) || 'index.html';
  let file = normalize(join(dir, rel));
  if (!file.startsWith(dir)) {
    res.writeHead(403).end();
    return;
  }
  if (existsSync(file) && statSync(file).isDirectory()) file = join(file, 'index.html');
  if (!existsSync(file)) {
    res.writeHead(404).end('Introuvable');
    return;
  }
  res.writeHead(200, {
    'Content-Type': MIME[extname(file)] ?? 'application/octet-stream',
    'Content-Length': statSync(file).size,
    'Cache-Control': 'max-age=600',
  });
  createReadStream(file).pipe(res);
}).listen(port, () => console.log(`Site servi sur http://localhost:${port}${base}`));
