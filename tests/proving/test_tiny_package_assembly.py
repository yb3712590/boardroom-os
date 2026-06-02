from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from boardroom_os.contracts.types import SourceSurfaceRef
from boardroom_os.evidence.table import FinalEvidenceStatus
from boardroom_os.workspace.assembler import PackageArtifactKind, PackageArtifactPath

_VERIFY_ERRORS = (ValueError, ValidationError)


def _build_negative_tiny_package_fixture(tmp_path: Path, *, package_contents):
    from tests.proving.fixtures.tiny_package_assembly import (
        build_tiny_package_assembly_fixture,
    )
    from tests.proving.fixtures.tiny_provider_attempts import (
        build_tiny_provider_attempt_fixture,
    )

    return build_tiny_package_assembly_fixture(
        package_root=tmp_path / "physical-package-root",
        package_contents=package_contents,
        provider_fixture=build_tiny_provider_attempt_fixture(use_fake_results=True),
        allow_fake_provider_for_negative_tests=True,
    )


def test_tiny_package_assembly_rejects_ref_only_source_inventory(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        build_tiny_package_assembly_fixture,
    )

    fixture = build_tiny_package_assembly_fixture(
        package_root=tmp_path / "physical-package-root",
    )

    with pytest.raises(_VERIFY_ERRORS, match="ref-only|source files|lineage"):
        fixture.build_source_inventory(source_files=(), lineage_records=())


