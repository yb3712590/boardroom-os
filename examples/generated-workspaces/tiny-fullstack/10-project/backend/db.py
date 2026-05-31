import atexit
import os
import sqlite3
import tempfile
import uuid
from contextlib import closing
from pathlib import Path

IN_LIBRARY = "IN_LIBRARY"
CHECKED_OUT = "CHECKED_OUT"
_VALID_STATES = (IN_LIBRARY, CHECKED_OUT)


class BookStore:
    """SQLite-backed storage for a tiny library.

    The store keeps only the database path on the instance. Each operation opens
    a fresh sqlite3 connection and closes it before returning, which keeps tests
    free to remove temporary database files on Windows.
    """

    def __init__(self, db_path):
        if db_path is None:
            raise ValueError("db_path is required")
        decoded_path = os.fsdecode(db_path)
        if not decoded_path:
            raise ValueError("db_path must not be empty")
        self._cleanup_path = None
        if decoded_path == ":memory:":
            decoded_path = os.path.join(
                tempfile.gettempdir(),
                "tiny_bookstore_" + uuid.uuid4().hex + ".sqlite3",
            )
            self._cleanup_path = decoded_path
            atexit.register(self._cleanup_file, decoded_path)
        self.db_path = decoded_path
        self._ensure_parent_directory()
        self._initialize_schema()

    @staticmethod
    def _cleanup_file(path):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def _ensure_parent_directory(self):
        parent = Path(self.db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)

    def _connect(self):
        self._ensure_parent_directory()
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_schema(self):
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS books (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        state TEXT NOT NULL CHECK (state IN ('IN_LIBRARY', 'CHECKED_OUT'))
                    )
                    """
                )

    @staticmethod
    def _validate_title(title):
        if not isinstance(title, str):
            raise TypeError("title must be a string")
        if not title.strip():
            raise ValueError("title must not be empty")
        return title

    @staticmethod
    def _normalize_book_id(book_id):
        if isinstance(book_id, bool):
            raise TypeError("book_id must be an integer")
        try:
            normalized = int(book_id)
        except (TypeError, ValueError):
            raise TypeError("book_id must be an integer") from None
        if normalized < 1:
            raise ValueError("book_id must be a positive integer")
        return normalized

    @staticmethod
    def _row_to_book(row):
        if row is None:
            return None
        return {"id": int(row["id"]), "title": row["title"], "state": row["state"]}

    def _fetch_book_row(self, conn, book_id):
        return conn.execute(
            "SELECT id, title, state FROM books WHERE id = ?",
            (book_id,),
        ).fetchone()

    def create_book(self, title):
        title = self._validate_title(title)
        with closing(self._connect()) as conn:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO books (title, state) VALUES (?, ?)",
                    (title, IN_LIBRARY),
                )
                row = self._fetch_book_row(conn, cursor.lastrowid)
                return self._row_to_book(row)

    def list_books(self):
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, title, state FROM books ORDER BY id"
            ).fetchall()
            return [self._row_to_book(row) for row in rows]

    def get_book(self, book_id):
        book_id = self._normalize_book_id(book_id)
        with closing(self._connect()) as conn:
            return self._row_to_book(self._fetch_book_row(conn, book_id))

    def checkout_book(self, book_id):
        book_id = self._normalize_book_id(book_id)
        with closing(self._connect()) as conn:
            with conn:
                if self._fetch_book_row(conn, book_id) is None:
                    raise KeyError("book not found: %s" % book_id)
                conn.execute(
                    "UPDATE books SET state = ? WHERE id = ?",
                    (CHECKED_OUT, book_id),
                )
                return self._row_to_book(self._fetch_book_row(conn, book_id))

    def return_book(self, book_id):
        book_id = self._normalize_book_id(book_id)
        with closing(self._connect()) as conn:
            with conn:
                if self._fetch_book_row(conn, book_id) is None:
                    raise KeyError("book not found: %s" % book_id)
                conn.execute(
                    "UPDATE books SET state = ? WHERE id = ?",
                    (IN_LIBRARY, book_id),
                )
                return self._row_to_book(self._fetch_book_row(conn, book_id))

    def delete_book(self, book_id):
        book_id = self._normalize_book_id(book_id)
        with closing(self._connect()) as conn:
            with conn:
                cursor = conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
                return cursor.rowcount > 0

    add_book = create_book
    get_books = list_books
    remove_book = delete_book


__all__ = ["BookStore", "IN_LIBRARY", "CHECKED_OUT"]
