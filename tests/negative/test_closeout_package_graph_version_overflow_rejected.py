from __future__ import annotations

import pytest

from boardroom_os.closeout.package import CloseoutPackageError, build_closeout_package
from tests.closeout.test_closeout_package import _closeout_package_builder_input


def test_closeout_package_rejects_graph_version_above_replay_boundary() -> None:
    builder_input = _closeout_package_builder_input()

    with pytest.raises(
        CloseoutPackageError,
        match="graph_version must equal replay bundle proof boundary",
    ):
        build_closeout_package(
            builder_input.model_copy(update={"graph_version": builder_input.graph_version + 1})
        )


def test_closeout_package_rejects_graph_version_below_replay_boundary() -> None:
    builder_input = _closeout_package_builder_input()

    with pytest.raises(
        CloseoutPackageError,
        match="graph_version must equal replay bundle proof boundary",
    ):
        build_closeout_package(
            builder_input.model_copy(update={"graph_version": builder_input.graph_version - 1})
        )
