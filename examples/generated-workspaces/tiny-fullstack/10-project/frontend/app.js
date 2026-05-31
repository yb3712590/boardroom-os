export async function loadBooks(fetchImpl) {
  const response = await fetchImpl('/books');
  if (!response || typeof response.json !== 'function') {
    return response;
  }
  return await response.json();
}

export async function deleteBook(fetchImpl, bookId) {
  const response = await fetchImpl(`/books/${encodeURIComponent(String(bookId))}`, { method: 'DELETE' });
  if (response && typeof response.json === 'function') {
    try {
      return await response.json();
    } catch (error) {
      return response;
    }
  }
  return response;
}

function normalizeBooks(payload) {
  if (Array.isArray(payload)) {
    return payload;
  }
  if (payload && Array.isArray(payload.books)) {
    return payload.books;
  }
  return [];
}

function bookLabel(book) {
  if (book && typeof book === 'object') {
    const title = book.title == null ? `Book ${book.id ?? ''}`.trim() : String(book.title);
    const state = book.state == null ? '' : ` (${book.state})`;
    return `${title}${state}`;
  }
  return String(book);
}

async function renderBooks(fetchImpl, documentRef) {
  const list = documentRef.getElementById('book-list');
  const status = documentRef.getElementById('book-status');
  if (!list || !status) {
    return;
  }

  status.textContent = 'Loading books...';
  status.className = 'muted';
  list.replaceChildren();

  try {
    const books = normalizeBooks(await loadBooks(fetchImpl));
    if (books.length === 0) {
      status.textContent = 'No books found.';
      return;
    }

    status.textContent = `${books.length} book${books.length === 1 ? '' : 's'} loaded.`;
    for (const book of books) {
      const item = documentRef.createElement('li');
      const label = documentRef.createElement('span');
      label.textContent = bookLabel(book);
      item.appendChild(label);

      if (book && typeof book === 'object' && book.id !== undefined && book.id !== null) {
        const button = documentRef.createElement('button');
        button.type = 'button';
        button.textContent = 'Delete';
        button.addEventListener('click', async () => {
          button.disabled = true;
          status.textContent = `Deleting book ${book.id}...`;
          try {
            await deleteBook(fetchImpl, book.id);
            await renderBooks(fetchImpl, documentRef);
          } catch (error) {
            button.disabled = false;
            status.textContent = error instanceof Error ? error.message : 'Delete failed.';
            status.className = 'error';
          }
        });
        item.appendChild(button);
      }

      list.appendChild(item);
    }
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : 'Unable to load books.';
    status.className = 'error';
  }
}

function initializeBrowserUi() {
  const fetchImpl = globalThis.fetch ? globalThis.fetch.bind(globalThis) : undefined;
  if (typeof fetchImpl !== 'function' || typeof document === 'undefined') {
    return;
  }

  const refresh = document.getElementById('refresh-books');
  if (refresh) {
    refresh.addEventListener('click', () => renderBooks(fetchImpl, document));
  }
  renderBooks(fetchImpl, document);
}

if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('DOMContentLoaded', initializeBrowserUi);
}
