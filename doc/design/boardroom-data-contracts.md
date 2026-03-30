# Boardroom Data Contracts

## Status
- Draft
- Date: 2026-03-28
- Scope: projection schemas, review payloads, and command/event contracts for the Boardroom UI

## 1. Purpose

This document defines the first-pass UI-facing data contracts for the `Boardroom UI`.

The goal is not to mirror internal storage tables one-to-one. The goal is to expose stable, projection-first read models for the frontend and a clear `Board Review Pack` contract for human approval.

This draft covers:

- dashboard projection
- inbox projection
- ticket artifacts projection
- workforce projection
- review room projection
- `BoardReviewPack`
- event stream envelope
- key command payloads

## 2. Design Rules

1. Frontend consumes projections, not raw event tables.
2. UI contracts should be task-oriented, not normalized like database tables.
3. Review-facing payloads should be human-readable first, machine-auditable second.
4. Internal execution artifacts may be linked but should not be the default UI surface.
5. Every projection response should be versioned.

## 3. Common Envelope

All projection APIs should return a common envelope.

```json
{
  "schema_version": "2026-03-28.boardroom.v1",
  "generated_at": "2026-03-28T02:00:00+08:00",
  "projection_version": 1842,
  "cursor": "evt_0001842",
  "data": {}
}
```

Field meaning:

- `schema_version`: frontend contract version
- `generated_at`: response build timestamp
- `projection_version`: monotonic projection version for drift detection
- `cursor`: latest event cursor included in this view
- `data`: actual projection payload

## 4. Dashboard Projection

Suggested endpoint:

- `GET /api/v1/projections/dashboard`

Purpose:

- populate the main control screen in one round trip
- avoid excessive chatty frontend bootstrapping

```json
{
  "schema_version": "2026-03-28.boardroom.v1",
  "generated_at": "2026-03-28T02:00:00+08:00",
  "projection_version": 1842,
  "cursor": "evt_0001842",
  "data": {
    "workspace": {
      "workspace_id": "ws_default",
      "workspace_name": "Default Workspace"
    },
    "active_workflow": {
      "workflow_id": "wf_001",
      "title": "Dark-mode Todo App",
      "north_star_goal": "Ship a usable React todo app with dark mode",
      "status": "EXECUTING",
      "current_stage": "ui_implementation",
      "started_at": "2026-03-28T01:30:00+08:00",
      "deadline_at": null
    },
    "ops_strip": {
      "budget_total": 500000,
      "budget_used": 132400,
      "budget_remaining": 367600,
      "token_burn_rate_5m": 1820,
      "active_tickets": 8,
      "blocked_nodes": 2,
      "open_incidents": 1,
      "open_circuit_breakers": 0,
      "provider_health_summary": "DEGRADED"
    },
    "pipeline_summary": {
      "phases": [
        {
          "phase_id": "phase_discovery",
          "label": "Discovery",
          "status": "COMPLETED",
          "node_counts": {
            "pending": 0,
            "executing": 0,
            "under_review": 0,
            "blocked_for_board": 0,
            "fused": 0,
            "completed": 4
          }
        },
        {
          "phase_id": "phase_ui",
          "label": "UI",
          "status": "EXECUTING",
          "node_counts": {
            "pending": 2,
            "executing": 3,
            "under_review": 1,
            "blocked_for_board": 1,
            "fused": 0,
            "completed": 2
          }
        }
      ],
      "critical_path_node_ids": [
        "node_ui_direction",
        "node_homepage_impl",
        "node_integration"
      ],
      "blocked_node_ids": [
        "node_homepage_release_candidate",
        "node_brand_visual_lock"
      ]
    },
    "inbox_counts": {
      "approvals_pending": 1,
      "incidents_pending": 1,
      "budget_alerts": 0,
      "provider_alerts": 1
    },
    "workforce_summary": {
      "active_workers": 6,
      "idle_workers": 2,
      "overloaded_workers": 1,
      "active_checkers": 1,
      "workers_in_rework_loop": 1
    },
    "event_stream_preview": [
      {
        "event_id": "evt_0001840",
        "occurred_at": "2026-03-28T01:59:10+08:00",
        "category": "ticket",
        "severity": "info",
        "message": "TICKET_COMPLETED by emp_frontend_2",
        "related_ref": "tkt_ui_home_03"
      }
    ]
  }
}
```

## 5. Inbox Projection

Suggested endpoint:

- `GET /api/v1/projections/inbox`

Purpose:

- populate the left-side approval and escalation inbox
- provide a uniform list regardless of underlying source

```json
{
  "schema_version": "2026-03-28.boardroom.v1",
  "generated_at": "2026-03-28T02:00:00+08:00",
  "projection_version": 1842,
  "cursor": "evt_0001842",
  "data": {
    "items": [
      {
        "inbox_item_id": "inbox_001",
        "workflow_id": "wf_001",
        "item_type": "BOARD_APPROVAL",
        "priority": "high",
        "status": "OPEN",
        "created_at": "2026-03-28T01:58:22+08:00",
        "sla_due_at": "2026-03-28T03:00:00+08:00",
        "title": "Review homepage visual milestone",
        "summary": "Visual milestone is blocked for board review.",
        "source_ref": "apr_visual_001",
        "route_target": {
          "view": "review_room",
          "review_pack_id": "brp_001"
        },
        "badges": [
          "visual",
          "board_gate",
          "critical_path"
        ]
      },
      {
        "inbox_item_id": "inbox_002",
        "workflow_id": "wf_001",
        "item_type": "INCIDENT_ESCALATION",
        "priority": "high",
        "status": "OPEN",
        "created_at": "2026-03-28T01:50:00+08:00",
        "sla_due_at": null,
        "title": "Repeated runtime timeout on homepage visual node",
        "summary": "The same node exceeded the runtime timeout threshold and opened a circuit breaker.",
        "source_ref": "inc_093",
        "route_target": {
          "view": "incident_detail",
          "incident_id": "inc_093"
        },
        "badges": [
          "runtime_timeout",
          "circuit_breaker"
        ]
      }
    ]
  }
}
```

