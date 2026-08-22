# Debate Protocol

Use only when the user asks for multiple perspectives, a thorough challenge, or when a decision has material uncertainty. The default single-playbook path is cheaper and easier to verify.

## Worker mode

Disclose one execution mode before the synthesis:

- `real_workers`: the host actually created isolated workers and supplies child-run receipts or equivalent provenance that the workers' prose cannot self-assert.
- `single_agent_role_simulation`: one model or one call produced multiple role perspectives.
- `contract_fixture`: a stored event stream is being validated for development or audit only.

Only the host can establish `real_workers`. Role names, worker IDs, output hashes, or a model-generated `worker_mode` field are not proof of independent execution. If host evidence is unavailable, use `single_agent_role_simulation` and describe the result as a structured multi-perspective review, not real multi-Agent debate. Never present `contract_fixture` as a normal user result.

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

The orchestrator reports consensus, disagreements, blind spots, evidence strength, one current judgment, 2–3 actions/experiments, and a stop condition. Majority vote cannot establish truth. High-risk topics require a risk-agent pass or `SAFE_STOP`.

### User decision

Offer `accept`, `reject`, `defer`, `add_facts`, `rerun_agent`, or `stop`. Store the decision and later result separately from author knowledge. Default maximum is two rounds and a fixed budget.

## Validation

Write the event stream as JSONL. Compute `packet_hash` from canonical JSON of the frozen CasePacket without its `content_hash` field, and each `output_hash` from canonical JSON of the worker payload without its `output_hash` field (`sort_keys=true`, compact separators, UTF-8). Run `scripts/validate_debate.py <events.jsonl>` before accepting a synthesis. Use `evals/debate-events-valid.jsonl` only as a contract fixture, never as evidence that actual worker processes were isolated.
