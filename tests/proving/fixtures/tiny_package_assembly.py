from __future__ import annotations

import ast
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping

from boardroom_os.adapters.process_runner import (
    CommandRunner,
    CommandRunnerInput,
    CommandRunnerResult,
)
from boardroom_os.contracts.evidence_obligation import EvidenceObligation
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import AcceptanceRef, ContractId, SourceSurfaceRef
from boardroom_os.evidence.claim import (
    EvidenceArtifactRef,
    build_evidence_claim_from_verification_run,
)
from boardroom_os.evidence.table import (
    FinalEvidenceTable,
    FinalEvidenceTableBuilder,
    FinalEvidenceTableInput,
)
from boardroom_os.evidence.verifier import (
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactSha256,
    EvidencePurposePolicy,
    EvidencePurposeRule,
    EvidenceVerificationInput,
    EvidenceVerifier,
    VerifiedEvidence,
)
from boardroom_os.execution.fallback import EvidencePurpose
from boardroom_os.execution.verification_run import (
    EnvironmentProfileRef,
    RunnerRef,
    WorkspaceSnapshotRef,
)
from boardroom_os.graph.ticket import TicketId
from boardroom_os.providers.attempt import ProviderAttempt
from boardroom_os.workspace.assembler import (
    PackageArtifact,
    PackageArtifactKind,
    PackageArtifactPath,
    PackageAssembly,
    assemble_package,
)
from boardroom_os.workspace.evidence_export import (
    EvidenceBundleArtifactKind,
    WorkspaceEvidenceBundle,
    build_workspace_evidence_bundle,
)
from boardroom_os.workspace.manifest import (
    WorkflowRef,
    WorkspaceManifest,
    WorkspacePath,
    build_workspace_manifest,
)
from boardroom_os.workspace.run_manifest import RunManifest, build_run_manifest
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceFilePath,
    SourceFileRecord,
    SourceInventory,
    SourceLineageRecord,
    build_source_inventory,
)
from tests.fixtures.execution.role_prompt_hooks import baseline_role_prompt_hook_registry
from tests.proving.fixtures.tiny_provider_attempts import (
    TinyProviderAttemptFixture,
    build_tiny_provider_attempt_fixture,
    openai_settings_from_test_env,
)
from tests.proving.fixtures.tiny_ticket_graph import (
    TICKET_BACKEND_API_ID,
    TICKET_DOCS_RUN_MANIFEST_ID,
    TICKET_FRONTEND_UI_ID,
    TICKET_TESTS_ID,
)


GENERATED_AT = datetime(2026, 5, 30, 9, 0, tzinfo=UTC)
VERIFIED_AT = datetime(2026, 5, 30, 9, 5, tzinfo=UTC)
COMMAND_STARTED_AT = datetime(2026, 5, 30, 9, 10, tzinfo=UTC)
COMMAND_FINISHED_AT = datetime(2026, 5, 30, 9, 10, 1, tzinfo=UTC)
PACKAGE_COMMIT_REF = PackageCommitRef(value="commit.tiny-package-assembly")

EXPECTED_TINY_PACKAGE_PATHS: tuple[str, ...] = (
    "AGENTS.md",
    "README.md",
    "backend/app.py",
    "backend/db.py",
    "backend/tests/test_api.py",
    "docs/usage.md",
    "frontend/app.js",
    "frontend/index.html",
    "package-contract.json",
    "run-manifest.json",
    "tests/integration/test_frontend_backend.py",
)

