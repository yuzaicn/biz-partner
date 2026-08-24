# Memory Governance

## Separate Namespaces

```text
global_policy       immutable safety and tool policy
user_profile        preferences, skills, constraints
project_state       current business, goals, experiments
decision_log        choices, evidence, costs, outcomes, review dates
asset_index         files, content units, source versions
playbook_feedback   observed usefulness of prompts and actions
```

Never merge author-derived knowledge into user facts or infer that a runtime user
is a named source author. A user observation is provisional until confirmed or
supported by repeated behavior/outcome evidence. Source attribution belongs in
evidence metadata, not `user_profile`.

## Proposal Lifecycle

`observed -> proposed -> user_confirmed -> active -> stale/retired`

Every proposal carries scope, consent, source, confidence, created time, last validation, expiry/decay, and deletion key. User deletion creates a suppression record so retrieval cannot resurrect the item.

All ordinary reads use an active-state projection. A record is inactive when its
timezone-aware `expires_at` is at or before the read time, or when a tombstone
matches its namespace and subject. This rule applies equally to `user_profile`,
`project_state`, `decision_log`, `asset_index`, and `playbook_feedback`.
Suppression removes matching records from the current materialized state and the
read filter also protects older databases where list records remain. The
tombstone keeps only namespace, subject, deletion key, operation, and time; it
does not copy the deleted value. Historical values may remain in the immutable
event log for integrity replay, so suppression is a retrieval guarantee rather
than a physical-erasure claim.

For list-shaped namespaces (`decision_log`, `asset_index`, and
`playbook_feedback`), `supersede` replaces the current record with the same
subject. Ordinary current-state reads therefore return only the newest record
for that subject, while earlier commits remain in the immutable event history.
After a suppression, a newly confirmed `add` or `supersede` for that namespace
and subject removes the old tombstone from the current projection so the new
value can become active. The earlier tombstone remains in its historical event.

“Evolution” may update confirmed, versioned profile and playbook observations.
`scripts/adaptive_context.py` projects only confirmed, active records into an
advisory conversation context: profile constraints, cadence/style preferences,
project context, decisions, assets, and playbook feedback. This context may
shape questions, explanations, sequencing, and suggested experiments. It may
not rewrite the Skill, change safety policy, expand tool permissions, alter
source attribution, or decide the final route automatically.

## Local Commit Protocol

The proposal shape is frozen in `references/schemas/memory-proposal.schema.json`.
Use `templates/profile-proposal.json` as the editable preview template; it never
counts as confirmation by itself.
For a user-approved project folder, `scripts/state_store.py` implements the local
commit sequence:

1. `plan-init <root>` or `plan-commit <root> <proposal.json>` prints the exact
   target, payload preview, state version, and confirmation hash without writing.
2. Show that preview to the user and obtain confirmation for that exact payload.
3. Call `init` or `commit` with the matching hash. `commit` also requires the
   expected state version and confirmation timestamp. The timestamp must be at
   or after both the proposal's `created_at` and the current state's
   `updated_at`; a confirmation cannot predate its proposal and time cannot move
   backwards.
4. The script writes only `<root>/.biz-partner`, uses an exclusive lock and atomic
   state replacement, increments `state_version`, and appends an audit event.
   The `.biz-partner` directory and `state.sqlite3` must be real paths inside the
   resolved project root; either path being a symbolic link is rejected.
5. A stale version becomes a conflict. A changed proposal produces a different
   confirmation hash and must be confirmed again.

`show` and `export` return the active-state projection by default. Pass an
explicit `--as-of` timestamp for reproducible historical visibility checks.
Historical reads first replay the latest committed event at or before that
instant, so later commits are not visible, and only then apply expiry and
suppression to the replayed state. An `--as-of` earlier than state initialization
is rejected because no project state existed yet.
`adaptive_context.py <root> [--as-of TIMESTAMP]` uses the same projection and
writes no state. `plan-commit` is only a preview: until the exact hash is
confirmed and `commit` succeeds, the proposal cannot appear in adaptive context.

The script is a storage primitive, not proof of human consent. The calling agent
must not invoke a write command unless the current conversation contains explicit
approval. Never put raw credentials, health details, private financial data, or
unnecessary PII into a proposal.
