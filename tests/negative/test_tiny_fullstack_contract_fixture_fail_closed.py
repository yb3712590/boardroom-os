import pytest

from tests.fixtures.contracts.tiny_fullstack_contract import (
    TINY_FULLSTACK_AC_V2_BINDINGS,
    build_tiny_fullstack_contract_fixture,
    validate_tiny_fullstack_ac_v2_bindings,
)


def test_tiny_fullstack_fixture_requires_every_acceptance_ref_to_bind_ac_v2() -> None:
    fixture = build_tiny_fullstack_contract_fixture()
    incomplete_bindings = dict(TINY_FULLSTACK_AC_V2_BINDINGS)
    incomplete_bindings.pop("AC-TINY-API-BOOK-CREATE")

    with pytest.raises(ValueError, match="AC-V2 binding is required"):
        validate_tiny_fullstack_ac_v2_bindings(
            acceptance_contract=fixture.acceptance_contract,
            ac_v2_bindings=incomplete_bindings,
        )


def test_tiny_fullstack_fixture_rejects_unknown_ac_v2_binding() -> None:
    fixture = build_tiny_fullstack_contract_fixture()
    bindings = {
        **TINY_FULLSTACK_AC_V2_BINDINGS,
        "AC-TINY-API-BOOK-CREATE": ("AC-V2-UNKNOWN-999",),
    }

    with pytest.raises(ValueError, match="unknown AC-V2 binding"):
        validate_tiny_fullstack_ac_v2_bindings(
            acceptance_contract=fixture.acceptance_contract,
            ac_v2_bindings=bindings,
        )


def test_tiny_fullstack_fixture_rejects_fallback_as_implementation_evidence() -> None:
    fixture = build_tiny_fullstack_contract_fixture()
    bindings = {
        **TINY_FULLSTACK_AC_V2_BINDINGS,
        "AC-TINY-EVIDENCE-NO-FALLBACK": ("AC-V2-EXECUTION-003",),
    }

    with pytest.raises(ValueError, match="fallback cannot satisfy implementation evidence"):
        validate_tiny_fullstack_ac_v2_bindings(
            acceptance_contract=fixture.acceptance_contract,
            ac_v2_bindings=bindings,
        )