TINY_PACKAGE_CONTENTS: Mapping[str, str] = {
    "README.md": "# Tiny Book Availability Tracker\n",
    "AGENTS.md": "Run declared commands from the package root.\n",
    "package-contract.json": '{"package_root":"10-project"}\n',
    "backend/app.py": (
        "import json\n"
        "import os\n"
        "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
        "from urllib.parse import urlparse\n\n"
        "from backend.db import BookStore\n\n"
        "DEFAULT_DB_PATH = 'books.sqlite3'\n\n"
        "def create_store(db_path=DEFAULT_DB_PATH):\n"
        "    return BookStore(db_path)\n\n"
        "def create_book(title, *, store=None):\n"
        "    active_store = store or create_store()\n"
        "    return active_store.add_book(title)\n\n"
        "def list_books(*, store=None):\n"
        "    active_store = store or create_store()\n"
        "    return active_store.list_books()\n\n"
        "def checkout_book(book_id, *, store=None):\n"
        "    active_store = store or create_store()\n"
        "    return active_store.set_book_state(book_id, 'CHECKED_OUT')\n\n"
        "def return_book(book_id, *, store=None):\n"
        "    active_store = store or create_store()\n"
        "    return active_store.set_book_state(book_id, 'IN_LIBRARY')\n\n"
        "def delete_book(book_id, *, store=None):\n"
        "    active_store = store or create_store()\n"
        "    return active_store.delete_book(book_id)\n"
        "\n"
        "def _active_store():\n"
        "    return create_store(os.environ.get('BOOKS_DB_PATH', DEFAULT_DB_PATH))\n"
        "\n"
        "class LibraryHandler(BaseHTTPRequestHandler):\n"
        "    def _send_json(self, status, payload):\n"
        "        body = json.dumps(payload).encode('utf-8')\n"
        "        self.send_response(status)\n"
        "        self.send_header('Content-Type', 'application/json')\n"
        "        self.send_header('Content-Length', str(len(body)))\n"
        "        self.end_headers()\n"
        "        self.wfile.write(body)\n\n"
        "    def _read_json(self):\n"
        "        length = int(self.headers.get('Content-Length', '0'))\n"
        "        if length == 0:\n"
        "            return {}\n"
        "        return json.loads(self.rfile.read(length).decode('utf-8'))\n\n"
        "    def do_GET(self):\n"
        "        path = urlparse(self.path).path\n"
        "        if path == '/health':\n"
        "            self._send_json(200, {'status': 'ok'})\n"
        "        elif path == '/books':\n"
        "            self._send_json(200, {'books': list_books(store=_active_store())})\n"
        "        else:\n"
        "            self._send_json(404, {'error': 'not found'})\n\n"
        "    def do_POST(self):\n"
        "        path = urlparse(self.path).path\n"
        "        store = _active_store()\n"
        "        if path == '/books':\n"
        "            payload = self._read_json()\n"
        "            self._send_json(201, create_book(payload.get('title', ''), store=store))\n"
        "        elif path.startswith('/books/') and path.endswith('/checkout'):\n"
        "            self._send_json(200, checkout_book(int(path.split('/')[2]), store=store))\n"
        "        elif path.startswith('/books/') and path.endswith('/return'):\n"
        "            self._send_json(200, return_book(int(path.split('/')[2]), store=store))\n"
        "        else:\n"
        "            self._send_json(404, {'error': 'not found'})\n\n"
        "    def do_DELETE(self):\n"
        "        path = urlparse(self.path).path\n"
        "        if path.startswith('/books/'):\n"
        "            self._send_json(200, delete_book(int(path.split('/')[2]), store=_active_store()))\n"
        "        else:\n"
        "            self._send_json(404, {'error': 'not found'})\n\n"
        "def run():\n"
        "    port = int(os.environ.get('PORT', '8000'))\n"
        "    ThreadingHTTPServer(('127.0.0.1', port), LibraryHandler).serve_forever()\n\n"
        "if __name__ == '__main__':\n"
        "    run()\n"
    ),
    "backend/db.py": (
        "import sqlite3\n\n"
        "VALID_STATES = {'IN_LIBRARY', 'CHECKED_OUT'}\n\n"
        "class BookStore:\n"
        "    def __init__(self, db_path):\n"
        "        self.db_path = str(db_path)\n"
        "        self._ensure_schema()\n\n"
        "    def _connect(self):\n"
        "        return sqlite3.connect(self.db_path)\n\n"
        "    def _ensure_schema(self):\n"
        "        with self._connect() as connection:\n"
        "            connection.execute(\n"
        "                'CREATE TABLE IF NOT EXISTS books ('\n"
        "                'id INTEGER PRIMARY KEY AUTOINCREMENT, '\n"
        "                'title TEXT NOT NULL, '\n"
        "                \"state TEXT NOT NULL CHECK(state IN ('IN_LIBRARY', 'CHECKED_OUT'))\"\n"
        "                ')'\n"
        "            )\n"
        "            connection.commit()\n\n"
        "    def add_book(self, title):\n"
        "        normalized_title = title.strip()\n"
        "        if not normalized_title:\n"
        "            raise ValueError('title is required')\n"
        "        with self._connect() as connection:\n"
        "            cursor = connection.execute(\n"
        "                'INSERT INTO books(title, state) VALUES (?, ?)',\n"
        "                (normalized_title, 'IN_LIBRARY'),\n"
        "            )\n"
        "            connection.commit()\n"
        "            return self.get_book(cursor.lastrowid)\n\n"
        "    def list_books(self):\n"
        "        with self._connect() as connection:\n"
        "            rows = connection.execute(\n"
        "                'SELECT id, title, state FROM books ORDER BY id'\n"
        "            ).fetchall()\n"
        "        return [self._book_from_row(row) for row in rows]\n\n"
        "    def get_book(self, book_id):\n"
        "        with self._connect() as connection:\n"
        "            row = connection.execute(\n"
        "                'SELECT id, title, state FROM books WHERE id = ?',\n"
        "                (book_id,),\n"
        "            ).fetchone()\n"
        "        if row is None:\n"
        "            raise KeyError(f'book not found: {book_id}')\n"
        "        return self._book_from_row(row)\n\n"
        "    def set_book_state(self, book_id, state):\n"
        "        if state not in VALID_STATES:\n"
        "            raise ValueError('invalid book state')\n"
        "        with self._connect() as connection:\n"
        "            cursor = connection.execute(\n"
        "                'UPDATE books SET state = ? WHERE id = ?',\n"
        "                (state, book_id),\n"
        "            )\n"
        "            if cursor.rowcount != 1:\n"
        "                raise KeyError(f'book not found: {book_id}')\n"
        "            connection.commit()\n"
        "        return self.get_book(book_id)\n\n"
        "    def delete_book(self, book_id):\n"
        "        with self._connect() as connection:\n"
        "            cursor = connection.execute('DELETE FROM books WHERE id = ?', (book_id,))\n"
        "            if cursor.rowcount != 1:\n"
        "                raise KeyError(f'book not found: {book_id}')\n"
        "            connection.commit()\n"
        "        return {'id': book_id, 'deleted': True}\n\n"
        "    @staticmethod\n"
        "    def _book_from_row(row):\n"
        "        return {'id': row[0], 'title': row[1], 'state': row[2]}\n"
    ),
    "frontend/index.html": (
        "<!doctype html>\n"
        "<html><body><main id=\"app\"></main><script src=\"app.js\"></script></body></html>\n"
    ),
    "frontend/app.js": (
        "const API_BASE = globalThis.BOARDROOM_API_BASE || 'http://127.0.0.1:8000';\n"
        "function apiPath(path) { return `${API_BASE}${path}`; }\n\n"
        "export async function probeBackend(fetchImpl) {\n"
        "  const response = await fetchImpl(apiPath('/health'));\n"
        "  return response.json();\n"
        "}\n\n"
        "export async function loadBooks(fetchImpl) {\n"
        "  const response = await fetchImpl(apiPath('/books'));\n"
        "  return response.json();\n"
        "}\n\n"
        "export async function deleteBook(fetchImpl, bookId) {\n"
        "  const response = await fetchImpl(apiPath(`/books/${encodeURIComponent(String(bookId))}`), { method: 'DELETE' });\n"
        "  return response.json();\n"
        "}\n"
    ),
    "backend/tests/test_api.py": (
        "from contextlib import closing\n"
        "import sqlite3\n\n"
        "from backend.app import checkout_book, create_book, delete_book, list_books, return_book\n"
        "from backend.db import BookStore\n\n"
        "def test_backend_api_delete_and_sqlite_persistence_contract(tmp_path):\n"
        "    db_path = tmp_path / 'books.sqlite3'\n"
        "    store = BookStore(db_path)\n"
        "    book = create_book('Dune', store=store)\n"
        "    assert book['state'] == 'IN_LIBRARY'\n"
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
        "    with closing(sqlite3.connect(db_path)) as connection:\n"
        "        table_names = {\n"
        "            row[0]\n"
        "            for row in connection.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")\n"
        "        }\n"
        "    assert 'books' in table_names\n"
    ),
    "tests/integration/test_frontend_backend.py": (
        "import json\n"
        "import os\n"
        "import socket\n"
        "import subprocess\n"
        "import sys\n"
        "import time\n"
        "import urllib.error\n"
        "import urllib.request\n"
        "from pathlib import Path\n\n"
        "def _free_port():\n"
        "    sock = socket.socket()\n"
        "    sock.bind(('127.0.0.1', 0))\n"
        "    port = sock.getsockname()[1]\n"
        "    sock.close()\n"
        "    return port\n\n"
        "def _request(url, method='GET', payload=None):\n"
        "    body = None if payload is None else json.dumps(payload).encode('utf-8')\n"
        "    request = urllib.request.Request(url, data=body, method=method)\n"
        "    request.add_header('Content-Type', 'application/json')\n"
        "    with urllib.request.urlopen(request, timeout=2) as response:\n"
        "        return response.status, json.loads(response.read().decode('utf-8'))\n\n"
        "def test_frontend_fetches_backend_and_run_manifest_exists():\n"
        "    port = _free_port()\n"
        "    base_url = f'http://127.0.0.1:{port}'\n"
        "    env = dict(os.environ, PORT=str(port), BOOKS_DB_PATH=str(Path.cwd() / 'books.integration.sqlite3'))\n"
        "    server = subprocess.Popen([sys.executable, '-m', 'backend.app'], cwd=Path.cwd(), env=env)\n"
        "    try:\n"
        "        for _ in range(50):\n"
        "            try:\n"
        "                status, _ = _request(base_url + '/health')\n"
        "                if status == 200:\n"
        "                    break\n"
        "            except (OSError, urllib.error.URLError):\n"
        "                time.sleep(0.1)\n"
        "        assert _request(base_url + '/health')[0] == 200\n"
        "        status, created = _request(base_url + '/books', method='POST', payload={'title': 'Dune'})\n"
        "        assert status == 201\n"
        "        book_id = created['id']\n"
        "        assert _request(f'{base_url}/books/{book_id}/checkout', method='POST')[1]['state'] == 'CHECKED_OUT'\n"
        "        assert _request(f'{base_url}/books/{book_id}/return', method='POST')[1]['state'] == 'IN_LIBRARY'\n"
        "        assert _request(f'{base_url}/books/{book_id}', method='DELETE')[1]['deleted'] is True\n"
        "        assert all(book['id'] != book_id for book in _request(base_url + '/books')[1]['books'])\n"
        "    finally:\n"
        "        server.terminate()\n"
        "        server.wait(timeout=5)\n"
        "    frontend = Path('frontend/app.js').read_text(encoding='utf-8')\n"
        "    assert 'probeBackend' in frontend and '/health' in frontend\n"
        "    assert 'loadBooks(fetchImpl)' in frontend and 'deleteBook(fetchImpl, bookId)' in frontend\n"
        "    assert Path('run-manifest.json').exists()\n"
    ),
    "docs/usage.md": "Use pytest backend/tests and pytest tests/integration.\n",
}


