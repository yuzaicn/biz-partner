# Workbench Runtime

Use `scripts/workbench_runtime.py` when one approved canonical content root must
serve multiple local Agent or application roots without copying the private
knowledge body into each consumer.

## Configuration Boundary

Start from `templates/workbench-config.json`. Declare absolute canonical and
consumer roots, an owner for each root, every canonical asset as a relative
path with a version and classification, each consumer discovery path,
capabilities, consumer version, and supported workbench schema versions.

Choose `canonical_to_consumer` or `manual_read_only` as `sync_direction`.
Adapters default to `read_only`; any writable adapter or bidirectional direction
fails closed. This runtime creates manifests and contracts only. It is not an
installer for a named Agent product and does not claim that a consumer can use a
capability merely because it was listed in configuration.

## Confirmed Apply Protocol

Run:

```bash
python3 scripts/workbench_runtime.py plan /absolute/path/workbench-config.json
```

`plan` performs no writes. It emits the canonical root and owner, current and
next versions, directories, manifests, adapter contracts, discovery targets,
pre-existing target hashes, and a confirmation hash. Show this exact plan to the
user. After confirmation, bind both values from that plan:

```bash
python3 scripts/workbench_runtime.py apply /absolute/path/workbench-config.json \
  --expected-version 0 \
  --confirmation-hash sha256:...
```

Changing configuration, source asset content, a managed bridge, or the current
workbench version changes the plan and invalidates the confirmation hash.
Writes use same-directory temporary files, `fsync`, and atomic replacement.
The current manifest is replaced last. On an apply failure, mutable bridge and
manifest targets are restored; an incomplete new release is removed.

## Generated Layout

The canonical root receives only `.biz-partner-workbench/`:

```text
.biz-partner-workbench/
  manifest.json
  releases/v000001/
    asset-index.json
    consumer-matrix.json
    release-manifest.json
    adapters/<consumer-id>.json
  rollback/v000001.json
```

The asset index stores path, declared version, classification, size, and SHA-256,
not file contents. Adapter contracts freeze ownership, capability/version
claims, read-only mode, single direction, allowed reads, and forbidden writes.
The consumer matrix records compatibility claims for independent verification.

Each consumer receives only the configured thin bridge manifest. It contains
the canonical root and hash plus paths and hashes for the asset index and
adapter contract. It does not contain the asset list or private source body.
Rollback manifests preserve the previous version and release pointer, target
preconditions, and the deterministic restoration strategy. Previous canonical
releases remain versioned and are not overwritten.

## Verification

Run:

```bash
python3 scripts/workbench_runtime.py verify /absolute/path/workbench-config.json
```

Verification is read-only. It recomputes canonical source hashes and checks the
current manifest, asset index, release manifest, adapter contracts, capability
matrix, discovery paths, schema and workbench versions, thin bridge hashes, and
exact generated-document drift. It rejects bridge or adapter paths that escape
their declared root through symlinks and reports `PASS` or `FAIL` separately for
the canonical workbench and every consumer.

A `PASS` proves only that this local manifest contract is internally consistent
at verification time. It does not prove that every external Agent product has
loaded the bridge, supports all advertised capabilities, or will preserve the
contract after its own upgrade. Validate those product-specific behaviors
separately without adding silent writes to this runtime.
