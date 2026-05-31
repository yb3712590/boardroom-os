import os
import tempfile
import uuid

try:
    from .db import BookStore, CHECKED_OUT, IN_LIBRARY
except ImportError:  # pragma: no cover - supports running this file directly.
    from db import BookStore, CHECKED_OUT, IN_LIBRARY

_DEFAULT_DB_PATH = os.environ.get("TINY_BOOKSTORE_DB_PATH")
if not _DEFAULT_DB_PATH:
    _DEFAULT_DB_PATH = os.path.join(
        tempfile.gettempdir(),
        "tiny_fullstack_bookstore_" + uuid.uuid4().hex + ".sqlite3",
    )

_DEFAULT_STORE = None


def create_store(db_path):
    """Create a SQLite-backed BookStore and make it the module default store."""
    global _DEFAULT_STORE
    _DEFAULT_STORE = BookStore(db_path)
    return _DEFAULT_STORE


def _resolve_store(store):
    global _DEFAULT_STORE
    if store is not None:
        if isinstance(store, (str, bytes, os.PathLike)):
            return BookStore(store)
        return store
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = BookStore(_DEFAULT_DB_PATH)
    return _DEFAULT_STORE


def create_book(title, store=None):
    """Create a book with state IN_LIBRARY and return it as a dict."""
    return _resolve_store(store).create_book(title)


def list_books(store=None):
    """Return all books ordered by id."""
    return _resolve_store(store).list_books()


def checkout_book(book_id, store=None):
    """Mark a book CHECKED_OUT and return the updated book dict."""
    return _resolve_store(store).checkout_book(book_id)


def return_book(book_id, store=None):
    """Mark a book IN_LIBRARY and return the updated book dict."""
    return _resolve_store(store).return_book(book_id)


def delete_book(book_id, store=None):
    """Delete a book by id. Returns True when a row was deleted, otherwise False."""
    return _resolve_store(store).delete_book(book_id)


__all__ = [
    "BookStore",
    "IN_LIBRARY",
    "CHECKED_OUT",
    "create_store",
    "create_book",
    "list_books",
    "checkout_book",
    "return_book",
    "delete_book",
]
