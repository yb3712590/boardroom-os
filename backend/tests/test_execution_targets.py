from app.core.execution_targets import (
    build_role_template_capability_contract,
    infer_execution_contract_payload,
)


def test_infer_execution_contract_payload_supports_new_runtime_live_roles() -> None:
    assert infer_execution_contract_payload(
        role_profile_ref="backend_engineer_primary",
        output_schema_ref="source_code_delivery",
    ) == {
        "execution_target_ref": "execution_target:backend_build",
        "required_capability_tags": ["structured_output", "implementation"],
        "runtime_contract_version": "execution_contract_v1",
    }
    assert infer_execution_contract_payload(
        role_profile_ref="database_engineer_primary",
        output_schema_ref="source_code_delivery",
    ) == {
        "execution_target_ref": "execution_target:database_build",
        "required_capability_tags": ["structured_output", "implementation"],
        "runtime_contract_version": "execution_contract_v1",
    }
    assert infer_execution_contract_payload(
        role_profile_ref="platform_sre_primary",
        output_schema_ref="source_code_delivery",
    ) == {
        "execution_target_ref": "execution_target:platform_build",
        "required_capability_tags": ["structured_output", "implementation"],
        "runtime_contract_version": "execution_contract_v1",
    }


def test_role_template_capability_contract_does_not_emit_runtime_execution_key() -> None:
    contract = build_role_template_capability_contract("backend_engineer_primary")

    assert contract == {
        "role_template_ref": "backend_engineer_primary",
        "capability_set": [
            "source.modify.backend",
            "test.run.backend",
            "evidence.write.test",
            "evidence.write.git",
            "docs.update.delivery",
        ],
        "provider_preferences": {"purpose": "implementation"},
    }
    assert "execution_target_ref" not in contract
    assert "runtime_execution_key" not in contract
