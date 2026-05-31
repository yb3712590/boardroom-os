from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from boardroom_os.agents.categories import RoleCategory
from boardroom_os.agents.skills import _LayeredAgentValue, _normalize_ref_fields


class RolePromptHookRef(_LayeredAgentValue):
    pass


class RolePromptPolicyRef(_LayeredAgentValue):
    pass


class RolePromptHookSha256(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str

    @classmethod
    def from_text(cls, text: str) -> Self:
        return cls(value=hashlib.sha256(text.encode("utf-8")).hexdigest())

    @field_validator("value")
    @classmethod
    def _require_lowercase_sha256(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
            raise ValueError("content_sha256 must be a 64-character lowercase sha256")
        return normalized


class RolePromptHook(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    hook_ref: RolePromptHookRef
    role_kind: str
    role_category: RoleCategory
    hook_version: str
    template_path: str
    content_sha256: RolePromptHookSha256
    prompt_text: str
    policy_refs: tuple[RolePromptPolicyRef, ...]
    required_responsibilities: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _normalize_refs(cls, data: Any) -> Any:
        return _normalize_ref_fields(
            data,
            {
                "hook_ref": RolePromptHookRef,
                "content_sha256": RolePromptHookSha256,
            },
            {
                "policy_refs": RolePromptPolicyRef,
            },
        )

    @field_validator("role_kind", "hook_version", "template_path")
    @classmethod
    def _reject_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("prompt_text")
    @classmethod
    def _reject_empty_prompt_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt_text must not be empty")
        return value

    @field_validator("policy_refs")
    @classmethod
    def _reject_empty_policy_refs(
        cls,
        values: tuple[RolePromptPolicyRef, ...],
    ) -> tuple[RolePromptPolicyRef, ...]:
        if not values:
            raise ValueError("policy_refs must not be empty")
        return values

    @field_validator("required_responsibilities")
    @classmethod
    def _reject_empty_responsibilities(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("required_responsibilities must not be empty")
        normalized_values = tuple(value.strip() for value in values)
        if any(not value for value in normalized_values):
            raise ValueError("required_responsibilities must not contain empty values")
        return normalized_values

    @model_validator(mode="after")
    def _validate_content_hash(self) -> Self:
        expected_sha256 = RolePromptHookSha256.from_text(self.prompt_text)
        if self.content_sha256 != expected_sha256:
            raise ValueError("content_sha256 does not match prompt_text")
        return self


_ROLE_KIND_CATEGORY: dict[str, RoleCategory] = {
    "ceo": RoleCategory.GOVERNANCE,
    "architect": RoleCategory.ARCHITECTURE,
    "worker": RoleCategory.IMPLEMENTATION,
    "tester": RoleCategory.VERIFICATION,
    "checker": RoleCategory.AUDIT,
    "closeout": RoleCategory.AUDIT,
}

_ROLE_REQUIRED_RESPONSIBILITY_TERMS: dict[str, tuple[tuple[str, ...], ...]] = {
    "ceo": (
        ("goal",),
        ("scope",),
        ("non-goal",),
        ("dynamic acceptance",),
    ),
    "architect": (
        ("contract",),
        ("run command", "service boundary"),
        ("test command",),
        ("integration boundary",),
        ("evidence obligation",),
    ),
    "worker": (
        ("allowed write set",),
        ("fallback", "implementation evidence"),
    ),
    "tester": (
        ("negative tests first",),
        ("blackbox service probe",),
        ("live integration",),
    ),
    "checker": (
        ("evidence gap", "blocker"),
        ("notes", "blocker"),
    ),
    "closeout": (
        ("workflow completed", "CloseoutPackage"),
        ("CLOSEOUT_COMMITTED",),
    ),
}

_BYPASS_TARGETS = (
    "AcceptanceContract",
    "PackageContract",
    "Reducer",
    "reducer",
    "EvidenceVerifier",
    "CloseoutGate",
)


class RolePromptHookRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    hooks: tuple[RolePromptHook, ...]

    @classmethod
    def from_hooks(cls, *hooks: RolePromptHook) -> Self:
        return cls(hooks=hooks)

    @model_validator(mode="after")
    def _validate_hooks(self) -> Self:
        if not self.hooks:
            raise ValueError("hooks must not be empty")
        seen: set[RolePromptHookRef] = set()
        for hook in self.hooks:
            if hook.hook_ref in seen:
                raise ValueError("hook_ref values must be unique")
            seen.add(hook.hook_ref)
            self._validate_hook_governance(hook)
        return self

    def require(self, hook_ref: RolePromptHookRef) -> RolePromptHook:
        for hook in self.hooks:
            if hook.hook_ref == hook_ref:
                return hook
        raise ValueError(f"unknown role_prompt_hook_ref: {hook_ref.value}")

    def contains(self, hook_ref: RolePromptHookRef) -> bool:
        return any(hook.hook_ref == hook_ref for hook in self.hooks)

    @classmethod
    def _validate_hook_governance(cls, hook: RolePromptHook) -> None:
        expected_category = _ROLE_KIND_CATEGORY.get(hook.role_kind)
        if expected_category is None:
            raise ValueError(f"unknown role_kind: {hook.role_kind}")
        if hook.role_category is not expected_category:
            raise ValueError("role prompt hook category mismatch")
        cls._reject_bypass_claims(hook)
        cls._require_role_responsibilities(hook)

    @staticmethod
    def _reject_bypass_claims(hook: RolePromptHook) -> None:
        normalized_text = hook.prompt_text.lower()
        governance_gate_pattern = "|".join(
            rf"\b{re.escape(target.lower())}\b" if target.lower() == "reducer" else re.escape(target.lower())
            for target in _BYPASS_TARGETS
        )
        unsafe_patterns = (
            rf"\b(?:bypasses?|supersedes?|replaces?)\s+(?:the\s+)?(?:{governance_gate_pattern})\b",
            rf"\b(?:{governance_gate_pattern})\s+(?:is|are)\s+(?:bypassed|superseded|replaced)\b",
        )
        if any(
            re.search(pattern, normalized_text)
            for pattern in unsafe_patterns
        ):
            raise ValueError(
                "role prompt hook must not claim to bypass programmed governance gates"
            )

    @staticmethod
    def _require_role_responsibilities(hook: RolePromptHook) -> None:
        required_term_groups = _ROLE_REQUIRED_RESPONSIBILITY_TERMS[hook.role_kind]
        responsibilities = tuple(
            responsibility.lower()
            for responsibility in hook.required_responsibilities
        )
        missing_groups: list[str] = []
        for term_group in required_term_groups:
            if not any(all(term.lower() in responsibility for term in term_group) for responsibility in responsibilities):
                missing_groups.append(" and ".join(term_group))
        if missing_groups:
            raise ValueError(
                "role prompt hook missing required responsibilities: "
                + ", ".join(missing_groups)
            )


_AGENTS_PACKAGE_DIR = Path(__file__).parent
_SOURCE_ROOT = _AGENTS_PACKAGE_DIR.parents[1]
_BASELINE_TEMPLATE_DIR = _AGENTS_PACKAGE_DIR / "prompt_templates" / "baseline" / "v1"
_BASELINE_HOOK_SPECS = (
    (
        "ceo",
        "role-prompt-hook.baseline.ceo.v1",
        RoleCategory.GOVERNANCE,
        "ceo.md",
        (
            "Define project goal from current directive.",
            "Maintain scope boundaries.",
            "Record non-goals explicitly.",
            "Derive dynamic acceptance propositions.",
        ),
    ),
    (
        "architect",
        "role-prompt-hook.baseline.architect.v1",
        RoleCategory.ARCHITECTURE,
        "architect.md",
        (
            "Compile AcceptanceContract and PackageContract.",
            "Check run command and service boundary consistency.",
            "Check test command obligations.",
            "Define integration boundary.",
            "Bind evidence obligations to acceptance refs.",
        ),
    ),
    (
        "worker",
        "role-prompt-hook.baseline.worker.v1",
        RoleCategory.IMPLEMENTATION,
        "worker.md",
        (
            "Implement only inside allowed write set.",
            "Do not use fallback to satisfy implementation evidence.",
        ),
    ),
    (
        "tester",
        "role-prompt-hook.baseline.tester.v1",
        RoleCategory.VERIFICATION,
        "tester.md",
        (
            "Write negative tests first.",
            "Run blackbox service probe when services are declared.",
            "Verify live integration when integration is declared.",
        ),
    ),
    (
        "checker",
        "role-prompt-hook.baseline.checker.v1",
        RoleCategory.AUDIT,
        "checker.md",
        (
            "Treat every evidence gap as blocker.",
            "Do not let notes clear blocker.",
        ),
    ),
    (
        "closeout",
        "role-prompt-hook.baseline.closeout.v1",
        RoleCategory.AUDIT,
        "closeout.md",
        (
            "Workflow completed cannot replace CloseoutPackage.",
            "Require CLOSEOUT_COMMITTED after closeout package.",
        ),
    ),
)


def build_baseline_role_prompt_hook_registry() -> RolePromptHookRegistry:
    hooks: list[RolePromptHook] = []
    for role_kind, hook_ref, role_category, filename, responsibilities in _BASELINE_HOOK_SPECS:
        path = _BASELINE_TEMPLATE_DIR / filename
        prompt_text = path.read_text(encoding="utf-8")
        hooks.append(
            RolePromptHook(
                hook_ref=RolePromptHookRef(value=hook_ref),
                role_kind=role_kind,
                role_category=role_category,
                hook_version="v1",
                template_path=str(path.relative_to(_SOURCE_ROOT)).replace("\\", "/"),
                content_sha256=RolePromptHookSha256.from_text(prompt_text),
                prompt_text=prompt_text,
                policy_refs=(
                    RolePromptPolicyRef(value="policy.contract-first"),
                    RolePromptPolicyRef(value="policy.reducer-protected"),
                    RolePromptPolicyRef(value="policy.evidence-first"),
                    RolePromptPolicyRef(value="policy.fail-closed"),
                    RolePromptPolicyRef(value="policy.runtime-bounded"),
                ),
                required_responsibilities=responsibilities,
            )
        )
    return RolePromptHookRegistry.from_hooks(*hooks)


__all__ = [
    "RolePromptHook",
    "RolePromptHookRef",
    "RolePromptHookRegistry",
    "RolePromptHookSha256",
    "RolePromptPolicyRef",
    "build_baseline_role_prompt_hook_registry",
]
