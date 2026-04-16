from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.contracts.commands import RuntimeProviderCapabilityTag
from app.core.output_schemas import (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
    DETAILED_DESIGN_SCHEMA_REF,
    CONSENSUS_DOCUMENT_SCHEMA_REF,
    DELIVERY_CHECK_REPORT_SCHEMA_REF,
    DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
    GOVERNANCE_DOCUMENT_SCHEMA_REFS,
    GRAPH_PATCH_PROPOSAL_SCHEMA_REF,
    MAKER_CHECKER_VERDICT_SCHEMA_REF,
    MILESTONE_PLAN_SCHEMA_REF,
    SOURCE_CODE_DELIVERY_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
    UI_MILESTONE_REVIEW_SCHEMA_REF,
)

EXECUTION_CONTRACT_VERSION = "execution_contract_v1"

EXECUTION_TARGET_SCOPE_CONSENSUS = "execution_target:scope_consensus"
EXECUTION_TARGET_SCOPE_GOVERNANCE_DOCUMENT = "execution_target:scope_governance_document"
EXECUTION_TARGET_FRONTEND_BUILD = "execution_target:frontend_build"
EXECUTION_TARGET_BACKEND_BUILD = "execution_target:backend_build"
EXECUTION_TARGET_DATABASE_BUILD = "execution_target:database_build"
EXECUTION_TARGET_PLATFORM_BUILD = "execution_target:platform_build"
EXECUTION_TARGET_FRONTEND_GOVERNANCE_DOCUMENT = "execution_target:frontend_governance_document"
EXECUTION_TARGET_ARCHITECT_GOVERNANCE_DOCUMENT = "execution_target:architect_governance_document"
EXECUTION_TARGET_CTO_GOVERNANCE_DOCUMENT = "execution_target:cto_governance_document"
EXECUTION_TARGET_BOARD_ADVISORY_ANALYSIS = "execution_target:board_advisory_analysis"
EXECUTION_TARGET_CHECKER_DELIVERY_CHECK = "execution_target:checker_delivery_check"
EXECUTION_TARGET_CHECKER_MAKER_CHECKER = "execution_target:checker_maker_checker"
EXECUTION_TARGET_FRONTEND_REVIEW = "execution_target:frontend_review"
EXECUTION_TARGET_FRONTEND_CLOSEOUT = "execution_target:frontend_closeout"

_ARCHITECT_GOVERNANCE_DOCUMENT_SCHEMA_REFS = (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
    DETAILED_DESIGN_SCHEMA_REF,
)
_CTO_GOVERNANCE_DOCUMENT_SCHEMA_REFS = (
    ARCHITECTURE_BRIEF_SCHEMA_REF,
    TECHNOLOGY_DECISION_SCHEMA_REF,
    MILESTONE_PLAN_SCHEMA_REF,
    BACKLOG_RECOMMENDATION_SCHEMA_REF,
)


@dataclass(frozen=True)
class ExecutionTargetDefinition:
    execution_target_ref: str
    role_profile_ref: str | None
    output_schema_ref: str
    required_capability_tags: tuple[RuntimeProviderCapabilityTag, ...]
    label: str


