// @ts-check
/**
 * Démarrage du moteur Python dans Pyodide.
 *
 * Écrit en JavaScript (et non TypeScript) pour être partagé tel quel entre le
 * Web Worker du navigateur et le test Node (tests/pyodide/smoke.mjs) : le code
 * testé est exactement celui qui tourne en production.
 */

const ENGINE_DIR = '/home/pyodide';

/**
 * @param {object} options
 * @param {string} options.indexURL  Dossier contenant pyodide.mjs, les paquets et manifest.json.
 * @param {(opts: object) => Promise<any>} options.loadPyodide  Fonction exportée par pyodide.mjs.
 * @param {(url: string) => Promise<Uint8Array>} options.fetchBytes  Lecture d'un fichier (fetch ou fs).
 * @param {Record<string, string>} options.engineFiles  Sources du paquet pvsim : nom de fichier -> contenu.
 * @param {(step: string, detail?: string) => void} [options.onProgress]
 * @returns {Promise<{ pyodide: any, engine: any, manifest: any }>}
 */
export async function bootEngine({ indexURL, loadPyodide, fetchBytes, engineFiles, onProgress = () => {} }) {
  const manifest = JSON.parse(new TextDecoder().decode(await fetchBytes(indexURL + 'manifest.json')));

  onProgress('python', `Démarrage de Python ${manifest.python} (Pyodide ${manifest.pyodideVersion})`);
  const pyodide = await loadPyodide({ indexURL });

  onProgress('packages', 'Chargement de NumPy, SciPy et pandas');
  await pyodide.loadPackage(manifest.packages, { messageCallback: () => {} });

  const sitePackages = pyodide.runPython("import sysconfig; sysconfig.get_paths()['purelib']");
  for (const wheel of manifest.wheels) {
    onProgress('wheels', `Installation de ${wheel.name} ${wheel.version}`);
    const bytes = await fetchBytes(indexURL + wheel.file);
    pyodide.unpackArchive(bytes, 'wheel', { extractDir: sitePackages });
  }

  onProgress('engine', 'Chargement du moteur de simulation');
  pyodide.FS.mkdirTree(`${ENGINE_DIR}/pvsim`);
  for (const [name, source] of Object.entries(engineFiles)) {
    pyodide.FS.writeFile(`${ENGINE_DIR}/pvsim/${name}`, source);
  }
  pyodide.runPython(`import sys\nif ${JSON.stringify(ENGINE_DIR)} not in sys.path: sys.path.insert(0, ${JSON.stringify(ENGINE_DIR)})`);
  const api = pyodide.pyimport('pvsim.api');
  return { pyodide, engine: api.ENGINE, manifest };
}