@dataclass(frozen=True)
class TinyPackageAssemblyFixture:
    provider_fixture: TinyProviderAttemptFixture
    workspace_manifest: WorkspaceManifest
    package_contract: PackageContract
    package_artifacts: tuple[PackageArtifact, ...]
    package_assembly: PackageAssembly
    run_manifest: RunManifest
    package_root_path: Path
    source_contents: Mapping[str, str]
    command_results_by_id: Mapping[str, CommandRunnerResult]
    verified_evidence: tuple[VerifiedEvidence, ...]
    source_inventory: SourceInventory
    final_evidence_table: FinalEvidenceTable
    workspace_evidence_bundle: WorkspaceEvidenceBundle | None

    @property
    def provider_attempts_by_ticket_id(self) -> Mapping[TicketId, ProviderAttempt]:
        return self.provider_fixture.provider_attempts_by_ticket_id

    @property
    def required_evidence_artifact_kinds(self) -> set[EvidenceBundleArtifactKind]:
        return set(EvidenceBundleArtifactKind)

    @property
    def expected_package_paths(self) -> tuple[str, ...]:
        return EXPECTED_TINY_PACKAGE_PATHS

    def assemble_package(
        self,
        *,
        artifacts: tuple[PackageArtifact, ...],
    ) -> PackageAssembly:
        return assemble_package(
            workspace_manifest=self.workspace_manifest,
            package_contract=self.package_contract,
            artifacts=artifacts,
        )

    def build_source_inventory(
        self,
        *,
        source_files: tuple[SourceFileRecord, ...],
        lineage_records: tuple[SourceLineageRecord, ...],
    ) -> SourceInventory:
        return build_source_inventory(
            package_assembly=self.package_assembly,
            package_contract=self.package_contract,
            package_commit_ref=PACKAGE_COMMIT_REF,
            source_files=source_files,
            lineage_records=lineage_records,
        )


def build_tiny_package_assembly_fixture(
    *,
    package_root: Path,
    package_contents: Mapping[str, str] | None = None,
    provider_fixture: TinyProviderAttemptFixture | None = None,
    allow_fake_provider_for_negative_tests: bool = False,
) -> TinyPackageAssemblyFixture:
    _validate_package_content_override_paths(package_contents)
    _validate_source_override_usage(
        package_contents=package_contents,
        allow_fake_provider_for_negative_tests=allow_fake_provider_for_negative_tests,
    )
    provider_fixture = provider_fixture or build_tiny_provider_attempt_fixture(
        settings=openai_settings_from_test_env(),
        use_fake_results=False,
    )
    _validate_real_provider_fixture(
        provider_fixture,
        allow_fake_provider_for_negative_tests=allow_fake_provider_for_negative_tests,
    )
    package_contract = provider_fixture.compiled.ticket_graph_fixture.contracts.package_contract
    workspace_manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-tiny-package-assembly"),
        workspace_root=WorkspacePath(value="workspace/workflow-tiny-package-assembly"),
        package_contract=package_contract,
    )
    package_artifacts = _package_artifacts()
    package_assembly = assemble_package(
        workspace_manifest=workspace_manifest,
        package_contract=package_contract,
        artifacts=package_artifacts,
    )
    run_manifest = build_run_manifest(
        workspace_manifest=workspace_manifest,
        package_contract=package_contract,
    )
    provider_contents = _source_delivery_files_from_provider(
        provider_fixture,
        allow_fake_provider_for_negative_tests=allow_fake_provider_for_negative_tests,
    )
    contents = _package_contents_with_generated_files(
        provider_contents=provider_contents,
        override_contents=package_contents,
        run_manifest=run_manifest,
    )
    _validate_tiny_package_functional_scope(contents)
    _write_ephemeral_tiny_package_for_command_evidence(
        package_root=package_root,
        package_contents=contents,
    )
    _validate_physical_run_manifest(
        package_root=package_root,
        run_manifest=run_manifest,
    )
    command_results_by_id = _command_results_by_id(
        provider_fixture=provider_fixture,
        package_root=package_root,
    )
    verified_evidence = _verified_evidence(
        provider_fixture=provider_fixture,
        command_results_by_id=command_results_by_id,
    )
    source_inventory = build_source_inventory(
        package_assembly=package_assembly,
        package_contract=package_contract,
        package_commit_ref=PACKAGE_COMMIT_REF,
        source_files=_source_files(contents),
        lineage_records=_source_lineage_records(
            provider_fixture=provider_fixture,
            verified_evidence=verified_evidence,
        ),
    )
    final_evidence_table = FinalEvidenceTableBuilder().build(
        FinalEvidenceTableInput(
            active_acceptance_contract=(
                provider_fixture.compiled.ticket_graph_fixture.contracts.acceptance_contract
            ),
            verified_evidence=verified_evidence,
            generated_at=GENERATED_AT,
        )
    )
    workspace_evidence_bundle = (
        build_workspace_evidence_bundle(
            workspace_manifest=workspace_manifest,
            package_assembly=package_assembly,
            source_inventory=source_inventory,
            run_manifest=run_manifest,
            verification_runs=tuple(
                result.verification_run for result in command_results_by_id.values()
            ),
            verified_evidence=verified_evidence,
            final_evidence_table=final_evidence_table,
        )
        if final_evidence_table.complete is True
        else None
    )
    return TinyPackageAssemblyFixture(
        provider_fixture=provider_fixture,
        workspace_manifest=workspace_manifest,
        package_contract=package_contract,
        package_artifacts=package_artifacts,
        package_assembly=package_assembly,
        run_manifest=run_manifest,
        package_root_path=package_root,
        source_contents=contents,
        command_results_by_id=command_results_by_id,
        verified_evidence=verified_evidence,
        source_inventory=source_inventory,
        final_evidence_table=final_evidence_table,
        workspace_evidence_bundle=workspace_evidence_bundle,
    )


