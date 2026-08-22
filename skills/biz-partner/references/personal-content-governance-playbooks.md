# Personal, Content, and Governance Playbooks

## Contents

- Shared rules; concept/problem clarification; goal, action, and learning
- Durable decisions; save, restore, and report
- Content direction, hook, title, script, resonance, and publish check
- Folder knowledge base and multi-agent workbench
- Local Skill audit and next signals

Use these playbooks only after freezing a `CasePacket`. Every result must satisfy
`output-contract.md`. Select one primary playbook by default; return a `next_signal` rather
than silently starting a second playbook. A user-explicit, low-risk, tightly coupled
combination may run sequentially against one packet, but every leaf produces an independent
Handoff and versioned `task_id`. Never combine multiple TaskSpecs into one Handoff.

## Shared Rules

Each playbook must:

1. Separate confirmed facts, user claims, inferences, and unknowns.
2. Ask only for missing information that changes the action or acceptance test.
3. Produce one current judgment, one artifact, one next action, and one stop condition.
4. Cite knowledge atoms only as attributed candidate rules; current user evidence wins.
5. Create a `memory_proposal` only when durable reuse is useful. Never commit it silently.
6. Mark unsupported experiment numbers as provisional parameters and state the evidence or
   condition that will adjust them.

## Concept and Problem Clarification (`reasoning.clarify`)

- **Trigger**: an important term has multiple plausible meanings, participants use the same
  word differently, or a situation is phrased as a solution, cause, or complaint before the
  actual problem and decision have been defined.
- **Required slots**: `term_or_problem` in the user's wording and the `decision_context` that
  makes the distinction useful. Ask one question when the intended decision is missing.
- **Concept mode**: state the working definition, anti-definition, in-scope and out-of-scope
  cases, observable indicators, one example, and one counterexample. Distinguish a
  source-defined term from a locally stipulated or operational definition; do not present a
  convenient definition as universal fact.
- **Problem mode**: separate observed state, desired state, affected actor and situation,
  evidence, assumed causes, proposed solutions, constraints, and unknowns. Remove causes and
  solutions from the problem statement unless evidence already supports them.
- **Output**: one `clarification_frame` artifact containing mode, original wording, working
  definition or problem statement, scope boundary, competing interpretations, evidence refs,
  unknowns, and one decision question that would change the next route.
- **Boundary**: if the meaning is already clear and the user needs an observable outcome,
  use `personal.goal`; if a defined business problem has reality evidence and the user asks
  why it occurs or what to test, use `business.diagnose`; if the task is to choose a customer
  segment or buying role rather than define a term, use `business.customer`.
- **Stop**: the term or problem has a usable boundary, unsupported assumptions remain labeled,
  and the next decision can be expressed as one answerable question. Route through a next
  signal; do not silently start goal setting or diagnosis.

## Goal Clarification (`personal.goal`)

- **Trigger**: vague goals such as “做个人品牌”“变得更强”“收入更高”.
- **Required slots**: desired observable change, baseline, deadline or review horizon,
  constraints, beneficiary, evidence of completion.
- **Method**: preserve the user's wording; identify ambiguous nouns and hidden trade-offs;
  translate the request into an observable outcome, non-goals, leading action, lagging
  measure, and review date.
- **Output**: goal card, unresolved choice, first checkpoint, rejection conditions.
- **Stop**: goal has an owner, observable acceptance test, constraints, and review date.
- **Escalate**: incompatible goals require a decision playbook; clinical or crisis content
  leaves this Skill's scope.

## Action Friction (`personal.action`)

- **Trigger**: procrastination, repeated research, changing direction, perfectionism,
  avoidance, or rushing without validation.
- **Required slots**: observable goal, last attempted action, where the attempt stopped,
  available time, reversible cost, deadline.
- **Diagnosis buckets**: unclear target, missing skill, emotional/physical load, oversized
  step, missing permission/resource, weak expected value, avoidance of evidence, or no
  consequence for delay. Do not infer a clinical condition.
- **Method**: reconstruct the last failed sequence; identify the earliest observable break;
  reduce the next action to 15-60 minutes; remove one friction; define visible completion;
  schedule one check-in and a stop/replan threshold.
- **Output**: friction hypothesis with confidence, smallest action, environment change,
  check-in question, stop condition.
