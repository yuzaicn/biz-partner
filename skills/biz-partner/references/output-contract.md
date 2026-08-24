# Output Contract

## CasePacket

```json
{
  "kind": "case_packet",
  "schema_version": "1.0",
  "packet_id": "packet_...",
  "case_id": "case_...",
  "project_id": "project_...",
  "parent_packet_hash": null,
  "created_at": "2026-08-20T00:00:00+08:00",
  "frozen_at": "2026-08-20T00:00:01+08:00",
  "request": {"raw_goal": "...", "intent": "...", "explicit_command": "/biz diagnose"},
  "items": [{"id":"fact_1","kind":"fact","value":"...","source_ref":"turn_12","confidence":0.9}],
  "acceptance_criteria": ["..."],
  "unknowns": ["..."],
  "negative_constraints": ["..."],
  "consent": {"read_local": true, "network_read": false, "write_local": false, "external_write": false, "destructive": false, "sensitive": false},
  "tool_policy": {"allowed_tools": ["read_local"]},
  "risk": {"class":"medium","platform":null,"jurisdiction":"CN"},
  "ttl": "2026-09-03T00:00:00+08:00",
  "content_hash": "sha256:..."
}
```

`items.kind` is one of `fact`, `user_claim`, `inference`, `constraint`, `unknown`. A frozen packet is immutable; changes create a new packet with `parent_packet_hash`.

`created_at`, `frozen_at`, and `ttl` are required ISO 8601 date-times with explicit
timezones. Their order is `created_at <= frozen_at < ttl`. Direct function callers may
provide a timezone-aware `validation_time` when expiry must be checked deterministically;
the validator CLI always checks the packet against the current time and rejects an expired
`ttl`.

Create the hash from the actual packet content. Use `scripts/freeze_contract_bundle.py`
to fill a missing/empty `content_hash`, bind the Handoff `packet_hash`, and validate the
packet/state lease. Never type a plausible hash by hand. If the actual CasePacket is not
available or the deterministic freezer cannot run, the structured Handoff is not delivered;
render consultation prose only.

## Handoff

```json
{
  "schema_version":"1.0",
  "run_id":"run_...",
  "packet_hash":"sha256:...",
  "state_version":1,
  "task_id":"business.diagnose@1.0.0",
  "state":"completed",
  "claims":[{"claim_id":"c1","kind":"judgment","assertion":"...","supporting_refs":["e1"],"strength":"medium"}],
  "evidence_refs":[{"id":"e1","source":"turn_12","evidence_kind":"user_input","locator":"...","as_of":"2026-08-20"}],
  "assumptions":[],
  "blockers":[],
  "artifacts":[],
  "rejected_options":[],
  "open_questions":[],
  "next_action":{"owner":"user","due":"2026-08-27","acceptance":"..."},
  "stop_condition":{"predicate":"no_new_evidence"},
  "approvals":[],
  "proposed_patches":[],
  "memory_proposal":null,
  "tool_trace":[],
  "error":null
}
```

One Handoff represents one leaf TaskSpec. A user-explicit, low-risk, tightly coupled
combination may share one CasePacket, but every leaf has a separate Handoff, `run_id`, and
versioned `task_id`. The final prose may synthesize those leaf results. Never place multiple
TaskSpecs in one Handoff.

## Auditable artifacts

`/biz intervene` first creates this artifact and then attaches it to the selected leaf
Handoff:

```json
{
  "type": "route_decision",
  "top_candidates": [
    {"task_id":"personal.action@1.0.0","score":0.82,"rejection_reason":"selected as primary","route_change_condition":"new customer-loss evidence favors diagnosis"},
    {"task_id":"business.diagnose@1.0.0","score":0.61,"rejection_reason":"execution friction is the current blocker","route_change_condition":"the attempted action reveals a system break"},
    {"task_id":"governance.workbench@1.0.0","score":0.22,"rejection_reason":"tooling is not the current bottleneck","route_change_condition":"multi-agent drift becomes a confirmed constraint"}
  ],
  "selected_task":"personal.action@1.0.0",
  "route_reason":"Frozen evidence identifies action friction as the primary blocker.",
  "confidence":0.82
}
```

