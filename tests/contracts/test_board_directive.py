import pytest

from boardroom_os.contracts.directive import BoardDirective, DirectiveRegistry
from boardroom_os.contracts.project import ProjectCharter, create_project_charter
from boardroom_os.contracts.types import ContractId


def test_contract_package_exports_board_directive_entrypoint() -> None:
    from boardroom_os.contracts import (
        BoardDirective,
        BoardDirectiveSourceType,
        DeliveryType,
        DirectiveRegistry,
        ProjectCharter,
        create_project_charter,
    )

    assert BoardDirective.__name__ == "BoardDirective"
    assert BoardDirectiveSourceType.NATURAL_LANGUAGE == "natural_language"
    assert DeliveryType.GENERATED_PROJECT_PACKAGE == "generated_project_package"
    assert DirectiveRegistry.__name__ == "DirectiveRegistry"
    assert ProjectCharter.__name__ == "ProjectCharter"
    assert create_project_charter.__name__ == "create_project_charter"


@pytest.mark.parametrize(
    ("source_type", "content_ref"),
    [
        ("natural_language", "content-natural-language"),
        ("prd_file", "doc/01-product/prd.md"),
        ("human_review_update", "review-note-001"),
    ],
)
def test_board_directive_source_serializes_and_can_be_referenced_by_project_charter(
    source_type: str,
    content_ref: str,
) -> None:
    directive = BoardDirective(
        board_directive_id=ContractId(value=f"directive-{source_type}"),
        source_type=source_type,
        content_ref=ContractId(value=content_ref),
        received_at="2026-05-14T09:00:00Z",
        requester_ref=ContractId(value="human-board"),
    )
    registry = DirectiveRegistry.from_directives(directive)

    charter = create_project_charter(
        registry=registry,
        project_charter_id=ContractId(value=f"charter-{source_type}"),
        board_directive_ref=ContractId(value=f"directive-{source_type}"),
        project_goal="Generate a tiny book availability tracker.",
        delivery_type="generated_project_package",
        non_goals=("Do not migrate legacy runtime.",),
        constraints=("Contract first.", "Evidence first."),
        risks=("Evidence gaps block closeout.",),
        success_summary="A runnable and auditable generated project package.",
    )

    assert directive.model_dump() == {
        "board_directive_id": {"value": f"directive-{source_type}"},
        "source_type": source_type,
        "content_ref": {"value": content_ref},
        "received_at": "2026-05-14T09:00:00Z",
        "requester_ref": {"value": "human-board"},
    }
    assert isinstance(charter, ProjectCharter)
    assert charter.project_charter_id.value == f"charter-{source_type}"
    assert charter.board_directive_ref.value == f"directive-{source_type}"
    assert charter.delivery_type == "generated_project_package"
    assert charter.non_goals == ("Do not migrate legacy runtime.",)
    assert charter.constraints == ("Contract first.", "Evidence first.")
    assert charter.risks == ("Evidence gaps block closeout.",)
    assert charter.success_summary == "A runnable and auditable generated project package."
