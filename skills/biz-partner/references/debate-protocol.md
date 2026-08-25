# Debate Protocol

Use only when the user asks for multiple perspectives, a thorough challenge, or when a decision has material uncertainty. The default single-playbook path is cheaper and easier to verify.

## Worker mode

Record one execution mode before the synthesis:

- `real_workers`: the host actually created isolated workers and supplies child-run receipts or equivalent provenance that the workers' prose cannot self-assert.
- `single_agent_role_simulation`: one model or one call produced multiple role perspectives.
- `contract_fixture`: a stored event stream is being validated for development or audit only.

Only the host can establish `real_workers`. Role names, worker IDs, output hashes, or a model-generated `worker_mode` field are not proof of independent execution. If host evidence is unavailable, use `single_agent_role_simulation` and describe the result as a structured multi-perspective review, not real multi-Agent debate. Never present `contract_fixture` as a normal user result.

Keep the raw enum, worker IDs and receipts in the event stream. In ordinary prose, disclose the mode in one natural sentence: say how many independent workers actually ran, whether they cross-examined one another, or whether the result was a single-agent structured review. Show receipts only when the user asks for the audit trail.

Put `execution_mode` in `DebateStarted`. In `real_workers` mode, add one `host_receipts` entry per role with a unique `worker_id`, `receipt_id`, and `run_id`, plus the `output_hash` of that worker's final payload. The matching `WorkerStarted` event carries `host_receipt_id`; the matching `WorkerCompleted` event carries both `host_receipt_id` and `host_run_id`, and its canonical `output_hash` must equal the receipt's `output_hash`. The validator checks these event-to-receipt bindings only. It cannot authenticate the host receipt or prove process, context, or model isolation; that evidence remains the host's responsibility. Simulation and fixture modes must not carry host receipt or run claims.

## Roles

Use framework agents, not simulated celebrity voices:

1. `business_economics`: customer, offer, price, cost, channel, competition.
2. `user_product`: JTBD, scenario, delivery, usability, acceptance.
3. `contrarian_risk`: counterexamples, missing evidence, compliance, downside.

Add history, content, or action agents only when the CasePacket has a corresponding requirement. Each agent sees the same frozen packet and an explicit knowledge allowlist.

## Events

```text
DebateStarted -> PacketFrozen -> WorkerStarted* -> WorkerCompleted*
-> CrossExamStarted -> CrossExamCompleted* -> Synthesis -> UserDecision
-> MemoryCommit (only after confirmation)
```

## Rounds

### Round 1: Independent analysis

Each agent returns `position`, `claims`, `evidence_refs`, `assumptions`, `counterexamples`, `falsifiers`, `confidence`, and `proposed_test`. Agents cannot see other first-round outputs.

### Round 2: Cross-examination

Send only de-identified summaries and conflicting claims. Ask each agent to identify the weakest premise, missing evidence, a possible disconfirming observation, and a lower-cost test.

### Synthesis

The orchestrator keeps consensus, disagreements, blind spots, evidence strength, one current judgment, proposed tests, and a stop condition in the synthesis artifact. Require at least one executable action or experiment. Do not pad a simple decision to two or three actions. Alternatives may be empty when the event stream records no real disagreement; when `conflicting_claims` or `disagreements` is non-empty, keep at least two reasonable alternatives. The prose should lead with the decision and surface only the disagreements that could change it; do not print the same full set of headings for every debate. Majority vote cannot establish truth. High-risk topics require a risk-agent pass or `SAFE_STOP`.

### User decision

End with the decision the user actually needs to make. Store it internally as `accept`, `reject`, `defer`, `add_facts`, `rerun_agent`, or `stop`, but do not force those enum labels into the question. Store the decision and later result separately from author knowledge. Default maximum is two rounds and a fixed budget.

When the user confirms a memory write, `MemoryCommit` must bind the complete proposal and its canonical `proposal_hash`, the referenced `UserDecision` and its canonical `confirmation_hash`, a positive `state_version`, and a `state_event_ref` emitted by the state store. The state reference repeats the version and both hashes and has its own canonical `content_hash`. The debate validator checks the hashes and cross-references inside the event stream; the caller must still retrieve the referenced state event to establish that it really exists.

## Validation

Write the event stream as JSONL. Compute `packet_hash` from canonical JSON of the frozen CasePacket without its `content_hash` field, and each `output_hash` from canonical JSON of the worker payload without its `output_hash` field (`sort_keys=true`, compact separators, UTF-8). The CasePacket must be unexpired at validation time, and every event from `PacketFrozen` onward must have a timestamp in the half-open lease window `frozen_at <= timestamp < ttl`. Run `scripts/validate_debate.py <events.jsonl>` before accepting a synthesis. A successful `real_workers` CLI result reports `claimed_mode=real_workers receipt_binding=internal_only`: it confirms only internal event consistency, not worker isolation. Use `evals/debate-events-valid.jsonl` only as a contract fixture, never as evidence that actual worker processes were isolated.
