import pytest
from pydantic import ValidationError

from boardroom_os.contracts.directive import BoardDirective, DirectiveRegistry
from boardroom_os.contracts.project import ProjectCharter, create_project_charter
from boardroom_os.contracts.types import ContractId


def test_board_directive_requires_source_type() -> None:
    with pytest.raises(ValidationError):
        BoardDirective(
            board_directive_id=ContractId(value="directive-001"),
            content_ref=ContractId(value="content-001"),
            received_at="2026-05-14T09:00:00Z",
            requester_ref=ContractId(value="human-board"),
        )


def test_board_directive_requires_content_ref() -> None:
    with pytest.raises(ValidationError):
        BoardDirective(
            board_directive_id=ContractId(value="directive-001"),
            source_type="natural_language",
            received_at="2026-05-14T09:00:00Z",
            requester_ref=ContractId(value="human-board"),
        )


def test_board_directive_requires_received_at() -> None:
    with pytest.raises(ValidationError):
        BoardDirective(
            board_directive_id=ContractId(value="directive-001"),
            source_type="natural_language",
            content_ref=ContractId(value="content-001"),
            requester_ref=ContractId(value="human-board"),
        )


def test_board_directive_requires_requester_ref() -> None:
    with pytest.raises(ValidationError):
        BoardDirective(
            board_directive_id=ContractId(value="directive-001"),
            source_type="natural_language",
            content_ref=ContractId(value="content-001"),
            received_at="2026-05-14T09:00:00Z",
        )


def test_board_directive_rejects_unknown_source_type() -> None:
    with pytest.raises(ValidationError):
        BoardDirective(
            board_directive_id=ContractId(value="directive-001"),
            source_type="chat_message",
            content_ref=ContractId(value="content-001"),
            received_at="2026-05-14T09:00:00Z",
            requester_ref=ContractId(value="human-board"),
        )


def test_project_charter_rejects_missing_board_directive_ref() -> None:
    with pytest.raises(ValidationError):
        ProjectCharter(
            project_charter_id=ContractId(value="charter-001"),
            project_goal="Generate a tiny book availability tracker.",
            delivery_type="generated_project_package",
            non_goals=("Do not migrate legacy runtime.",),
            constraints=("Contract first.",),
            risks=("Evidence gaps block closeout.",),
            success_summary="A runnable and auditable generated project package.",
        )


def test_board_directive_rejects_naive_received_at() -> None:
    with pytest.raises(ValidationError):
        BoardDirective(
            board_directive_id=ContractId(value="directive-001"),
            source_type="natural_language",
            content_ref=ContractId(value="content-001"),
            received_at="2026-05-14T09:00:00",
            requester_ref=ContractId(value="human-board"),
        )


def test_board_directive_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        BoardDirective(
            board_directive_id=ContractId(value="directive-001"),
            source_type="natural_language",
            content_ref=ContractId(value="content-001"),
            received_at="2026-05-14T09:00:00Z",
            requester_ref=ContractId(value="human-board"),
            synthetic_success=True,
        )


def test_project_charter_direct_constructor_requires_registry_validation() -> None:
    with pytest.raises(ValidationError, match="board directive registry is required"):
        ProjectCharter(
            project_charter_id=ContractId(value="charter-001"),
            board_directive_ref=ContractId(value="directive-001"),
            project_goal="Generate a tiny book availability tracker.",
            delivery_type="generated_project_package",
            non_goals=("Do not migrate legacy runtime.",),
            constraints=("Contract first.",),
            risks=("Evidence gaps block closeout.",),
            success_summary="A runnable and auditable generated project package.",
        )


def test_project_charter_rejects_unknown_board_directive_ref() -> None:
    registry = DirectiveRegistry(directives=())

    with pytest.raises(ValidationError, match="board directive ref must exist"):
        create_project_charter(
            registry=registry,
            project_charter_id=ContractId(value="charter-001"),
            board_directive_ref=ContractId(value="directive-missing"),
            project_goal="Generate a tiny book availability tracker.",
            delivery_type="generated_project_package",
            non_goals=("Do not migrate legacy runtime.",),
            constraints=("Contract first.",),
            risks=("Evidence gaps block closeout.",),
            success_summary="A runnable and auditable generated project package.",
        )


def test_project_charter_rejects_unknown_fields() -> None:
    directive = BoardDirective(
        board_directive_id=ContractId(value="directive-001"),
        source_type="natural_language",
        content_ref=ContractId(value="content-001"),
        received_at="2026-05-14T09:00:00Z",
        requester_ref=ContractId(value="human-board"),
    )
    registry = DirectiveRegistry.from_directives(directive)

    with pytest.raises(ValidationError):
        create_project_charter(
            registry=registry,
            project_charter_id=ContractId(value="charter-001"),
            board_directive_ref=ContractId(value="directive-001"),
            project_goal="Generate a tiny book availability tracker.",
            delivery_type="generated_project_package",
            non_goals=("Do not migrate legacy runtime.",),
            constraints=("Contract first.",),
            risks=("Evidence gaps block closeout.",),
            success_summary="A runnable and auditable generated project package.",
            synthetic_success=True,
        )
