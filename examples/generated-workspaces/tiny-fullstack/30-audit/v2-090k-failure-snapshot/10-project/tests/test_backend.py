import json
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import server as library_server  # noqa: E402


class LibraryBackendTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tempdir.name) / "isolated-library.sqlite3")
        self.original_db_path = library_server.DB_PATH
        library_server.DB_PATH = self.db_path
        library_server.init_db()
        self.assertEqual(library_server.list_books(), [], "tests must start from an empty, unseeded catalog")

    def tearDown(self):
        library_server.DB_PATH = self.original_db_path
        self.tempdir.cleanup()

    def test_add_and_list_books_without_seed_data(self):
        first = library_server.create_book(
            {"title": "Parable of the Sower", "author": "Octavia E. Butler", "isbn": "9780446675505"}
        )
        second = library_server.create_book(
            {"title": "A Wizard of Earthsea", "author": "Ursula K. Le Guin", "isbn": "9780547773742"}
        )

        self.assertIsInstance(first["id"], int)
        self.assertFalse(first["checked_out"])
        self.assertTrue(first["available"])
        self.assertEqual(first["title"], "Parable of the Sower")

        all_books = library_server.list_books()
        self.assertEqual([book["id"] for book in all_books], [first["id"], second["id"]])
        self.assertEqual([book["title"] for book in all_books], ["Parable of the Sower", "A Wizard of Earthsea"])

        search_results = library_server.list_books("Octavia")
        self.assertEqual(len(search_results), 1)
        self.assertEqual(search_results[0]["id"], first["id"])

    def test_checkout_and_return_state_transitions(self):
        book = library_server.create_book({"title": "Kindred", "author": "Octavia E. Butler"})

        checked_out, error = library_server.set_checkout_state(book["id"], True)
        self.assertIsNone(error)
        self.assertTrue(checked_out["checked_out"])
        self.assertFalse(checked_out["available"])

        still_checked_out, error = library_server.set_checkout_state(book["id"], True)
        self.assertEqual(error, "book is already checked out")
        self.assertTrue(still_checked_out["checked_out"])

        returned, error = library_server.set_checkout_state(book["id"], False)
        self.assertIsNone(error)
        self.assertFalse(returned["checked_out"])
        self.assertTrue(returned["available"])

        still_returned, error = library_server.set_checkout_state(book["id"], False)
        self.assertEqual(error, "book is not checked out")
        self.assertFalse(still_returned["checked_out"])

    def test_delete_book_removes_book_from_catalog(self):
        book = library_server.create_book({"title": "The Left Hand of Darkness", "author": "Ursula K. Le Guin"})

        deleted = library_server.delete_book(book["id"])
        self.assertEqual(deleted["id"], book["id"])
        self.assertIsNone(library_server.fetch_book(book["id"]))
        self.assertEqual(library_server.list_books(), [])
        self.assertIsNone(library_server.delete_book(book["id"]))

    def test_sqlite_persistence_uses_isolated_database_file(self):
        created = library_server.create_book(
            {"title": "The Dispossessed", "author": "Ursula K. Le Guin", "isbn": "9780061054884"}
        )
        self.assertTrue(Path(self.db_path).is_file())

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT title, author, isbn, checked_out FROM books WHERE id = ?", (created["id"],)
            ).fetchone()
        self.assertEqual(row, ("The Dispossessed", "Ursula K. Le Guin", "9780061054884", 0))

        library_server.init_db()
        persisted = library_server.fetch_book(created["id"])
        self.assertEqual(persisted["title"], "The Dispossessed")
        self.assertEqual(library_server.list_books(), [persisted])

    def test_http_api_paths_for_catalog_lifecycle(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), library_server.LibraryRequestHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            health_status, health = self.request_json(base_url, "GET", "/api/health")
            self.assertEqual(health_status, 200)
            self.assertTrue(health["ok"])
            self.assertEqual(health["db_path"], self.db_path)

            create_status, created = self.request_json(
                base_url,
                "POST",
                "/api/books",
                {"title": "Dawn", "author": "Octavia E. Butler", "isbn": "9780446603775"},
            )
            self.assertEqual(create_status, 201)
            book_id = created["id"]

            list_status, listed = self.request_json(base_url, "GET", "/api/books")
            self.assertEqual(list_status, 200)
            self.assertEqual(listed["count"], 1)
            self.assertEqual(listed["books"][0]["id"], book_id)

            checkout_status, checkout = self.request_json(base_url, "POST", f"/api/books/{book_id}/checkout", {})
            self.assertEqual(checkout_status, 200)
            self.assertTrue(checkout["book"]["checked_out"])

            return_status, returned = self.request_json(base_url, "POST", f"/api/books/{book_id}/return", {})
            self.assertEqual(return_status, 200)
            self.assertFalse(returned["book"]["checked_out"])

            delete_status, deleted = self.request_json(base_url, "DELETE", f"/api/books/{book_id}")
            self.assertEqual(delete_status, 200)
            self.assertTrue(deleted["deleted"])

            final_status, final_list = self.request_json(base_url, "GET", "/api/books")
            self.assertEqual(final_status, 200)
            self.assertEqual(final_list["books"], [])
        finally:
            httpd.shutdown()
            thread.join(timeout=5)
            httpd.server_close()

    def request_json(self, base_url, method, path, payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)


if __name__ == "__main__":
    unittest.main()
