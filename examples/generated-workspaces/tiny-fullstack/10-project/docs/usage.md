# Usage Guide

This guide shows the expected workflow for the tiny library package.

## Backend workflow

```python
from backend.app import create_store, create_book, list_books, checkout_book, return_book, delete_book

store = create_store('library.sqlite3')
book = create_book('Example Book', store=store)
print(list_books(store=store))

checked_out = checkout_book(book['id'], store=store)
print(checked_out)

returned = return_book(book['id'], store=store)
print(returned)

delete_book(book['id'], store=store)
print(list_books(store=store))
```

Expected state transitions:

1. New books are created as `IN_LIBRARY`.
2. Checking out a book changes it to `CHECKED_OUT`.
3. Returning a book changes it back to `IN_LIBRARY`.
4. Deleting a book removes it from later `list_books` results.

## Frontend workflow

```javascript
import { loadBooks, deleteBook } from './frontend/app.js';

const books = await loadBooks(fetch);
await deleteBook(fetch, books[0].id);
```

`loadBooks(fetchImpl)` performs a request to `/books`.

`deleteBook(fetchImpl, bookId)` performs a `DELETE` request for the selected book resource.

## Verification commands

Run the integration tests:

```sh
python -X utf8 -m pytest tests/integration --basetemp=.pytest-tmp-integration
```

Run the backend tests:

```sh
python -X utf8 -m pytest backend/tests --basetemp=.pytest-tmp-backend
```
