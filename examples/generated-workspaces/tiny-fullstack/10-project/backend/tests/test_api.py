import contextlib
import importlib
import inspect
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

app = importlib.import_module('backend.app')


def _new_store(tmp_path):
    db_path = tmp_path / 'library.sqlite3'
    return app.create_store(str(db_path)), db_path


def _books(store):
    return list(app.list_books(store=store))


def _field(book, name):
    if isinstance(book, dict):
        assert name in book, f'missing {name!r} in {book!r}'
        return book[name]
    try:
        keys = book.keys()
    except AttributeError:
        keys = None
    if keys is not None and name in keys:
        return book[name]
    if hasattr(book, name):
        return getattr(book, name)
    if isinstance(book, (tuple, list)):
        if name == 'id':
            return book[0]
        if name == 'title':
            return book[1]
        if name == 'state':
            return book[2] if len(book) > 2 else book[-1]
    raise AssertionError(f'cannot read field {name!r} from {book!r}')


def _find_book(books, book_id):
    for book in books:
        if _field(book, 'id') == book_id:
            return book
    raise AssertionError(f'book id {book_id!r} was not present in {books!r}')


def _state_from_mutation_result(mutation_result, book_id, store):
    if mutation_result in ('IN_LIBRARY', 'CHECKED_OUT'):
        return mutation_result
    try:
        return _field(mutation_result, 'state')
    except Exception:
        return _field(_find_book(_books(store), book_id), 'state')


def _quote_identifier(name):
    return chr(34) + name.replace(chr(34), chr(34) * 2) + chr(34)


def test_public_api_signatures_are_explicit_and_expose_required_arguments():
    required_parameters = {
        'create_store': 'db_path',
        'create_book': 'title',
        'checkout_book': 'book_id',
        'return_book': 'book_id',
        'delete_book': 'book_id',
    }
    for name in ('create_store', 'create_book', 'list_books', 'checkout_book', 'return_book', 'delete_book'):
        function = getattr(app, name, None)
        assert callable(function), f'backend.app.{name} must be callable'
        signature = inspect.signature(function)
        variadic = [parameter.name for parameter in signature.parameters.values() if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)]
        assert not variadic, f'{name} uses non-inspectable variadic parameters: {variadic}'
        if name in required_parameters:
            assert required_parameters[name] in signature.parameters
        if name != 'create_store':
            assert 'store' in signature.parameters, f'{name} must accept an optional store parameter'
            store_parameter = signature.parameters['store']
            assert store_parameter.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
            assert store_parameter.default is not inspect.Signature.empty

    db = importlib.import_module('backend.db')
    BookStore = getattr(db, 'BookStore', None)
    assert inspect.isclass(BookStore), 'backend.db.BookStore must be a class'
    assert 'db_path' in inspect.signature(BookStore).parameters
    for method_name in ('create_book', 'list_books', 'checkout_book', 'return_book', 'delete_book'):
        method = getattr(BookStore, method_name, None)
        assert callable(method), f'BookStore.{method_name} must be callable'
        method_signature = inspect.signature(method)
        variadic = [parameter.name for parameter in method_signature.parameters.values() if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)]
        assert not variadic, f'BookStore.{method_name} uses variadic parameters: {variadic}'


def test_create_book_defaults_to_in_library_and_list_books_returns_created_book(tmp_path):
    store, db_path = _new_store(tmp_path)
    title = 'The Left Hand of Darkness'

    created = app.create_book(title, store=store)

    assert db_path.exists(), 'creating a book should create the SQLite database file'
    assert _field(created, 'title') == title
    assert _field(created, 'state') == 'IN_LIBRARY'
    book_id = _field(created, 'id')
    listed = _books(store)
    listed_book = _find_book(listed, book_id)
    assert _field(listed_book, 'title') == title
    assert _field(listed_book, 'state') == 'IN_LIBRARY'


def test_checkout_and_return_change_book_state(tmp_path):
    store, _db_path = _new_store(tmp_path)
    created = app.create_book('A Wizard of Earthsea', store=store)
    book_id = _field(created, 'id')

    checked_out = app.checkout_book(book_id, store=store)
    assert _state_from_mutation_result(checked_out, book_id, store) == 'CHECKED_OUT'
    assert _field(_find_book(_books(store), book_id), 'state') == 'CHECKED_OUT'

    returned = app.return_book(book_id, store=store)
    assert _state_from_mutation_result(returned, book_id, store) == 'IN_LIBRARY'
    assert _field(_find_book(_books(store), book_id), 'state') == 'IN_LIBRARY'


def test_delete_book_removes_book_from_listing(tmp_path):
    store, _db_path = _new_store(tmp_path)
    first = app.create_book('Kindred', store=store)
    second = app.create_book('Parable of the Sower', store=store)
    deleted_id = _field(first, 'id')
    remaining_id = _field(second, 'id')

    app.delete_book(deleted_id, store=store)

    remaining_books = _books(store)
    remaining_ids = [_field(book, 'id') for book in remaining_books]
    assert deleted_id not in remaining_ids
    assert remaining_id in remaining_ids


def test_sqlite_file_persists_books_across_store_instances_and_is_removable(tmp_path):
    db_path = tmp_path / 'persistent.sqlite3'
    title = 'Station Eleven'
    store = app.create_store(str(db_path))
    created = app.create_book(title, store=store)
    created_id = _field(created, 'id')

    assert db_path.exists()
    store_again = app.create_store(str(db_path))
    persisted = _find_book(_books(store_again), created_id)
    assert _field(persisted, 'title') == title
    assert _field(persisted, 'state') == 'IN_LIBRARY'

    with contextlib.closing(sqlite3.connect(str(db_path))) as conn:
        tables = [row[0] for row in conn.execute('SELECT name FROM sqlite_master WHERE type = ?', ('table',)).fetchall()]
        assert tables, 'SQLite database did not contain any tables'
        direct_rows = []
        for table in tables:
            qname = _quote_identifier(table)
            columns = [row[1] for row in conn.execute(f'PRAGMA table_info({qname})').fetchall()]
            if 'title' in columns and 'state' in columns:
                direct_rows.extend(conn.execute(f'SELECT title, state FROM {qname} WHERE title = ?', (title,)).fetchall())
        assert any(row[0] == title and row[1] == 'IN_LIBRARY' for row in direct_rows), 'created book was not directly visible in a SQLite table with title/state columns'

    db_path.unlink()
    assert not db_path.exists()