def test_tiny_package_assembly_rejects_missing_run_manifest_artifact(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import TINY_PACKAGE_CONTENTS

    fixture = _build_negative_tiny_package_fixture(
        tmp_path,
        package_contents=TINY_PACKAGE_CONTENTS,
    )
    artifacts = tuple(
        artifact
        for artifact in fixture.package_artifacts
        if artifact.relative_path.value != "run-manifest.json"
    )

    with pytest.raises(_VERIFY_ERRORS, match="run-manifest.json"):
        fixture.assemble_package(artifacts=artifacts)


@pytest.mark.parametrize(
    "bad_path",
    [
        "/tmp/backend/app.py",
        "../backend/app.py",
        "20-evidence/source-inventory/source-inventory.json",
        "30-audit/process-audit.md",
        "00-boardroom/tickets/ticket.json",
        "10-project/backend/app.py",
    ],
)
def test_tiny_package_assembly_rejects_artifact_outside_package_root(
    bad_path: str,
) -> None:
    with pytest.raises(_VERIFY_ERRORS, match="package artifact path|relative|parent|10-project|workspace"):
        PackageArtifactPath(value=bad_path)


@pytest.mark.parametrize("reserved_root", [Path("10-project"), Path("20-evidence")])
def test_tiny_package_assembly_requires_isolated_tmp_package_root(
    reserved_root: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        build_tiny_package_assembly_fixture,
    )

    with pytest.raises(_VERIFY_ERRORS, match="isolated tmp package root"):
        build_tiny_package_assembly_fixture(package_root=reserved_root)


def test_tiny_generated_package_locates_package_source_and_evidence(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        EXPECTED_TINY_PACKAGE_PATHS,
        build_tiny_package_assembly_fixture,
    )

    fixture = build_tiny_package_assembly_fixture(
        package_root=tmp_path / "physical-package-root",
    )

    assert fixture.workspace_manifest.package_root.value == "10-project"
    assert fixture.package_assembly.package_root.value == "10-project"
    assert {artifact.relative_path.value for artifact in fixture.package_assembly.artifacts} == set(
        EXPECTED_TINY_PACKAGE_PATHS
    )
    assert fixture.command_results_by_id["test-backend"].verification_run.exit_code == 0
    assert fixture.command_results_by_id["test-integration"].verification_run.exit_code == 0
    assert "passed" in fixture.command_results_by_id["test-backend"].stdout
    assert "passed" in fixture.command_results_by_id["test-integration"].stdout
    assert fixture.run_manifest.package_contract_ref == fixture.package_contract.package_contract_id
    assert fixture.source_inventory.package_assembly_ref == fixture.package_assembly.package_assembly_id
    assert fixture.final_evidence_table.complete is False
    assert fixture.workspace_evidence_bundle is None

    inventory_paths = {entry.path.value for entry in fixture.source_inventory.entries}
    assert inventory_paths == {
        "backend/app.py",
        "backend/db.py",
        "docs/usage.md",
        "frontend/app.js",
        "frontend/index.html",
        "backend/tests/test_api.py",
        "tests/integration/test_frontend_backend.py",
    }
    assert fixture.workspace_evidence_bundle is None
    assert "def delete_book" in fixture.source_contents["backend/app.py"]
    assert "sqlite3.connect" in fixture.source_contents["backend/db.py"]
    assert "CREATE TABLE" in fixture.source_contents["backend/db.py"]
    assert "delete_book" in fixture.source_contents["backend/tests/test_api.py"]
    assert "sqlite3.connect" in fixture.source_contents["backend/tests/test_api.py"]
    assert {
        row.acceptance_ref.value
        for row in fixture.final_evidence_table.rows
        if row.status is FinalEvidenceStatus.SATISFIED
    } == {
        "AC-TINY-API-BOOK-CREATE",
        "AC-TINY-API-BOOK-LIST",
        "AC-TINY-API-CHECKOUT-RETURN",
        "AC-TINY-API-BOOK-DELETE",
        "AC-TINY-PERSISTENCE-SQLITE",
    }
    assert {
        row.acceptance_ref.value
        for row in fixture.final_evidence_table.rows
        if row.status is FinalEvidenceStatus.MISSING
    } == {
        "AC-TINY-BACKEND-STARTUP",
        "AC-TINY-BACKEND-HTTP-CRUD",
        "AC-TINY-SQLITE-PERSISTENCE-VIA-HTTP",
        "AC-TINY-FRONTEND-STARTUP",
        "AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION",
        "AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",
    }
    assert "AC-TINY-UI-FETCH-BACKEND" not in {
        acceptance_ref.value
        for artifact in fixture.package_artifacts
        for acceptance_ref in artifact.acceptance_refs
    }
    assert "AC-TINY-RUN-TEST-COMMANDS" not in {
        acceptance_ref.value
        for artifact in fixture.package_artifacts
        for acceptance_ref in artifact.acceptance_refs
    }


def test_tiny_package_assembly_rejects_missing_delete_book_api(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
    )

    broken_contents = dict(TINY_PACKAGE_CONTENTS)
    broken_contents["backend/app.py"] = broken_contents["backend/app.py"].replace(
        "def delete_book(book_id, *, store=None):",
        "def remove_book(book_id, *, store=None):",
    )

    with pytest.raises(_VERIFY_ERRORS, match="delete_book|AC-TINY-API-BOOK-DELETE"):
        _build_negative_tiny_package_fixture(
            tmp_path,
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_rejects_non_sqlite_persistence(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
    )

    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "backend/db.py": (
            "def persist_state(book):\n"
            "    return {'title': book['title'], 'state': book['state']}\n"
        ),
    }

    with pytest.raises(_VERIFY_ERRORS, match="SQLite|sqlite3|AC-TINY-PERSISTENCE-SQLITE"):
        _build_negative_tiny_package_fixture(
            tmp_path,
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_rejects_missing_sqlite_test_import(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import TINY_PACKAGE_CONTENTS

    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "backend/tests/test_api.py": (
            TINY_PACKAGE_CONTENTS["backend/tests/test_api.py"]
            .replace("import sqlite3\n\n", "")
        ),
    }

    with pytest.raises(_VERIFY_ERRORS, match="SQLite verification evidence"):
        _build_negative_tiny_package_fixture(
            tmp_path,
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_accepts_sqlite_cleanup_evidence_without_schema_query(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import TINY_PACKAGE_CONTENTS

    package_contents = {
        **TINY_PACKAGE_CONTENTS,
        "backend/tests/test_api.py": (
            "import sqlite3\n\n"
            "from backend.app import checkout_book, create_book, delete_book, list_books, return_book\n"
            "from backend.db import BookStore\n\n"
            "def test_backend_api_delete_and_sqlite_persistence_contract(tmp_path):\n"
            "    db_path = tmp_path / 'books.sqlite3'\n"
            "    store = BookStore(db_path)\n"
            "    book = create_book('Dune', store=store)\n"
            "    assert book['state'] == 'IN_LIBRARY'\n"
            "    assert db_path.exists()\n"
            "    assert not any(isinstance(value, sqlite3.Connection) for value in vars(store).values())\n"
            "    checked_out = checkout_book(book['id'], store=store)\n"
            "    assert checked_out['state'] == 'CHECKED_OUT'\n"
            "    reopened = BookStore(db_path)\n"
            "    assert reopened.get_book(book['id'])['state'] == 'CHECKED_OUT'\n"
            "    returned = return_book(book['id'], store=reopened)\n"
            "    assert returned['state'] == 'IN_LIBRARY'\n"
            "    assert list_books(store=reopened)[0]['title'] == 'Dune'\n"
            "    deleted = delete_book(book['id'], store=reopened)\n"
            "    assert deleted == {'id': book['id'], 'deleted': True}\n"
            "    assert list_books(store=BookStore(db_path)) == []\n"
        ),
    }

    fixture = _build_negative_tiny_package_fixture(
        tmp_path,
        package_contents=package_contents,
    )

    assert fixture.final_evidence_table.complete is False


def test_tiny_package_assembly_rejects_persistent_sqlite_connection(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import TINY_PACKAGE_CONTENTS

    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "backend/db.py": (
            "import sqlite3\n\n"
            "class BookStore:\n"
            "    def __init__(self, db_path):\n"
            "        self.db_path = str(db_path)\n"
            "        self._conn = sqlite3.connect(self.db_path)\n"
            "    def add_book(self, title):\n"
            "        self._conn.execute('CREATE TABLE IF NOT EXISTS books (id INTEGER, title TEXT, state TEXT)')\n"
            "        self._conn.execute('INSERT INTO books(title, state) VALUES (?, ?)', (title, 'IN_LIBRARY'))\n"
            "        self._conn.commit()\n"
            "    def set_book_state(self, book_id, state):\n"
            "        self._conn.execute('UPDATE books SET state = ? WHERE id = ?', (state, book_id))\n"
            "    def delete_book(self, book_id):\n"
            "        self._conn.execute('DELETE FROM books WHERE id = ?', (book_id,))\n"
        ),
    }

    with pytest.raises(_VERIFY_ERRORS, match="SQLite connection|Windows"):
        _build_negative_tiny_package_fixture(
            tmp_path,
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_rejects_invalid_sql_create_table_literal(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import TINY_PACKAGE_CONTENTS

    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "backend/db.py": (
            TINY_PACKAGE_CONTENTS["backend/db.py"]
            + "\nBROKEN_SQL = \"CREATE TABLE books (id INTEGER, author TEXT NOT NULL DEFAULT , state TEXT)\"\n"
        ),
    }

    with pytest.raises(_VERIFY_ERRORS, match="SQLite|CREATE TABLE|schema"):
        _build_negative_tiny_package_fixture(
            tmp_path,
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_rejects_unclosed_sqlite_test_connection(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import TINY_PACKAGE_CONTENTS

    broken_contents = dict(TINY_PACKAGE_CONTENTS)
    broken_contents["backend/tests/test_api.py"] = (
        TINY_PACKAGE_CONTENTS["backend/tests/test_api.py"]
        .replace("from contextlib import closing\n", "")
        .replace("with closing(sqlite3.connect(db_path)) as connection:\n", "with sqlite3.connect(db_path) as connection:\n")
    )

    with pytest.raises(_VERIFY_ERRORS, match="SQLite test connection|Windows"):
        _build_negative_tiny_package_fixture(
            tmp_path,
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_rejects_frontend_default_fetch_signature(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import TINY_PACKAGE_CONTENTS

    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "frontend/app.js": (
            TINY_PACKAGE_CONTENTS["frontend/app.js"]
            .replace("loadBooks(fetchImpl)", "loadBooks(fetchImpl = globalThis.fetch)")
            .replace("deleteBook(fetchImpl, bookId)", "deleteBook(fetchImpl = globalThis.fetch, bookId)")
        ),
    }

    with pytest.raises(_VERIFY_ERRORS, match="loadBooks\\(fetchImpl\\)|deleteBook"):
        _build_negative_tiny_package_fixture(
            tmp_path,
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_rejects_unguarded_frontend_window_listener(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import TINY_PACKAGE_CONTENTS

    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "frontend/app.js": (
            TINY_PACKAGE_CONTENTS["frontend/app.js"]
            + "\nwindow.addEventListener('DOMContentLoaded', () => {});\n"
        ),
    }

    with pytest.raises(_VERIFY_ERRORS, match="window.addEventListener|frontend module"):
        _build_negative_tiny_package_fixture(
            tmp_path,
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_rejects_regex_only_frontend_integration_test(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import TINY_PACKAGE_CONTENTS

    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "tests/integration/test_frontend_backend.py": (
            "from pathlib import Path\n"
            "\n"
            "def test_delete_book_uses_delete_method():\n"
            "    app_js = Path('frontend/app.js').read_text(encoding='utf-8')\n"
            "    assert '/books/' in app_js\n"
            "    assert \"DELETE\" in app_js\n"
        ),
    }

    with pytest.raises(_VERIFY_ERRORS, match="integration|deleteBook|behavior"):
        _build_negative_tiny_package_fixture(
            tmp_path,
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_rejects_frontend_integration_that_reports_delete_only_calls(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import TINY_PACKAGE_CONTENTS

    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "tests/integration/test_frontend_backend.py": (
            "import json\n"
            "import subprocess\n\n"
            "def test_frontend_fetches_backend_and_run_manifest_exists():\n"
            "    script = \"\"\"\n"
            "const allCalls = [];\n"
            "async function loadBooks(fetchImpl) { return await fetchImpl('/books'); }\n"
            "async function deleteBook(fetchImpl, bookId) { return await fetchImpl(`/books/${bookId}`, { method: 'DELETE' }); }\n"
            "const fakeFetch = async (url, options = {}) => { allCalls.push({ url, options }); return { json: async () => [] }; };\n"
            "await loadBooks(fakeFetch);\n"
            "allCalls.length = 0;\n"
            "await deleteBook(fakeFetch, 7);\n"
            "console.log(JSON.stringify({ calls: allCalls }));\n"
            "\"\"\"\n"
            "    completed = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True)\n"
            "    assert completed.returncode == 0, completed.stderr\n"
            "    report = json.loads(completed.stdout)\n"
            "    assert report['calls'][0]['url'] == '/books/7'\n"
            "    assert report['calls'][0]['options']['method'] == 'DELETE'\n"
        ),
    }

    with pytest.raises(_VERIFY_ERRORS, match="integration|loadBooks|deleteBook|calls"):
        _build_negative_tiny_package_fixture(
            tmp_path,
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_rejects_frontend_integration_that_excludes_pytest_tmp_root(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import TINY_PACKAGE_CONTENTS

    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "tests/integration/test_frontend_backend.py": (
            "import json\n"
            "import subprocess\n"
            "from pathlib import Path\n\n"
            "ROOT = Path(__file__).resolve().parents[2]\n\n"
            "def test_frontend_fetches_backend_and_run_manifest_exists(tmp_path):\n"
            "    candidates = []\n"
            "    for path in ROOT.rglob('*'):\n"
            "        if any(part.startswith('.pytest-tmp') for part in path.parts):\n"
            "            continue\n"
            "        if path.name == 'app.js':\n"
            "            candidates.append(path)\n"
            "    assert candidates or True\n"
            "    script = \"\"\"\n"
            "const calls = [];\n"
            "async function loadBooks(fetchImpl) { return await fetchImpl('/books'); }\n"
            "async function deleteBook(fetchImpl, bookId) { return await fetchImpl(`/books/${bookId}`, { method: 'DELETE' }); }\n"
            "const fakeFetch = async (url, options = {}) => { calls.push({ url, options }); return { json: async () => [] }; };\n"
            "await loadBooks(fakeFetch);\n"
            "await deleteBook(fakeFetch, 7);\n"
            "console.log(JSON.stringify({ calls }));\n"
            "\"\"\"\n"
            "    completed = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True)\n"
            "    assert completed.returncode == 0, completed.stderr\n"
            "    calls = json.loads(completed.stdout)['calls']\n"
            "    assert calls[0]['url'] == '/books'\n"
            "    assert calls[1]['options']['method'] == 'DELETE'\n"
        ),
    }

    with pytest.raises(_VERIFY_ERRORS, match="integration|pytest-tmp|frontend"):
        _build_negative_tiny_package_fixture(
            tmp_path,
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_rejects_delete_test_that_refetches_deleted_book(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import TINY_PACKAGE_CONTENTS

    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "backend/tests/test_api.py": (
            "import sqlite3\n\n"
            "from backend.app import checkout_book, create_book, delete_book, list_books, return_book\n"
            "from backend.db import BookStore\n\n"
            "def _find_book(store, book_id):\n"
            "    for book in list_books(store=store):\n"
            "        if str(book['id']) == str(book_id):\n"
            "            return book\n"
            "    raise AssertionError('missing book')\n\n"
            "def _mutate_book(func, store, book_id):\n"
            "    result = func(book_id, store=store)\n"
            "    if result is None or isinstance(result, (bool, int, str)):\n"
            "        return _find_book(store, book_id)\n"
            "    return result\n\n"
            "def test_backend_api_delete_and_sqlite_persistence_contract(tmp_path):\n"
            "    db_path = tmp_path / 'books.sqlite3'\n"
            "    store = BookStore(db_path)\n"
            "    book = create_book('Dune', store=store)\n"
            "    checked_out = checkout_book(book['id'], store=store)\n"
            "    assert checked_out['state'] == 'CHECKED_OUT'\n"
            "    returned = return_book(book['id'], store=store)\n"
            "    assert returned['state'] == 'IN_LIBRARY'\n"
            "    _mutate_book(delete_book, store, book['id'])\n"
            "    assert list_books(store=BookStore(db_path)) == []\n"
            "    assert db_path.exists()\n"
            "    assert not any(isinstance(value, sqlite3.Connection) for value in vars(store).values())\n"
        ),
    }

    with pytest.raises(_VERIFY_ERRORS, match="delete_book|deleted book|refetch"):
        _build_negative_tiny_package_fixture(
            tmp_path,
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_default_path_rejects_fake_provider_attempts(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        build_tiny_package_assembly_fixture,
    )
    from tests.proving.fixtures.tiny_provider_attempts import (
        build_tiny_provider_attempt_fixture,
    )

    fake_provider_fixture = build_tiny_provider_attempt_fixture(use_fake_results=True)

    with pytest.raises(_VERIFY_ERRORS, match="fake provider|ProviderAttempt|real provider"):
        build_tiny_package_assembly_fixture(
            package_root=tmp_path / "physical-package-root",
            provider_fixture=fake_provider_fixture,
        )


def test_tiny_package_assembly_rejects_source_overrides_on_real_provider_path(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
        build_tiny_package_assembly_fixture,
    )
    from tests.proving.fixtures.tiny_provider_attempts import (
        build_tiny_provider_attempt_fixture,
    )

    fake_provider_fixture = build_tiny_provider_attempt_fixture(use_fake_results=True)

    with pytest.raises(_VERIFY_ERRORS, match="override|negative"):
        build_tiny_package_assembly_fixture(
            package_root=tmp_path / "physical-package-root",
            package_contents=TINY_PACKAGE_CONTENTS,
            provider_fixture=fake_provider_fixture,
        )


def test_tiny_source_inventory_binds_producer_attempts_and_verified_evidence(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        build_tiny_package_assembly_fixture,
    )

    fixture = build_tiny_package_assembly_fixture(
        package_root=tmp_path / "physical-package-root",
    )
    provider_attempt_refs = {
        attempt.provider_attempt_id
        for attempt in fixture.provider_attempts_by_ticket_id.values()
    }
    final_table_evidence_refs = {
        evidence_ref
        for row in fixture.final_evidence_table.rows
        for evidence_ref in row.verified_evidence_refs
    }

    for entry in fixture.source_inventory.entries:
        assert entry.producer_attempt_ref in provider_attempt_refs
        assert entry.evidence_refs
        assert set(entry.evidence_refs).issubset(final_table_evidence_refs)
        assert entry.sha256.value == hashlib.sha256(
            fixture.source_contents[entry.path.value].encode("utf-8")
        ).hexdigest()
        assert (fixture.package_root_path / entry.path.value).read_text(
            encoding="utf-8"
        ) == fixture.source_contents[entry.path.value]

    backend_entries = tuple(
        entry
        for entry in fixture.source_inventory.entries
        if entry.source_surface_ref == SourceSurfaceRef(value="backend-api")
    )
    assert {entry.path.value for entry in backend_entries} == {"backend/app.py"}
    assert all(entry.sha256.value != "0" * 64 for entry in fixture.source_inventory.entries)
    assert "AC-TINY-UI-FETCH-BACKEND" not in {
        acceptance_ref.value
        for entry in fixture.source_inventory.entries
        for acceptance_ref in entry.acceptance_refs
    }
    assert "AC-TINY-RUN-TEST-COMMANDS" not in {
        acceptance_ref.value
        for entry in fixture.source_inventory.entries
        for acceptance_ref in entry.acceptance_refs
    }


def test_tiny_package_assembly_rejects_failed_declared_command(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
    )

    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "backend/tests/test_api.py": (
            TINY_PACKAGE_CONTENTS["backend/tests/test_api.py"]
            + "\n\n"
            "def test_backend_source_inventory_contract():\n"
            "    assert False, 'backend command evidence must fail closed'\n"
        ),
    }

    with pytest.raises(AssertionError, match="tiny evidence verification failed"):
        _build_negative_tiny_package_fixture(
            tmp_path,
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_rejects_run_manifest_content_mismatch(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
    )

    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "run-manifest.json": "not json\n",
    }

    with pytest.raises(_VERIFY_ERRORS, match="run-manifest.json|run manifest"):
        _build_negative_tiny_package_fixture(
            tmp_path,
            package_contents=broken_contents,
        )


def test_tiny_package_assembly_rejects_escape_path_before_writing(
    tmp_path: Path,
) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        TINY_PACKAGE_CONTENTS,
    )

    escaped_path = tmp_path / "escape.txt"
    broken_contents = {
        **TINY_PACKAGE_CONTENTS,
        "../escape.txt": "must not be written\n",
    }

    with pytest.raises(_VERIFY_ERRORS, match="package artifact path|package root"):
        _build_negative_tiny_package_fixture(
            tmp_path,
            package_contents=broken_contents,
        )

    assert not escaped_path.exists()


def test_tiny_package_assembly_is_pure_model_proof(tmp_path: Path) -> None:
    from tests.proving.fixtures.tiny_package_assembly import (
        build_tiny_package_assembly_fixture,
    )

    fixture = build_tiny_package_assembly_fixture(
        package_root=tmp_path / "physical-package-root",
    )

    assert fixture.package_root_path == tmp_path / "physical-package-root"
    assert not (tmp_path / "10-project").exists()
    assert not (tmp_path / "20-evidence").exists()
    assert tuple(
        artifact.relative_path.value
        for artifact in fixture.package_assembly.artifacts
    ) == tuple(sorted(fixture.expected_package_paths))
    assert PackageArtifactKind.RUN_MANIFEST in {
        artifact.artifact_kind for artifact in fixture.package_assembly.artifacts
    }
