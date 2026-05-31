from __future__ import annotations

from boardroom_os.agents.role_prompt_hooks import (
    RolePromptHook,
    RolePromptHookRegistry,
    RolePromptHookRef,
    build_baseline_role_prompt_hook_registry,
)
from boardroom_os.agents.categories import RoleCategory


_HOOK_REF_BY_CATEGORY = {
    RoleCategory.GOVERNANCE: "role-prompt-hook.baseline.ceo.v1",
    RoleCategory.ARCHITECTURE: "role-prompt-hook.baseline.architect.v1",
    RoleCategory.IMPLEMENTATION: "role-prompt-hook.baseline.worker.v1",
    RoleCategory.VERIFICATION: "role-prompt-hook.baseline.tester.v1",
    RoleCategory.AUDIT: "role-prompt-hook.baseline.checker.v1",
    RoleCategory.INTEGRATION: "role-prompt-hook.baseline.tester.v1",
}


def baseline_role_prompt_hook_registry() -> RolePromptHookRegistry:
    return build_baseline_role_prompt_hook_registry()


def baseline_role_prompt_hook(
    hook_ref: str = "role-prompt-hook.baseline.worker.v1",
) -> RolePromptHook:
    return baseline_role_prompt_hook_registry().require(RolePromptHookRef(value=hook_ref))


def baseline_role_prompt_hook_fields(
    hook_ref: str = "role-prompt-hook.baseline.worker.v1",
) -> dict[str, object]:
    hook = baseline_role_prompt_hook(hook_ref)
    return {
        "role_prompt_hook_ref": hook.hook_ref,
        "role_prompt_hook_version": hook.hook_version,
        "role_prompt_hook_sha256": hook.content_sha256,
    }


def baseline_role_prompt_hook_fields_for_category(
    role_category: RoleCategory | str,
) -> dict[str, object]:
    resolved_category = (
        role_category
        if isinstance(role_category, RoleCategory)
        else RoleCategory(role_category)
    )
    return baseline_role_prompt_hook_fields(_HOOK_REF_BY_CATEGORY[resolved_category])
