import json
import shutil
import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]

NODE_SCRIPT = r'''
import { pathToFileURL } from 'node:url';

const frontendPath = process.argv[2];
const mod = await import(pathToFileURL(frontendPath).href);

if (typeof mod.loadBooks !== 'function') {
  throw new Error('loadBooks export is not a function');
}
if (typeof mod.deleteBook !== 'function') {
  throw new Error('deleteBook export is not a function');
}
if (mod.loadBooks.length !== 1) {
  throw new Error('loadBooks must declare exactly one parameter');
}
if (mod.deleteBook.length !== 2) {
  throw new Error('deleteBook must declare exactly two parameters');
}

const capturedCalls = new Array();
async function fakeFetch(url, options) {
  capturedCalls.push({
    url: String(url),
    options: options === undefined ? null : options
  });
  return {
    ok: true,
    status: String(url) === '/books' ? 200 : 204,
    headers: {
      get(name) {
        return name.toLowerCase() === 'content-type' ? 'application/json' : null;
      }
    },
    async json() {
      return String(url) === '/books' ? [{ id: 42, title: 'Node Test', state: 'IN_LIBRARY' }] : { deleted: true };
    },
    async text() {
      return '';
    }
  };
}

await mod.loadBooks(fakeFetch);
await mod.deleteBook(fakeFetch, 42);
console.log(JSON.stringify({ calls: capturedCalls }));
'''


def test_frontend_functions_fetch_backend_api_paths(tmp_path):
    node = shutil.which('node')
    assert node, 'Node.js executable is required for the frontend/backend integration test'
    frontend = ROOT / 'frontend' / 'app.js'
    assert frontend.exists(), 'frontend/app.js must exist'

    runner = tmp_path / 'exercise_frontend.mjs'
    runner.write_text(textwrap.dedent(NODE_SCRIPT), encoding='utf-8')
    completed = subprocess.run(
        [node, str(runner), str(frontend)],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip(), completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1], object_hook=lambda data: SimpleNamespace(**data))
    calls = payload.calls
    assert len(calls) == 2
    assert calls[0].url == '/books'
    assert calls[1].url == '/books/42'
    assert calls[1].options.method == 'DELETE'
