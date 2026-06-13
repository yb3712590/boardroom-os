# Library backend run instructions

## Backend service command

Run the backend from the repository root with Python 3:

```sh
python backend/server.py
```

By default the service listens on `0.0.0.0:8000`, initializes the SQLite schema, and persists catalog data in `data/library.sqlite3` relative to the current working directory.

## Environment variables

The backend is configured with these environment variables:

| Variable | Purpose | Default |
| --- | --- | --- |
| `HOST` | Bind address for the HTTP server. | `0.0.0.0` |
| `PORT` | TCP port for the HTTP server. | `8000` |
| `LIBRARY_HOST` | Alternate bind address used when `HOST` is unset. | `0.0.0.0` |
| `LIBRARY_PORT` | Alternate TCP port used when `PORT` is unset. | `8000` |
| `LIBRARY_DB_PATH` | SQLite database file path. Parent directories are created automatically. Use a temporary path for isolated tests or local experiments. | `data/library.sqlite3` |
| `LIBRARY_STATIC_DIR` | Optional directory for static frontend files. | unset |
| `STATIC_DIR` | Alternate static directory used when `LIBRARY_STATIC_DIR` is unset. | unset |

Example isolated local run:

```sh
LIBRARY_DB_PATH=/tmp/library.sqlite3 HOST=127.0.0.1 PORT=8000 python backend/server.py
```

## Readiness and frontend URL

After starting the backend, verify readiness with:

```sh
curl http://127.0.0.1:8000/api/health
```

The frontend/static entry point is served by the same backend at:

```text
http://127.0.0.1:8000/
```

If a frontend build or static files exist in `LIBRARY_STATIC_DIR`, `STATIC_DIR`, `backend/static`, `frontend`, or `public`, the backend serves those files. Otherwise `/` returns a small default HTML page.

## Catalog API paths

The JSON API supports the library lifecycle covered by the tests:

| Behavior | Method and path |
| --- | --- |
| Add a book | `POST /api/books` with JSON such as `{ "title": "Dawn", "author": "Octavia E. Butler", "isbn": "9780446603775" }` |
| List books | `GET /api/books` |
| Search books | `GET /api/books?q=Octavia` |
| Fetch one book | `GET /api/books/<id>` |
| Checkout a book | `POST /api/books/<id>/checkout` |
| Return a book | `POST /api/books/<id>/return` |
| Delete a book | `DELETE /api/books/<id>` |

Successful responses are JSON objects with `ok: true`. Errors return JSON with `ok: false` and an `error` message.

## Finite test command

Run the backend unit tests from the repository root with:

```sh
python -m unittest discover -s tests -p 'test_*.py'
```

The tests in `tests/test_backend.py` create a temporary SQLite database for each test case, assert that the catalog starts empty, and do not rely on seeded data in `data/library.sqlite3`.