def _package_artifacts() -> tuple[PackageArtifact, ...]:
    return (
        _artifact(
            "README.md",
            PackageArtifactKind.README,
            "docs",
            ("AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",),
        ),
        _artifact(
            "AGENTS.md",
            PackageArtifactKind.AGENTS,
            "docs",
            ("AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",),
        ),
        _artifact(
            "package-contract.json",
            PackageArtifactKind.PACKAGE_CONTRACT,
            "docs",
            ("AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",),
        ),
        _artifact(
            "run-manifest.json",
            PackageArtifactKind.RUN_MANIFEST,
            "run-manifest",
            (
                "AC-TINY-BACKEND-STARTUP",
                "AC-TINY-FRONTEND-STARTUP",
                "AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",
            ),
        ),
        _artifact(
            "backend/app.py",
            PackageArtifactKind.SOURCE,
            "backend-api",
            (
                "AC-TINY-API-BOOK-CREATE",
                "AC-TINY-API-BOOK-LIST",
                "AC-TINY-API-CHECKOUT-RETURN",
                "AC-TINY-API-BOOK-DELETE",
                "AC-TINY-BACKEND-STARTUP",
                "AC-TINY-BACKEND-HTTP-CRUD",
            ),
        ),
        _artifact(
            "backend/db.py",
            PackageArtifactKind.SOURCE,
            "persistence",
            ("AC-TINY-PERSISTENCE-SQLITE", "AC-TINY-SQLITE-PERSISTENCE-VIA-HTTP"),
        ),
        _artifact(
            "frontend/index.html",
            PackageArtifactKind.SOURCE,
            "frontend-ui",
            (
                "AC-TINY-FRONTEND-STARTUP",
                "AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION",
            ),
        ),
        _artifact(
            "frontend/app.js",
            PackageArtifactKind.SOURCE,
            "frontend-ui",
            (
                "AC-TINY-FRONTEND-STARTUP",
                "AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION",
            ),
        ),
        _artifact(
            "backend/tests/test_api.py",
            PackageArtifactKind.TEST,
            "tests",
            (
                "AC-TINY-API-BOOK-CREATE",
                "AC-TINY-API-BOOK-LIST",
                "AC-TINY-API-CHECKOUT-RETURN",
                "AC-TINY-API-BOOK-DELETE",
                "AC-TINY-PERSISTENCE-SQLITE",
            ),
        ),
        _artifact(
            "tests/integration/test_frontend_backend.py",
            PackageArtifactKind.TEST,
            "tests",
            (
                "AC-TINY-BACKEND-STARTUP",
                "AC-TINY-BACKEND-HTTP-CRUD",
                "AC-TINY-SQLITE-PERSISTENCE-VIA-HTTP",
                "AC-TINY-FRONTEND-STARTUP",
                "AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION",
                "AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",
            ),
        ),
        _artifact(
            "docs/usage.md",
            PackageArtifactKind.DOC,
            "docs",
            ("AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",),
        ),
    )


def _artifact(
    relative_path: str,
    artifact_kind: PackageArtifactKind,
    source_surface_ref: str | None = None,
    acceptance_refs: tuple[str, ...] = (),
) -> PackageArtifact:
    if artifact_kind in {PackageArtifactKind.README, PackageArtifactKind.AGENTS}:
        if source_surface_ref is not None:
            return PackageArtifact(
                relative_path=PackageArtifactPath(value=relative_path),
                artifact_kind=artifact_kind,
                source_surface_refs=(SourceSurfaceRef(value=source_surface_ref),),
                acceptance_refs=tuple(AcceptanceRef(value=value) for value in acceptance_refs),
            )
        return PackageArtifact(
            relative_path=PackageArtifactPath(value=relative_path),
            artifact_kind=artifact_kind,
        )
    if source_surface_ref is None:
        raise ValueError("source_surface_ref is required for implementation artifacts")
    return PackageArtifact(
        relative_path=PackageArtifactPath(value=relative_path),
        artifact_kind=artifact_kind,
        source_surface_refs=(SourceSurfaceRef(value=source_surface_ref),),
        acceptance_refs=tuple(AcceptanceRef(value=value) for value in acceptance_refs),
    )


def _source_files(package_contents: Mapping[str, str]) -> tuple[SourceFileRecord, ...]:
    return tuple(
        SourceFileRecord(
            path=SourceFilePath(value=path),
            sha256=_sha256(package_contents[path]),
        )
        for path in (
            "backend/app.py",
            "backend/db.py",
            "backend/tests/test_api.py",
            "docs/usage.md",
            "frontend/app.js",
            "frontend/index.html",
            "tests/integration/test_frontend_backend.py",
        )
    )


def _source_lineage_records(
    *,
    provider_fixture: TinyProviderAttemptFixture,
    verified_evidence: tuple[VerifiedEvidence, ...],
) -> tuple[SourceLineageRecord, ...]:
    evidence_refs_by_type = _evidence_refs_by_artifact_type(verified_evidence)
    return (
        _lineage(
            path="backend/app.py",
            surface_ref="backend-api",
            producer_ticket_ref=TICKET_BACKEND_API_ID,
            producer_attempt_ref=provider_fixture.provider_attempts_by_ticket_id[
                TICKET_BACKEND_API_ID
            ].provider_attempt_id,
            consumer_ticket_refs=(TICKET_BACKEND_API_ID, TICKET_TESTS_ID),
            acceptance_refs=(
                "AC-TINY-API-BOOK-CREATE",
                "AC-TINY-API-BOOK-LIST",
                "AC-TINY-API-CHECKOUT-RETURN",
                "AC-TINY-API-BOOK-DELETE",
                "AC-TINY-BACKEND-STARTUP",
                "AC-TINY-BACKEND-HTTP-CRUD",
            ),
            evidence_refs=evidence_refs_by_type["backend_source_inventory"],
        ),
        _lineage(
            path="backend/db.py",
            surface_ref="persistence",
            producer_ticket_ref=TICKET_BACKEND_API_ID,
            producer_attempt_ref=provider_fixture.provider_attempts_by_ticket_id[
                TICKET_BACKEND_API_ID
            ].provider_attempt_id,
            consumer_ticket_refs=(TICKET_BACKEND_API_ID, TICKET_TESTS_ID),
            acceptance_refs=("AC-TINY-PERSISTENCE-SQLITE", "AC-TINY-SQLITE-PERSISTENCE-VIA-HTTP"),
            evidence_refs=(
                *evidence_refs_by_type["backend_source_inventory"],
                *evidence_refs_by_type["sqlite_persistence_evidence"],
            ),
        ),
        _lineage(
            path="frontend/app.js",
            surface_ref="frontend-ui",
            producer_ticket_ref=TICKET_FRONTEND_UI_ID,
            producer_attempt_ref=provider_fixture.provider_attempts_by_ticket_id[
                TICKET_FRONTEND_UI_ID
            ].provider_attempt_id,
            consumer_ticket_refs=(TICKET_FRONTEND_UI_ID, TICKET_TESTS_ID),
            acceptance_refs=(
                "AC-TINY-FRONTEND-STARTUP",
                "AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION",
            ),
            evidence_refs=evidence_refs_by_type["frontend_source_inventory"],
        ),
        _lineage(
            path="frontend/index.html",
            surface_ref="frontend-ui",
            producer_ticket_ref=TICKET_FRONTEND_UI_ID,
            producer_attempt_ref=provider_fixture.provider_attempts_by_ticket_id[
                TICKET_FRONTEND_UI_ID
            ].provider_attempt_id,
            consumer_ticket_refs=(TICKET_FRONTEND_UI_ID, TICKET_TESTS_ID),
            acceptance_refs=(
                "AC-TINY-FRONTEND-STARTUP",
                "AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION",
            ),
            evidence_refs=evidence_refs_by_type["frontend_source_inventory"],
        ),
        _lineage(
            path="backend/tests/test_api.py",
            surface_ref="tests",
            producer_ticket_ref=TICKET_TESTS_ID,
            producer_attempt_ref=provider_fixture.provider_attempts_by_ticket_id[
                TICKET_TESTS_ID
            ].provider_attempt_id,
            consumer_ticket_refs=(TICKET_TESTS_ID,),
            acceptance_refs=(
                "AC-TINY-API-BOOK-CREATE",
                "AC-TINY-API-BOOK-LIST",
                "AC-TINY-API-CHECKOUT-RETURN",
                "AC-TINY-API-BOOK-DELETE",
                "AC-TINY-PERSISTENCE-SQLITE",
            ),
            evidence_refs=(
                *evidence_refs_by_type["backend_source_inventory"],
                *evidence_refs_by_type["sqlite_persistence_evidence"],
                *evidence_refs_by_type["test_command_evidence"],
            ),
        ),
        _lineage(
            path="tests/integration/test_frontend_backend.py",
            surface_ref="tests",
            producer_ticket_ref=TICKET_TESTS_ID,
            producer_attempt_ref=provider_fixture.provider_attempts_by_ticket_id[
                TICKET_TESTS_ID
            ].provider_attempt_id,
            consumer_ticket_refs=(TICKET_TESTS_ID,),
            acceptance_refs=(
                "AC-TINY-BACKEND-STARTUP",
                "AC-TINY-BACKEND-HTTP-CRUD",
                "AC-TINY-SQLITE-PERSISTENCE-VIA-HTTP",
                "AC-TINY-FRONTEND-STARTUP",
                "AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION",
                "AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",
            ),
            evidence_refs=(
                *evidence_refs_by_type["frontend_source_inventory"],
                *evidence_refs_by_type["run_manifest"],
                *evidence_refs_by_type["test_command_evidence"],
            ),
        ),
        _lineage(
            path="docs/usage.md",
            surface_ref="docs",
            producer_ticket_ref=TICKET_DOCS_RUN_MANIFEST_ID,
            producer_attempt_ref=provider_fixture.provider_attempts_by_ticket_id[
                TICKET_DOCS_RUN_MANIFEST_ID
            ].provider_attempt_id,
            consumer_ticket_refs=(TICKET_DOCS_RUN_MANIFEST_ID,),
            acceptance_refs=("AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",),
            evidence_refs=(
                *evidence_refs_by_type["run_manifest"],
                *evidence_refs_by_type["test_command_evidence"],
            ),
        ),
    )


