# Context Compiler Design

## Status
- Draft
- Date: 2026-03-28
- Scope: provider-agnostic context compilation pipeline for ticket execution

## 1. Positioning

The `Context Compiler` is a deterministic middleware component between the control plane and the worker runtime.

It is not:

- an LLM policy role
- a free-form prompt template helper
- an authority that can rewrite ticket intent
- a replacement for CEO planning

It is:

- a query planner
- an artifact hydrator
- a retrieval orchestrator
- a token budget manager
- a context reducer
- a provider-specific prompt renderer frontend

If the framework is compared to a computer:

- Board sets goals and constraints
- CEO emits control intent and references
- workers execute atomic tasks
- Context Compiler behaves like the memory bus plus cache controller

Its purpose is to keep CEO attention expensive and scarce. CEO should declare what evidence classes are needed. Compiler should fetch, filter, compress, isolate, and assemble the final execution package.

## 2. Main Goal

The compiler should:

- convert control-plane references into execution-ready context
- minimize token waste
- keep trust boundaries explicit
- prevent retrieved data from becoming accidental system instructions
- leave a replayable audit trail
- support multiple model vendors without changing ticket semantics

## 3. Non-Goal

The compiler does not attempt to:

- guarantee zero hallucination
- infer missing business intent that the ticket never specified
- silently override CEO intent
- expose workers to arbitrary global memory
- store hidden long-term agent memory

## 4. Responsibility Boundary

### 4.1 CEO responsibility

CEO should decide:

- atomic task
- acceptance criteria
- required output contract
- role and constraints references
- explicit input artifact references
- query intent class through `context_query_plan`
- execution risk level and budget profile

CEO should not manually assemble long prompt bodies.

### 4.2 Context Compiler responsibility

Compiler should decide:

- how to resolve references
- how to extract relevant fragments
- how to apply retrieval policy
- how to enforce token budgets
- how to compress low-priority context
- how to render the provider-specific execution prompt

Compiler must not:

- invent new task requirements
- loosen hard rules
- treat retrieved text as control instructions

## 5. Core Design Principles

1. IR first, rendering second.
2. Control instructions and reference data must be physically separated in the intermediate representation.
3. Large artifacts should be addressed by fragment selectors, not by whole-file dumping.
4. Token budgets should be allocated before aggressive retrieval, not only after overflow happens.
5. Every compile run should emit a machine-auditable manifest.
6. Missing critical context should fail closed unless policy explicitly allows best-effort continuation.

## 6. Inputs

The compiler consumes a `CompileRequest` assembled by runtime from ticket data plus stable system metadata.

Important rule:

- CEO produces the business-facing `Ticket`
- runtime translates the ticket plus stable system state into `CompileRequest`
- the compiler consumes `CompileRequest`, not raw ticket storage rows

This translation step matters because the compiler needs execution-oriented controls such as source selectors, input-token budget, modality hints, and overflow policy.

### 6.1 Canonical CompileRequest

`CompileRequest` should be the smallest stable control contract required to compile execution-ready context.

It should include:

- control refs
- explicit source references
- retrieval plan
- budget policy
- task category
- optional strategy hints

It should not include:

