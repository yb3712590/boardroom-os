from __future__ import annotations

import hashlib
import http.client
import json
import re
import sqlite3
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Mapping

from boardroom_os.adapters.process_runner import (
    CommandRunner,
    CommandRunnerInput,
    CommandRunnerResult,
    ServiceRunner,
    ServiceRunnerInput,
)
from boardroom_os.contracts.evidence_obligation import EvidenceObligation
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import AcceptanceRef, ContractId, NonEmptyTextValue, SourceSurfaceRef
from boardroom_os.evidence.claim import (
    EvidenceArtifactRef,
    build_evidence_claim_from_live_blackbox,
    build_evidence_claim_from_service_run,
    build_evidence_claim_from_verification_run,
)
from boardroom_os.evidence.live_blackbox import (
    LiveBlackboxIntegrationEvidence,
    LiveBlackboxIntegrationEvidenceRef,
    LiveBlackboxIntegrationVerifier,
    LiveBlackboxProbeResult,
    LiveBlackboxVerifierInput,
    artifact_refs_for_live_blackbox,
)
from boardroom_os.evidence.service_run import ServiceReadinessUrl, ServiceRunEvidence, ServiceRunEvidenceRef
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
from boardroom_os.execution.package import ExecutionPackageId
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


@dataclass(frozen=True)
class TinyLiveBlackboxFixture(TinyPackageAssemblyFixture):
    service_runs: tuple[ServiceRunEvidence, ...] = ()
    service_run_outputs: tuple["TinyServiceRunOutput", ...] = ()
    live_blackbox_evidence: LiveBlackboxIntegrationEvidence | None = None


@dataclass(frozen=True)
class TinyServiceRunOutput:
    service_run: ServiceRunEvidence
    stdout: str
    stderr: str