def _lineage(
    *,
    path: str,
    surface_ref: str,
    producer_ticket_ref: TicketId,
    producer_attempt_ref,
    consumer_ticket_refs: tuple[TicketId, ...],
    acceptance_refs: tuple[str, ...],
    evidence_refs: tuple[object, ...],
) -> SourceLineageRecord:
    return SourceLineageRecord(
        path=SourceFilePath(value=path),
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        producer_ticket_ref=producer_ticket_ref,
        producer_attempt_ref=producer_attempt_ref,
        consumer_ticket_refs=consumer_ticket_refs,
        acceptance_refs=tuple(AcceptanceRef(value=value) for value in acceptance_refs),
        evidence_refs=evidence_refs,
    )


def _command_results_by_id(
    *,
    provider_fixture: TinyProviderAttemptFixture,
    package_root: Path,
) -> dict[str, CommandRunnerResult]:
    execution_package = provider_fixture.execution_packages[TICKET_TESTS_ID]
    package_contract = provider_fixture.compiled.ticket_graph_fixture.contracts.package_contract
    runner = CommandRunner(
        clock=SequenceClock(
            COMMAND_STARTED_AT,
            COMMAND_FINISHED_AT,
            COMMAND_STARTED_AT,
            COMMAND_FINISHED_AT,
        )
    )
    results: dict[str, CommandRunnerResult] = {}
    for command_id in ("test-backend", "test-integration"):
        results[command_id] = runner.run(
            CommandRunnerInput(
                execution_package=execution_package,
                package_contract=package_contract,
                command_id=ContractId(value=command_id),
                package_root=package_root,
                runner_ref=RunnerRef(value="runner.tiny-package-assembly"),
                environment_profile_ref=EnvironmentProfileRef(
                    value="env.tiny-package-assembly"
                ),
                workspace_snapshot_ref=WorkspaceSnapshotRef(
                    value="workspace-snapshot.tiny-package-assembly"
                ),
            )
        )
    return results


def _validate_real_provider_fixture(
    provider_fixture: TinyProviderAttemptFixture,
    *,
    allow_fake_provider_for_negative_tests: bool,
) -> None:
    fake_attempt_refs = tuple(
        attempt.provider_attempt_id.value
        for attempt in provider_fixture.provider_attempts_by_ticket_id.values()
        if ".fake." in attempt.provider_attempt_id.value
    )
    if fake_attempt_refs and not allow_fake_provider_for_negative_tests:
        raise ValueError("fake provider attempts cannot build tiny package assembly")
    if not provider_fixture.provider_attempts_by_ticket_id:
        raise ValueError("ProviderAttempt records are required for tiny package assembly")


def _source_delivery_files_from_provider(
    provider_fixture: TinyProviderAttemptFixture,
    *,
    allow_fake_provider_for_negative_tests: bool,
) -> dict[str, str]:
    if _provider_fixture_uses_fake_attempts(provider_fixture):
        if allow_fake_provider_for_negative_tests:
            return {}
        raise ValueError("fake provider attempts cannot deliver source files")
    files: dict[str, str] = {}
    artifact_root = _provider_artifact_root(provider_fixture)
    for result in provider_fixture.runtime_results:
        attempt = result.provider_attempt
        if attempt.parsed_output_ref is None:
            raise ValueError("ProviderAttempt parsed artifact is required")
        execution_package = _execution_package_for_attempt(
            provider_fixture=provider_fixture,
            attempt=attempt,
        )
        parsed_text = _read_provider_artifact_text(
            artifact_root=artifact_root,
            artifact_ref=attempt.parsed_output_ref.value,
        )
        extracted = _extract_source_delivery_payload(
            parsed_text=parsed_text,
            allowed_paths=tuple(path.value for path in execution_package.allowed_write_set),
        )
        overlap = set(files) & set(extracted)
        if overlap:
            raise ValueError("provider source delivery contains duplicate file paths")
        files.update(extracted)
    expected_paths = _expected_provider_source_paths(provider_fixture)
    if set(files) != expected_paths:
        raise ValueError("provider source delivery must cover every implementation file")
    return files


def _provider_fixture_uses_fake_attempts(
    provider_fixture: TinyProviderAttemptFixture,
) -> bool:
    return any(
        ".fake." in attempt.provider_attempt_id.value
        for attempt in provider_fixture.provider_attempts_by_ticket_id.values()
    )


def _provider_artifact_root(provider_fixture: TinyProviderAttemptFixture) -> Path:
    return provider_fixture.provider_artifact_root


def _execution_package_for_attempt(
    *,
    provider_fixture: TinyProviderAttemptFixture,
    attempt: ProviderAttempt,
):
    for execution_package in provider_fixture.execution_packages.values():
        if execution_package.execution_package_id.value == attempt.input_package_ref.value:
            return execution_package
    raise ValueError("ProviderAttempt input package must resolve to an ExecutionPackage")


def _read_provider_artifact_text(*, artifact_root: Path, artifact_ref: str) -> str:
    safe_name = artifact_ref.replace("/", "_").replace("\\", "_").replace(":", "_")
    path = artifact_root / f"{safe_name}.txt"
    if not path.exists():
        raise ValueError(f"provider artifact is missing: {artifact_ref}")
    return path.read_text(encoding="utf-8")


