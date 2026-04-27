from typing import Any, Iterable, Mapping

from app.core.constants import EMPLOYEE_STATE_ACTIVE

ROLE_ALREADY_COVERED_REASON_CODE = "ROLE_ALREADY_COVERED"


def normalize_role_profile_refs(role_profile_refs: Iterable[Any]) -> list[str]:
    return sorted({str(item).strip() for item in role_profile_refs if str(item).strip()})


def find_reuse_candidate_employee(
    *,
    role_type: str,
    role_profile_refs: Iterable[Any],
    employees: Iterable[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    normalized_role_type = str(role_type or "").strip()
    required_role_profile_refs = set(normalize_role_profile_refs(role_profile_refs))
    if not normalized_role_type or not required_role_profile_refs:
        return None

    candidates: list[Mapping[str, Any]] = []
    for employee in employees:
        employee_id = str(employee.get("employee_id") or "").strip()
        if not employee_id:
            continue
        if str(employee.get("state") or "").strip().upper() != EMPLOYEE_STATE_ACTIVE:
            continue
        if not bool(employee.get("board_approved")):
            continue
        if str(employee.get("role_type") or "").strip() != normalized_role_type:
            continue
        employee_role_profile_refs = {
            str(item).strip()
            for item in list(employee.get("role_profile_refs") or [])
            if str(item).strip()
        }
        if not required_role_profile_refs.issubset(employee_role_profile_refs):
            continue
        candidates.append(employee)

    if not candidates:
        return None
    return sorted(candidates, key=lambda item: str(item.get("employee_id") or ""))[0]


def build_role_already_covered_details(
    *,
    role_type: str,
    role_profile_refs: Iterable[Any],
    reuse_candidate_employee_id: str,
) -> dict[str, Any]:
    return {
        "reason_code": ROLE_ALREADY_COVERED_REASON_CODE,
        "reuse_candidate_employee_id": str(reuse_candidate_employee_id),
        "role_type": str(role_type),
        "role_profile_refs": normalize_role_profile_refs(role_profile_refs),
    }

