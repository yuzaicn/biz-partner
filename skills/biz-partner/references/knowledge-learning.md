# User-private knowledge learning

This workflow turns an Agent-produced change-set into a versioned local
KnowledgePack. It does not train model weights or let source material change
the Skill. `analyze`, `plan-apply`, `verify`, and `search` are read-only.
`apply` and `rollback` write only to the exact user-private pack passed with
`--pack`.

The target is deliberately narrow. It must be an absolute path shaped as
`<project>/.biz-partner/knowledge-packs/<pack-id>`, and `<pack-id>` must match
`target.pack_id`. Broad paths, paths inside the installed Skill, symlink
targets, and existing non-directories are rejected.

## Boundary

- Use the existing `/biz knowledge` task. Do not add another role or router.
- The Agent reads the material and writes the candidate change-set. The script
  does not call a model or fetch a URL.
- A live URL is not frozen evidence. Capture the material separately, retain
  its URL, capture time, and content hash in a private source record, then let
  the Agent create candidates from that snapshot.
- Every candidate is `operation: add`. IDs use `user_source_`, `user_atom_`,
  `user_concept_`, `user_method_`, or `user_case_`; public IDs cannot be
  overwritten.
- New sources and records remain private-only and non-published. User approval
  authorizes storage; it does not prove a claim, effectiveness, rights, or
  public-release eligibility.
- Conversation text is a user claim, not external fact. An atom based on a
  conversation source must remain a `user_claim`, `user_observation`, or
  `hypothesis`.
- The bundled `public-knowledge` directory is read only. This workflow has no
  publish, network-write, Git, or GitHub command.

`concept_kind: operational_dictionary` is the working dictionary. Other
concepts remain ordinary concept rows. Controlled meaning comes from aliases,
atom links, method links, and the existing `supports`, `contradicts`,
`refines`, and `depends_on` relations; this workflow does not add embeddings or
another semantic store.

## Candidate and decision files

Start from `templates/knowledge-change-set.json`. It contains one worked row for
every supported candidate kind: source, atom, concept, method, atom relation,
and retrieval case. Replace its project path, source path, wording, IDs, dates,
and hashes with values from the exact material; do not treat the example hashes
as evidence for new content. `references/schemas/knowledge-change-set.schema.json`
is authoritative for the outer document. `analyze`, the record validators, and
Atom v2 define the concrete source, atom, concept, method, relation, and retrieval
case contracts. `analyze` also reports exact duplicates, bounded lexical near
matches, concept alias collisions, dependency cycles, credentials, unnecessary
personal data, private-rights failures, and a stale target base.

The report keeps `ready_for_plan` for existing callers and also separates two
questions. `structurally_ready` covers the change-set contract, graph, rights,
duplicates, and base revision. `evidence_verification` reports `verified`,
`failed`, `unverified`, or `not_applicable`. For an absolute local `file`
locator, `analyze` reads the file and compares its SHA-256 with the referenced
source record. Only after that whole-file hash matches, it parses `locator.lines`
as a one-based inclusive range, splits the file using its original line breaks,
joins the selected lines with `\n`, and compares that UTF-8 SHA-256 with
`quote_hash`. A missing, unreadable, non-UTF-8, hash-mismatched, malformed, or
out-of-bounds locator is `failed` and cannot be planned. This proves byte and
locator consistency only; it is not a semantic, factual, or rights review.
Relative files without a declared root, live URLs, and conversation or session
sources remain `unverified`; the script does not fetch or promote them.
`ready_for_plan` is true only when the structure is ready and evidence
verification has not failed.

The change-set itself has no final-review status. Use
`templates/knowledge-decisions.json` to record one `accept`, `reject`, or
`defer` decision for every candidate. Each decision binds the complete
change-set hash and that candidate's exact hash. Editing the base, target,
candidate, or decision invalidates the old plan. When `expires_at` is present,
the change-set stops working at that time and must be regenerated.
The example decisions file covers all seven current example candidates. After
changing any candidate, run `analyze` again and copy its new `change_set_hash`
and every reported `candidate_hash` into the decisions file; stale or guessed
hashes are not reusable.

An `atom_relation` candidate may only add a relation to an atom added in the
same accepted change-set. This preserves add-only behavior; existing atoms are
never patched in place. Cross-pack targets are not accepted by this version.

## Commands

Run from the Skill root. Paths must be absolute.

```bash
python3 scripts/knowledge_learning.py analyze \
  --pack /absolute/project/.biz-partner/knowledge-packs/my-business \
  --change-set /absolute/change-set.json

python3 scripts/knowledge_learning.py plan-apply \
  --pack /absolute/project/.biz-partner/knowledge-packs/my-business \
  --change-set /absolute/change-set.json \
  --decisions /absolute/decisions.json
```

Show the complete plan to the user. Only after explicit approval of that exact
preview, pass its revision and confirmation hash:

```bash
python3 scripts/knowledge_learning.py apply \
  --pack /absolute/project/.biz-partner/knowledge-packs/my-business \
  --change-set /absolute/change-set.json \
  --decisions /absolute/decisions.json \
  --expected-revision 0 \
  --confirmation-hash sha256:...
```

Changing the active revision, target, candidates, decisions, or result hashes
causes the command to fail closed. Before confirmation, the target pack is not
created. An accepted version is written to `versions/vNNNNNN`, checked through
the existing KnowledgePack private loader, and activated by an atomic
`active.json` replacement. Before writing, both `versions` and the target
`vNNNNNN` are rejected if they are symbolic links, and their resolved paths
must remain inside the pack's `versions` directory.

The first confirmed write also creates a fixed `.gitignore` inside the pack. It
keeps the private versions out of an ordinary `git add .`. It does not protect
against `git add -f`, backup tools, cloud-drive sync, or manual copying, so raw
private material still belongs outside the repository and needs its own access
controls.

Verify and search the active revision:

```bash
python3 scripts/knowledge_learning.py verify \
  --pack /absolute/project/.biz-partner/knowledge-packs/my-business
python3 scripts/knowledge_learning.py search \
  --pack /absolute/project/.biz-partner/knowledge-packs/my-business \
  --query '客户为什么不愿意付费' --limit 5
```

Plan and confirm a rollback separately:

```bash
python3 scripts/knowledge_learning.py plan-rollback \
  --pack /absolute/project/.biz-partner/knowledge-packs/my-business \
  --to-revision 0
python3 scripts/knowledge_learning.py rollback \
  --pack /absolute/project/.biz-partner/knowledge-packs/my-business \
  --to-revision 0 \
  --expected-revision 3 --confirmation-hash sha256:...
```

Rollback never deletes history. It creates the next revision with the selected
older content and records `restores_revision` in both its manifest and active
pointer. Revision `0` means the empty state before the first write; restoring it
creates a new revision containing five empty JSONL files and keeps every older
version directory intact. Verification requires a revision-0 rollback to carry
the empty-file SHA-256 for all five files and zero for every count. A rollback
to revision `N` must reproduce exactly the `files` and `counts` maps in revision
`N`'s manifest.

## Version layout

```text
<project>/.biz-partner/knowledge-packs/my-business/
  .gitignore
  active.json
  versions/
    v000001/
      sources.jsonl
      atoms.jsonl
      concepts.jsonl
      methods.jsonl
      retrieval-cases.jsonl
      manifest.json
```

Every manifest binds the five JSONL hashes, record counts, parent revision,
parent manifest hash, action, change-set hash, and decision hash. The active
pointer binds the exact latest manifest. Verification walks the hash-linked
manifest chain back to the first revision. A stale concurrent writer or edited
older manifest becomes a conflict and cannot replace the active version.