def _extract_source_delivery_payload(
    *,
    parsed_text: str,
    allowed_paths: tuple[str, ...],
) -> dict[str, str]:
    data = _parse_json_payload(parsed_text)
    files = data.get("files")
    if not isinstance(files, dict):
        raise ValueError("provider source delivery must include a files object")
    ignored_typed_paths = {"package-contract.json", "run-manifest.json"}
    allowed_path_set = set(allowed_paths) - ignored_typed_paths
    extracted: dict[str, str] = {}
    for path, content in files.items():
        if path in ignored_typed_paths:
            continue
        if path not in allowed_path_set:
            raise ValueError("provider source delivery wrote outside allowed_write_set")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("provider source delivery file content is required")
        extracted[path] = content
    if allowed_path_set and set(extracted) != allowed_path_set:
        raise ValueError("provider source delivery must cover allowed_write_set")
    return extracted


def _expected_provider_source_paths(
    provider_fixture: TinyProviderAttemptFixture,
) -> set[str]:
    return {
        path.value
        for execution_package in provider_fixture.execution_packages.values()
        for path in execution_package.allowed_write_set
        if path.value not in {"package-contract.json", "run-manifest.json"}
    }


def _parse_json_payload(parsed_text: str) -> dict[str, object]:
    text = parsed_text.strip()
    if text.startswith("```"):
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if match is None:
            raise ValueError("provider source delivery fenced JSON is invalid")
        text = match.group(1)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("provider source delivery must be JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("provider source delivery must be a JSON object")
    return payload


def _validate_tiny_package_functional_scope(package_contents: Mapping[str, str]) -> None:
    backend_app = package_contents.get("backend/app.py", "")
    backend_db = package_contents.get("backend/db.py", "")
    backend_tests = package_contents.get("backend/tests/test_api.py", "")
    frontend_app = package_contents.get("frontend/app.js", "")
    integration_tests = package_contents.get("tests/integration/test_frontend_backend.py", "")
    if "def delete_book" not in backend_app or "delete_book" not in backend_tests:
        raise ValueError("AC-TINY-API-BOOK-DELETE requires delete_book source and tests")
    _validate_backend_public_api_signatures(backend_app)
    _validate_backend_standard_library_http_service(backend_app)
    _reject_delete_test_that_refetches_deleted_book(backend_tests)
    sqlite_markers = (
        "import sqlite3",
        "sqlite3.connect",
        "CREATE TABLE",
        "INSERT INTO books",
        "UPDATE books",
        "DELETE FROM books",
    )
    if any(marker not in backend_db for marker in sqlite_markers):
        raise ValueError("AC-TINY-PERSISTENCE-SQLITE requires real sqlite3 persistence")
    _validate_sqlite_schema_literals(backend_db)
    persistent_connection_markers = (
        "self._conn = sqlite3.connect",
        "self.connection = sqlite3.connect",
        "self.conn = sqlite3.connect",
    )
    if any(marker in backend_db for marker in persistent_connection_markers):
        raise ValueError(
            "SQLite connection must not be kept open on BookStore instances; "
            "Windows file cleanup requires short-lived connections"
        )
    if "import sqlite3" not in backend_tests:
        raise ValueError("AC-TINY-PERSISTENCE-SQLITE requires SQLite verification evidence")
    if "with sqlite3.connect" in backend_tests and "closing(sqlite3.connect" not in backend_tests:
        raise ValueError(
            "SQLite test connection must be explicitly closed for Windows cleanup"
        )
    sqlite_evidence_markers = (
        "sqlite3.connect",
        "sqlite_master",
        "sqlite3.Connection",
        ".exists()",
        "os.path.exists",
        "os.remove",
    )
    if not any(marker in backend_tests for marker in sqlite_evidence_markers):
        raise ValueError("AC-TINY-PERSISTENCE-SQLITE requires SQLite verification evidence")
    if not _frontend_has_exact_function_signature(
        frontend_app,
        function_name="loadBooks",
        parameters=("fetchImpl",),
    ):
        raise ValueError(
            "AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION requires loadBooks(fetchImpl)"
        )
    if not _frontend_has_exact_function_signature(
        frontend_app,
        function_name="deleteBook",
        parameters=("fetchImpl", "bookId"),
    ):
        raise ValueError(
            "AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION requires deleteBook(fetchImpl, bookId)"
        )
    if "/health" not in frontend_app or "/books" not in frontend_app or "DELETE" not in frontend_app:
        raise ValueError("AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION requires live backend HTTP paths")
    if not _frontend_module_is_node_import_safe(frontend_app):
        raise ValueError(
            "frontend module must guard window.addEventListener before Node integration import"
        )
    _validate_frontend_integration_behavior_evidence(integration_tests)


def _reject_delete_test_that_refetches_deleted_book(backend_tests: str) -> None:
    try:
        tree = ast.parse(backend_tests)
    except SyntaxError as error:
        raise ValueError("backend tests must be valid Python") from error
    helper_names = _helpers_that_refetch_bool_like_mutations(tree)
    if not helper_names:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called_name = _callable_name(node.func)
        if called_name not in helper_names:
            continue
        if any(_is_delete_book_ref(argument) for argument in node.args):
            raise ValueError(
                "delete_book tests must not refetch a deleted book after a "
                "bool/int/str mutation result"
            )


def _validate_backend_public_api_signatures(backend_app: str) -> None:
    try:
        tree = ast.parse(backend_app)
    except SyntaxError as error:
        raise ValueError("backend app source must be valid Python") from error
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    required = {
        "create_store": ("db_path",),
        "create_book": ("title",),
        "list_books": (),
        "checkout_book": ("book_id",),
        "return_book": ("book_id",),
        "delete_book": ("book_id",),
    }
    for function_name, required_names in required.items():
        node = functions.get(function_name)
        if node is None:
            raise ValueError(f"backend app must expose {function_name}")
        if node.args.vararg is not None or node.args.kwarg is not None:
            raise ValueError(
                "backend public API functions must use explicit parameters, not *args or **kwargs"
            )
        positional = tuple(argument.arg for argument in node.args.args)
        keyword_only = tuple(argument.arg for argument in node.args.kwonlyargs)
        available = (*positional, *keyword_only)
        for required_name in required_names:
            if required_name not in available:
                raise ValueError(
                    f"backend app {function_name} must include explicit {required_name} parameter"
                )


def _validate_backend_standard_library_http_service(backend_app: str) -> None:
    try:
        ast.parse(backend_app)
    except SyntaxError as error:
        raise ValueError("backend/app.py must be valid Python") from error
    service_markers = (
        "http.server",
        "BaseHTTPRequestHandler",
        "HTTPServer",
        "ThreadingHTTPServer",
        "socketserver.TCPServer",
    )
    if not any(marker in backend_app for marker in service_markers):
        raise ValueError("AC-TINY-BACKEND-STARTUP requires standard-library HTTP service")
    if "serve_forever" not in backend_app or "__main__" not in backend_app:
        raise ValueError("AC-TINY-BACKEND-STARTUP requires runnable backend service entrypoint")
    route_markers = ("/health", "/books", "checkout", "return")
    if not all(marker in backend_app for marker in route_markers):
        raise ValueError("AC-TINY-BACKEND-HTTP-CRUD requires live HTTP CRUD routes")
    if not any(marker in backend_app for marker in ("do_DELETE", "DELETE", "delete")):
        raise ValueError("AC-TINY-BACKEND-HTTP-CRUD requires delete HTTP endpoint")


def _helpers_that_refetch_bool_like_mutations(tree: ast.AST) -> set[str]:
    helper_names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        has_bool_like_branch = any(
            isinstance(inner, ast.Call)
            and _callable_name(inner.func) == "isinstance"
            and len(inner.args) >= 2
            and _node_mentions_name(inner.args[0], "result")
            and _node_mentions_any_name(inner.args[1], {"bool", "int", "str"})
            for inner in ast.walk(node)
        )
        returns_finder = any(
            isinstance(inner, ast.Return)
            and isinstance(inner.value, ast.Call)
            and _callable_name(inner.value.func).endswith("find_book")
            for inner in ast.walk(node)
        )
        if has_bool_like_branch and returns_finder:
            helper_names.add(node.name)
    return helper_names


def _is_delete_book_ref(node: ast.AST) -> bool:
    return _callable_name(node).endswith("delete_book")


def _callable_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _callable_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _node_mentions_name(node: ast.AST, name: str) -> bool:
    return any(isinstance(inner, ast.Name) and inner.id == name for inner in ast.walk(node))


def _node_mentions_any_name(node: ast.AST, names: set[str]) -> bool:
    return any(isinstance(inner, ast.Name) and inner.id in names for inner in ast.walk(node))


def _validate_sqlite_schema_literals(backend_db: str) -> None:
    try:
        tree = ast.parse(backend_db)
    except SyntaxError as error:
        raise ValueError("backend db source must be valid Python") from error
    create_table_sql = tuple(
        value
        for value in _string_literals(tree)
        if "CREATE TABLE" in value.upper()
    )
    if not create_table_sql:
        raise ValueError("SQLite schema must include executable CREATE TABLE SQL")
    for sql in create_table_sql:
        try:
            connection = sqlite3.connect(":memory:")
            try:
                connection.execute(sql)
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise ValueError("SQLite CREATE TABLE schema must be executable") from error


def _string_literals(tree: ast.AST) -> tuple[str, ...]:
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value)
    return tuple(values)


