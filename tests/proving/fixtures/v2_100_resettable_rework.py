from __future__ import annotations

from boardroom_os.proving.v2_100_resettable_fixture import V2_100ResettableFixture


def without_provider_attempt(base: V2_100ResettableFixture) -> V2_100ResettableFixture:
    return base.without_provider_attempt()


def with_stale_final_evidence(base: V2_100ResettableFixture) -> V2_100ResettableFixture:
    return base.with_stale_final_evidence()


def with_command_success_wrong_claim(base: V2_100ResettableFixture) -> V2_100ResettableFixture:
    return base.with_command_success_wrong_claim()


def with_old_closeout_run_ref(base: V2_100ResettableFixture) -> V2_100ResettableFixture:
    return base.with_old_closeout_run_ref()
