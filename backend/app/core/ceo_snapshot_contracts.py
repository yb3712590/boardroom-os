from __future__ import annotations

from typing import Any, Mapping


def projection_snapshot_view(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    projection_snapshot = snapshot.get("projection_snapshot")
    if not isinstance(projection_snapshot, Mapping):
        raise ValueError("CEO snapshot is missing projection_snapshot.")
    return dict(projection_snapshot)


def replan_focus_view(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    replan_focus = snapshot.get("replan_focus")
    if not isinstance(replan_focus, Mapping):
        raise ValueError("CEO snapshot is missing replan_focus.")
    return dict(replan_focus)


def controller_state_view(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    focus = replan_focus_view(snapshot)
    controller_state = focus.get("controller_state")
    if not isinstance(controller_state, Mapping):
        raise ValueError("CEO snapshot replan_focus is missing controller_state.")
    return dict(controller_state)


def capability_plan_view(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    focus = replan_focus_view(snapshot)
    capability_plan = focus.get("capability_plan")
    if not isinstance(capability_plan, Mapping):
        raise ValueError("CEO snapshot replan_focus is missing capability_plan.")
    return dict(capability_plan)


def task_sensemaking_view(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    focus = replan_focus_view(snapshot)
    task_sensemaking = focus.get("task_sensemaking")
    if not isinstance(task_sensemaking, Mapping):
        raise ValueError("CEO snapshot replan_focus is missing task_sensemaking.")
    return dict(task_sensemaking)
