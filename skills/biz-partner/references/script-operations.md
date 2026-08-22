# Script Operations

`route_task.py` is the deterministic pre-router backed by
`references/task-specs.jsonl`. `freeze_contract_bundle.py` fills the actual
CasePacket hash, binds the Handoff lease, and validates the bundle without
persisting input. `validate_tasks.py`, `validate_contracts.py`, and
`validate_debate.py` validate the open runtime contracts and fixtures.

`state_store.py` provides a consent-gated SQLite project state store. Preview the
exact target and confirmation hash before every write. Commits use state-version
compare-and-swap and append-only events.

`adaptive_context.py <approved-project> [--as-of TIMESTAMP]` reads only confirmed,
active project records and returns advisory context. Expired or suppressed records
do not influence later context, and the result cannot choose a route or expand
permissions.

`knowledge_runtime.py` supports allowlisted local folder indexing/search and an
optional external KnowledgePack. Public pack mode is the default and fails closed
unless source and atom records carry explicit public redistribution rights and the
shared Atom v2 provenance contract. Folder-index previews emit a confirmation hash;
commits require that exact hash and fail if sources or options changed. Search
verifies the source hash.

`workbench_runtime.py` implements `plan -> confirmed apply -> verify` for a
canonical content root and read-only consumer bridge manifests. Bind both the
expected version and confirmation hash emitted by `plan`; product-specific bridge
loading remains a separate verification responsibility.

`audit_skill.py <exact-skill-path>` is read-only. It inventories files and emits
heuristic findings without executing or changing the audited Skill.

`render_source_attribution.py <source-registry.jsonl> <atoms.jsonl> <handoff.json>`
deterministically returns only registered sources whose registered atoms materially
support final Handoff claims. Both the source and atom must be release-eligible or
published and carry an explicit license ID, version, redistribution scope, and
redistribution rights. It rejects missing atom
provenance, duplicate evidence IDs, atom/source mismatches, and any optional
authorization or release-decision field that is not an explicit approved value.
Unused sources and runtime-user facts do not trigger attribution. This public
build has no maintainer-only source override. The CLI returns only resolver-bound typed
attribution segments; no standalone renderer accepts caller-supplied source labels.

The bundled regression suites cover routing and contracts plus state adaptation,
folder/KnowledgePack retrieval, public-pack field and privacy gates, material-use
attribution, and workbench plan/apply/verify behavior. The built-in retrieval
fixture contains only questions and relevant atom IDs, never answer text.

`validate_public_runtime.py <skill-path>` rejects private source artifacts,
machine-local paths, private source locators, bytecode, symlinks, and broken local
Markdown links from an open-runtime package.