Recommended `item_type` enum:

- `BOARD_APPROVAL`
- `INCIDENT_ESCALATION`
- `BUDGET_ALERT`
- `PROVIDER_INCIDENT`
- `MEETING_ESCALATION`
- `CORE_HIRE_APPROVAL`

## 5.1 Ticket Artifacts Projection

Suggested endpoint:

- `GET /api/v1/projections/tickets/{ticket_id}/artifacts`

Purpose:

- show the per-ticket artifact index without replaying raw events
- expose whether each artifact is truly materialized or only registered

```json
{
  "schema_version": "2026-03-28.boardroom.v1",
  "generated_at": "2026-03-30T12:00:00+08:00",
  "projection_version": 1910,
  "cursor": "evt_0001910",
  "data": {
    "ticket_id": "tkt_ui_home_03",
    "artifacts": [
      {
        "artifact_ref": "art://runtime/tkt_ui_home_03/option-a.json",
        "path": "reports/review/option-a.json",
        "kind": "JSON",
        "media_type": "application/json",
        "status": "MATERIALIZED",
        "materialization_status": "MATERIALIZED",
        "lifecycle_status": "ACTIVE",
        "content_url": "/api/v1/artifacts/content?artifact_ref=art%3A%2F%2Fruntime%2Ftkt_ui_home_03%2Foption-a.json&disposition=inline",
        "download_url": "/api/v1/artifacts/content?artifact_ref=art%3A%2F%2Fruntime%2Ftkt_ui_home_03%2Foption-a.json&disposition=attachment",
        "preview_url": "/api/v1/artifacts/preview?artifact_ref=art%3A%2F%2Fruntime%2Ftkt_ui_home_03%2Foption-a.json",
        "size_bytes": 114,
        "content_hash": "8f14e45fceea167a5a36dedd4bea2543af6c9426c6b8f4d95b2f7d0d6f8b4f9a",
        "created_at": "2026-03-30T11:58:00+08:00"
      },
      {
        "artifact_ref": "art://runtime/tkt_ui_home_03/mockup.png",
        "path": "artifacts/ui/homepage/mockup.png",
        "kind": "IMAGE",
        "media_type": "image/png",
        "status": "MATERIALIZED",
        "materialization_status": "MATERIALIZED",
        "lifecycle_status": "ACTIVE",
        "content_url": "/api/v1/artifacts/content?artifact_ref=art%3A%2F%2Fruntime%2Ftkt_ui_home_03%2Fmockup.png&disposition=inline",
        "download_url": "/api/v1/artifacts/content?artifact_ref=art%3A%2F%2Fruntime%2Ftkt_ui_home_03%2Fmockup.png&disposition=attachment",
        "preview_url": "/api/v1/artifacts/preview?artifact_ref=art%3A%2F%2Fruntime%2Ftkt_ui_home_03%2Fmockup.png",
        "size_bytes": 24576,
        "content_hash": "63f7f4ff7c0cfbce5b7cfe9f95cbd6fce431bd53f4e6f08d076b0b7bfb4e4d1a",
        "created_at": "2026-03-30T11:58:00+08:00"
      }
    ]
  }
}
```

Rules:

- missing ticket should return `404`
- `status = MATERIALIZED` means the artifact body was persisted into the current artifact store and metadata such as `size_bytes` / `content_hash` may be present
- `status = REGISTERED_ONLY` means the ref and metadata were accepted, but runtime has no stored body for that artifact yet
- `materialization_status` keeps the raw storage fact, while `lifecycle_status` tells consumers whether the artifact is still consumable
- `content_url` / `download_url` / `preview_url` are local backend artifact routes keyed by `artifact_ref`

### 5.1.1 Artifact Read APIs

Suggested endpoints:

- `GET /api/v1/artifacts/by-ref?artifact_ref=...`
- `GET /api/v1/artifacts/content?artifact_ref=...&disposition=inline|attachment`
- `GET /api/v1/artifacts/preview?artifact_ref=...`

Implementation rules:

- `by-ref` returns metadata plus local content / download / preview URLs
- `content` returns raw persisted bytes only when `materialization_status = MATERIALIZED` and `lifecycle_status = ACTIVE`
- `content` should return conflict-style errors for `REGISTERED_ONLY`, and gone-style errors for `DELETED` / `EXPIRED`
- `preview` returns parsed JSON for `JSON`, text for `TEXT` / `MARKDOWN`, inline-media metadata for images and PDFs, and `download_only` for other binaries
- review room and incident detail consume these local routes via `artifact_ref`
- external workers now consume the worker-scoped equivalents under `/api/v1/worker-runtime/artifacts/*`, rather than inventing special-case artifact readers

## 5.2 Incident Detail Projection

Suggested endpoint:

- `GET /api/v1/projections/incidents/{incident_id}`

Purpose:

- open a concrete escalation target from Inbox
- show the minimal incident / circuit-breaker state without replaying raw events in the UI

```json
{
  "schema_version": "2026-03-28.boardroom.v1",
  "generated_at": "2026-03-28T02:00:00+08:00",
  "projection_version": 1842,
  "cursor": "evt_0001842",
  "data": {
    "incident": {
      "incident_id": "inc_093",
      "workflow_id": "wf_001",
      "node_id": "node_homepage_visual",
      "ticket_id": "tkt_ui_home_03_retry_1",
      "provider_id": null,
      "incident_type": "RUNTIME_TIMEOUT_ESCALATION",
      "status": "OPEN",
      "severity": "high",
      "fingerprint": "wf_001:node_homepage_visual:runtime-timeout",
      "circuit_breaker_state": "OPEN",
      "opened_at": "2026-03-28T01:50:00+08:00",
      "closed_at": null,
      "payload": {
        "timeout_streak_count": 2,
        "latest_failure_kind": "TIMEOUT_SLA_EXCEEDED"
      }
    }
  }
}
```

This endpoint remains intentionally minimal in the current slice. After the operator resolves an incident, `incident.payload` also carries:

- `followup_action`
- `followup_ticket_id`

For provider pauses, the same endpoint now also exposes:

- top-level `provider_id`
- `incident_type = PROVIDER_EXECUTION_PAUSED`
- `payload.pause_reason` with values such as `PROVIDER_RATE_LIMITED` or `UPSTREAM_UNAVAILABLE`

For repeated ordinary failures, the same endpoint may expose:

- `incident_type = REPEATED_FAILURE_ESCALATION`
- `payload.failure_streak_count`
- `payload.latest_failure_kind`
- `payload.latest_failure_fingerprint`

It still does not expose a broader automated recovery workflow.

## 5.3 Incident Resolve Command

Suggested endpoint:

- `POST /api/v1/commands/incident-resolve`

Purpose:

- let an operator manually reopen dispatch on a fused node or paused provider
- close the minimal timeout or provider incident in the same transaction

```json
{
  "incident_id": "inc_093",
  "resolved_by": "emp_ops_1",
  "resolution_summary": "Operator confirmed mitigation and reopened dispatch on the node.",
  "followup_action": "RESTORE_ONLY",
  "idempotency_key": "incident-resolve:inc_093"
}
```

Implementation rules:

- command is accepted only when the incident exists, `status=OPEN`, and `circuit_breaker_state=OPEN`
- `followup_action` defaults to `RESTORE_ONLY` for backward compatibility
- accepted `RESTORE_ONLY` emits `CIRCUIT_BREAKER_CLOSED` first and `INCIDENT_CLOSED` second
- accepted `RESTORE_AND_RETRY_LATEST_FAILURE` emits `CIRCUIT_BREAKER_CLOSED`, then `TICKET_RETRY_SCHEDULED` plus a new `TICKET_CREATED`, then `INCIDENT_CLOSED`
- accepted `RESTORE_AND_RETRY_LATEST_TIMEOUT` emits `CIRCUIT_BREAKER_CLOSED`, then `TICKET_RETRY_SCHEDULED` plus a new `TICKET_CREATED`, then `INCIDENT_CLOSED`
- accepted `RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE` emits `CIRCUIT_BREAKER_CLOSED`, then `TICKET_RETRY_SCHEDULED` plus a new `TICKET_CREATED`, then `INCIDENT_CLOSED`
- `RESTORE_AND_RETRY_LATEST_FAILURE` is accepted only for `REPEATED_FAILURE_ESCALATION`, when the incident source ticket still exists, its latest terminal event is an ordinary failure, and its retry budget still allows one more retry
- `RESTORE_AND_RETRY_LATEST_TIMEOUT` is accepted only when the incident source ticket still exists, its latest terminal event is timeout-based, and its retry budget still allows one more timeout retry
- `RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE` is accepted only for `PROVIDER_EXECUTION_PAUSED`, when the incident source ticket still exists, its latest terminal event is a provider failure, and its retry budget still allows one more retry
- `INCIDENT_CLOSED.payload` now carries `followup_action` and `followup_ticket_id`
- default close behavior still does not auto-create a retry ticket; retry creation only happens when the operator explicitly requests `RESTORE_AND_RETRY_LATEST_FAILURE`, `RESTORE_AND_RETRY_LATEST_TIMEOUT`, or `RESTORE_AND_RETRY_LATEST_PROVIDER_FAILURE`

## 6. Workforce Projection

Suggested endpoint:

- `GET /api/v1/projections/workforce`

Purpose:

- populate the workforce panel
- avoid exposing raw employee rows directly

