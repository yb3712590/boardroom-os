# Agent Instructions

## Scope

Work only within the files assigned by the active task. Do not modify contracts, governance files, generated manifests, or undeclared evidence artifacts unless they are explicitly included in the allowed write set for the task.

## Backend expectations

- Backend public functions live in `backend/app.py`.
- SQLite persistence is implemented in `backend/db.py`.
- Use only Python standard library modules.
- Do not keep a `sqlite3.Connection` object on long-lived store instances.
- Open SQLite connections inside each operation and close them promptly.
- Book states are exactly `IN_LIBRARY` and `CHECKED_OUT`.

## Frontend expectations

- `frontend/app.js` exports `loadBooks(fetchImpl)` and `deleteBook(fetchImpl, bookId)`.
- `loadBooks` calls `fetchImpl('/books')`.
- `deleteBook` calls the book resource path with method `DELETE`.
- The module must be importable in Node without requiring `window` or a DOM.

## Test expectations

Required commands:

```sh
python -X utf8 -m pytest tests/integration --basetemp=.pytest-tmp-integration
python -X utf8 -m pytest backend/tests --basetemp=.pytest-tmp-backend
```

Backend tests should cover deletion, persistence, checkout, and return behavior. Integration tests should execute frontend functions with a fake fetch implementation and verify the captured calls.
