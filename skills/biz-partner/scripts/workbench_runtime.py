#!/usr/bin/env python3
"""Plan, apply, and verify a local canonical multi-consumer workbench."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


CONFIG_SCHEMA = "biz-partner.workbench-config/v1"
WORKBENCH_SCHEMA = "biz-partner.workbench/v1"
ASSET_INDEX_SCHEMA = "biz-partner.asset-index/v1"
ADAPTER_SCHEMA = "biz-partner.adapter-contract/v1"
MATRIX_SCHEMA = "biz-partner.consumer-matrix/v1"
BRIDGE_SCHEMA = "biz-partner.bridge/v1"
ROLLBACK_SCHEMA = "biz-partner.rollback-manifest/v1"
WORKBENCH_DIR = ".biz-partner-workbench"
SUPPORTED_SCHEMA_VERSION = "1.0"
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")


class WorkbenchError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return "sha256:" + hasher.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkbenchError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkbenchError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkbenchError(f"JSON root must be an object: {path}")
    return value


def resolve_root(raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise WorkbenchError(f"{label} must be a non-empty absolute path")
    configured = Path(raw).expanduser()
    if not configured.is_absolute():
        raise WorkbenchError(f"{label} must be an absolute path: {configured}")
    if configured.is_symlink():
        raise WorkbenchError(f"{label} must not itself be a symlink: {configured}")
    resolved = configured.resolve()
    if not resolved.is_dir():
        raise WorkbenchError(f"{label} must be an existing directory: {resolved}")
    return resolved


def relative_path(raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise WorkbenchError(f"{label} must be a non-empty relative path")
    value = Path(raw)
    if value.is_absolute() or any(part in {"", ".", ".."} for part in value.parts):
        raise WorkbenchError(f"{label} must be a normalized relative path: {raw}")
    return value


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def safe_target(root: Path, relative: Path, label: str) -> Path:
    target = root / relative
    resolved = target.resolve(strict=False)
    if not is_within(resolved, root):
        raise WorkbenchError(f"{label} escapes its declared root through a symlink: {target}")
    return target


def strict_fields(value: dict[str, Any], allowed: set[str], label: str) -> None:
    extras = sorted(set(value) - allowed)
    if extras:
        raise WorkbenchError(f"{label} has unexpected fields: {', '.join(extras)}")


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise WorkbenchError(f"{label} must be a non-empty list")
    if not all(isinstance(item, str) and item for item in value):
        raise WorkbenchError(f"{label} must contain non-empty strings")
    if len(set(value)) != len(value):
        raise WorkbenchError(f"{label} must not contain duplicates")
    return sorted(value)


def normalized_config(
    config_path: Path,
    *,
    enforce_consumer_boundaries: bool = True,
) -> dict[str, Any]:
    raw = load_json(config_path)
    strict_fields(
        raw,
        {
            "schema",
            "schema_version",
            "canonical_root",
            "canonical_owner",
            "sync_direction",
            "assets",
            "consumers",
        },
        "config",
    )
    if raw.get("schema") != CONFIG_SCHEMA:
        raise WorkbenchError(f"config schema must be {CONFIG_SCHEMA}")
    if raw.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise WorkbenchError(f"config schema_version must be {SUPPORTED_SCHEMA_VERSION}")
    canonical_root = resolve_root(raw.get("canonical_root"), "canonical_root")
    canonical_owner = raw.get("canonical_owner")
    if not isinstance(canonical_owner, str) or not canonical_owner:
        raise WorkbenchError("canonical_owner must be a non-empty string")
    sync_direction = raw.get("sync_direction")
    if sync_direction not in {"canonical_to_consumer", "manual_read_only"}:
        raise WorkbenchError(
            "sync_direction must be canonical_to_consumer or manual_read_only; "
            "bidirectional sync is not supported"
        )

    assets_raw = raw.get("assets")
    if not isinstance(assets_raw, list) or not assets_raw:
        raise WorkbenchError("assets must be a non-empty list")
    assets: list[dict[str, Any]] = []
    asset_ids: set[str] = set()
    asset_paths: set[str] = set()
    for index, item in enumerate(assets_raw):
        if not isinstance(item, dict):
            raise WorkbenchError(f"assets[{index}] must be an object")
        strict_fields(item, {"id", "path", "version", "classification"}, f"assets[{index}]")
        asset_id = item.get("id")
        if not isinstance(asset_id, str) or not ID_PATTERN.fullmatch(asset_id):
            raise WorkbenchError(f"assets[{index}].id is invalid")
        if asset_id in asset_ids:
            raise WorkbenchError(f"duplicate asset id: {asset_id}")
        asset_ids.add(asset_id)
        source_relative = relative_path(item.get("path"), f"assets[{index}].path")
        if source_relative.parts[0] == WORKBENCH_DIR:
            raise WorkbenchError("canonical assets cannot be inside the generated workbench directory")
        source = safe_target(canonical_root, source_relative, f"assets[{index}].path")
        if not source.is_file():
            raise WorkbenchError(f"canonical asset must be an existing file: {source}")
        if source.is_symlink():
            raise WorkbenchError(f"canonical asset must not itself be a symlink: {source}")
        source_key = source_relative.as_posix()
        if source_key in asset_paths:
            raise WorkbenchError(f"duplicate asset path: {source_key}")
        asset_paths.add(source_key)
        version = item.get("version")
        if not isinstance(version, str) or not version:
            raise WorkbenchError(f"assets[{index}].version must be a non-empty string")
        classification = item.get("classification")
        if classification not in {"private", "internal", "public"}:
            raise WorkbenchError(
                f"assets[{index}].classification must be private, internal, or public"
            )
        assets.append(
            {
                "id": asset_id,
                "path": source_key,
                "version": version,
                "classification": classification,
                "size_bytes": source.stat().st_size,
                "content_hash": file_digest(source),
            }
        )

    consumers_raw = raw.get("consumers")
    if not isinstance(consumers_raw, list) or not consumers_raw:
        raise WorkbenchError("consumers must be a non-empty list")
    consumers: list[dict[str, Any]] = []
    consumer_ids: set[str] = set()
    discovery_targets: set[str] = set()
    for index, item in enumerate(consumers_raw):
        if not isinstance(item, dict):
            raise WorkbenchError(f"consumers[{index}] must be an object")
        strict_fields(
            item,
            {
                "id",
                "root",
                "owner",
                "discovery_path",
                "consumer_version",
                "capabilities",
                "supported_schema_versions",
                "adapter_mode",
            },
            f"consumers[{index}]",
        )
        consumer_id = item.get("id")
        if not isinstance(consumer_id, str) or not ID_PATTERN.fullmatch(consumer_id):
            raise WorkbenchError(f"consumers[{index}].id is invalid")
        if consumer_id in consumer_ids:
            raise WorkbenchError(f"duplicate consumer id: {consumer_id}")
        consumer_ids.add(consumer_id)
        consumer_root = resolve_root(item.get("root"), f"consumers[{index}].root")
        owner = item.get("owner")
        if not isinstance(owner, str) or not owner:
            raise WorkbenchError(f"consumers[{index}].owner must be a non-empty string")
        discovery_relative = relative_path(
            item.get("discovery_path"), f"consumers[{index}].discovery_path"
        )
        discovery = consumer_root / discovery_relative
        if enforce_consumer_boundaries:
            discovery = safe_target(
                consumer_root,
                discovery_relative,
                f"consumers[{index}].discovery_path",
            )
        discovery_key = str(discovery)
        if discovery_key in discovery_targets:
            raise WorkbenchError(f"duplicate consumer discovery target: {discovery}")
        discovery_targets.add(discovery_key)
        consumer_version = item.get("consumer_version")
        if not isinstance(consumer_version, str) or not consumer_version:
            raise WorkbenchError(f"consumers[{index}].consumer_version must be non-empty")
        capabilities = string_list(item.get("capabilities"), f"consumers[{index}].capabilities")
        supported = string_list(
            item.get("supported_schema_versions"),
            f"consumers[{index}].supported_schema_versions",
        )
        if SUPPORTED_SCHEMA_VERSION not in supported:
            raise WorkbenchError(
                f"consumer {consumer_id} does not support schema {SUPPORTED_SCHEMA_VERSION}"
            )
        adapter_mode = item.get("adapter_mode", "read_only")
        if adapter_mode != "read_only":
            raise WorkbenchError(f"consumer {consumer_id} adapter_mode must be read_only")
        consumers.append(
            {
                "id": consumer_id,
                "root": str(consumer_root),
                "owner": owner,
                "discovery_path": discovery_relative.as_posix(),
                "consumer_version": consumer_version,
                "capabilities": capabilities,
                "supported_schema_versions": supported,
                "adapter_mode": adapter_mode,
            }
        )

    normalized = {
        "schema": CONFIG_SCHEMA,
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "canonical_root": str(canonical_root),
        "canonical_owner": canonical_owner,
        "sync_direction": sync_direction,
        "assets": sorted(assets, key=lambda item: item["id"]),
        "consumers": sorted(consumers, key=lambda item: item["id"]),
    }
    return normalized


def workbench_paths(config: dict[str, Any], version: int) -> dict[str, Path]:
    canonical_root = Path(config["canonical_root"])
    workbench = safe_target(canonical_root, Path(WORKBENCH_DIR), "workbench directory")
    release = workbench / "releases" / f"v{version:06d}"
    return {
        "workbench": workbench,
        "current_manifest": workbench / "manifest.json",
        "release": release,
        "asset_index": release / "asset-index.json",
        "consumer_matrix": release / "consumer-matrix.json",
        "release_manifest": release / "release-manifest.json",
        "adapters": release / "adapters",
        "rollback": workbench / "rollback" / f"v{version:06d}.json",
    }


def current_manifest(config: dict[str, Any]) -> dict[str, Any] | None:
    path = workbench_paths(config, 1)["current_manifest"]
    if not path.exists():
        return None
    if path.is_symlink():
        raise WorkbenchError(f"current manifest must not be a symlink: {path}")
    value = load_json(path)
    if value.get("schema") != WORKBENCH_SCHEMA:
        raise WorkbenchError(f"unmanaged current manifest at {path}")
    if value.get("canonical_root") != config["canonical_root"]:
        raise WorkbenchError("current manifest canonical_root does not match config")
    version = value.get("workbench_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise WorkbenchError("current manifest has invalid workbench_version")
    return value


def precondition(path: Path) -> dict[str, Any]:
    if not path.exists() and not path.is_symlink():
        return {"path": str(path), "exists": False, "content_hash": None}
    if path.is_symlink():
        raise WorkbenchError(f"managed target must not be a symlink: {path}")
    if not path.is_file():
        raise WorkbenchError(f"managed target must be a regular file: {path}")
    return {"path": str(path), "exists": True, "content_hash": file_digest(path)}


def build_plan(config_path: Path) -> dict[str, Any]:
    config = normalized_config(config_path)
    previous = current_manifest(config)
    expected_version = previous["workbench_version"] if previous else 0
    next_version = expected_version + 1
    paths = workbench_paths(config, next_version)
    if paths["release"].exists() or paths["release"].is_symlink():
        raise WorkbenchError(f"next release path already exists: {paths['release']}")
    if paths["rollback"].exists() or paths["rollback"].is_symlink():
        raise WorkbenchError(f"next rollback manifest already exists: {paths['rollback']}")

    bridge_targets: list[Path] = []
    adapter_targets: list[Path] = []
    for consumer in config["consumers"]:
        consumer_root = Path(consumer["root"])
        bridge_target = safe_target(
            consumer_root,
            Path(consumer["discovery_path"]),
            f"consumer {consumer['id']} discovery_path",
        )
        managed_bridge_or_absent(bridge_target, consumer["id"])
        bridge_targets.append(bridge_target)
        adapter_targets.append(paths["adapters"] / f"{consumer['id']}.json")

    managed_targets = [paths["current_manifest"], paths["rollback"], *bridge_targets]
    plan = {
        "action": "apply_workbench",
        "config_path": str(config_path.resolve()),
        "config_hash": digest(config),
        "canonical_hash": digest({"assets": config["assets"]}),
        "canonical_root": config["canonical_root"],
        "canonical_owner": config["canonical_owner"],
        "sync_direction": config["sync_direction"],
        "expected_version": expected_version,
        "next_version": next_version,
        "directories": sorted(
            {
                str(paths["workbench"]),
                str(paths["release"]),
                str(paths["adapters"]),
                str(paths["rollback"].parent),
                *(str(path.parent) for path in bridge_targets),
            }
        ),
        "manifests": [
            str(paths["asset_index"]),
            str(paths["consumer_matrix"]),
            str(paths["release_manifest"]),
            str(paths["current_manifest"]),
            str(paths["rollback"]),
            *(str(path) for path in bridge_targets),
        ],
        "adapters": [
            {
                "consumer_id": consumer["id"],
                "mode": "read_only",
                "sync_direction": config["sync_direction"],
                "contract_path": str(target),
                "bridge_path": str(bridge),
            }
            for consumer, target, bridge in zip(
                config["consumers"], adapter_targets, bridge_targets, strict=True
            )
        ],
        "preconditions": [precondition(path) for path in managed_targets],
    }
    return {"plan": plan, "confirmation_hash": digest(plan)}


def generated_documents(config: dict[str, Any], version: int) -> dict[str, Any]:
    paths = workbench_paths(config, version)
    canonical_hash = digest({"assets": config["assets"]})
    asset_index = {
        "schema": ASSET_INDEX_SCHEMA,
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "workbench_version": version,
        "canonical_root": config["canonical_root"],
        "canonical_owner": config["canonical_owner"],
        "canonical_hash": canonical_hash,
        "assets": config["assets"],
    }
    adapters: dict[str, dict[str, Any]] = {}
    bridges: dict[str, dict[str, Any]] = {}
    for consumer in config["consumers"]:
        adapter = {
            "schema": ADAPTER_SCHEMA,
            "schema_version": SUPPORTED_SCHEMA_VERSION,
            "workbench_version": version,
            "consumer_id": consumer["id"],
            "consumer_root": consumer["root"],
            "consumer_owner": consumer["owner"],
            "canonical_root": config["canonical_root"],
            "canonical_owner": config["canonical_owner"],
            "canonical_hash": canonical_hash,
            "mode": "read_only",
            "sync_direction": config["sync_direction"],
            "allowed_actions": ["discover_manifest", "read_canonical_assets"],
            "forbidden_actions": [
                "bidirectional_sync",
                "write_canonical_assets",
                "write_consumer_assets",
            ],
            "capabilities": consumer["capabilities"],
            "consumer_version": consumer["consumer_version"],
            "supported_schema_versions": consumer["supported_schema_versions"],
        }
        adapter_path = paths["adapters"] / f"{consumer['id']}.json"
        adapter_hash = digest(adapter)
        adapters[consumer["id"]] = adapter
        bridges[consumer["id"]] = {
            "schema": BRIDGE_SCHEMA,
            "schema_version": SUPPORTED_SCHEMA_VERSION,
            "workbench_version": version,
            "consumer_id": consumer["id"],
            "canonical_root": config["canonical_root"],
            "canonical_hash": canonical_hash,
            "asset_index_path": str(paths["asset_index"]),
            "adapter_contract_path": str(adapter_path),
            "adapter_contract_hash": adapter_hash,
            "adapter_mode": "read_only",
            "sync_direction": config["sync_direction"],
        }
    matrix = {
        "schema": MATRIX_SCHEMA,
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "workbench_version": version,
        "canonical_hash": canonical_hash,
        "consumers": [
            {
                "id": consumer["id"],
                "owner": consumer["owner"],
                "consumer_version": consumer["consumer_version"],
                "capabilities": consumer["capabilities"],
                "supported_schema_versions": consumer["supported_schema_versions"],
                "adapter_mode": "read_only",
                "sync_direction": config["sync_direction"],
            }
            for consumer in config["consumers"]
        ],
    }
    release_files = {
        str(paths["asset_index"]): asset_index,
        str(paths["consumer_matrix"]): matrix,
        **{
            str(paths["adapters"] / f"{consumer_id}.json"): adapter
            for consumer_id, adapter in adapters.items()
        },
    }
    release_manifest = {
        "schema": WORKBENCH_SCHEMA,
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "workbench_version": version,
        "canonical_root": config["canonical_root"],
        "canonical_hash": canonical_hash,
        "files": [
            {"path": path, "content_hash": digest(document)}
            for path, document in sorted(release_files.items())
        ],
    }
    current = {
        "schema": WORKBENCH_SCHEMA,
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "workbench_version": version,
        "canonical_root": config["canonical_root"],
        "canonical_owner": config["canonical_owner"],
        "canonical_hash": canonical_hash,
        "config_hash": digest(config),
        "release_path": str(paths["release"]),
        "release_manifest_path": str(paths["release_manifest"]),
        "release_manifest_hash": digest(release_manifest),
        "sync_direction": config["sync_direction"],
    }
    return {
        "asset_index": asset_index,
        "adapters": adapters,
        "bridges": bridges,
        "consumer_matrix": matrix,
        "release_manifest": release_manifest,
        "current_manifest": current,
    }


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        handle.write(payload)
        handle.write(b"\n")
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except Exception:
        handle.close()
        temporary.unlink(missing_ok=True)
        raise


def managed_bridge_or_absent(path: Path, consumer_id: str) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink():
        raise WorkbenchError(f"bridge target must not be a symlink: {path}")
    value = load_json(path)
    if value.get("schema") != BRIDGE_SCHEMA or value.get("consumer_id") != consumer_id:
        raise WorkbenchError(f"refusing to overwrite unmanaged bridge target: {path}")


def restore_files(backups: dict[Path, bytes | None]) -> None:
    for path, content in backups.items():
        if content is None:
            path.unlink(missing_ok=True)
            continue
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, delete=False)
        temporary = Path(handle.name)
        try:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
            os.replace(temporary, path)
        except Exception:
            handle.close()
            temporary.unlink(missing_ok=True)
            raise


def apply_plan(
    config_path: Path,
    *,
    expected_version: int,
    confirmation_hash: str,
) -> dict[str, Any]:
    planned = build_plan(config_path)
    plan = planned["plan"]
    if expected_version != plan["expected_version"]:
        raise WorkbenchError(
            f"version conflict: expected {expected_version}, current {plan['expected_version']}"
        )
    if confirmation_hash != planned["confirmation_hash"]:
        raise WorkbenchError("confirmation hash does not match the exact current plan")
    current_preconditions = [
        precondition(Path(item["path"])) for item in plan["preconditions"]
    ]
    if current_preconditions != plan["preconditions"]:
        raise WorkbenchError("managed targets changed after planning; create and confirm a new plan")

    config = normalized_config(config_path)
    if digest(config) != plan["config_hash"]:
        raise WorkbenchError("configuration or canonical assets changed during apply")
    version = plan["next_version"]
    paths = workbench_paths(config, version)
    documents = generated_documents(config, version)
    bridge_targets: dict[str, Path] = {}
    for consumer in config["consumers"]:
        target = safe_target(
            Path(consumer["root"]),
            Path(consumer["discovery_path"]),
            f"consumer {consumer['id']} discovery_path",
        )
        managed_bridge_or_absent(target, consumer["id"])
        bridge_targets[consumer["id"]] = target

    mutable_targets = [paths["current_manifest"], paths["rollback"], *bridge_targets.values()]
    backups = {
        path: path.read_bytes() if path.exists() and not path.is_symlink() else None
        for path in mutable_targets
    }
    previous = current_manifest(config)
    rollback = {
        "schema": ROLLBACK_SCHEMA,
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "applied_version": version,
        "previous_version": previous["workbench_version"] if previous else 0,
        "previous_release_path": previous.get("release_path") if previous else None,
        "previous_manifest_hash": digest(previous) if previous else None,
        "created_release_path": str(paths["release"]),
        "managed_targets_before_apply": plan["preconditions"],
        "rollback_strategy": "restore the previous manifest and regenerate thin bridges from the previous release",
    }

    try:
        atomic_write_json(paths["asset_index"], documents["asset_index"])
        atomic_write_json(paths["consumer_matrix"], documents["consumer_matrix"])
        for consumer_id, adapter in documents["adapters"].items():
            atomic_write_json(paths["adapters"] / f"{consumer_id}.json", adapter)
        atomic_write_json(paths["release_manifest"], documents["release_manifest"])
        for consumer_id, bridge in documents["bridges"].items():
            atomic_write_json(bridge_targets[consumer_id], bridge)
        atomic_write_json(paths["rollback"], rollback)
        atomic_write_json(paths["current_manifest"], documents["current_manifest"])
    except Exception as exc:
        restore_files(backups)
        if paths["release"].exists() and is_within(paths["release"], paths["workbench"]):
            shutil.rmtree(paths["release"])
        if isinstance(exc, WorkbenchError):
            raise
        raise WorkbenchError(f"workbench apply failed and mutable targets were restored: {exc}") from exc

    return {
        "status": "APPLIED",
        "workbench_version": version,
        "canonical_root": config["canonical_root"],
        "canonical_hash": documents["current_manifest"]["canonical_hash"],
        "manifest": str(paths["current_manifest"]),
        "rollback_manifest": str(paths["rollback"]),
        "consumers": [
            {"id": consumer_id, "bridge": str(path)}
            for consumer_id, path in sorted(bridge_targets.items())
        ],
    }


def check(name: str, passed: bool, detail: str) -> dict[str, str]:
    return {"check": name, "status": "PASS" if passed else "FAIL", "detail": detail}


def verify_workbench(config_path: Path) -> dict[str, Any]:
    config = normalized_config(config_path, enforce_consumer_boundaries=False)
    canonical_checks: list[dict[str, str]] = []
    try:
        manifest = current_manifest(config)
    except WorkbenchError as exc:
        manifest = None
        canonical_checks.append(check("current_manifest", False, str(exc)))
    if manifest is None:
        if not canonical_checks:
            canonical_checks.append(check("current_manifest", False, "current manifest is missing"))
        return {
            "status": "FAIL",
            "canonical": {"status": "FAIL", "checks": canonical_checks},
            "consumers": [
                {
                    "id": consumer["id"],
                    "status": "FAIL",
                    "checks": [check("canonical_ready", False, "canonical manifest is unavailable")],
                }
                for consumer in config["consumers"]
            ],
        }

    version = manifest["workbench_version"]
    paths = workbench_paths(config, version)
    expected = generated_documents(config, version)
    canonical_checks.extend(
        [
            check(
                "schema_version",
                manifest.get("schema_version") == SUPPORTED_SCHEMA_VERSION,
                f"expected {SUPPORTED_SCHEMA_VERSION}, got {manifest.get('schema_version')}",
            ),
            check(
                "config_hash",
                manifest.get("config_hash") == digest(config),
                "current normalized config must match the applied config hash",
            ),
            check(
                "canonical_hash",
                manifest.get("canonical_hash") == expected["current_manifest"]["canonical_hash"],
                "canonical asset paths, versions, sizes, and content hashes must match",
            ),
            check(
                "current_manifest_drift",
                digest(manifest) == digest(expected["current_manifest"]),
                "current manifest must exactly match the generated manifest",
            ),
        ]
    )
    document_checks = [
        ("asset_index", paths["asset_index"], ASSET_INDEX_SCHEMA, expected["asset_index"]),
        (
            "consumer_matrix",
            paths["consumer_matrix"],
            MATRIX_SCHEMA,
            expected["consumer_matrix"],
        ),
        (
            "release_manifest",
            paths["release_manifest"],
            WORKBENCH_SCHEMA,
            expected["release_manifest"],
        ),
    ]
    for name, path, schema, expected_document in document_checks:
        if path.is_symlink() or not is_within(path.resolve(strict=False), paths["workbench"]):
            canonical_checks.append(
                check(name, False, f"generated document escapes through a symlink: {path}")
            )
            continue
        try:
            actual = load_json(path)
            passed = (
                actual.get("schema") == schema
                and actual.get("schema_version") == SUPPORTED_SCHEMA_VERSION
                and actual.get("workbench_version") == version
                and digest(actual) == digest(expected_document)
            )
            canonical_checks.append(check(name, passed, f"verified {path}"))
        except WorkbenchError as exc:
            canonical_checks.append(check(name, False, str(exc)))
    rollback_path = paths["rollback"]
    if rollback_path.is_symlink() or not is_within(
        rollback_path.resolve(strict=False), paths["workbench"]
    ):
        canonical_checks.append(
            check(
                "rollback_manifest",
                False,
                f"rollback manifest escapes through a symlink: {rollback_path}",
            )
        )
    else:
        try:
            rollback = load_json(rollback_path)
            rollback_valid = (
                rollback.get("schema") == ROLLBACK_SCHEMA
                and rollback.get("schema_version") == SUPPORTED_SCHEMA_VERSION
                and rollback.get("applied_version") == version
                and rollback.get("previous_version") == version - 1
            )
            canonical_checks.append(
                check(
                    "rollback_manifest",
                    rollback_valid,
                    f"verified {rollback_path}",
                )
            )
        except WorkbenchError as exc:
            canonical_checks.append(check("rollback_manifest", False, str(exc)))

    consumer_reports: list[dict[str, Any]] = []
    for consumer in config["consumers"]:
        checks: list[dict[str, str]] = []
        consumer_root = Path(consumer["root"])
        boundary_passed = False
        try:
            target = safe_target(
                consumer_root,
                Path(consumer["discovery_path"]),
                f"consumer {consumer['id']} discovery_path",
            )
            boundary_passed = True
            checks.append(check("discovery_boundary", True, str(target)))
        except WorkbenchError as exc:
            target = consumer_root / consumer["discovery_path"]
            checks.append(check("discovery_boundary", False, str(exc)))
        if not boundary_passed:
            bridge = None
        elif target.is_symlink():
            checks.append(check("discovery_symlink", False, f"bridge must not be a symlink: {target}"))
            bridge = None
        else:
            try:
                bridge = load_json(target)
                checks.append(check("discovery_path", True, f"found {target}"))
            except WorkbenchError as exc:
                bridge = None
                checks.append(check("discovery_path", False, str(exc)))
        expected_bridge = expected["bridges"][consumer["id"]]
        if bridge is not None:
            checks.extend(
                [
                    check(
                        "bridge_schema_version",
                        bridge.get("schema") == BRIDGE_SCHEMA
                        and bridge.get("schema_version") == SUPPORTED_SCHEMA_VERSION,
                        "bridge schema and version must match",
                    ),
                    check(
                        "bridge_version",
                        bridge.get("workbench_version") == version,
                        f"expected workbench version {version}",
                    ),
                    check(
                        "bridge_canonical_hash",
                        bridge.get("canonical_hash") == manifest.get("canonical_hash"),
                        "bridge canonical hash must match current manifest",
                    ),
                    check(
                        "bridge_drift",
                        digest(bridge) == digest(expected_bridge),
                        "bridge must exactly match the generated thin manifest",
                    ),
                ]
            )
        adapter_path = paths["adapters"] / f"{consumer['id']}.json"
        if adapter_path.is_symlink() or not is_within(
            adapter_path.resolve(strict=False), paths["workbench"]
        ):
            checks.append(
                check(
                    "adapter_boundary",
                    False,
                    f"adapter contract escapes through a symlink: {adapter_path}",
                )
            )
        else:
            try:
                adapter = load_json(adapter_path)
                expected_adapter = expected["adapters"][consumer["id"]]
                checks.extend(
                    [
                        check(
                            "adapter_schema_version",
                            adapter.get("schema") == ADAPTER_SCHEMA
                            and adapter.get("schema_version") == SUPPORTED_SCHEMA_VERSION,
                            "adapter schema and version must match",
                        ),
                        check(
                            "adapter_mode",
                            adapter.get("mode") == "read_only"
                            and adapter.get("sync_direction") == config["sync_direction"],
                            "adapter must remain read-only and use the configured one-way direction",
                        ),
                        check(
                            "adapter_drift",
                            digest(adapter) == digest(expected_adapter),
                            "adapter contract must match the current configuration",
                        ),
                    ]
                )
            except WorkbenchError as exc:
                checks.append(check("adapter_contract", False, str(exc)))
        status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
        consumer_reports.append({"id": consumer["id"], "status": status, "checks": checks})

    canonical_status = (
        "PASS" if all(item["status"] == "PASS" for item in canonical_checks) else "FAIL"
    )
    overall = (
        "PASS"
        if canonical_status == "PASS"
        and all(consumer["status"] == "PASS" for consumer in consumer_reports)
        else "FAIL"
    )
    return {
        "status": overall,
        "canonical": {"status": canonical_status, "checks": canonical_checks},
        "consumers": consumer_reports,
    }


def cmd_plan(args: argparse.Namespace) -> int:
    print(json.dumps(build_plan(Path(args.config).expanduser().resolve()), ensure_ascii=False, indent=2))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    result = apply_plan(
        Path(args.config).expanduser().resolve(),
        expected_version=args.expected_version,
        confirmation_hash=args.confirmation_hash,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    result = verify_workbench(Path(args.config).expanduser().resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan")
    plan.add_argument("config")
    plan.set_defaults(func=cmd_plan)

    apply = subparsers.add_parser("apply")
    apply.add_argument("config")
    apply.add_argument("--expected-version", required=True, type=int)
    apply.add_argument("--confirmation-hash", required=True)
    apply.set_defaults(func=cmd_apply)

    verify = subparsers.add_parser("verify")
    verify.add_argument("config")
    verify.set_defaults(func=cmd_verify)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except WorkbenchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