EXECUTION_TARGET_DEFINITIONS = (
    ExecutionTargetDefinition(
        execution_target_ref=EXECUTION_TARGET_SCOPE_CONSENSUS,
        role_profile_ref="ui_designer_primary",
        output_schema_ref=CONSENSUS_DOCUMENT_SCHEMA_REF,
        required_capability_tags=(
            RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
            RuntimeProviderCapabilityTag.PLANNING,
        ),
        label="Scope Consensus",
    ),
    *(
        ExecutionTargetDefinition(
            execution_target_ref=EXECUTION_TARGET_SCOPE_GOVERNANCE_DOCUMENT,
            role_profile_ref="ui_designer_primary",
            output_schema_ref=output_schema_ref,
            required_capability_tags=(
                RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
                RuntimeProviderCapabilityTag.PLANNING,
            ),
            label="Scope Governance Document",
        )
        for output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS
    ),
    *(
        ExecutionTargetDefinition(
            execution_target_ref=EXECUTION_TARGET_FRONTEND_GOVERNANCE_DOCUMENT,
            role_profile_ref="frontend_engineer_primary",
            output_schema_ref=output_schema_ref,
            required_capability_tags=(
                RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
                RuntimeProviderCapabilityTag.PLANNING,
            ),
            label="Frontend Governance Document",
        )
        for output_schema_ref in GOVERNANCE_DOCUMENT_SCHEMA_REFS
    ),
    *(
        ExecutionTargetDefinition(
            execution_target_ref=EXECUTION_TARGET_ARCHITECT_GOVERNANCE_DOCUMENT,
            role_profile_ref="architect_primary",
            output_schema_ref=output_schema_ref,
            required_capability_tags=(
                RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
                RuntimeProviderCapabilityTag.PLANNING,
            ),
            label="Architect Governance Document",
        )
        for output_schema_ref in _ARCHITECT_GOVERNANCE_DOCUMENT_SCHEMA_REFS
    ),
    *(
        ExecutionTargetDefinition(
            execution_target_ref=EXECUTION_TARGET_CTO_GOVERNANCE_DOCUMENT,
            role_profile_ref="cto_primary",
            output_schema_ref=output_schema_ref,
            required_capability_tags=(
                RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
                RuntimeProviderCapabilityTag.PLANNING,
            ),
            label="CTO Governance Document",
        )
        for output_schema_ref in _CTO_GOVERNANCE_DOCUMENT_SCHEMA_REFS
    ),
    ExecutionTargetDefinition(
        execution_target_ref=EXECUTION_TARGET_BOARD_ADVISORY_ANALYSIS,
        role_profile_ref=None,
        output_schema_ref=GRAPH_PATCH_PROPOSAL_SCHEMA_REF,
        required_capability_tags=(
            RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
            RuntimeProviderCapabilityTag.PLANNING,
        ),
        label="Board Advisory Analysis",
    ),
    ExecutionTargetDefinition(
        execution_target_ref=EXECUTION_TARGET_FRONTEND_BUILD,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        required_capability_tags=(
            RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
            RuntimeProviderCapabilityTag.IMPLEMENTATION,
        ),
        label="Frontend Build",
    ),
    ExecutionTargetDefinition(
        execution_target_ref=EXECUTION_TARGET_BACKEND_BUILD,
        role_profile_ref="backend_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        required_capability_tags=(
            RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
            RuntimeProviderCapabilityTag.IMPLEMENTATION,
        ),
        label="Backend Build",
    ),
    ExecutionTargetDefinition(
        execution_target_ref=EXECUTION_TARGET_DATABASE_BUILD,
        role_profile_ref="database_engineer_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        required_capability_tags=(
            RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
            RuntimeProviderCapabilityTag.IMPLEMENTATION,
        ),
        label="Database Build",
    ),
    ExecutionTargetDefinition(
        execution_target_ref=EXECUTION_TARGET_PLATFORM_BUILD,
        role_profile_ref="platform_sre_primary",
        output_schema_ref=SOURCE_CODE_DELIVERY_SCHEMA_REF,
        required_capability_tags=(
            RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
            RuntimeProviderCapabilityTag.IMPLEMENTATION,
        ),
        label="Platform Build",
    ),
    ExecutionTargetDefinition(
        execution_target_ref=EXECUTION_TARGET_CHECKER_DELIVERY_CHECK,
        role_profile_ref="checker_primary",
        output_schema_ref=DELIVERY_CHECK_REPORT_SCHEMA_REF,
        required_capability_tags=(
            RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
            RuntimeProviderCapabilityTag.REVIEW,
        ),
        label="Checker Delivery Check",
    ),
    ExecutionTargetDefinition(
        execution_target_ref=EXECUTION_TARGET_CHECKER_MAKER_CHECKER,
        role_profile_ref="checker_primary",
        output_schema_ref=MAKER_CHECKER_VERDICT_SCHEMA_REF,
        required_capability_tags=(
            RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
            RuntimeProviderCapabilityTag.REVIEW,
        ),
        label="Checker Maker-Checker Verdict",
    ),
    ExecutionTargetDefinition(
        execution_target_ref=EXECUTION_TARGET_FRONTEND_REVIEW,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=UI_MILESTONE_REVIEW_SCHEMA_REF,
        required_capability_tags=(
            RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
            RuntimeProviderCapabilityTag.IMPLEMENTATION,
        ),
        label="Frontend Review",
    ),
    ExecutionTargetDefinition(
        execution_target_ref=EXECUTION_TARGET_FRONTEND_CLOSEOUT,
        role_profile_ref="frontend_engineer_primary",
        output_schema_ref=DELIVERY_CLOSEOUT_PACKAGE_SCHEMA_REF,
        required_capability_tags=(
            RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
            RuntimeProviderCapabilityTag.IMPLEMENTATION,
        ),
        label="Frontend Closeout",
    ),
)

