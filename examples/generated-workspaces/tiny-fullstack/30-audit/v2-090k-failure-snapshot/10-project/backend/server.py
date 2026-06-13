#!/usr/bin/env python3
"""Standard-library SQLite backend for a small library catalog.

The service intentionally depends only on Python's standard library.  It offers a
JSON API for adding, listing, checking out, returning, and deleting books while
persisting state in SQLite.  The database path is configurable with
LIBRARY_DB_PATH and defaults to data/library.sqlite3 relative to the process
working directory.
"""

from __future__ import annotations

import json
import mimetypes
import os
import posixpath
import sqlite3
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

APP_NAME = "library-backend"
DEFAULT_HOST = os.environ.get("HOST", os.environ.get("LIBRARY_HOST", "0.0.0.0"))
DEFAULT_PORT = int(os.environ.get("PORT", os.environ.get("LIBRARY_PORT", "8000")))
_DB_LOCK = threading.RLock()


def configured_db_path() -> str:
    """Return the SQLite path, honoring LIBRARY_DB_PATH."""
    raw = os.environ.get("LIBRARY_DB_PATH") or os.path.join(os.getcwd(), "data", "library.sqlite3")
    if raw != ":memory:":
        raw_path = Path(raw)
        if not raw_path.is_absolute():
            raw_path = Path(os.getcwd()) / raw_path
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        return str(raw_path)
    return raw


