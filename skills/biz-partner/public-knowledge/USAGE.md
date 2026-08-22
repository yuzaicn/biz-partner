# Public Knowledge Pack

This built-in pack contains independently worded knowledge atoms, methods, and
concept definitions. It contains no book text, source-post text, raw capture,
review ledger, local path, or personal runtime memory.

## Retrieval

Use public mode only:

```bash
python3 scripts/knowledge_runtime.py pack-search \
  --sources public-knowledge/sources.jsonl \
  --atoms public-knowledge/atoms.jsonl \
  --query '客户为什么不愿意付费' \
  --limit 5
```

Read `methods.md` when a retrieved atom needs a multi-step workflow. Read
`concept-dictionary.md` when a term needs clarification or contrast. Read
`book-metadata.md` for the ten registered titles, authors, and public projection counts.

## Attribution and identity

Pass materially used atom IDs into the Handoff evidence graph and resolve them
through `scripts/render_source_attribution.py`. Attribute only sources that
materially support a rendered claim. A named author or maintainer is always an
external source and must never be inferred as the runtime user.

## Rights boundary

The repository license covers this pack's original paraphrases and compilation.
It does not grant rights to source-book text, illustrations, tables, examples,
or other source expression. Do not reconstruct or quote excluded source material.
