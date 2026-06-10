# Atomic-agent contract lock

## Purpose

This file records the reviewed external atomic-agent（原子智能体） contract inputs for Boardroom OS V2-090H. It is an audit lock, not a second source of truth. If any hash changes, V2-090H implementation must stop for contract review.

## Source

- atomic_agent_path_env: `BOARDROOM_ATOMIC_AGENT_PATH`
- default_atomic_agent_path: `../atomic-agent`
- package_name: `atomic-agent`
- import_name: `atomic_agent`

## Contract hashes

| Path | sha256 |
|---|---|
| `docs/03-contracts/agent-runtime-port.md` | `sha256:edc8c617f0cf35c2f8f257d39b8757de81c4e489d8c25872996037bcf2c1a50b` |
| `docs/03-contracts/agent-action-protocol.md` | `sha256:e9a8319b4d9a99d82bfeb08decd5eafb44e879293eb4bd3721ed3e6ce0fa03c5` |
| `docs/03-contracts/event-stream-protocol.md` | `sha256:2f67d46cf7bb73ed274a72b30a1e57f04adf19dca09a4770b6ef9e03bbff2b83` |
| `src/atomic_agent/models.py` | `sha256:0eaeb41dcfe643c68b3d3c632a19baa2bbca2b7a87fc7e6904e4febac6bd2c18` |
| `src/atomic_agent/event_recorder.py` | `sha256:685946430066b3dc6537c5f05b5777a35231e41b3fae3d624b3e8e553a993bf8` |

## Active model fields

- AgentInvocation: `invocation_id`, `task`, `workspace_root`, `allowed_write_set`, `tools`, `permission_policy`, `provider_profile`, `budgets`, `output_requirements`, `role_context`, `skill_context`, `initial_files`, `metadata`
- AgentRunResult: `run_id`, `status`, `event_stream_ref`, `events_hash`, `tool_attempts`, `workspace_mutations`, `artifacts`, `summary`, `failure_kind`, `failure_message`, `failed_action_ref`

## Event stream format

`jsonl-utf8-lf-canonical-json-v1`: one canonical JSON object per LF-terminated line, UTF-8, `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`; `events_hash` is sha256 of raw bytes.
