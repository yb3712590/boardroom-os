from app.core.execution_targets import infer_execution_contract_payload


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