_EXECUTION_TARGET_BY_COMBO = {
    (definition.role_profile_ref, definition.output_schema_ref): definition
    for definition in EXECUTION_TARGET_DEFINITIONS
    if definition.role_profile_ref is not None
}
_EXECUTION_TARGET_BY_REF = {
    definition.execution_target_ref: definition for definition in EXECUTION_TARGET_DEFINITIONS
}
_ROLE_PROFILE_CAPABILITY_TAGS = {
    "ui_designer_primary": (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.PLANNING,
    ),
    "frontend_engineer_primary": (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.PLANNING,
        RuntimeProviderCapabilityTag.IMPLEMENTATION,
    ),
    "checker_primary": (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.REVIEW,
    ),
    "backend_engineer_primary": (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.IMPLEMENTATION,
    ),
    "database_engineer_primary": (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.IMPLEMENTATION,
    ),
    "platform_sre_primary": (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.IMPLEMENTATION,
    ),
    "architect_primary": (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.PLANNING,
    ),
    "cto_primary": (
        RuntimeProviderCapabilityTag.STRUCTURED_OUTPUT,
        RuntimeProviderCapabilityTag.PLANNING,
    ),
}


def get_execution_target_definition(
    *,
    role_profile_ref: str | None,
    output_schema_ref: str | None,
) -> ExecutionTargetDefinition | None:
    normalized_role_profile_ref = str(role_profile_ref or "").strip()
    normalized_output_schema_ref = str(output_schema_ref or "").strip()
    if not normalized_role_profile_ref or not normalized_output_schema_ref:
        return None
    return _EXECUTION_TARGET_BY_COMBO.get((normalized_role_profile_ref, normalized_output_schema_ref))


def get_execution_target_definition_by_ref(execution_target_ref: str | None) -> ExecutionTargetDefinition | None:
    normalized_execution_target_ref = str(execution_target_ref or "").strip()
    if not normalized_execution_target_ref:
        return None
    return _EXECUTION_TARGET_BY_REF.get(normalized_execution_target_ref)


def infer_execution_contract_payload(
    *,
    role_profile_ref: str | None,
    output_schema_ref: str | None,
) -> dict[str, Any] | None:
    definition = get_execution_target_definition(
        role_profile_ref=role_profile_ref,
        output_schema_ref=output_schema_ref,
    )
    if definition is None:
        return None
    return {
        "execution_target_ref": definition.execution_target_ref,
        "required_capability_tags": [tag.value for tag in definition.required_capability_tags],
        "runtime_contract_version": EXECUTION_CONTRACT_VERSION,
    }