- full hydrated content
- raw rendered prompt text
- arbitrary frontend state

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CompileRequest_v1",
  "type": "object",
  "description": "Runtime-to-compiler control contract",
  "properties": {
    "meta": {
      "type": "object",
      "properties": {
        "compile_request_id": { "type": "string" },
        "ticket_id": { "type": "string" },
        "workflow_id": { "type": "string" },
        "node_id": { "type": "string" },
        "attempt_no": { "type": "integer" },
        "task_category": {
          "type": "string",
          "enum": [
            "IMPLEMENTATION",
            "DEBUGGING",
            "REVIEW",
            "DESIGN",
            "PLANNING",
            "TESTING"
          ]
        },
        "task_subtype": { "type": "string" }
      },
      "required": [
        "compile_request_id",
        "ticket_id",
        "workflow_id",
        "task_category"
      ]
    },
    "control_refs": {
      "type": "object",
      "properties": {
        "role_profile_ref": { "type": "string" },
        "constraints_ref": { "type": "string" },
        "output_schema_ref": { "type": "string" },
        "output_schema_version": { "type": "integer" },
        "board_directive_refs": {
          "type": "array",
          "items": { "type": "string" }
        }
      },
      "required": [
        "role_profile_ref",
        "constraints_ref",
        "output_schema_ref"
      ]
    },
    "budget_policy": {
      "type": "object",
      "properties": {
        "max_input_tokens": { "type": "integer" },
        "reserved_output_tokens": { "type": "integer" },
        "overflow_policy": {
          "type": "string",
          "enum": [
            "FAIL_CLOSED",
            "BEST_EFFORT",
            "STRICT_BUCKETS"
          ]
        },
        "priority_bucket_targets": {
          "type": "object",
          "properties": {
            "p0_target_tokens": { "type": "integer" },
            "p1_target_tokens": { "type": "integer" },
            "p2_target_tokens": { "type": "integer" },
            "p3_target_tokens": { "type": "integer" }
          }
        },
        "allow_summarizer_model": { "type": "boolean" }
      },
      "required": [
        "max_input_tokens",
        "overflow_policy"
      ]
    },
    "explicit_sources": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "source_ref": { "type": "string" },
          "source_kind": {
            "type": "string",
            "enum": [
              "ARTIFACT",
              "REPO_FILE",
              "PROJECTION",
              "INCIDENT",
              "APPROVAL",
              "EVENT_SUMMARY"
            ]
          },
          "selector": {
            "type": "object",
            "properties": {
              "type": {
                "type": "string",
                "enum": [
                  "WHOLE_ARTIFACT",
                  "JSON_PATH",
                  "AST_SYMBOL",
                  "LINE_RANGE",
                  "DIFF_HUNK",
                  "MARKDOWN_SECTION",
                  "LOG_WINDOW",
                  "TEST_CASE_ID"
                ]
              },
              "value": { "type": "string" }
            },
            "required": ["type", "value"]
          },
          "representation_hint": {
            "type": "string",
            "enum": [
              "AUTO",
              "RAW",
              "SKELETON",
              "DIFF",
              "SUMMARY",
              "PREVIEW"
            ]
          },
          "is_mandatory": { "type": "boolean" }
        },
        "required": [
          "source_ref",
          "source_kind"
        ]
      }
    },
    "retrieval_plan": {
      "type": "object",
      "properties": {
        "hard_rules_tags": {
          "type": "array",
          "items": { "type": "string" }
        },
        "role_sop_tags": {
          "type": "array",
          "items": { "type": "string" }
        },
        "historical_pattern_query": { "type": "string" },
        "background_query": { "type": "string" },
        "max_hits_by_channel": {
          "type": "object",
          "properties": {
            "hard_rules": { "type": "integer" },
            "role_sop": { "type": "integer" },
            "historical_patterns": { "type": "integer" },
            "background_refs": { "type": "integer" }
          }
        }
      }
    },
    "compile_hints": {
      "type": "object",
      "properties": {
        "risk_class": {
          "type": "string",
          "enum": ["low", "medium", "high", "critical"]
        },
        "preferred_modalities": {
          "type": "array",
          "items": {
            "type": "string",
            "enum": [
              "TEXT",
              "CODE",
              "JSON",
              "DIFF",
              "LOG",
              "IMAGE",
              "HTML_PREVIEW"
            ]
          }
        },
        "target_entity_refs": {
          "type": "array",
          "items": { "type": "string" }
        },
        "diff_base_ref": { "type": "string" },
        "compression_profile_override": { "type": "string" },
        "preferred_render_target": { "type": "string" }
      }
    }
  },
  "required": [
    "meta",
    "control_refs",
    "budget_policy",
    "explicit_sources"
  ]
}
```

### 6.2 Why This Shape

The contract is intentionally more specific than a ticket because the compiler needs two kinds of control that a CEO should not micromanage in free text:

- where to fetch evidence from
- how aggressively to compress and drop context

Key decisions:

- `task_category` selects the default compression family
- `task_subtype` allows future specialization without exploding the main enum
- `overflow_policy` is policy-level, not an implementation-specific "drop P3" command
- `max_input_tokens` is more precise than a vague total-token limit
- `preferred_modalities` preserves multimodal fidelity for design and review tasks

### 6.3 Canonical Task Categories

Recommended stable categories:

- `IMPLEMENTATION`
- `DEBUGGING`
- `REVIEW`
- `DESIGN`
- `PLANNING`
- `TESTING`

Guidance:

- keep this enum small and stable
- use `task_subtype` or `compression_profile_override` for finer distinctions
- do not create a new top-level category for every department or workflow stage

## 7. Fragment Selector Model

To prevent token explosion, artifacts should support first-class selectors instead of only whole-document references.

Recommended selector types:

- `WHOLE_ARTIFACT`
- `JSON_PATH`
- `AST_SYMBOL`
- `LINE_RANGE`
- `DIFF_HUNK`
- `MARKDOWN_SECTION`
- `LOG_WINDOW`
- `TEST_CASE_ID`

Examples:

- `artifact_id + JSON_PATH($.routes.users)`
- `artifact_id + AST_SYMBOL(UserService.createUser)`
- `artifact_id + MARKDOWN_SECTION(API Contract)`
- `artifact_id + DIFF_HUNK(file=src/app.ts, hunk=3)`

Rules:

- selectors should be resolved deterministically
- selectors should fail loudly if the referenced fragment no longer exists
- large artifacts should default to fragment extraction instead of full hydration

## 8. Trust and Instruction Authority Model

Context sources should not be treated as equally trustworthy.

### 8.1 Trust levels

- `Trust 0`
  - control-plane instructions
  - role profile
  - hard constraints
  - board directives
  - output contract
  - atomic task
- `Trust 1`
  - committed workflow artifacts
  - repository fragments
  - state projection snapshots
  - approved prior deliverables
- `Trust 2`
  - internal documentation
  - SOP material
  - historical failure patterns
  - retrieval results from indexed corpora
- `Trust 3`
  - optional future external or user-supplied untrusted material

### 8.2 Instruction authority

Every compiled block must declare one of:

- `CONTROL`
- `DATA_ONLY`

Rules:

- only `Trust 0` sections may carry `CONTROL`
- all retrieved context must be `DATA_ONLY`
- renderers must never place `DATA_ONLY` content into the same authority channel as system controls when the provider supports separation
- if provider separation is weak, compiler must render `DATA_ONLY` blocks inside explicit sandbox tags

This is the minimum protection against prompt injection from historical artifacts or retrieved text.

## 9. Pipeline

The compiler keeps the four-stage idea, but adds a mandatory preflight substep before heavy retrieval.

### 9.1 Preflight

Before Stage 1:

- validate required refs
- compute model token limit
- assign token budget buckets
- choose fail mode
- compute cache fingerprint

Default budget priority:

- `P0`: role, hard rules, output contract, atomic task
- `P1`: explicit hydrated artifacts
- `P2`: internal historical patterns and progress summaries
- `P3`: broad retrieval references

### 9.2 Stage 1: Explicit Hydration

Actions:

- resolve `input_artifact_refs`
- apply fragment selectors
- load exact content from filesystem, artifact store, or projections
- normalize into typed content blocks

Rules:

- exact referenced artifacts should win over fuzzy retrieval
- missing critical explicit refs should usually fail closed
- repository code hydration should prefer symbol or diff-local extraction for large files

### 9.3 Stage 2: Implicit Retrieval

Actions:

- execute `context_query_plan`
- query FTS and vector stores
- retrieve hard rules, role SOP, historical patterns, and background references through separate channels

Retrieval channels should remain distinct:

- `hard_rules`
- `role_sop`
- `historical_patterns`
- `background_refs`

Historical failure records should preferably be converted into compact anti-pattern cards instead of dumping raw failed transcripts.

### 9.4 Stage 3: Budget Enforcement and Compression

If collected context exceeds budget, compiler should reduce lower-value material before touching critical blocks.

Recommended reduction order:

1. drop or shrink `P3`
2. compress `P2`
3. fragment or summarize `P1`
4. fail if `P0` cannot fit

Compression strategies should be task-aware:

- implementation tasks:
  - favor signatures, types, call sites, adjacent code
- debugging tasks:
  - favor stack trace, failing tests, recent diff, symbol neighborhood
- review tasks:
  - favor diff, policy, findings schema, acceptance criteria
- design tasks:
  - favor constraints, approved decisions, references, rejected options

Code-specific reduction examples:

- `AST_SKELETON`
- `PUBLIC_SIGNATURES_ONLY`
- `CALL_GRAPH_SLICE`
- `TYPE_SURFACE_ONLY`

Text reduction examples:

- heading-only outline
- section summary
- delta summary versus prior approved version

### 9.4.1 Task-Type Compression Matrix

The compiler should route every compile request through a task-category-specific compression family.

This prevents one generic reducer from harming very different task types.

#### `IMPLEMENTATION`

Attention priority:

- target files
- public types and interfaces
- adjacent module surfaces
- allowed write scope
- concrete acceptance criteria

Default strategy:

- keep target implementation files in full when they are explicitly selected
- reduce non-target code to `AST_SKELETON`, `PUBLIC_SIGNATURES_ONLY`, or `TYPE_SURFACE_ONLY`
- prefer local dependency context over broad repository history
- do not hydrate third-party library source unless explicitly requested
- keep `allowed_write_set` and output contract near the top of the compiled bundle

#### `DEBUGGING`

Attention priority:

- error stack
- failing test or failing input
- recent diff
- symbol neighborhood
- incident fingerprint history

Default strategy:

- denoise framework stack frames and retain business-code frames first
- prioritize `DIFF_HUNK` or recent change slices over whole-file hydration
- use `CALL_GRAPH_SLICE` or symbol-neighborhood extraction around the failing symbol
- include only the smallest log window that still preserves causal sequence
- inject historical failure material as compact anti-pattern cards, not raw logs

#### `REVIEW`

Attention priority:

- diff
- acceptance criteria
- hard constraints
- output contract
- checker policy

Default strategy:

- prefer strict diff or patch view over full source bodies
- amplify `Trust 0` constraints and acceptance criteria in the token budget
- aggressively down-rank broad RAG and historical references unless directly relevant
- highlight changed regions, touched APIs, and policy-sensitive writes
- favor structured findings templates over narrative background

#### `DESIGN`

Attention priority:

- high-level constraints
- approved decisions
- rejected alternatives
- user-facing or visual references
- system boundaries

Default strategy:

- summarize long text documents into outline or decision-note form before compilation
- preserve multimodal preview refs when the downstream model supports image or HTML preview inputs
- do not flatten important visual references into text if visual fidelity matters
- inject anti-pattern cards from prior escalations or rejected approaches
- prioritize ADR-style decisions and board-approved direction over raw implementation detail

#### `PLANNING`

Attention priority:

- north star goal
- hard constraints
- current state snapshot
- dependency structure
- budget and risk

Default strategy:

- summarize broad context into structured bullets or phase-level outlines
- include topology and blocker summaries instead of raw execution detail
- down-rank deep code bodies unless the plan is specifically code-coupled
- prefer concise state projection snapshots over long historical event streams
- surface risk, scope, and milestone implications early

#### `TESTING`

Attention priority:

- acceptance criteria
- changed behavior surface
- public interfaces
- existing failing tests
- environment or fixture constraints

Default strategy:

- prioritize diff plus public contract over entire implementation bodies
- include failing tests or target test identifiers first
- reduce helper modules to signatures or short summaries unless they are under test
- include environment assumptions, mocks, fixtures, and reproducible setup data
- attach flaky or historically unstable pattern summaries only when relevant

### 9.4.2 Strategy Overrides

The compiler should support a small override surface without abandoning the default matrix.

Acceptable overrides:

- `compression_profile_override`
- stronger `overflow_policy`
- modality preservation request
- diff-first hint
- full-source preservation for a specific selected artifact

Rule:

- overrides may strengthen or specialize a category strategy
- overrides should not silently disable trust separation or budget enforcement

### 9.5 Stage 4: Link and Render Preparation

Actions:

- order final blocks by authority and priority
- emit provider-agnostic IR
- generate provider-specific render hints
- optionally render a final prompt or message payload

Output should be two-layered:

- `CompiledContextBundle`
- rendered provider payload derived from the bundle

The IR is the contract. Rendered prompt text is a downstream view.

## 10. CompiledContextBundle

This is the canonical intermediate representation. It is not raw prompt text.

Key refinement versus a simpler schema:

- control-plane instructions are separated from contextual data
- artifact and retrieval material are unified into typed context blocks
- each block carries trust, priority, selector, and transform metadata

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CompiledContextBundle_v1",
  "type": "object",
  "description": "Provider-agnostic structured context IR for worker execution",
  "properties": {
    "meta": {
      "type": "object",
      "properties": {
        "bundle_id": { "type": "string" },
        "ticket_id": { "type": "string" },
        "workflow_id": { "type": "string" },
        "node_id": { "type": "string" },
        "compiler_version": { "type": "string" },
        "compiled_at": { "type": "string", "format": "date-time" },
        "model_profile": { "type": "string" },
        "render_target": { "type": "string" },
        "is_degraded": { "type": "boolean" }
      },
      "required": [
        "bundle_id",
        "ticket_id",
        "workflow_id",
        "compiler_version",
        "compiled_at"
      ]
    },
    "system_controls": {
      "type": "object",
      "description": "Trust 0 / CONTROL only",
      "properties": {
        "role_profile": { "type": "object" },
        "hard_rules": {
          "type": "array",
          "items": { "type": "string" }
        },
        "board_constraints": {
          "type": "array",
          "items": { "type": "string" }
        },
        "output_contract": {
          "type": "object",
          "properties": {
            "schema_ref": { "type": "string" },
            "schema_version": { "type": "integer" },
            "schema_body": { "type": "object" }
          },
          "required": ["schema_ref", "schema_version"]
        },
        "allowed_write_set": {
          "type": "array",
          "items": { "type": "string" }
        }
      },
      "required": ["role_profile", "hard_rules", "output_contract"]
    },
    "task_definition": {
      "type": "object",
      "description": "Trust 0 / CONTROL only",
      "properties": {
        "task_type": { "type": "string" },
        "atomic_task": { "type": "string" },
        "acceptance_criteria": {
          "type": "array",
          "items": { "type": "string" }
        },
        "risk_class": {
          "type": "string",
          "enum": ["low", "medium", "high", "critical"]
        },
        "budget_profile": { "type": "string" }
      },
      "required": ["atomic_task"]
    },
    "context_blocks": {
      "type": "array",
      "description": "Trust 1+ / DATA_ONLY blocks",
      "items": {
        "type": "object",
        "properties": {
          "block_id": { "type": "string" },
          "source_ref": { "type": "string" },
          "source_kind": {
            "type": "string",
            "enum": [
              "HYDRATED_ARTIFACT",
              "REPOSITORY_FRAGMENT",
              "RETRIEVED_RULE",
              "RETRIEVED_REFERENCE",
              "NEGATIVE_PATTERN",
              "PROGRESS_SUMMARY"
            ]
          },
          "trust_level": {
            "type": "integer",
            "enum": [1, 2, 3]
          },
          "instruction_authority": {
            "type": "string",
            "enum": ["DATA_ONLY"]
          },
          "priority_class": {
            "type": "string",
            "enum": ["P1", "P2", "P3"]
          },
          "selector": {
            "type": "object",
            "properties": {
              "selector_type": { "type": "string" },
              "selector_value": { "type": "string" }
            },
            "required": ["selector_type", "selector_value"]
          },
          "transform_chain": {
            "type": "array",
            "items": { "type": "string" }
          },
          "content_type": {
            "type": "string",
            "enum": [
              "JSON",
              "TEXT",
              "MARKDOWN",
              "CODE",
              "CODE_SKELETON",
              "DIFF",
              "LOG",
              "TABLE"
            ]
          },
          "content_payload": {
            "type": ["string", "object", "array"]
          },
          "token_estimate": { "type": "integer" },
          "relevance_score": { "type": "number" },
          "source_hash": { "type": "string" },
          "trust_note": { "type": "string" }
        },
        "required": [
          "block_id",
          "source_ref",
          "source_kind",
          "trust_level",
          "instruction_authority",
          "priority_class",
          "content_type",
          "content_payload"
        ]
      }
    },
    "render_hints": {
      "type": "object",
      "properties": {
        "preferred_section_order": {
          "type": "array",
          "items": { "type": "string" }
        },
        "sandbox_untrusted_data": { "type": "boolean" },
        "preferred_markup": {
          "type": "string",
          "enum": [
            "provider_native",
            "xml",
            "markdown",
            "json_messages"
          ]
        }
      }
    }
  },
  "required": [
    "meta",
    "system_controls",
    "task_definition",
    "context_blocks"
  ]
}
```

