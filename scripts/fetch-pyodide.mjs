#!/usr/bin/env node
/**
 * Télécharge Pyodide et les paquets Python nécessaires dans static/pyodide/,
 * pour que le site les serve lui-même (aucun CDN requis à l'exécution).
 *
 *   node scripts/fetch-pyodide.mjs
 *
 * - Lit pyodide.config.json (version, paquets, roues supplémentaires).
 * - Résout les dépendances à partir de pyodide-lock.json.
 * - Vérifie l'empreinte SHA-256 de chaque paquet et ne retélécharge pas les fichiers déjà valides.
 * - Écrit static/pyodide/manifest.json, lu par le Web Worker.
 */
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const config = JSON.parse(await readFile(join(root, 'pyodide.config.json'), 'utf8'));
const outDir = join(root, 'static', 'pyodide');
const cdn = config.cdn.replace('{version}', config.pyodideVersion);

const sha256 = (buf) => createHash('sha256').update(buf).digest('hex');

async function download(url, attempts = 3) {
  for (let i = 1; ; i++) {
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return Buffer.from(await res.arrayBuffer());
    } catch (err) {
      if (i >= attempts) throw new Error(`Échec du téléchargement de ${url} : ${err.message}`);
      await new Promise((r) => setTimeout(r, 1000 * i));
    }
  }
}

async function ensure(file, url, expectedSha) {
  const path = join(outDir, file);
  if (existsSync(path)) {
    if (!expectedSha) return 'présent';
    if (sha256(await readFile(path)) === expectedSha) return 'présent';
  }
  const buf = await download(url);
  if (expectedSha && sha256(buf) !== expectedSha) {
    throw new Error(`Empreinte SHA-256 invalide pour ${file}`);
  }
  await writeFile(path, buf);
  return `téléchargé (${(buf.length / 1e6).toFixed(1)} Mo)`;
}

await mkdir(outDir, { recursive: true });

// Le fichier de verrouillage est toujours relu depuis le CDN pour la version demandée.
const lockBuf = await download(cdn + 'pyodide-lock.json');
await writeFile(join(outDir, 'pyodide-lock.json'), lockBuf);
const lock = JSON.parse(lockBuf.toString('utf8'));

for (const file of config.coreFiles.filter((f) => f !== 'pyodide-lock.json')) {
  console.log(`${file} : ${await ensure(file, cdn + file)}`);
}

// Résolution récursive des dépendances.
const resolved = new Set();
const visit = (name) => {
  const key = name.toLowerCase();
  const pkg = lock.packages[key];
  if (!pkg) throw new Error(`Paquet absent de Pyodide ${config.pyodideVersion} : ${name}`);
  if (resolved.has(key)) return;
  resolved.add(key);
  pkg.depends.forEach(visit);
};
config.packages.forEach(visit);

let total = 0;
for (const key of [...resolved].sort()) {
  const pkg = lock.packages[key];
  console.log(`${key} ${pkg.version} : ${await ensure(pkg.file_name, cdn + pkg.file_name, pkg.sha256)}`);
}
for (const wheel of config.wheels) {
  console.log(`${wheel.name} ${wheel.version} : ${await ensure(wheel.file, wheel.url, wheel.sha256)}`);
}

const files = [
  ...config.coreFiles,
  ...[...resolved].map((k) => lock.packages[k].file_name),
  ...config.wheels.map((w) => w.file),
];
for (const f of files) total += (await readFile(join(outDir, f))).length;

const manifest = {
  pyodideVersion: config.pyodideVersion,
  python: lock.info.python,
  packages: config.packages,
  wheels: config.wheels.map(({ name, version, file }) => ({ name, version, file })),
  totalBytes: total,
};
await writeFile(join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`\nPyodide ${config.pyodideVersion} (Python ${lock.info.python}) prêt dans static/pyodide/ — ${(total / 1e6).toFixed(1)} Mo.`);
