# Task Registry

Each task is a versioned `TaskSpec`; natural-language keyword lists are not the source of truth.
The canonical machine-readable registry is `task-specs.jsonl`. Run
`scripts/validate_tasks.py references/task-specs.jsonl` after every routing change.

## Registry Fields

```json
{
  "id": "business.diagnose",
  "version": "1.0.0",
  "aliases": ["/biz diagnose"],
  "domain": ["business", "customer", "pricing"],
  "required_slots": ["customer", "problem_or_job", "offer_or_idea"],
  "outputs": ["diagnosis", "evidence_gaps", "experiment"],
  "allowed_tools": ["read_local", "network_read"],
  "risk": "medium",
  "can_write": false,
  "next_signals": ["needs_benchmark", "needs_standard", "needs_action", "needs_decision"]
}
```

## Registered Task Groups

This summary is for review; `task-specs.jsonl` remains authoritative.

| Group | Task IDs | Main output |
|---|---|---|
| Runtime | `runtime.intervene`, `runtime.status` | route trace or project status |
| Clarification | `reasoning.clarify` | concept boundary or evidence-bounded problem statement |
| Explore/diagnose | `business.explore`, `business.diagnose` | hypotheses/tests or evidence-led diagnosis |
| Customer/pricing | `business.customer`, `business.pricing` | JTBD/customer or pricing experiment |
| Research | `research.benchmark`, `research.standard` | comparison or structural analogue matrix |
| Product | `product.define` | discovery/build-ready PRD, MVP and acceptance |
| Content | `content.plan`, `content.hook`, `content.title`, `content.script`, `content.resonate`, `content.publish_check` | brief, draft analysis, or publish-risk review |
| Personal growth | `personal.goal`, `personal.action`, `personal.learning` | goal card, friction action, or feedback lesson |
| Decisions | `decision.record`, `decision.save`, `decision.restore`, `decision.report` | versioned decision/state artifacts |
| Governance | `governance.knowledge`, `governance.workbench`, `governance.bridge`, `governance.audit_skill` | index/search evidence, versioned bridge contracts, or risk findings |
| Debate | `debate.run` | independent round, cross-exam, synthesis, user decision |

The current registry contains 28 TaskSpecs and 29 aliases. The validator rejects
duplicate aliases, unsupported tools, invalid risk classes, and write-capability
contradictions.

## Required Handoff Signals

- `needs_benchmark`: comparable operator or offer is missing.
- `needs_standard`: mechanism requires historical analogue research.
- `needs_action`: model is plausible but execution is blocked.
- `needs_decision`: a choice needs a dated record and later outcome.
- `needs_clarification`: a missing slot changes execution or acceptance.

Do not automatically call the next task. Emit the signal, then let `/biz` or an explicit user command choose it.