def _frontend_has_exact_function_signature(
    frontend_app: str,
    *,
    function_name: str,
    parameters: tuple[str, ...],
) -> bool:
    parameter_pattern = r"\s*,\s*".join(re.escape(parameter) for parameter in parameters)
    patterns = (
        rf"(?:export\s+)?async\s+function\s+{re.escape(function_name)}\s*\(\s*{parameter_pattern}\s*\)",
        rf"(?:export\s+)?(?:const|let|var)\s+{re.escape(function_name)}\s*=\s*async\s*\(\s*{parameter_pattern}\s*\)",
        rf"(?:export\s+)?(?:const|let|var)\s+{re.escape(function_name)}\s*=\s*\(\s*{parameter_pattern}\s*\)\s*=>",
    )
    if not any(re.search(pattern, frontend_app) for pattern in patterns):
        return False
    default_pattern = rf"{re.escape(function_name)}\s*\([^)]*="
    return re.search(default_pattern, frontend_app) is None


def _frontend_module_is_node_import_safe(frontend_app: str) -> bool:
    if "window.addEventListener" not in frontend_app:
        return True
    guard_markers = (
        "typeof window.addEventListener === 'function'",
        'typeof window.addEventListener === "function"',
        "'addEventListener' in window",
        '"addEventListener" in window',
    )
    return any(marker in frontend_app for marker in guard_markers)


def _validate_frontend_integration_behavior_evidence(integration_tests: str) -> None:
    if not integration_tests.strip():
        raise ValueError("frontend integration behavior evidence is required")
    try:
        ast.parse(integration_tests)
    except SyntaxError as error:
        raise ValueError("frontend integration tests must be valid Python") from error
    runner_markers = ("subprocess.Popen", "subprocess.run", "asyncio.run", "pytest.mark.asyncio")
    if not any(marker in integration_tests for marker in runner_markers):
        raise ValueError("integration behavior evidence must execute frontend functions")
    startup_markers = (
        "python -m backend.app",
        '"-m", "backend.app"',
        "'-m', 'backend.app'",
        "backend.app",
    )
    http_client_markers = ("urllib.request", "http.client", "urlopen(")
    if (
        not any(marker in integration_tests for marker in startup_markers)
        or not any(marker in integration_tests for marker in http_client_markers)
        or "/health" not in integration_tests
        or "/books" not in integration_tests
        or ("127.0.0.1" not in integration_tests and "localhost" not in integration_tests)
    ):
        raise ValueError("live HTTP integration evidence must start backend and probe /health and /books")
    if "DELETE" not in integration_tests:
        raise ValueError("integration behavior evidence must assert backend delete API path")
    if "fakeFetch" in integration_tests:
        raise ValueError("fakeFetch-only cannot satisfy live frontend/backend integration evidence")
    reset_markers = (".length = 0", ".splice(0")
    if any(marker in integration_tests for marker in reset_markers):
        raise ValueError(
            "integration behavior evidence must preserve loadBooks and deleteBook fetch calls"
        )
    pytest_tmp_filter_markers = (
        "part.startswith(\".pytest-tmp\")",
        "part.startswith('.pytest-tmp')",
        "startswith(\".pytest-tmp\")",
        "startswith('.pytest-tmp')",
    )
    if any(marker in integration_tests for marker in pytest_tmp_filter_markers):
        raise ValueError(
            "integration behavior evidence must not exclude frontend modules "
            "because the package root is under a pytest-tmp directory"
        )


class SequenceClock:
    def __init__(self, *timestamps: datetime) -> None:
        self._timestamps = list(timestamps)

    def now(self) -> datetime:
        if not self._timestamps:
            raise ValueError("clock exhausted")
        return self._timestamps.pop(0)


def _verified_evidence(
    *,
    provider_fixture: TinyProviderAttemptFixture,
    command_results_by_id: Mapping[str, CommandRunnerResult],
) -> tuple[VerifiedEvidence, ...]:
    verified: list[VerifiedEvidence] = []
    for obligation in provider_fixture.compiled.ticket_graph_fixture.contracts.contract_gate.evidence_obligations:
        if obligation.required_artifact_type.value not in _SUPPORTED_PACKAGE_ASSEMBLY_EVIDENCE_TYPES:
            continue
        command_result = command_results_by_id[_command_id_for_obligation(obligation)]
        producer_attempt_ref = _producer_attempt_ref_for_obligation(
            provider_fixture=provider_fixture,
            obligation=obligation,
        )
        claim = build_evidence_claim_from_verification_run(
            verification_run=command_result.verification_run,
            evidence_obligation=obligation,
            producer_attempt_ref=producer_attempt_ref,
            acceptance_refs=obligation.acceptance_refs,
            source_surface_refs=obligation.source_surface_refs,
            expected_purpose=EvidencePurpose.IMPLEMENTATION,
            summary=(
                "Tiny package assembly evidence verified from declared runner output."
            ),
        )
        result = EvidenceVerifier().verify(
            EvidenceVerificationInput(
                claim=claim,
                evidence_obligation=obligation,
                active_acceptance_contract=(
                    provider_fixture.compiled.ticket_graph_fixture.contracts.acceptance_contract
                ),
                artifact_manifest=_artifact_manifest(
                    command_result=command_result,
                    producer_attempt_ref=producer_attempt_ref,
                    artifact_kind=obligation.required_artifact_type.value,
                ),
                purpose_policy=EvidencePurposePolicy(
                    rules=(
                        EvidencePurposeRule(
                            required_artifact_type=obligation.required_artifact_type,
                            allowed_purposes=(EvidencePurpose.IMPLEMENTATION,),
                        ),
                    )
                ),
                provider_attempts=tuple(provider_fixture.provider_attempts_by_ticket_id.values()),
                execution_packages=tuple(provider_fixture.execution_packages.values()),
                role_prompt_hook_registry=baseline_role_prompt_hook_registry(),
                verification_runs=(command_result.verification_run,),
                verified_at=VERIFIED_AT,
            )
        )
        if not result.success or result.verified_evidence is None:
            raise AssertionError(f"tiny evidence verification failed: {result.blockers}")
        verified.append(result.verified_evidence)
    return tuple(verified)


