import pytest
from pydantic import ValidationError

from boardroom_os.contracts.types import (
    AcceptanceRef,
    AcceptanceRefSet,
    ContractId,
    ContractStatus,
)


def test_contract_id_rejects_empty_value() -> None:
    with pytest.raises(ValidationError):
        ContractId(value="")


def test_acceptance_ref_set_rejects_empty_refs() -> None:
    with pytest.raises(ValidationError):
        AcceptanceRefSet(refs=[])


def test_contract_value_objects_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AcceptanceRef.model_validate(
            {"value": "AC-V2-CONTRACT-001", "unknown": "must-fail"}
        )


def test_contract_status_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        ContractStatus(value="unknown")


def test_contract_value_objects_serialize_valid_values() -> None:
    contract_id = ContractId(value="contract-001")
    acceptance_refs = AcceptanceRefSet(
        refs=[AcceptanceRef(value="AC-V2-CONTRACT-001")]
    )
    status = ContractStatus(value="active")

    assert contract_id.model_dump() == {"value": "contract-001"}
    assert acceptance_refs.as_tuple() == ("AC-V2-CONTRACT-001",)
    assert acceptance_refs.model_dump() == {
        "refs": [{"value": "AC-V2-CONTRACT-001"}]
    }
    assert status.value == "active"