- **Stop**: two attempts without new evidence become `blocked` or route to goal/business
  diagnosis. Repeating encouragement is not progress.

## Feedback-Driven Learning (`personal.learning`)

- **Trigger**: learn a business, product, communication, reasoning, or execution skill.
- **Required slots**: target performance, current baseline, real use case, available time,
  feedback source.
- **Method**: define a performance task; select one small concept; require retrieval or
  application; compare output against criteria; record error type; choose the next lesson
  from observed error rather than a fixed curriculum.
- **Output**: learning card, one exercise, rubric, feedback request, next-lesson gate.
- **Memory**: propose only demonstrated capability or stable learning preference. Never
  infer intelligence, personality, or health.

## Durable Decisions (`decision.record`)

- **Trigger**: a consequential choice, rejected option, or experiment result worth revisiting.
- **Required slots**: decision, options, evidence, assumptions, cost, reversibility, owner,
  review date, outcome metric.
- **Method**: distinguish choice from rationale; record rejected options fairly; define what
  evidence would reverse the decision; assign review date and result owner.
- **Output**: a `decision_record` artifact with `status: proposed|confirmed` and a record
  conforming to `templates/decision-record.json`. Use `confirmed` only when
  `confirmation_ref` points to explicit `user_input` evidence. Otherwise keep it `proposed`
  and do not say the decision was made or recorded.
- **Write gate**: preview exact path and record; write only after confirmation. Use a new
  version to amend; never overwrite the original rationale.

## Save, Restore, and Report

### `decision.save`

Extract only confirmed facts, accepted judgments, rejected options, active experiments,
blockers, next action, and stop condition. Present the complete proposed snapshot and
destination before a local write. Assign `state_version` and `parent_hash`.

### `decision.restore`

Read only the approved project namespace. Show snapshot timestamp, version, staleness,
confirmed facts, open assumptions, and last user-confirmed next action. Do not treat old
assumptions as current facts; ask one question if staleness changes the route.

### `decision.report`

Join immutable decision records by date and project. Separate decisions, experiments,
outcomes, changed assumptions, and unresolved items. Deduplicate by record ID, not prose.
Reporting is read-only unless the user approves an exact output path.

## Content Direction (`content.plan`)

- **Trigger**: topic selection, content direction, series planning, or adapting a business
  insight into content.
- **Required slots**: business objective, target audience, audience situation, factual
  anchor, platform/format, desired response, prohibited claims.
- **Method**: identify the audience's current tension; connect one verified mechanism to one
  useful outcome; select format; state proof needed; propose 3-5 angles; rank by relevance,
  evidence strength, distinctiveness, effort, and business fit.
- **Output**: ranked angle table and one selected brief. No draft when the factual anchor is
  missing.

## Hook and Title (`content.hook`, `content.title`)

- **Trigger**: an existing topic or draft needs an opening/title.
- **Required slots**: concrete topic, audience, proof, platform, prohibited claims.
- **Method**: name the current hook failure; generate variants using tension, result,
  contradiction, question, or specific scene; score clarity, truthfulness, audience fit, and
  continuity with the body.
- **Output**: top three with why each fits and what claim must be supported.
- **Guard**: no fabricated number, urgency, authority, identity, guarantee, or personal event.

## Script Logic and Resonance (`content.script`, `content.resonate`)

- **Trigger**: a completed or partial script needs logic, pacing, or audience fit review.
- **Method**: segment claims; map premise -> evidence -> inference -> implication; locate
  unsupported jumps and duplicate sections; identify audience situation, emotion, desired
  progress, and credible stance; propose minimum edits before a rewrite.
- **Output (`content.script`)**: an artifact with `logic_map`, `highest_loss_point`, and
  `edit_plan`, plus revised text only when requested.
- **Output (`content.resonate`)**: audience-situation and stance findings, the highest-loss
  resonance point, and minimum edits. Keep this separate from the script Handoff.
- **Guard**: resonance is a hypothesis until tested with audience behavior.

When the user explicitly asks for `title + script + resonate + publish-check`, run those
four leaf playbooks in order against the same frozen packet and emit four independent
Handoffs. Synthesize their results only in the final prose; do not report a second leaf as
completed inside another leaf's Handoff.