def build_tiny_package_assembly_fixture(
    *,
    package_root: Path,
    package_contents: Mapping[str, str] | None = None,
    provider_fixture: TinyProviderAttemptFixture | None = None,
    allow_test_provider_transport: bool = False,
) -> TinyPackageAssemblyFixture:
    _validate_package_content_override_paths(package_contents)
    _validate_source_override_usage(
        package_contents=package_contents,
        allow_test_provider_transport=allow_test_provider_transport,
    )
    provider_fixture = provider_fixture or build_tiny_provider_attempt_fixture(
        settings=openai_settings_from_test_env(),
        use_fake_results=False,
    )
    _validate_real_provider_fixture(
        provider_fixture,
        allow_test_provider_transport=allow_test_provider_transport,
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
        allow_test_provider_transport=allow_test_provider_transport,
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


def build_tiny_live_blackbox_fixture(
    *,
    package_root: Path,
    package_contents: Mapping[str, str] | None = None,
    provider_fixture: TinyProviderAttemptFixture | None = None,
    allow_test_provider_transport: bool = False,
) -> TinyLiveBlackboxFixture:
    base = build_tiny_package_assembly_fixture(
        package_root=package_root,
        package_contents=package_contents,
        provider_fixture=provider_fixture,
        allow_test_provider_transport=allow_test_provider_transport,
    )
    live_execution_package = _live_blackbox_execution_package(base)
    service_runs, service_run_outputs, live_blackbox_evidence = _tiny_service_runs(
        base,
        live_execution_package=live_execution_package,
    )
    live_result = LiveBlackboxIntegrationVerifier().verify(
        LiveBlackboxVerifierInput(
            evidence=live_blackbox_evidence,
            package_contract=base.package_contract,
            service_runs=service_runs,
        )
    )
    if not live_result.success:
        messages = "; ".join(blocker.message for blocker in live_result.blockers)
        raise ValueError(f"live blackbox verification failed: {messages}")

    live_verified_evidence = _live_verified_evidence(
        provider_fixture=base.provider_fixture,
        live_execution_package=live_execution_package,
        live_blackbox_evidence=live_blackbox_evidence,
        service_runs=service_runs,
        service_run_outputs=service_run_outputs,
    )
    verified_evidence = (*base.verified_evidence, *live_verified_evidence)
    source_inventory = build_source_inventory(
        package_assembly=base.package_assembly,
        package_contract=base.package_contract,
        package_commit_ref=PACKAGE_COMMIT_REF,
        source_files=_source_files(base.source_contents),
        lineage_records=_source_lineage_records(
            provider_fixture=base.provider_fixture,
            verified_evidence=verified_evidence,
        ),
    )
    final_evidence_table = FinalEvidenceTableBuilder().build(
        FinalEvidenceTableInput(
            active_acceptance_contract=(
                base.provider_fixture.compiled.ticket_graph_fixture.contracts.acceptance_contract
            ),
            verified_evidence=verified_evidence,
            generated_at=GENERATED_AT,
        )
    )
    workspace_evidence_bundle = build_workspace_evidence_bundle(
        workspace_manifest=base.workspace_manifest,
        package_assembly=base.package_assembly,
        source_inventory=source_inventory,
        run_manifest=base.run_manifest,
        verification_runs=tuple(
            result.verification_run for result in base.command_results_by_id.values()
        ),
        service_runs=service_runs,
        live_blackbox_evidence=(live_blackbox_evidence,),
        verified_evidence=verified_evidence,
        final_evidence_table=final_evidence_table,
    )
    return TinyLiveBlackboxFixture(
        provider_fixture=base.provider_fixture,
        workspace_manifest=base.workspace_manifest,
        package_contract=base.package_contract,
        package_artifacts=base.package_artifacts,
        package_assembly=base.package_assembly,
        run_manifest=base.run_manifest,
        package_root_path=base.package_root_path,
        source_contents=base.source_contents,
        command_results_by_id=base.command_results_by_id,
        verified_evidence=verified_evidence,
        source_inventory=source_inventory,
        final_evidence_table=final_evidence_table,
        workspace_evidence_bundle=workspace_evidence_bundle,
        service_runs=service_runs,
        service_run_outputs=service_run_outputs,
        live_blackbox_evidence=live_blackbox_evidence,
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
            evidence_refs=(
                *evidence_refs_by_type["backend_http_api_evidence"],
                *evidence_refs_by_type["backend_source_inventory"],
                *evidence_refs_by_type["backend_service_run"],
                *evidence_refs_by_type["backend_http_crud_evidence"],
            ),
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
                *evidence_refs_by_type["backend_service_run"],
                *evidence_refs_by_type["backend_http_crud_evidence"],
                *evidence_refs_by_type["sqlite_persistence_evidence"],
                *evidence_refs_by_type["sqlite_persistence_http_evidence"],
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
            evidence_refs=(
                *evidence_refs_by_type["frontend_source_inventory"],
                *evidence_refs_by_type["frontend_service_run"],
                *evidence_refs_by_type["live_frontend_backend_integration_evidence"],
            ),
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
            evidence_refs=(
                *evidence_refs_by_type["frontend_source_inventory"],
                *evidence_refs_by_type["frontend_service_run"],
            ),
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
                *evidence_refs_by_type["backend_http_api_evidence"],
                *evidence_refs_by_type["sqlite_persistence_evidence"],
                *evidence_refs_by_type["backend_service_run"],
                *evidence_refs_by_type["backend_http_crud_evidence"],
                *evidence_refs_by_type["sqlite_persistence_http_evidence"],
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
                *evidence_refs_by_type["backend_service_run"],
                *evidence_refs_by_type["frontend_service_run"],
                *evidence_refs_by_type["backend_http_crud_evidence"],
                *evidence_refs_by_type["sqlite_persistence_http_evidence"],
                *evidence_refs_by_type["live_frontend_backend_integration_evidence"],
                *evidence_refs_by_type["run_manifest"],
                *evidence_refs_by_type["test_command_evidence"],
                *evidence_refs_by_type["final_command_evidence"],
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
                *evidence_refs_by_type["final_command_evidence"],
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


def _tiny_service_runs(
    base: TinyPackageAssemblyFixture,
    *,
    live_execution_package,
) -> tuple[
    tuple[ServiceRunEvidence, ...],
    tuple[TinyServiceRunOutput, ...],
    LiveBlackboxIntegrationEvidence,
]:
    backend_port = 8765
    frontend_port = 8766
    db_path = base.package_root_path / "20-evidence-runtime" / "books.blackbox.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    live_evidence: LiveBlackboxIntegrationEvidence | None = None
    frontend_run: ServiceRunEvidence | None = None
    frontend_output: TinyServiceRunOutput | None = None

    def probe_backend_while_ready(backend_service: ServiceRunEvidence) -> None:
        nonlocal live_evidence, frontend_run, frontend_output

        def probe_frontend_while_ready(frontend_service: ServiceRunEvidence) -> None:
            nonlocal live_evidence
            live_evidence = _live_blackbox_evidence(
                base=base,
                backend_service=backend_service,
                frontend_service=frontend_service,
            )

        frontend_result = _run_service_command(
            base,
            live_execution_package=live_execution_package,
            command_id="run-frontend",
            readiness_url=f"http://127.0.0.1:{frontend_port}/index.html",
            environment_overrides={"FRONTEND_PORT": str(frontend_port)},
            after_ready_probe=probe_frontend_while_ready,
        )
        frontend_run = frontend_result.service_run_evidence
        frontend_output = TinyServiceRunOutput(
            service_run=frontend_result.service_run_evidence,
            stdout=frontend_result.stdout,
            stderr=frontend_result.stderr,
        )

    backend_result = _run_service_command(
        base,
        live_execution_package=live_execution_package,
        command_id="run-backend",
        readiness_url=f"http://127.0.0.1:{backend_port}/health",
        environment_overrides={
            "PORT": str(backend_port),
            "BOOKS_DB_PATH": str(db_path),
        },
        after_ready_probe=probe_backend_while_ready,
    )
    backend_run = backend_result.service_run_evidence
    backend_output = TinyServiceRunOutput(
        service_run=backend_result.service_run_evidence,
        stdout=backend_result.stdout,
        stderr=backend_result.stderr,
    )
    if frontend_run is None or frontend_output is None or live_evidence is None:
        raise ValueError("live blackbox probes must run while backend and frontend services are ready")
    return (backend_run, frontend_run), (backend_output, frontend_output), live_evidence


def _run_service_command(
    base: TinyPackageAssemblyFixture,
    *,
    live_execution_package,
    command_id: str,
    readiness_url: str,
    environment_overrides: Mapping[str, str],
    after_ready_probe=None,
):
    return ServiceRunner(
        clock=SequenceClock(
            VERIFIED_AT,
            VERIFIED_AT + timedelta(seconds=1),
            VERIFIED_AT + timedelta(seconds=2),
        )
    ).run(
        ServiceRunnerInput(
            execution_package=live_execution_package,
            package_contract=base.package_contract,
            command_id=ContractId(value=command_id),
            package_root=base.package_root_path,
            readiness_url=readiness_url,
            runner_ref=RunnerRef(value=f"runner.tiny-live-blackbox.{command_id}"),
            environment_profile_ref=EnvironmentProfileRef(
                value="env.tiny-live-blackbox"
            ),
            workspace_snapshot_ref=WorkspaceSnapshotRef(
                value="workspace-snapshot.tiny-live-blackbox"
            ),
            environment_overrides=dict(environment_overrides),
            timeout_seconds=5,
            poll_interval_seconds=0.05,
        ),
        after_ready_probe=after_ready_probe,
    )


def _live_blackbox_execution_package(base: TinyPackageAssemblyFixture):
    source_package = base.provider_fixture.execution_packages[TICKET_TESTS_ID]
    return source_package.model_copy(
        update={
            "execution_package_id": ExecutionPackageId(value="exec.tiny-live-blackbox"),
            "commands": base.package_contract.run_commands,
        }
    )


def _live_blackbox_evidence(
    *,
    base: TinyPackageAssemblyFixture,
    backend_service: ServiceRunEvidence,
    frontend_service: ServiceRunEvidence,
) -> LiveBlackboxIntegrationEvidence:
    backend_port = _required_env_value(backend_service, "PORT")
    db_path = Path(_required_env_value(backend_service, "BOOKS_DB_PATH"))
    backend_url = f"http://127.0.0.1:{backend_port}"
    backend_probe = _probe_backend_crud(
        backend_url,
        backend_service_ref=backend_service.service_run_evidence_id,
        backend_command_id=ContractId(value="run-backend"),
    )
    sqlite_probe = _probe_sqlite(
        db_path,
        deleted_book_id=int(backend_probe.observed_facts["created_book_id"]),
        backend_service_ref=backend_service.service_run_evidence_id,
        backend_command_id=ContractId(value="run-backend"),
    )
    frontend_probe = _probe_frontend_live(
        package_root=base.package_root_path,
        backend_url=backend_url,
        frontend_url=frontend_service.readiness_url.value,
        backend_service_ref=backend_service.service_run_evidence_id,
        frontend_service_ref=frontend_service.service_run_evidence_id,
    )

    return LiveBlackboxIntegrationEvidence(
        live_blackbox_evidence_id=LiveBlackboxIntegrationEvidenceRef(
            value="live-blackbox.tiny-fullstack"
        ),
        package_contract_ref=base.package_contract.package_contract_id,
        backend_command_id=ContractId(value="run-backend"),
        frontend_command_id=ContractId(value="run-frontend"),
        backend_service_run_ref=backend_service.service_run_evidence_id,
        frontend_service_run_ref=frontend_service.service_run_evidence_id,
        probes=(backend_probe, sqlite_probe, frontend_probe),
        generated_at=VERIFIED_AT,
    )


def _probe_backend_crud(
    backend_url: str,
    *,
    backend_service_ref: ServiceRunEvidenceRef,
    backend_command_id: ContractId,
) -> LiveBlackboxProbeResult:
    create_status, created = _http_json(
        f"{backend_url}/books",
        method="POST",
        payload={"title": "Dune"},
    )
    book_id = int(created["id"])
    list_status, _ = _http_json(f"{backend_url}/books")
    checkout_status, checked_out = _http_json(
        f"{backend_url}/books/{book_id}/checkout",
        method="POST",
    )
    return_status, returned = _http_json(
        f"{backend_url}/books/{book_id}/return",
        method="POST",
    )
    delete_status, deleted = _http_json(
        f"{backend_url}/books/{book_id}",
        method="DELETE",
    )
    _, after_delete = _http_json(f"{backend_url}/books")
    witness_in_library_status, _ = _http_json(
        f"{backend_url}/books",
        method="POST",
        payload={"title": "State witness in library"},
    )
    witness_checked_out_status, witness_checked_out = _http_json(
        f"{backend_url}/books",
        method="POST",
        payload={"title": "State witness checked out"},
    )
    if witness_in_library_status != 201 or witness_checked_out_status != 201:
        raise ValueError("HTTP workflow failed to create SQLite state witnesses")
    _http_json(
        f"{backend_url}/books/{int(witness_checked_out['id'])}/checkout",
        method="POST",
    )
    delete_confirmed = bool(deleted.get("deleted")) and all(
        book.get("id") != book_id for book in after_delete.get("books", [])
    )
    checkout_state = str(checked_out.get("state", ""))
    return_state = str(returned.get("state", ""))
    passed = (
        create_status == 201
        and list_status == 200
        and checkout_status == 200
        and checkout_state == "CHECKED_OUT"
        and return_status == 200
        and return_state == "IN_LIBRARY"
        and delete_status == 200
        and delete_confirmed
    )
    return LiveBlackboxProbeResult(
        probe_ref=NonEmptyTextValue(value="backend-http-crud"),
        acceptance_refs=(
            AcceptanceRef(value="AC-TINY-BACKEND-HTTP-CRUD"),
            AcceptanceRef(value="AC-TINY-API-BOOK-CREATE"),
            AcceptanceRef(value="AC-TINY-API-BOOK-LIST"),
            AcceptanceRef(value="AC-TINY-API-CHECKOUT-RETURN"),
            AcceptanceRef(value="AC-TINY-API-BOOK-DELETE"),
        ),
        service_run_refs=(backend_service_ref,),
        command_ids=(backend_command_id,),
        probe_url=ServiceReadinessUrl(value=f"{backend_url}/books"),
        status_code=200 if passed else 500,
        passed=passed,
        observed_facts={
            "created_book_id": book_id,
            "create_status": create_status,
            "list_status": list_status,
            "checkout_status": checkout_status,
            "checkout_state": checkout_state,
            "return_status": return_status,
            "return_state": return_state,
            "delete_status": delete_status,
            "delete_confirmed": delete_confirmed,
            "post_delete_list_excludes_deleted_id": delete_confirmed,
        },
        probed_at=VERIFIED_AT,
    )


def _probe_sqlite(
    db_path: Path,
    *,
    deleted_book_id: int,
    backend_service_ref: ServiceRunEvidenceRef,
    backend_command_id: ContractId,
) -> LiveBlackboxProbeResult:
    if not db_path.exists():
        raise ValueError("SQLite HTTP workflow did not create database file")
    file_size = db_path.stat().st_size
    with closing(sqlite3.connect(db_path)) as connection:
        schema_rows = tuple(
            tuple(str(item) for item in row)
            for row in connection.execute(
                "SELECT type, name FROM sqlite_master WHERE type IN ('table', 'index') ORDER BY type, name"
            )
        )
    passed = file_size > 0 and bool(schema_rows)
    return LiveBlackboxProbeResult(
        probe_ref=NonEmptyTextValue(value="sqlite-persistence-http"),
        acceptance_refs=(
            AcceptanceRef(value="AC-TINY-PERSISTENCE-SQLITE"),
            AcceptanceRef(value="AC-TINY-SQLITE-PERSISTENCE-VIA-HTTP"),
        ),
        service_run_refs=(backend_service_ref,),
        command_ids=(backend_command_id,),
        probe_url=None,
        status_code=None,
        passed=passed,
        observed_facts={
            "db_path": str(db_path),
            "db_file_exists": True,
            "db_file_size": file_size,
            "schema_object_count": len(schema_rows),
            "deleted_book_id_from_http_workflow": deleted_book_id,
            "source": "http_workflow",
        },
        probed_at=VERIFIED_AT,
    )


def _probe_frontend_live(
    *,
    package_root: Path,
    backend_url: str,
    frontend_url: str,
    backend_service_ref: ServiceRunEvidenceRef,
    frontend_service_ref: ServiceRunEvidenceRef,
) -> LiveBlackboxProbeResult:
    frontend_status, frontend_body = _http_text(frontend_url)
    if frontend_status != 200:
        raise ValueError("frontend service did not serve index.html")
    delete_status, delete_candidate = _http_json(
        f"{backend_url}/books",
        method="POST",
        payload={"title": "Frontend delete candidate"},
    )
    if delete_status != 201:
        raise ValueError("frontend live probe failed to create delete candidate")
    frontend_app_url = frontend_url.rsplit("/", 1)[0] + "/app.js"
    script = (
        "import { Buffer } from 'node:buffer';\n"
        f"globalThis.BOARDROOM_API_BASE = {json.dumps(backend_url)};\n"
        f"const appResponse = await fetch({json.dumps(frontend_app_url)});\n"
        "if (!appResponse.ok) { throw new Error(`frontend app.js fetch failed: ${appResponse.status}`); }\n"
        "const appSource = await appResponse.text();\n"
        "const appModuleUrl = `data:text/javascript;base64,${Buffer.from(appSource, 'utf8').toString('base64')}`;\n"
        "const mod = await import(appModuleUrl);\n"
        "const fetchedPaths = [];\n"
        "const fetchedMethods = [];\n"
        "const liveFetch = async (url, options = {}) => {\n"
        "  const parsed = new URL(url);\n"
        "  fetchedPaths.push(parsed.pathname);\n"
        "  fetchedMethods.push((options.method || 'GET').toUpperCase());\n"
        "  return await fetch(url, options);\n"
        "};\n"
        "await mod.probeBackend(liveFetch);\n"
        "await mod.loadBooks(liveFetch);\n"
        f"await mod.deleteBook(liveFetch, {int(delete_candidate['id'])});\n"
        "console.log(JSON.stringify({ fetchedPaths, fetchedMethods }));\n"
    )
    completed = subprocess.run(
        ("node", "--input-type=module", "-e", script),
        cwd=package_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(f"frontend live probe failed: {completed.stderr}")
    report = json.loads(completed.stdout)
    fetched_paths = tuple(report["fetchedPaths"])
    fetched_methods = tuple(report["fetchedMethods"])
    passed = (
        "/health" in fetched_paths
        and "/books" in fetched_paths
        and any(
            method == "DELETE" and path.startswith("/books/")
            for method, path in zip(fetched_methods, fetched_paths, strict=True)
        )
    )
    return LiveBlackboxProbeResult(
        probe_ref=NonEmptyTextValue(value="frontend-live-backend"),
        acceptance_refs=(
            AcceptanceRef(value="AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION"),
            AcceptanceRef(value="AC-TINY-FRONTEND-STARTUP"),
        ),
        service_run_refs=(backend_service_ref, frontend_service_ref),
        command_ids=(ContractId(value="run-backend"), ContractId(value="run-frontend")),
        probe_url=ServiceReadinessUrl(value=frontend_url),
        status_code=frontend_status if passed else 500,
        passed=passed,
        observed_facts={
            "frontend_url": frontend_url,
            "backend_url": backend_url,
            "fetched_paths": list(fetched_paths),
            "fetched_methods": list(fetched_methods),
            "used_fake_fetch": False,
        },
        body_sha256=hashlib.sha256(frontend_body.encode("utf-8")).hexdigest(),
        probed_at=VERIFIED_AT,
    )


def _live_verified_evidence(
    *,
    provider_fixture: TinyProviderAttemptFixture,
    live_execution_package,
    live_blackbox_evidence: LiveBlackboxIntegrationEvidence,
    service_runs: tuple[ServiceRunEvidence, ...],
    service_run_outputs: tuple[TinyServiceRunOutput, ...],
) -> tuple[VerifiedEvidence, ...]:
    verified: list[VerifiedEvidence] = []
    for obligation in provider_fixture.compiled.ticket_graph_fixture.contracts.contract_gate.evidence_obligations:
        if obligation.required_artifact_type.value in _SERVICE_RUN_EVIDENCE_TYPES:
            service_run = _service_for_obligation(obligation, service_runs)
            claim = build_evidence_claim_from_service_run(
                service_run=service_run,
                evidence_obligation=obligation,
                producer_attempt_ref=_producer_attempt_ref_for_obligation(
                    provider_fixture=provider_fixture,
                    obligation=obligation,
                ),
                acceptance_refs=obligation.acceptance_refs,
                source_surface_refs=obligation.source_surface_refs,
                expected_purpose=EvidencePurpose.IMPLEMENTATION,
                summary="Tiny service command readiness evidence.",
            )
            artifact_manifest = _service_artifact_manifest(
                service_run=service_run,
                service_run_outputs=service_run_outputs,
                producer_attempt_ref=claim.producer_attempt_ref,
            )
            result = EvidenceVerifier().verify(
                EvidenceVerificationInput(
                    claim=claim,
                    evidence_obligation=obligation,
                    active_acceptance_contract=(
                        provider_fixture.compiled.ticket_graph_fixture.contracts.acceptance_contract
                    ),
                    artifact_manifest=artifact_manifest,
                    purpose_policy=_purpose_policy(obligation),
                    provider_attempts=tuple(provider_fixture.provider_attempts_by_ticket_id.values()),
                    execution_packages=(
                        *provider_fixture.execution_packages.values(),
                        live_execution_package,
                    ),
                    role_prompt_hook_registry=baseline_role_prompt_hook_registry(),
                    service_runs=(service_run,),
                    verified_at=VERIFIED_AT,
                )
            )
        elif obligation.required_artifact_type.value in _LIVE_BLACKBOX_EVIDENCE_TYPES:
            claim = build_evidence_claim_from_live_blackbox(
                evidence=live_blackbox_evidence,
                evidence_obligation=obligation,
                producer_attempt_ref=_producer_attempt_ref_for_obligation(
                    provider_fixture=provider_fixture,
                    obligation=obligation,
                ),
                expected_purpose=EvidencePurpose.IMPLEMENTATION,
                summary="Tiny live blackbox integration evidence.",
            )
            result = EvidenceVerifier().verify(
                EvidenceVerificationInput(
                    claim=claim,
                    evidence_obligation=obligation,
                    active_acceptance_contract=(
                        provider_fixture.compiled.ticket_graph_fixture.contracts.acceptance_contract
                    ),
                    active_package_contract=(
                        provider_fixture.compiled.ticket_graph_fixture.contracts.package_contract
                    ),
                    artifact_manifest=_live_blackbox_artifact_manifest(
                        live_blackbox_evidence=live_blackbox_evidence,
                        artifact_refs=tuple(
                            artifact_ref.value for artifact_ref in claim.artifact_refs
                        ),
                        producer_attempt_ref=claim.producer_attempt_ref,
                        artifact_kind=obligation.required_artifact_type.value,
                    ),
                    purpose_policy=_purpose_policy(obligation),
                    provider_attempts=tuple(provider_fixture.provider_attempts_by_ticket_id.values()),
                    execution_packages=(
                        *provider_fixture.execution_packages.values(),
                        live_execution_package,
                    ),
                    role_prompt_hook_registry=baseline_role_prompt_hook_registry(),
                    service_runs=service_runs,
                    live_blackbox_evidence=(live_blackbox_evidence,),
                    verified_at=VERIFIED_AT,
                )
            )
        else:
            continue
        if not result.success or result.verified_evidence is None:
            raise AssertionError(f"tiny live evidence verification failed: {result.blockers}")
        verified.append(result.verified_evidence)
    return tuple(verified)


_SERVICE_RUN_EVIDENCE_TYPES = {"backend_service_run", "frontend_service_run"}
_LIVE_BLACKBOX_EVIDENCE_TYPES = {
    "backend_http_crud_evidence",
    "sqlite_persistence_http_evidence",
    "live_frontend_backend_integration_evidence",
}


def _purpose_policy(obligation: EvidenceObligation) -> EvidencePurposePolicy:
    return EvidencePurposePolicy(
        rules=(
            EvidencePurposeRule(
                required_artifact_type=obligation.required_artifact_type,
                allowed_purposes=(EvidencePurpose.IMPLEMENTATION,),
            ),
        )
    )


def _service_artifact_manifest(
    *,
    service_run: ServiceRunEvidence,
    service_run_outputs: tuple[TinyServiceRunOutput, ...],
    producer_attempt_ref,
) -> ArtifactManifest:
    output = _service_output_for_run(
        service_run=service_run,
        service_run_outputs=service_run_outputs,
    )
    return ArtifactManifest(
        entries=(
            ArtifactManifestEntry(
                artifact_ref=EvidenceArtifactRef(value=service_run.stdout_ref.value),
                sha256=_sha256(output.stdout),
                producer_attempt_ref=producer_attempt_ref,
                source_ref=service_run.service_run_evidence_id.value,
                artifact_kind="service_stdout",
            ),
            ArtifactManifestEntry(
                artifact_ref=EvidenceArtifactRef(value=service_run.stderr_ref.value),
                sha256=_sha256(output.stderr),
                producer_attempt_ref=producer_attempt_ref,
                source_ref=service_run.service_run_evidence_id.value,
                artifact_kind="service_stderr",
            ),
        )
    )


def _service_output_for_run(
    *,
    service_run: ServiceRunEvidence,
    service_run_outputs: tuple[TinyServiceRunOutput, ...],
) -> TinyServiceRunOutput:
    for output in service_run_outputs:
        if output.service_run.service_run_evidence_id == service_run.service_run_evidence_id:
            return output
    raise ValueError(
        f"missing service process output for {service_run.service_run_evidence_id.value}"
    )


def _live_blackbox_artifact_manifest(
    *,
    live_blackbox_evidence: LiveBlackboxIntegrationEvidence,
    artifact_refs: tuple[str, ...],
    producer_attempt_ref,
    artifact_kind: str,
) -> ArtifactManifest:
    return ArtifactManifest(
        entries=tuple(
            ArtifactManifestEntry(
                artifact_ref=EvidenceArtifactRef(value=artifact_ref),
                sha256=_sha256(f"{artifact_kind}:{artifact_ref}"),
                producer_attempt_ref=producer_attempt_ref,
                source_ref=live_blackbox_evidence.live_blackbox_evidence_id.value,
                artifact_kind=f"{artifact_kind}_{index}",
            )
            for index, artifact_ref in enumerate(
                artifact_refs,
                start=1,
            )
        )
    )


def _service_for_obligation(
    obligation: EvidenceObligation,
    service_runs: tuple[ServiceRunEvidence, ...],
) -> ServiceRunEvidence:
    if obligation.required_artifact_type.value == "backend_service_run":
        return _service_by_command(service_runs, "run-backend")
    return _service_by_command(service_runs, "run-frontend")


def _service_by_command(
    service_runs: tuple[ServiceRunEvidence, ...],
    command_id: str,
) -> ServiceRunEvidence:
    for service_run in service_runs:
        if service_run.command_id == ContractId(value=command_id):
            return service_run
    raise ValueError(f"missing service run evidence for {command_id}")


def _required_env_value(service_run: ServiceRunEvidence, key: str) -> str:
    try:
        return service_run.environment_overrides[key]
    except KeyError as error:
        raise ValueError(f"service run missing environment override: {key}") from error


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_json(url: str, *, method: str = "GET", payload: Mapping[str, object] | None = None) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Content-Type", "application/json")
    last_error: Exception | None = None
    for _ in range(5):
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except (http.client.RemoteDisconnected, TimeoutError, urllib.error.URLError) as error:
            last_error = error
            time.sleep(0.05)
    raise ValueError(f"HTTP JSON probe failed: {url}") from last_error


def _http_text(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=2) as response:
        return response.status, response.read().decode("utf-8")


def _validate_real_provider_fixture(
    provider_fixture: TinyProviderAttemptFixture,
    *,
    allow_test_provider_transport: bool,
) -> None:
    fake_attempt_refs = tuple(
        attempt.provider_attempt_id.value
        for attempt in provider_fixture.provider_attempts_by_ticket_id.values()
        if ".fake." in attempt.provider_attempt_id.value
    )
    if fake_attempt_refs and not allow_test_provider_transport:
        raise ValueError("test provider attempts require explicit allow_test_provider_transport")
    if not provider_fixture.provider_attempts_by_ticket_id:
        raise ValueError("ProviderAttempt records are required for tiny package assembly")


def _source_delivery_files_from_provider(
    provider_fixture: TinyProviderAttemptFixture,
    *,
    allow_test_provider_transport: bool,
) -> dict[str, str]:
    if _provider_fixture_uses_fake_attempts(provider_fixture):
        if allow_test_provider_transport:
            return {}
        raise ValueError("test provider attempts cannot deliver source files without explicit test transport")
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
    if not package_contents:
        raise ValueError("package contents are required")


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
            command_id = command_result.verification_run.command_id.value
            raise AssertionError(
                "tiny evidence verification failed for "
                f"{command_id}: {result.blockers}; "
                f"stdout={command_result.stdout!r}; stderr={command_result.stderr!r}"
            )
        verified.append(result.verified_evidence)
    return tuple(verified)


_SUPPORTED_PACKAGE_ASSEMBLY_EVIDENCE_TYPES = {
    "backend_http_api_evidence",
    "backend_source_inventory",
    "backend_service_run",
    "backend_http_crud_evidence",
    "sqlite_persistence_evidence",
    "sqlite_persistence_http_evidence",
    "frontend_source_inventory",
    "frontend_service_run",
    "live_frontend_backend_integration_evidence",
    "run_manifest",
    "test_command_evidence",
    "final_command_evidence",
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
        "final_command_evidence",
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
    allow_test_provider_transport: bool,
) -> None:
    if package_contents is not None and not allow_test_provider_transport:
        raise ValueError(
            "package source override is only allowed when test provider transport is explicit"
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
