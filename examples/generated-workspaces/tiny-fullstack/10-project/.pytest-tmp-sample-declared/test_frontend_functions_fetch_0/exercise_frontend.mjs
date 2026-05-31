
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