## Publish Check (`content.publish_check`)

Follow `content-safety.md`. Produce exactly three sections: machine-visible signals,
substantive issues, and human review. Platform and region must be explicit user facts; if
either is absent, clarify before making platform-specific judgments. Record platform, region,
source/policy date, unavailable media context, and confidence. A platform-rule claim requires
current policy evidence; otherwise mark it `unverified` and place it under human review.
Drafting and checking never authorize publication and must not create a publish approval.
`approvals` may contain only a real user approval for the exact object and scope represented.

## Folder Knowledge Base (`governance.knowledge`)

- **Trigger**: index, search, ingest, deduplicate, version, or audit an approved folder.
- **Required slots**: exact root, operation, allowed file types, exclusions, source-of-truth
  rule, write consent.
- **Read-only flow**: inventory paths and sizes; detect likely versions, duplicates, broken
  links, sensitive files, and generated artifacts; propose taxonomy and canonical records.
  When search is required, run `scripts/knowledge_runtime.py folder-index` in preview
  mode, then search only a current hash-verified index.
- **Write flow**: preview the exact index target, changes, resulting index hash, and
  confirmation hash; require that same hash for `folder-index --commit`. Re-preview
  after any source, option, target, or prior-index change. Use atomic writes and
  preserve source files. Moves, deletion, or source rewriting remain separate
  approvals and are not performed by the indexer.
- **KnowledgePack flow**: default to public/released rights. Use `--mode private` only for
  an explicitly authorized local candidate pack. Return atom IDs, source edges, confidence,
  limits, conflicts, and freshness; retrieval is evidence selection, not a final claim.
- **Output**: inventory, risks, index preview or committed index hash, search results,
  version rules, unresolved ownership, and Recall@5 evidence when evaluating a pack.

## Content Assets and Multi-Agent Workbench (`governance.workbench`)

- **Trigger**: one knowledge/content source must serve multiple agents or clients.
- **Required slots**: canonical root, consumers, supported capabilities, format constraints,
  ownership, sync direction.
- **Method**: choose one canonical source; define thin read-only adapters; version asset
  and task/atom schemas; pin releases; test discovery and handoff contracts per consumer;
  prohibit two-way silent mutation. Use `scripts/workbench_runtime.py plan`, show its exact
  target set and confirmation hash, then call `apply` with the matching state version and
  finish with `verify`.
- **Output**: source-of-truth map, versioned asset index, adapter contracts, consumer
  capability/version matrix, bridge manifests, drift checks, and rollback manifest.
- **Boundary**: local manifest verification proves paths and contracts, not that a specific
  Agent product actually discovered, loaded, or honored the bridge. Test each real consumer
  separately before claiming integration.

## Local Skill Audit (`governance.audit_skill`)

- **Trigger**: inspect a local Skill for task hijacking, data access, external calls,
  destructive actions, advertising, credential handling, or hidden authority claims.
- **Default**: read-only. Resolve exact Skill path and symlinks before scanning.
- **Method**: inventory files; inspect frontmatter and all reachable instructions/scripts;
  classify file/network/process/data actions; find prompt injection, secret/PII reads,
  obfuscated execution, affiliate/advertising behavior, broad deletion, and undeclared writes;
  cite file and line for every finding; distinguish active path from dead example text.
- **Output**: severity, evidence location, exploit condition, impact, and minimal remediation.
- **Action gate**: quarantine, unlink, edit, or delete only after the user confirms exact
  targets and recovery plan.
- `scripts/audit_skill.py` is the deterministic read-only baseline scanner. It inventories
  text files, records hashes, emits line-level heuristic findings, and always reports
  `side_effects: []`; it is a signal generator, not a malware verdict. Run a deeper review
  when code, obfuscation, symlinks, credentials, or high-severity findings are present.

## Next Signals

- `needs_goal`: acceptance is not observable.
- `needs_business_evidence`: content/action rests on an unverified business assumption.
- `needs_publish_check`: a draft is ready but platform risk is unresolved.
- `needs_decision`: a choice or outcome should be recorded.
- `needs_knowledge_governance`: source ownership or versioning blocks retrieval.
- `needs_human_review`: legal, medical, financial, regulated, or platform uncertainty remains.
