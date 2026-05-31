# Tiny Full-Stack Library

Tiny Full-Stack Library is a small standard-library-oriented example package with a Python SQLite backend and a browser/Node-safe JavaScript frontend helper module.

## Backend overview

The backend API is exposed from `backend/app.py`:

- `create_store(db_path)` creates or opens a SQLite-backed store.
- `create_book(title, store=None)` creates a book in the `IN_LIBRARY` state.
- `list_books(store=None)` returns the current books.
- `checkout_book(book_id, store=None)` changes a book to `CHECKED_OUT`.
- `return_book(book_id, store=None)` changes a book to `IN_LIBRARY`.
- `delete_book(book_id, store=None)` removes a book.

Book state values are `IN_LIBRARY` and `CHECKED_OUT`.

## Frontend overview

The frontend helper module is `frontend/app.js` and exports:

- `loadBooks(fetchImpl)` which fetches `/books`.
- `deleteBook(fetchImpl, bookId)` which sends `DELETE` to `/books/<bookId>`.

The module is safe to import in Node-based tests and does not require a browser DOM at import time.

## Running tests

From the repository root, run the required test commands:

```sh
python -X utf8 -m pytest tests/integration --basetemp=.pytest-tmp-integration
python -X utf8 -m pytest backend/tests --basetemp=.pytest-tmp-backend
```

## Notes for contributors

Use only Python standard library modules for backend code. Keep SQLite connections short-lived and close them before temporary directories are cleaned up, especially on Windows.