Candidates are unique, ordered by descending score, and contain one to three entries. They
may use registry IDs such as `personal.action` or versioned IDs. `selected_task` is the
highest-scoring candidate, its score equals `confidence`, and it must identify the same leaf
as the Handoff's versioned `task_id`. `runtime.intervene` is not the final task ID; the
selected leaf is.

A decision artifact always carries an explicit confirmation state:

```json
{"type":"decision_record","status":"proposed","confirmation_ref":null,"record":{}}
```

Only `status: confirmed` may represent a decided/recorded choice, and then
`confirmation_ref` must point to a Handoff evidence ref with
`evidence_kind: user_input`. Without that evidence, keep the record `proposed` and avoid
“已决定” or “已记录” language. Unsupported experiment numbers are provisional parameters;
record the evidence or condition that will change each number.

For `content.script`, the artifact includes `logic_map`, `highest_loss_point`, and
`edit_plan`. In an explicit `title + script + resonate + publish-check` combination, emit
four independent leaf Handoffs sharing one packet, then synthesize the prose. A publish
check must treat platform and region as user facts; if either is missing, clarify. A
platform-rule judgment requires current policy evidence, otherwise label it `unverified`
and route it to human review.

## Invariants

The JSON shape is also available as `references/schemas/case-packet.schema.json` and
`references/schemas/handoff.schema.json`. Use a JSON Schema implementation for shape
validation, then run `scripts/validate_contracts.py` for cross-field evidence, state,
approval, and side-effect invariants.

1. Every `claim.supporting_refs` entry is unique and resolves to an existing `evidence_refs[].id`. Every non-`unknown` claim has at least one such supporting evidence ref; a missing or dangling ref is an explicit validation error.
2. Every evidence ref has a source, locator, and as-of time. User claims are not author evidence. Author-derived evidence uses `evidence_kind: knowledge_atom` plus `atom_id`.
3. `completed` requires claims, evidence or an explicit no-evidence explanation, next action, and stop condition.
4. `blocked` requires at least one blocker. `SAFE_STOP` has no side-effect intent and no proposed state patch.
5. Every `external_write`, `write_local`, or `destructive` trace requires exactly one prior approval, even when the trace later failed or was blocked. The approval and trace bind the same `authorization_ref`, and that ref must resolve to `user_input` evidence. External writes also bind target, body hash, scope hash and idempotency key; local writes bind target, scope hash and rollback ref. Destructive work additionally requires a different `user_input` ref for the second confirmation, a `tool_result` backup ref, and a post-action `tool_result` recovery check. Trace status is one of `attempted`, `completed`, `failed`, or `blocked`; spelling a success another way cannot bypass approval. The trace time must fall inside both the approval window and the frozen CasePacket window. These checks prove internal binding only: the host remains responsible for authenticating that the referenced user and tool events are genuine. Drafting or publish checking does not authorize publication, so an unapproved publish action must not appear there.
6. `tool_policy` and `tool_policy.allowed_tools` are required. Every `tool_trace.action` must be allowed twice: the matching CasePacket consent flag is `true`, and the action class is present in the allowlist. Internal advisory computation that did not use user-scoped data should not be mislabeled as a user-authorized file action.
7. `memory_proposal` cannot commit without explicit user confirmation; deletion creates a suppression event.
8. The bundle freezer requires an independently supplied `expected_state_version`; it never falls back to the Handoff's self-reported version. Pass `--expected-packet-hash` and `--expected-state-version` when validating a standalone Handoff against the current lease. A value not obtained from current project state proves explicit binding, not external freshness.
9. Terminal immutability and the two-retry limit require prior event history or runtime state-machine enforcement; they cannot be established from a standalone Handoff object.
10. Before rendering, verify `claim.supporting_refs -> evidence_ref -> atom_id -> atom.source_refs -> source registry`. Only a materially supporting `knowledge_atom` whose registered source declares `attribution_mode: when_materially_used` can trigger the public attribution name. Do not infer any relationship between that source identity and the runtime user.
11. A `route_decision` artifact has one to three auditable candidates, a selected leaf, route reason, and bounded confidence. A `decision_record` is `proposed` or `confirmed`; confirmation requires user-input evidence.