_SUPPORTED_PACKAGE_ASSEMBLY_EVIDENCE_TYPES = {
    "backend_source_inventory",
    "sqlite_persistence_evidence",
    "frontend_source_inventory",
    "run_manifest",
    "test_command_evidence",
}


def _producer_attempt_ref_for_obligation(
    *,
    provider_fixture: TinyProviderAttemptFixture,
    obligation: EvidenceObligation,
):
    artifact_type = obligation.required_artifact_type.value
    if artifact_type in {
        "backend_source_inventory",
        "sqlite_persistence_evidence",
    }:
        return provider_fixture.provider_attempts_by_ticket_id[
            TICKET_BACKEND_API_ID
        ].provider_attempt_id
    if artifact_type == "frontend_source_inventory":
        return provider_fixture.provider_attempts_by_ticket_id[
            TICKET_FRONTEND_UI_ID
        ].provider_attempt_id
    if artifact_type == "run_manifest":
        return provider_fixture.provider_attempts_by_ticket_id[
            TICKET_DOCS_RUN_MANIFEST_ID
        ].provider_attempt_id
    return provider_fixture.provider_attempts_by_ticket_id[TICKET_TESTS_ID].provider_attempt_id


def _artifact_manifest(
    *,
    command_result: CommandRunnerResult,
    producer_attempt_ref,
    artifact_kind: str,
) -> ArtifactManifest:
    run = command_result.verification_run
    return ArtifactManifest(
        entries=(
            ArtifactManifestEntry(
                artifact_ref=EvidenceArtifactRef(value=run.stdout_ref.value),
                sha256=_sha256(command_result.stdout),
                producer_attempt_ref=producer_attempt_ref,
                source_ref=run.verification_run_id.value,
                artifact_kind=f"{artifact_kind}_stdout",
            ),
            ArtifactManifestEntry(
                artifact_ref=EvidenceArtifactRef(value=run.stderr_ref.value),
                sha256=_sha256(command_result.stderr),
                producer_attempt_ref=producer_attempt_ref,
                source_ref=run.verification_run_id.value,
                artifact_kind=f"{artifact_kind}_stderr",
            ),
        )
    )


def _command_id_for_obligation(obligation: EvidenceObligation) -> str:
    if obligation.required_artifact_type.value in {
        "frontend_source_inventory",
        "run_manifest",
        "test_command_evidence",
    }:
        return "test-integration"
    return "test-backend"


def _write_ephemeral_tiny_package_for_command_evidence(
    *,
    package_root: Path,
    package_contents: Mapping[str, str],
) -> None:
    root_text = package_root.as_posix().rstrip("/")
    if root_text in {"10-project", "20-evidence"} or root_text.endswith(
        "/10-project"
    ) or root_text.endswith("/20-evidence"):
        raise ValueError("tiny package assembly fixture requires an isolated tmp package root")
    resolved_root = package_root.resolve()
    validated_targets: list[tuple[Path, str]] = []
    for relative_path, content in package_contents.items():
        PackageArtifactPath(value=relative_path)
        target = (resolved_root / relative_path).resolve()
        if target == resolved_root or resolved_root not in target.parents:
            raise ValueError("package artifact path must stay within package root")
        validated_targets.append((target, content))
    package_root.mkdir(parents=True, exist_ok=True)
    for target, content in validated_targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _package_contents_with_generated_files(
    *,
    provider_contents: Mapping[str, str],
    override_contents: Mapping[str, str] | None,
    run_manifest: RunManifest,
) -> Mapping[str, str]:
    if not provider_contents and override_contents is None:
        raise ValueError("provider source delivery files are required")
    contents = dict(provider_contents)
    contents["package-contract.json"] = (
        json.dumps({"package_root": "10-project"}, sort_keys=True)
        + "\n"
    )
    contents["run-manifest.json"] = (
        json.dumps(run_manifest.model_dump(mode="json"), sort_keys=True) + "\n"
    )
    if override_contents is not None:
        unknown_paths = set(override_contents) - set(EXPECTED_TINY_PACKAGE_PATHS)
        if unknown_paths:
            for unknown_path in unknown_paths:
                PackageArtifactPath(value=unknown_path)
            raise ValueError("package override contains paths outside package artifacts")
        contents.update(override_contents)
    missing_paths = set(EXPECTED_TINY_PACKAGE_PATHS) - set(contents)
    if missing_paths:
        raise ValueError("provider source delivery is missing package paths")
    return {
        path: contents[path]
        for path in EXPECTED_TINY_PACKAGE_PATHS
    }


def _validate_package_content_override_paths(
    override_contents: Mapping[str, str] | None,
) -> None:
    if override_contents is None:
        return
    unknown_paths = set(override_contents) - set(EXPECTED_TINY_PACKAGE_PATHS)
    if not unknown_paths:
        return
    for unknown_path in sorted(unknown_paths):
        PackageArtifactPath(value=unknown_path)
    raise ValueError("package override contains paths outside package artifacts")


def _validate_source_override_usage(
    *,
    package_contents: Mapping[str, str] | None,
    allow_fake_provider_for_negative_tests: bool,
) -> None:
    if package_contents is not None and not allow_fake_provider_for_negative_tests:
        raise ValueError(
            "package source override is only allowed for explicit negative tests"
        )


def _validate_physical_run_manifest(
    *,
    package_root: Path,
    run_manifest: RunManifest,
) -> None:
    manifest_path = package_root / "run-manifest.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError("run-manifest.json is required") from error
    except json.JSONDecodeError as error:
        raise ValueError("run-manifest.json must contain valid run manifest JSON") from error
    try:
        physical_manifest = RunManifest.model_validate(data)
    except Exception as error:
        raise ValueError("run-manifest.json must match RunManifest schema") from error
    if physical_manifest != run_manifest:
        raise ValueError("run-manifest.json must match in-memory RunManifest")


def _evidence_refs_by_artifact_type(
    verified_evidence: tuple[VerifiedEvidence, ...],
) -> dict[str, tuple[object, ...]]:
    by_type: dict[str, list[object]] = {}
    for evidence in verified_evidence:
        by_type.setdefault(evidence.required_artifact_type.value, []).append(
            evidence.verified_evidence_id
        )
    return {
        artifact_type: tuple(sorted(refs, key=lambda ref: ref.value))
        for artifact_type, refs in by_type.items()
    }


def _sha256(value: str) -> ArtifactSha256:
    return ArtifactSha256(value=hashlib.sha256(value.encode("utf-8")).hexdigest())


__all__ = [
    "EXPECTED_TINY_PACKAGE_PATHS",
    "TinyPackageAssemblyFixture",
    "build_tiny_package_assembly_fixture",
]
