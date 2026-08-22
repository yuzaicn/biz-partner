# Source Attribution

## Input modes

This public runtime accepts only sources and atoms whose status is
`release_eligible` or `published` and whose rights explicitly allow
redistribution. Sources must provide a license object with non-empty `id`,
`version`, and an allowed redistribution scope; atoms provide the same object
under `rights.license`. Candidate, private, blocked, unresolved, unknown,
rights-pending, unlicensed, or structurally incomplete records fail closed. The
public API and CLI expose only public-release inputs.

If `authorization_status` or `release_decision` is present, it must use an
explicit public-release approval value accepted by the resolver. Unknown,
negative, revoked, or merely non-blocking text fails closed; the resolver does
not infer approval from the absence of a denial word.

Every named source must declare:

- `attribution_mode: when_materially_used`
- `relationship_to_runtime_user: external_named_source`
- `ownership_status: not_claimed`

These are validation fields, not prose templates. They prevent an author, account,
or maintainer from being inferred as the runtime user or as user-owned material.

## Decision rule

Attribute a named source only when at least one of its registered atoms materially
supports the current judgment, method, example, or proposed test. Background
retrieval, route selection, or an unused search result does not trigger a mention.

## Rendering

1. Resolve `claim.supporting_refs` to evidence with `evidence_kind: knowledge_atom`
   and `atom_id`; verify that atom's `source_refs[].source_id` through the source registry.
2. Separate user facts, current external evidence, author claims, and model synthesis.
3. If a source uses `attribution_mode: when_materially_used`, name it once near the
   first materially supported claim. Group adjacent claims from the same source.
4. State the boundary when it matters: an author-derived rule is a perspective or
   candidate method until current customer or outcome evidence validates it.
5. Keep source IDs and atom IDs in structured evidence; do not fill the prose with
   locator mechanics unless the user asks for an audit trail.

The resolver validates the complete registry, atom graph, evidence list, and claim
list before rendering. Unknown source IDs on knowledge-atom evidence, unknown atom
IDs, broken supporting refs, duplicate source/atom/evidence/claim IDs, duplicate
claim refs, malformed rows, missing atom provenance, and atom/source mismatch all
fail closed. It does not silently skip bad records. Non-atom evidence may retain a
Handoff-local source such as a user turn or tool result.

Each resolver-bound segment contains `source_id`,
`source_role: external_named_source`, `claim_ids`, `evidence_ids`, `atom_ids`, and
`first_claim_id`. Use `first_claim_id` to place one natural mention near the first
materially supported claim; retain the remaining IDs as the audit trail.

The final renderer must represent source attribution as typed segments before
joining them into prose:

```text
source_attribution {
  source_id
  source_role
  first_claim_id
  claim_ids
  evidence_ids
  atom_ids
  text
}
```

Use `material_attribution_segments()` or the CLI `attribution_segments` output to
resolve and build these segments in one registry-bound operation. Insert each
segment next to its `first_claim_id`; do not call a standalone renderer or
regenerate attribution text from free-form source labels.

Apply these machine-checkable assertions:

1. The set of segment `source_id` values equals the resolver's attribution set.
2. There is exactly one segment for each returned source and no segment for an
   unreturned source.
3. Each segment's `first_claim_id` is the first claim supported by the resolved source.
4. The segment text uses the registry attribution name exactly once and keeps
   `source_role: external_named_source` outside user facts and durable memory.
5. Named-source attribution text may enter final prose only through these segments.
   A name present in quoted user text or an audit trail must stay typed as that
   non-attribution role and cannot satisfy an attribution assertion.

Render the name from the registry's `public_attribution_name`; do not hard-code
maintainer names in this rule. A concise pattern is “This judgment draws on
{public_attribution_name}'s perspective; whether it fits your case still depends
on current evidence.” Adapt the wording to the answer rather than using a fixed
signature.

## Prohibitions

- Do not infer that the runtime user is any named source, maintainer, or source owner.
- Do not attribute a named source from a free-form source label, missing atom ID,
  unknown atom, duplicate evidence ID, or atom/source mismatch.
- Do not turn a source author's experience into the user's biography, preference,
  capability, result, or durable memory.
- Do not name a source merely for branding, authority, or repetition.
- Do not present paraphrases as quotations or author views as universal facts.
- Do not expose private locators, raw excerpts, source-specific history, or build-only
  evidence in a public-facing response.