DB_PATH = configured_db_path()


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if DB_PATH != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    """Create the books schema if it does not already exist."""
    with _DB_LOCK:
        with connect_db() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    author TEXT NOT NULL DEFAULT '',
                    isbn TEXT NOT NULL DEFAULT '',
                    checked_out INTEGER NOT NULL DEFAULT 0 CHECK (checked_out IN (0, 1)),
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_books_title_author
                ON books(title, author)
                """
            )
            conn.commit()


def row_to_book(row: sqlite3.Row) -> Dict[str, Any]:
    checked_out = bool(row["checked_out"])
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "author": row["author"],
        "isbn": row["isbn"],
        "checked_out": checked_out,
        "available": not checked_out,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def fetch_book(book_id: int) -> Optional[Dict[str, Any]]:
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        return row_to_book(row) if row else None


def list_books(search: str = "") -> List[Dict[str, Any]]:
    with connect_db() as conn:
        if search:
            like = f"%{search}%"
            rows = conn.execute(
                """
                SELECT * FROM books
                WHERE title LIKE ? OR author LIKE ? OR isbn LIKE ?
                ORDER BY id ASC
                """,
                (like, like, like),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM books ORDER BY id ASC").fetchall()
        return [row_to_book(row) for row in rows]


def create_book(payload: Dict[str, Any]) -> Dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    author = str(payload.get("author", "")).strip()
    isbn = str(payload.get("isbn", "")).strip()
    if not title:
        raise ValueError("title is required")
    checked_out = 1 if bool(payload.get("checked_out", False)) else 0
    with _DB_LOCK:
        with connect_db() as conn:
            cur = conn.execute(
                """
                INSERT INTO books(title, author, isbn, checked_out)
                VALUES (?, ?, ?, ?)
                """,
                (title, author, isbn, checked_out),
            )
            conn.commit()
            book_id = int(cur.lastrowid)
    book = fetch_book(book_id)
    if book is None:
        raise RuntimeError("created book could not be loaded")
    return book


def set_checkout_state(book_id: int, checked_out: bool) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    with _DB_LOCK:
        with connect_db() as conn:
            row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
            if row is None:
                return None, "book not found"
            current = bool(row["checked_out"])
            if checked_out and current:
                return row_to_book(row), "book is already checked out"
            if not checked_out and not current:
                return row_to_book(row), "book is not checked out"
            conn.execute(
                """
                UPDATE books
                SET checked_out = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ?
                """,
                (1 if checked_out else 0, book_id),
            )
            conn.commit()
    return fetch_book(book_id), None


def delete_book(book_id: int) -> Optional[Dict[str, Any]]:
    with _DB_LOCK:
        with connect_db() as conn:
            row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
            if row is None:
                return None
            book = row_to_book(row)
            conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
            conn.commit()
            return book


def parse_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def static_roots() -> List[Path]:
    roots: List[Path] = []
    env_root = os.environ.get("LIBRARY_STATIC_DIR") or os.environ.get("STATIC_DIR")
    if env_root:
        roots.append(Path(env_root))
    here = Path(__file__).resolve().parent
    roots.extend(
        [
            here / "static",
            here.parent / "frontend",
            here.parent / "public",
            Path(os.getcwd()) / "frontend",
            Path(os.getcwd()) / "public",
        ]
    )
    seen = set()
    result: List[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


class LibraryRequestHandler(SimpleHTTPRequestHandler):
    server_version = "LibraryBackend/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep standard access logs but make them easy to identify.
        print("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802 - http.server method name
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = self.clean_path(parsed.path)
        query = urllib.parse.parse_qs(parsed.query)
        if path in {"/health", "/ready", "/api/health", "/api/ready"}:
            self.write_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "status": "ok",
                    "service": APP_NAME,
                    "db_path": DB_PATH,
                    "time": time.time(),
                },
            )
            return
        if path in {"/api/books", "/books", "/api/list", "/api/books/list"}:
            search = (query.get("q") or query.get("search") or [""])[0]
            books = list_books(search)
            self.write_json(HTTPStatus.OK, {"ok": True, "books": books, "count": len(books)})
            return
        book_id, action = self.book_id_and_action(path, query)
        if book_id is not None and action in {None, ""}:
            book = fetch_book(book_id)
            if book is None:
                self.write_error(HTTPStatus.NOT_FOUND, "book not found")
            else:
                self.write_json(HTTPStatus.OK, {"ok": True, "book": book})
            return
        self.serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = self.clean_path(parsed.path)
        query = urllib.parse.parse_qs(parsed.query)
        payload = self.read_json_body()
        if payload is None:
            return

        if path in {"/api/books", "/books", "/api/add", "/api/book", "/api/books/add"}:
            self.handle_create_book(payload)
            return

        book_id, action = self.book_id_and_action(path, query, payload)
        if action in {"checkout", "check-out", "borrow"}:
            self.handle_checkout(book_id)
            return
        if action in {"return", "checkin", "check-in"}:
            self.handle_return(book_id)
            return
        if action in {"delete", "remove"}:
            self.handle_delete(book_id)
            return

        self.write_error(HTTPStatus.NOT_FOUND, "unknown endpoint")

    def do_PUT(self) -> None:  # noqa: N802
        self.do_POST()

    def do_PATCH(self) -> None:  # noqa: N802
        self.do_POST()

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = self.clean_path(parsed.path)
        query = urllib.parse.parse_qs(parsed.query)
        book_id, _action = self.book_id_and_action(path, query)
        self.handle_delete(book_id)

    @staticmethod
    def clean_path(path: str) -> str:
        path = urllib.parse.unquote(path or "/")
        if not path.startswith("/"):
            path = "/" + path
        normalized = posixpath.normpath(path)
        if normalized == ".":
            normalized = "/"
        return normalized

    def read_json_body(self) -> Optional[Dict[str, Any]]:
        length = parse_int(self.headers.get("Content-Length")) or 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            decoded = raw.decode("utf-8")
            data = json.loads(decoded) if decoded.strip() else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.write_error(HTTPStatus.BAD_REQUEST, "request body must be valid JSON")
            return None
        if not isinstance(data, dict):
            self.write_error(HTTPStatus.BAD_REQUEST, "JSON body must be an object")
            return None
        return data

    def write_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_error(self, status: int, message: str, **extra: Any) -> None:
        payload = {"ok": False, "error": message}
        payload.update(extra)
        self.write_json(status, payload)

    def book_id_and_action(
        self,
        path: str,
        query: Dict[str, List[str]],
        payload: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        payload = payload or {}
        parts = [part for part in path.split("/") if part]
        action: Optional[str] = None
        book_id: Optional[int] = None

        # Supported route forms include:
        #   /api/books/1/checkout
        #   /books/1/return
        #   /api/checkout/1
        #   /api/checkout?id=1
        #   /api/books/checkout with {"id": 1}
        if parts[:2] == ["api", "books"]:
            if len(parts) >= 3:
                maybe_id = parse_int(parts[2])
                if maybe_id is not None:
                    book_id = maybe_id
                    action = parts[3].lower() if len(parts) >= 4 else None
                else:
                    action = parts[2].lower()
            if len(parts) >= 4 and book_id is None:
                book_id = parse_int(parts[3])
        elif parts[:1] == ["books"]:
            if len(parts) >= 2:
                book_id = parse_int(parts[1])
            if len(parts) >= 3:
                action = parts[2].lower()
        elif parts[:1] == ["api"] and len(parts) >= 2:
            action = parts[1].lower()
            if len(parts) >= 3:
                book_id = parse_int(parts[2])
        elif len(parts) >= 1:
            action = parts[0].lower()
            if len(parts) >= 2:
                book_id = parse_int(parts[1])

        if book_id is None:
            for key in ("id", "book_id", "bookId"):
                values = query.get(key)
                if values:
                    book_id = parse_int(values[0])
                    if book_id is not None:
                        break
        if book_id is None:
            for key in ("id", "book_id", "bookId"):
                book_id = parse_int(payload.get(key))
                if book_id is not None:
                    break
        if action is None:
            raw_action = payload.get("action") or payload.get("status")
            action = str(raw_action).lower() if raw_action else None
        return book_id, action

    def handle_create_book(self, payload: Dict[str, Any]) -> None:
        try:
            book = create_book(payload)
        except ValueError as exc:
            self.write_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self.write_json(HTTPStatus.CREATED, {"ok": True, "book": book, "id": book["id"]})

    def handle_checkout(self, book_id: Optional[int]) -> None:
        if book_id is None:
            self.write_error(HTTPStatus.BAD_REQUEST, "book id is required")
            return
        book, error = set_checkout_state(book_id, True)
        if book is None:
            self.write_error(HTTPStatus.NOT_FOUND, error or "book not found")
        elif error:
            self.write_error(HTTPStatus.CONFLICT, error, book=book)
        else:
            self.write_json(HTTPStatus.OK, {"ok": True, "book": book})

    def handle_return(self, book_id: Optional[int]) -> None:
        if book_id is None:
            self.write_error(HTTPStatus.BAD_REQUEST, "book id is required")
            return
        book, error = set_checkout_state(book_id, False)
        if book is None:
            self.write_error(HTTPStatus.NOT_FOUND, error or "book not found")
        elif error:
            self.write_error(HTTPStatus.CONFLICT, error, book=book)
        else:
            self.write_json(HTTPStatus.OK, {"ok": True, "book": book})

    def handle_delete(self, book_id: Optional[int]) -> None:
        if book_id is None:
            self.write_error(HTTPStatus.BAD_REQUEST, "book id is required")
            return
        book = delete_book(book_id)
        if book is None:
            self.write_error(HTTPStatus.NOT_FOUND, "book not found")
        else:
            self.write_json(HTTPStatus.OK, {"ok": True, "deleted": True, "book": book, "id": book_id})

    def serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            for root in static_roots():
                index = root / "index.html"
                if index.is_file():
                    self.send_file(index, "text/html; charset=utf-8")
                    return
            self.write_default_index()
            return

        relative = path.lstrip("/")
        for root in static_roots():
            candidate = (root / relative).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            if candidate.is_file():
                content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
                self.send_file(candidate, content_type)
                return
        self.write_error(HTTPStatus.NOT_FOUND, "not found")

    def send_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def write_default_index(self) -> None:
        body = (
            "<!doctype html><html><head><meta charset='utf-8'><title>Library</title></head>"
            "<body><h1>Library Backend</h1>"
            "<p>The JSON API is available at <code>/api/books</code>.</p>"
            "</body></html>"
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    init_db()
    httpd = ThreadingHTTPServer((host, port), LibraryRequestHandler)
    print(f"{APP_NAME} listening on http://{host}:{port}")
    print(f"SQLite database: {DB_PATH}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run()