```json
{
  "schema_version": "2026-03-28.boardroom.v1",
  "generated_at": "2026-03-28T02:00:00+08:00",
  "projection_version": 1842,
  "cursor": "evt_0001842",
  "data": {
    "role_lanes": [
      {
        "role_type": "frontend_engineer",
        "active_count": 2,
        "idle_count": 0,
        "overloaded_count": 1,
        "workers": [
          {
            "employee_id": "emp_frontend_2",
            "display_name": "Frontend Engineer A",
            "role_type": "frontend_engineer",
            "employment_state": "ACTIVE",
            "activity_state": "EXECUTING",
            "current_ticket_id": "tkt_ui_home_03",
            "current_node_id": "node_homepage_impl",
            "bound_model": {
              "provider_id": "prov_openai_compat",
              "preferred_model_id": "gpt-5.3-codex",
              "actual_model_id": "gpt-5.3-codex",
              "route_mode": "PRIMARY",
              "is_fallback_active": false,
              "fallback_reason": null,
              "degraded_since": null
            },
            "elapsed_sec": 740,
            "rework_pressure": "low",
            "health_state": "healthy",
            "last_update_at": "2026-03-28T01:58:40+08:00"
          }
        ]
      },
      {
        "role_type": "checker",
        "active_count": 1,
        "idle_count": 0,
        "overloaded_count": 0,
        "workers": [
          {
            "employee_id": "emp_checker_1",
            "display_name": "Checker A",
            "role_type": "checker",
            "employment_state": "ACTIVE",
            "activity_state": "REVIEWING",
            "current_ticket_id": "tkt_review_11",
            "current_node_id": "node_homepage_impl",
            "bound_model": {
              "provider_id": "prov_openai_compat",
              "preferred_model_id": "gpt-5.3-codex",
              "actual_model_id": "claude-3.5-sonnet",
              "route_mode": "FALLBACK",
              "is_fallback_active": true,
              "fallback_reason": "provider_rate_limited",
              "degraded_since": "2026-03-28T01:57:12+08:00"
            },
            "elapsed_sec": 220,
            "rework_pressure": "medium",
            "health_state": "healthy",
            "last_update_at": "2026-03-28T01:59:00+08:00"
          }
        ]
      }
    ]
  }
}
```

Recommended `activity_state` enum:

- `IDLE`
- `EXECUTING`
- `REVIEWING`
- `WAITING_DEPENDENCY`
- `WAITING_BOARD`
- `FUSED`
- `OFFLINE`

Recommended `bound_model.route_mode` enum:

- `PRIMARY`
- `FALLBACK`
- `MANUAL_OVERRIDE`

UI rule:

- when `is_fallback_active=true`, the model badge should be visually marked as degraded
- UI should show both `preferred_model_id` and `actual_model_id` when they differ

## 7. Review Room Projection

Suggested endpoint:

- `GET /api/v1/projections/review-room/{review_pack_id}`

Purpose:

- hydrate the review surface with everything needed for a board decision

This projection should mostly be a thin envelope around a `BoardReviewPack`.

```json
{
  "schema_version": "2026-03-28.boardroom.v1",
  "generated_at": "2026-03-28T02:00:00+08:00",
  "projection_version": 1842,
  "cursor": "evt_0001842",
  "data": {
    "review_pack": {
      "$ref": "#/definitions/BoardReviewPack"
    },
    "available_actions": [
      "APPROVE",
      "REJECT",
      "MODIFY_CONSTRAINTS"
    ],
    "draft_defaults": {
      "selected_option_id": "option_b",
      "comment_template": ""
    }
  }
}
```

### 7.1 Review Room Developer Inspector Companion Projection

Suggested endpoint:

- `GET /api/v1/projections/review-room/{review_pack_id}/developer-inspector`

Purpose:

- expose the raw persisted developer-facing compilation artifacts referenced by the review pack
- keep raw compiler IR behind an explicit advanced inspector path instead of mixing it into the default board-facing review surface

Suggested response:

```json
{
  "schema_version": "2026-03-28.boardroom.v1",
  "generated_at": "2026-03-29T00:40:00+08:00",
  "projection_version": 1849,
  "cursor": "evt_0001849",
  "data": {
    "review_pack_id": "brp_001",
    "compiled_context_bundle_ref": "ctx://homepage/visual-v1",
    "compile_manifest_ref": "manifest://homepage/visual-v1",
    "compiled_context_bundle": {
      "$ref": "persisted json payload"
    },
    "compile_manifest": {
      "$ref": "persisted json payload"
    },
    "availability": "ready"
  }
}
```

Implementation rules:

- this endpoint is scoped to one existing review pack, not a global arbitrary artifact reader
- `availability` should be `ready`, `partial`, or `missing`
- `developer_inspector_refs` may exist before payloads are materialized; in that case the endpoint must report that honestly instead of fabricating content

## 8. BoardReviewPack

This is the primary human-facing approval artifact. It should be assembled from approval state, artifacts, findings, delta summaries, and relevant workflow metadata.