## 11. CompileManifest

The manifest is the audit and debugging contract for compilation.

It exists so humans and runtime can answer:

- what sources were used
- what was dropped
- why compression happened
- whether execution ran in degraded mode
- how token budget was consumed
- whether cache was used correctly

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CompileManifest_v1",
  "type": "object",
  "description": "Audit and performance trace for a context compilation run",
  "properties": {
    "compile_meta": {
      "type": "object",
      "properties": {
        "compile_id": { "type": "string" },
        "ticket_id": { "type": "string" },
        "workflow_id": { "type": "string" },
        "compiler_version": { "type": "string" },
        "compiled_at": { "type": "string", "format": "date-time" },
        "duration_ms": { "type": "integer" },
        "model_profile": { "type": "string" },
        "cache_key": { "type": "string" }
      },
      "required": [
        "compile_id",
        "ticket_id",
        "compiler_version",
        "compiled_at"
      ]
    },
    "input_fingerprint": {
      "type": "object",
      "properties": {
        "ticket_hash": { "type": "string" },
        "role_profile_version": { "type": "string" },
        "constraints_version": { "type": "string" },
        "output_schema_version": { "type": "string" },
        "artifact_hashes": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "artifact_id": { "type": "string" },
              "hash": { "type": "string" }
            },
            "required": ["artifact_id", "hash"]
          }
        }
      },
      "required": ["ticket_hash"]
    },
    "budget_plan": {
      "type": "object",
      "properties": {
        "total_budget_tokens": { "type": "integer" },
        "reserved_p0": { "type": "integer" },
        "reserved_p1": { "type": "integer" },
        "reserved_p2": { "type": "integer" },
        "reserved_p3": { "type": "integer" },
        "soft_limit_tokens": { "type": "integer" },
        "hard_limit_tokens": { "type": "integer" }
      },
      "required": ["total_budget_tokens", "hard_limit_tokens"]
    },
    "budget_actual": {
      "type": "object",
      "properties": {
        "used_p0": { "type": "integer" },
        "used_p1": { "type": "integer" },
        "used_p2": { "type": "integer" },
        "used_p3": { "type": "integer" },
        "final_bundle_tokens": { "type": "integer" },
        "truncated_tokens": { "type": "integer" }
      },
      "required": ["final_bundle_tokens"]
    },
    "source_log": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "source_ref": { "type": "string" },
          "source_kind": { "type": "string" },
          "priority_class": { "type": "string" },
          "trust_level": { "type": "integer" },
          "selector_used": { "type": "string" },
          "critical": { "type": "boolean" },
          "status": {
            "type": "string",
            "enum": [
              "USED",
              "CACHE_HIT",
              "SUMMARIZED",
              "TRUNCATED",
              "DROPPED",
              "MISSING"
            ]
          },
          "tokens_before": { "type": "integer" },
          "tokens_after": { "type": "integer" },
          "reason": { "type": "string" }
        },
        "required": ["source_ref", "status"]
      }
    },
    "transform_log": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "stage": { "type": "string" },
          "operation_type": {
            "type": "string",
            "enum": [
              "HYDRATE",
              "RETRIEVE",
              "AST_SKELETON",
              "SUMMARIZE",
              "TRUNCATE",
              "DROP",
              "NORMALIZE",
              "RENDER_PREP"
            ]
          },
          "target_ref": { "type": "string" },
          "output_block_id": { "type": "string" },
          "reason": { "type": "string" }
        },
        "required": ["stage", "operation_type"]
      }
    },
    "degradation": {
      "type": "object",
      "properties": {
        "is_degraded": { "type": "boolean" },
        "fail_mode": {
          "type": "string",
          "enum": ["FAIL_CLOSED", "BEST_EFFORT"]
        },
        "missing_critical_sources": {
          "type": "array",
          "items": { "type": "string" }
        },
        "warnings": {
          "type": "array",
          "items": { "type": "string" }
        }
      },
      "required": ["is_degraded", "fail_mode"]
    },
    "cache_report": {
      "type": "object",
      "properties": {
        "cache_hit": { "type": "boolean" },
        "reused_from_compile_id": { "type": "string" },
        "invalidated_by": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },
    "final_bundle_stats": {
      "type": "object",
      "properties": {
        "context_block_count": { "type": "integer" },
        "trusted_block_count": { "type": "integer" },
        "reference_block_count": { "type": "integer" },
        "negative_pattern_count": { "type": "integer" }
      }
    }
  },
  "required": [
    "compile_meta",
    "input_fingerprint",
    "budget_plan",
    "budget_actual",
    "source_log",
    "transform_log",
    "degradation"
  ]
}
```

## 12. Fail Mode Policy

Compiler must explicitly choose one of two modes:

- `FAIL_CLOSED`
  - missing `P0`
  - missing critical `P1`
  - output contract unavailable
  - selector resolution failure on mandatory artifacts
- `BEST_EFFORT`
  - optional `P2` or `P3` retrieval fails
  - summarization service unavailable for non-critical references
  - background documentation missing

The chosen mode and every degradation must appear in `CompileManifest`.

## 13. Cache and Invalidation

Compilation should be cacheable. Repeated retries should not rebuild the exact same bundle unless inputs changed.

Recommended cache key components:

- ticket hash
- role profile version
- constraints version
- output schema version
- artifact hashes
- query plan hash
- compiler version
- model profile

Recommended invalidation triggers:

- any referenced artifact hash changes
- constraints or role profile updates
- output schema changes
- query plan changes
- compiler version changes

## 14. Rendering Contract

Rendering is downstream from the bundle.

Rules:

- if provider supports separate instruction channels, `system_controls` should map there
- `context_blocks` with `DATA_ONLY` should map to lower-authority channels
- retrieved references should be explicitly labeled as reference data
- XML or Markdown tags are rendering choices, not the source of truth

Example renderer order:

1. `system_controls`
2. `task_definition`
3. `P1` context blocks
4. `P2` context blocks
5. `P3` context blocks
6. output contract reminder

## 15. Operational Value

This design upgrades the compiler from a prompt-template helper into an auditable middleware layer.

The main architectural shift is:

- CEO creates pointers and evidence intent
- compiler resolves and compiles context deterministically
- worker executes against a bounded, typed package

The system becomes less dependent on agent memory and more dependent on deterministic data plumbing.

## 16. Final Position

The two core contracts should now be treated as stable foundation pieces:

- `CompiledContextBundle`
- `CompileManifest`

AST reducers, summarizers, vector retrieval, policy filters, and provider renderers can be added later as pluggable modules behind these contracts.