def build_execution_contract_payload_for_target(execution_target_ref: str | None) -> dict[str, Any] | None:
    definition = get_execution_target_definition_by_ref(execution_target_ref)
    if definition is None:
        return None
    return {
        "execution_target_ref": definition.execution_target_ref,
        "required_capability_tags": [tag.value for tag in definition.required_capability_tags],
        "runtime_contract_version": EXECUTION_CONTRACT_VERSION,
    }


def resolve_execution_target_ref_from_ticket_spec(created_spec: dict[str, Any] | None) -> str | None:
    if not isinstance(created_spec, dict):
        return None
    execution_contract = created_spec.get("execution_contract")
    if isinstance(execution_contract, dict):
        execution_target_ref = str(execution_contract.get("execution_target_ref") or "").strip()
        if execution_target_ref:
            return execution_target_ref

    inferred_execution_contract = infer_execution_contract_payload(
        role_profile_ref=created_spec.get("role_profile_ref"),
        output_schema_ref=created_spec.get("output_schema_ref"),
    )
    if inferred_execution_contract is not None:
        return str(inferred_execution_contract["execution_target_ref"])

    role_profile_ref = str(created_spec.get("role_profile_ref") or "").strip()
    if role_profile_ref:
        return f"role_profile:{role_profile_ref}"
    return None


def legacy_target_refs_for_execution_target(execution_target_ref: str | None) -> tuple[str, ...]:
    definition = get_execution_target_definition_by_ref(execution_target_ref)
    if definition is None or definition.role_profile_ref is None:
        return ()
    return (f"role_profile:{definition.role_profile_ref}",)


def execution_target_capability_tag_values(execution_target_ref: str | None) -> set[str]:
    definition = get_execution_target_definition_by_ref(execution_target_ref)
    if definition is None:
        return set()
    return {tag.value for tag in definition.required_capability_tags}


def employee_capability_tag_values(employee: dict[str, Any] | None) -> set[str]:
    if not isinstance(employee, dict):
        return set()

    tag_values: set[str] = set()
    for role_profile_ref in employee.get("role_profile_refs") or []:
        for capability_tag in _ROLE_PROFILE_CAPABILITY_TAGS.get(str(role_profile_ref), ()):
            tag_values.add(capability_tag.value)
    return tag_values


def role_profile_capability_tag_values(role_profile_ref: str | None) -> set[str]:
    return {
        tag.value
        for tag in _ROLE_PROFILE_CAPABILITY_TAGS.get(str(role_profile_ref or "").strip(), ())
    }


def pick_employee_role_profile_for_execution_contract(
    *,
    employee: dict[str, Any] | None,
    execution_contract: dict[str, Any] | None,
) -> str | None:
    if not isinstance(employee, dict):
        return None
    required_tag_values = {
        str(tag.value if hasattr(tag, "value") else tag)
        for tag in (execution_contract or {}).get("required_capability_tags") or []
    }
    if not required_tag_values:
        required_tag_values = execution_target_capability_tag_values(
            (execution_contract or {}).get("execution_target_ref")
        )
    role_profile_refs = [
        str(role_profile_ref).strip()
        for role_profile_ref in employee.get("role_profile_refs") or []
        if str(role_profile_ref).strip()
    ]
    for role_profile_ref in role_profile_refs:
        if required_tag_values.issubset(role_profile_capability_tag_values(role_profile_ref)):
            return role_profile_ref
    return role_profile_refs[0] if role_profile_refs else None


def employee_supports_execution_contract(
    *,
    employee: dict[str, Any] | None,
    execution_contract: dict[str, Any] | None,
) -> bool:
    if not isinstance(execution_contract, dict):
        return False

    required_tag_values = {
        str(tag.value if hasattr(tag, "value") else tag)
        for tag in execution_contract.get("required_capability_tags") or []
    }
    if not required_tag_values:
        required_tag_values = execution_target_capability_tag_values(execution_contract.get("execution_target_ref"))
    if not required_tag_values:
        return False
    return required_tag_values.issubset(employee_capability_tag_values(employee))