It should not expose raw compiler IR as the first thing the Board sees.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "BoardReviewPack_v1",
  "type": "object",
  "properties": {
    "meta": {
      "type": "object",
      "properties": {
        "review_pack_id": { "type": "string" },
        "review_pack_version": { "type": "integer" },
        "source_projection_version": { "type": "integer" },
        "workflow_id": { "type": "string" },
        "approval_id": { "type": "string" },
        "review_type": {
          "type": "string",
          "enum": [
            "VISUAL_MILESTONE",
            "BUDGET_EXCEPTION",
            "MEETING_ESCALATION",
            "CORE_HIRE_APPROVAL",
            "SCOPE_PIVOT"
          ]
        },
        "created_at": { "type": "string", "format": "date-time" },
        "priority": {
          "type": "string",
          "enum": ["low", "medium", "high", "critical"]
        }
      },
      "required": [
        "review_pack_id",
        "review_pack_version",
        "workflow_id",
        "approval_id",
        "review_type",
        "created_at"
      ]
    },
    "subject": {
      "type": "object",
      "properties": {
        "title": { "type": "string" },
        "subtitle": { "type": "string" },
        "source_node_id": { "type": "string" },
        "source_ticket_id": { "type": "string" },
        "blocking_scope": {
          "type": "string",
          "enum": ["NODE_ONLY", "DEPENDENT_SUBGRAPH", "WORKFLOW"]
        }
      },
      "required": ["title"]
    },
    "trigger": {
      "type": "object",
      "properties": {
        "trigger_event_id": { "type": "string" },
        "trigger_reason": { "type": "string" },
        "why_now": { "type": "string" }
      }
    },
    "recommendation": {
      "type": "object",
      "properties": {
        "recommended_action": {
          "type": "string",
          "enum": ["APPROVE", "REJECT", "MODIFY_CONSTRAINTS"]
        },
        "recommended_option_id": { "type": "string" },
        "summary": { "type": "string" }
      }
    },
    "options": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "option_id": { "type": "string" },
          "label": { "type": "string" },
          "summary": { "type": "string" },
          "artifact_refs": {
            "type": "array",
            "items": { "type": "string" }
          },
          "preview_assets": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "asset_id": { "type": "string" },
                "asset_type": {
                  "type": "string",
                  "enum": ["IMAGE", "HTML_PREVIEW", "JSON_VIEW", "DIFF"]
                },
                "delivery_mode": {
                  "type": "string",
                  "enum": ["EMBEDDED", "SIGNED_URI", "LOCAL_ROUTE"]
                },
                "uri": { "type": "string" },
                "mime_type": { "type": "string" },
                "caption": { "type": "string" },
                "expires_at": { "type": "string", "format": "date-time" }
              },
              "required": ["asset_id", "asset_type", "delivery_mode", "uri"]
            }
          },
          "pros": {
            "type": "array",
            "items": { "type": "string" }
          },
          "cons": {
            "type": "array",
            "items": { "type": "string" }
          },
          "risks": {
            "type": "array",
            "items": { "type": "string" }
          },
          "estimated_budget_impact_range": {
            "type": "object",
            "properties": {
              "min_tokens": { "type": "integer" },
              "max_tokens": { "type": "integer" }
            }
          }
        },
        "required": ["option_id", "label", "summary"]
      }
    },
    "evidence_summary": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "evidence_id": { "type": "string" },
          "source_type": {
            "type": "string",
            "enum": [
              "ARTIFACT",
              "CHECKER_FINDING",
              "MEETING_CONSENSUS",
              "BUDGET_REPORT",
              "INCIDENT_SUMMARY",
              "COMPILER_NOTE"
            ]
          },
          "headline": { "type": "string" },
          "summary": { "type": "string" },
          "source_ref": { "type": "string" }
        },
        "required": ["evidence_id", "source_type", "headline", "summary"]
      }
    },
    "delta_summary": {
      "type": "object",
      "properties": {
        "previous_attempt_ref": { "type": "string" },
        "what_changed": {
          "type": "array",
          "items": { "type": "string" }
        },
        "still_unresolved": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },
    "maker_checker_summary": {
      "type": "object",
      "properties": {
        "maker_employee_id": { "type": "string" },
        "checker_employee_id": { "type": "string" },
        "review_status": {
          "type": "string",
          "enum": [
            "APPROVED",
            "APPROVED_WITH_NOTES",
            "CHANGES_REQUIRED",
            "ESCALATED",
            "NOT_APPLICABLE"
          ]
        },
        "top_findings": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "finding_id": { "type": "string" },
              "severity": { "type": "string" },
              "headline": { "type": "string" }
            },
            "required": ["finding_id", "severity", "headline"]
          }
        }
      }
    },
    "risk_summary": {
      "type": "object",
      "properties": {
        "user_risk": { "type": "string" },
        "engineering_risk": { "type": "string" },
        "schedule_risk": { "type": "string" },
        "budget_risk": { "type": "string" }
      }
    },
    "budget_impact": {
      "type": "object",
      "properties": {
        "tokens_spent_so_far": { "type": "integer" },
        "tokens_if_approved_estimate_range": {
          "type": "object",
          "properties": {
            "min_tokens": { "type": "integer" },
            "max_tokens": { "type": "integer" }
          }
        },
        "tokens_if_rework_estimate_range": {
          "type": "object",
          "properties": {
            "min_tokens": { "type": "integer" },
            "max_tokens": { "type": "integer" }
          }
        },
        "estimate_confidence": {
          "type": "string",
          "enum": ["low", "medium", "high"]
        },
        "budget_risk": {
          "type": "string",
          "enum": ["LOW", "MEDIUM", "HIGH"]
        }
      }
    },
    "decision_form": {
      "type": "object",
      "properties": {
        "allowed_actions": {
          "type": "array",
          "items": {
            "type": "string",
            "enum": [
              "APPROVE",
              "REJECT",
              "MODIFY_CONSTRAINTS"
            ]
          }
        },
        "command_target_version": { "type": "integer" },
        "requires_comment_on_reject": { "type": "boolean" },
        "requires_constraint_patch_on_modify": { "type": "boolean" }
      }
    },
    "developer_inspector_refs": {
      "type": "object",
      "properties": {
        "compiled_context_bundle_ref": { "type": "string" },
        "compile_manifest_ref": { "type": "string" },
        "incident_ref": { "type": "string" },
        "meeting_consensus_ref": { "type": "string" }
      }
    }
  },
  "required": ["meta", "subject", "recommendation", "decision_form"]
}
```

`developer_inspector_refs` should point to persisted JSON artifacts when those artifacts have been materialized. The refs may still exist before materialization, but that state should be surfaced through the companion developer inspector projection instead of being treated as fully ready.

Implementation rules:

- commands from Review Room should carry `review_pack_version` and `command_target_version`
- backend should reject stale review actions if the approval target has already advanced
- UI should primarily display `budget_risk` and use token ranges only in expanded detail
- preview assets should be treated as review artifacts with explicit delivery mode and expiry semantics

## 9. Event Stream Envelope

Suggested endpoint:

- `GET /api/v1/events/stream?after={cursor}`

This stream is for incremental UI sync, not for reconstructing all business logic client-side.

```json
{
  "stream_type": "boardroom_events",
  "cursor": "evt_0001843",
  "projection_version_hint": 1843,
  "events": [
    {
      "event_id": "evt_0001843",
      "occurred_at": "2026-03-28T02:01:03+08:00",
      "category": "approval",
      "severity": "warning",
      "event_type": "BOARD_REVIEW_REQUIRED",
      "workflow_id": "wf_001",
      "node_id": "node_brand_visual_lock",
      "ticket_id": "tkt_visual_09",
      "causation_id": "cmd_board_approve_001",
      "related_command_id": null,
      "ui_hint": {
        "invalidate": [
          "dashboard",
          "inbox"
        ],
        "refresh_policy": "debounced",
        "refresh_after_ms": 250,
        "toast": "Board review requested for visual milestone."
      }
    }
  ]
}
```

Recommended `category` enum:

- `workflow`
- `ticket`
- `review`
- `approval`
- `incident`
- `provider`
- `budget`
- `system`

Recommended `severity` enum:

- `debug`
- `info`
- `warning`
- `critical`

Stream rules:

- frontend should treat `invalidate` as a cache invalidation hint, not as a full data patch
- repeated invalidations should be batched or debounced
- if cursor resume fails or projection drift is detected, frontend should force a full snapshot reload
- SSE events should carry causation hints where possible so the UI can reconcile in-flight commands

## 10. Command Payloads

Frontend commands should stay explicit and narrow.

Command submission rule:

- UI should place acted-on controls into an in-flight locked state until either:
  - command acknowledgement is received and later reconciled by stream updates
  - command rejection is returned
  - timeout or reconnect policy forces recovery

### 10.0 Command Ack Envelope

Suggested immediate HTTP response body for all command endpoints:

```json
{
  "command_id": "cmd_board_approve_001",
  "idempotency_key": "board-approve:apr_visual_001:1",
  "status": "ACCEPTED",
  "reason": null,
  "causation_hint": "approval:apr_visual_001",
  "received_at": "2026-03-28T02:05:00+08:00"
}
```

Recommended `status` enum:

- `ACCEPTED`
- `REJECTED`
- `DUPLICATE`

### 10.1 Project Init

`POST /api/v1/commands/project-init`

```json
{
  "north_star_goal": "Ship a dark-mode todo app in React",
  "hard_constraints": [
    "Do not use external state-management libraries"
  ],
  "budget_cap": 500000,
  "deadline_at": null
}
```

### 10.1.1 Ticket Create

`POST /api/v1/commands/ticket-create`

```json
{
  "ticket_id": "tkt_ui_home_03",
  "workflow_id": "wf_001",
  "node_id": "node_homepage_visual",
  "parent_ticket_id": null,
  "attempt_no": 1,
  "role_profile_ref": "ui_designer_primary",
  "constraints_ref": "global_constraints_v3",
  "input_artifact_refs": [
    "art://inputs/brief.md",
    "art://inputs/brand-guide.md"
  ],
  "context_query_plan": {
    "keywords": ["homepage", "brand", "visual"],
    "semantic_queries": ["approved visual direction"],
    "max_context_tokens": 3000
  },
  "acceptance_criteria": [
    "Must satisfy approved visual direction",
    "Must produce 2 options",
    "Must include rationale and risks"
  ],
  "output_schema_ref": "ui_milestone_review",
  "output_schema_version": 1,
  "allowed_tools": ["read_artifact", "write_artifact", "image_gen"],
  "allowed_write_set": [
    "artifacts/ui/homepage/*",
    "reports/review/*"
  ],
  "lease_timeout_sec": 600,
  "retry_budget": 2,
  "priority": "high",
  "timeout_sla_sec": 1800,
  "deadline_at": "2026-03-28T18:00:00+08:00",
  "escalation_policy": {
    "on_timeout": "retry",
    "on_schema_error": "retry",
    "on_repeat_failure": "escalate_ceo",
    "repeat_failure_threshold": 2,
    "timeout_repeat_threshold": 2,
    "timeout_backoff_multiplier": 1.5,
    "timeout_backoff_cap_multiplier": 2.0
  },
  "idempotency_key": "ticket-create:wf_001:tkt_ui_home_03"
}
```

Current minimal runtime-governance rule:

- ordinary `TICKET_FAILED` events now also participate in repeated-failure governance on the same `workflow_id + node_id` retry chain when the `failure_fingerprint` matches and the failure is not provider-scoped
- once the repeated-failure streak reaches `repeat_failure_threshold` and `on_repeat_failure=escalate_ceo`, backend opens an incident, opens a circuit breaker, and stops automatic dispatch on that node
- `TIMEOUT_SLA_EXCEEDED` and `HEARTBEAT_TIMEOUT` participate in the repeated-timeout streak for the same `workflow_id + node_id` retry chain
- timeout-triggered retry create may widen both `timeout_sla_sec` and `lease_timeout_sec`
- once the streak reaches `timeout_repeat_threshold`, backend opens an incident, opens a circuit breaker, and stops automatic dispatch on that node

### 10.1.2 Ticket Lease

`POST /api/v1/commands/ticket-lease`

```json
{
  "workflow_id": "wf_001",
  "ticket_id": "tkt_ui_home_03",
  "node_id": "node_homepage_visual",
  "leased_by": "emp_frontend_2",
  "lease_timeout_sec": 600,
  "idempotency_key": "ticket-lease:wf_001:tkt_ui_home_03:emp_frontend_2"
}
```

### 10.1.3 Ticket Start

`POST /api/v1/commands/ticket-start`

```json
{
  "workflow_id": "wf_001",
  "ticket_id": "tkt_ui_home_03",
  "node_id": "node_homepage_visual",
  "started_by": "emp_frontend_2",
  "idempotency_key": "ticket-start:wf_001:tkt_ui_home_03"
}
```

### 10.1.4 Ticket Fail

`POST /api/v1/commands/ticket-fail`

```json
{
  "workflow_id": "wf_001",
  "ticket_id": "tkt_ui_home_03",
  "node_id": "node_homepage_visual",
  "failed_by": "emp_frontend_2",
  "failure_kind": "SCHEMA_ERROR",
  "failure_message": "Output schema validation failed.",
  "failure_detail": {
    "schema_ref": "ui_milestone_review",
    "field": "options"
  },
  "idempotency_key": "ticket-fail:wf_001:tkt_ui_home_03:SCHEMA_ERROR"
}
```

### 10.1.5 Ticket Heartbeat

`POST /api/v1/commands/ticket-heartbeat`

```json
{
  "workflow_id": "wf_001",
  "ticket_id": "tkt_ui_home_03",
  "node_id": "node_homepage_visual",
  "reported_by": "emp_frontend_2",
  "idempotency_key": "ticket-heartbeat:wf_001:tkt_ui_home_03:emp_frontend_2"
}
```

This command is only valid after `ticket-start`.

It exists to prove that an `EXECUTING` ticket is still alive without overloading `ticket-lease` with mixed semantics.

### 10.1.6 Ticket Result Submit

`POST /api/v1/commands/ticket-result-submit`

```json
{
  "workflow_id": "wf_001",
  "ticket_id": "tkt_ui_home_03",
  "node_id": "node_homepage_visual",
  "submitted_by": "emp_frontend_2",
  "result_status": "COMPLETED",
  "schema_version": "ui_milestone_review_v1",
  "payload": {
    "summary": "Runtime prepared a minimal review package.",
    "recommended_option_id": "option_a",
    "options": [
      {
        "option_id": "option_a",
        "label": "Option A",
        "summary": "Primary minimal runtime-generated review option.",
        "artifact_refs": ["art://runtime/tkt_ui_home_03/option-a.json"]
      }
    ]
  },
  "artifact_refs": [
    "art://runtime/tkt_ui_home_03/option-a.json"
  ],
  "written_artifacts": [
    {
      "path": "reports/review/option-a.json",
      "artifact_ref": "art://runtime/tkt_ui_home_03/option-a.json",
      "kind": "JSON",
      "content_json": {
        "option_id": "option_a",
        "headline": "Primary runtime-generated structured review artifact."
      }
    }
  ],
  "assumptions": [
    "mobile first"
  ],
  "issues": [],
  "confidence": 0.78,
  "needs_escalation": false,
  "summary": "Runtime prepared a minimal review package.",
  "idempotency_key": "ticket-result-submit:wf_001:tkt_ui_home_03"
}
```

Implementation rules:

- this is the unified structured result ingress; legacy `ticket-complete` and `ticket-fail` remain compatibility routes, but new structured runtime output should use this command
- `schema_version` and `payload` are validated against the created ticket's schema registry entry
- current strict validator coverage includes `ui_milestone_review@1` and `consensus_document@1`
- `written_artifacts[*].path` must remain inside `allowed_write_set`
- the same submission must not repeat `artifact_ref` or normalized `path`
- `JSON` requires `content_json`
- `TEXT` and `MARKDOWN` require `content_text`
- binary artifact kinds may provide `content_base64` plus optional `media_type` to trigger real materialization
- binary artifact kinds may still omit inline body and remain `REGISTERED_ONLY` for compatibility
- each written artifact may carry `retention_class` and optional `retention_ttl_sec`
- artifact validation and materialization happen before the ticket is marked completed; failures are converted into the controlled governance paths `SCHEMA_ERROR`, `WRITE_SET_VIOLATION`, `ARTIFACT_VALIDATION_ERROR`, or `ARTIFACT_PERSIST_ERROR`

### 10.1.7 Scheduler Tick

`POST /api/v1/commands/scheduler-tick`

```json
{
  "workers": [
    {
      "employee_id": "emp_frontend_2",
      "role_profile_refs": ["ui_designer_primary"]
    },
    {
      "employee_id": "emp_checker_1",
      "role_profile_refs": ["checker_primary"]
    }
  ],
  "max_dispatches": 10,
  "idempotency_key": "scheduler-tick:2026-03-28T10:31:00+08:00"
}
```

This endpoint currently provides only the minimum explicit scheduler surface:

- detect total-SLA timeout for executing tickets
- detect heartbeat timeout for executing tickets
- schedule retry by appending `TICKET_RETRY_SCHEDULED` plus a new `TICKET_CREATED`
- dispatch `PENDING` or expired-lease tickets by appending `TICKET_LEASED`
- it does not replace explicit `ticket-start`
- it does not replace explicit `ticket-heartbeat`
- it does not itself deliver compiled execution packages
- in `EXTERNAL` mode workers continue through `/api/v1/worker-runtime/*`

### 10.1.8 External Worker Runtime

Current minimal authenticated worker handoff:

- `GET /api/v1/worker-runtime/assignments`
- `GET /api/v1/worker-runtime/tickets/{ticket_id}/execution-package`
- `GET /api/v1/worker-runtime/artifacts/by-ref?artifact_ref=...`
- `GET /api/v1/worker-runtime/artifacts/content?artifact_ref=...&disposition=inline|attachment`
- `GET /api/v1/worker-runtime/artifacts/preview?artifact_ref=...`
- `POST /api/v1/worker-runtime/commands/ticket-start`
- `POST /api/v1/worker-runtime/commands/ticket-heartbeat`
- `POST /api/v1/worker-runtime/commands/ticket-result-submit`

Bootstrap authentication headers:

- `X-Boardroom-Worker-Key`: deployment-level shared secret
- `X-Boardroom-Worker-Id`: the current `employee_id`

Behavior rules:

- assignment list includes only the current worker's `LEASED`, `EXECUTING`, and `CANCEL_REQUESTED` tickets
- `GET /api/v1/worker-runtime/assignments` remains the bootstrap call and now returns per-ticket `execution_package_url` plus `delivery_expires_at`
- execution-package reads require current lease ownership and return:
  - persisted `CompiledExecutionPackage`
  - `output_schema_body`
  - `bundle_id`
  - `compile_id`
  - `compile_request_id`
  - worker command endpoint URLs
  - `delivery_expires_at`
- if the current attempt has no persisted execution package yet, backend compiles and persists bundle / manifest / execution package before responding
- signed delivery URLs now use `access_token` query parameters scoped to one worker, one ticket, and one route family:
  - execution package URLs are scoped to one `ticket_id`
  - artifact URLs are scoped to one `ticket_id` plus one `artifact_ref`
  - worker command URLs are scoped to one `ticket_id` plus one command name
- `BOARDROOM_OS_PUBLIC_BASE_URL` rewrites the absolute delivery base, `BOARDROOM_OS_WORKER_DELIVERY_TOKEN_TTL_SEC` controls expiry, and `BOARDROOM_OS_WORKER_DELIVERY_SIGNING_SECRET` can differ from the bootstrap shared secret
- artifact routes keep existing lifecycle semantics:
  - `REGISTERED_ONLY` content reads return conflict-style errors
  - `DELETED` / `EXPIRED` content reads return gone-style errors
- signed URL calls do not need bootstrap headers, but header-based access remains as a compatibility fallback for local debugging
- worker command routes inject worker identity from either signed token or headers and then reuse the existing ticket handlers, so schema validation, write-set validation, artifact persistence, retry, incident, and breaker governance stay unchanged

### 10.2 Board Approve

`POST /api/v1/commands/board-approve`

```json
{
  "review_pack_id": "brp_001",
  "review_pack_version": 3,
  "command_target_version": 1842,
  "approval_id": "apr_visual_001",
  "selected_option_id": "option_b",
  "board_comment": "Proceed with option B. Keep contrast slightly stronger.",
  "idempotency_key": "board-approve:apr_visual_001:1"
}
```

### 10.3 Board Reject

`POST /api/v1/commands/board-reject`

```json
{
  "review_pack_id": "brp_001",
  "review_pack_version": 3,
  "command_target_version": 1842,
  "approval_id": "apr_visual_001",
  "board_comment": "Current direction is too flat and weak for first impression.",
  "rejection_reasons": [
    "visual_impact_insufficient",
    "brand_signal_weak"
  ],
  "idempotency_key": "board-reject:apr_visual_001:1"
}
```

### 10.4 Modify Constraints

`POST /api/v1/commands/modify-constraints`

```json
{
  "review_pack_id": "brp_001",
  "review_pack_version": 3,
  "command_target_version": 1842,
  "approval_id": "apr_visual_001",
  "constraint_patch": {
    "add_rules": [
      "Strengthen first-screen contrast and hierarchy"
    ],
    "remove_rules": [],
    "replace_rules": []
  },
  "board_comment": "Proceed with rework under stronger visual hierarchy constraint.",
  "idempotency_key": "board-modify:apr_visual_001:1"
}
```

Stale-write rule:

- backend should reject board commands whose `review_pack_version` or `command_target_version` no longer match current approval state
- frontend should surface this as "review pack outdated" and reload the review room

## 11. Recommended Projection Split

For MVP, avoid over-fragmenting read endpoints.

Suggested split:

- `GET /projections/dashboard`
  - top-level control screen bootstrap
- `GET /projections/inbox`
  - inbox list
- `GET /projections/workforce`
  - workforce panel
- `GET /projections/review-room/{review_pack_id}`
  - review page

Only add more granular endpoints when latency or payload size makes it necessary.

## 12. MVP Notes

Good enough for MVP:

- JSON over REST
- SSE cursor streaming
- typed but human-readable projection contracts
- review pack with previews and summaries

Do not overbuild in MVP:

- multi-tenant permission layers
- deeply normalized UI data contracts
- custom graph protocol
- separate projection per tiny widget

## 13. Final Position

These contracts are intended as a first usable boardroom reference, not the only valid final shape.

The important part is to keep three layers distinct:

- runtime truth
- UI projections
- human review artifacts

If those stay separated, the frontend can evolve without contaminating the workflow engine.
