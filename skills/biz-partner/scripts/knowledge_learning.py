#!/usr/bin/env python3
"""Consent-gated, add-only learning for a user-private KnowledgePack.

The agent produces a change-set.  This script only validates, plans, commits,
verifies, rolls back, and searches deterministic local pack versions.  It does
not fetch URLs, call a model, publish, run Git, or modify the bundled pack.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from atom_contract import validate_atom_v2
from knowledge_runtime import load_knowledge_pack, search_knowledge_pack


CHANGE_SET_SCHEMA = "knowledge-change-set-v1"
DECISIONS_SCHEMA = "knowledge-decisions-v1"
ACTIVE_SCHEMA = "user-knowledge-pack-active-v1"
MANIFEST_SCHEMA = "user-knowledge-pack-manifest-v2"
PACK_KIND = "user_private"
PACK_GITIGNORE = b"*\n!.gitignore\n"
FILES = (
    "sources.jsonl",
    "atoms.jsonl",
    "concepts.jsonl",
    "methods.jsonl",
    "retrieval-cases.jsonl",
)
KIND_TO_FILE = {
    "source": "sources.jsonl",
    "atom": "atoms.jsonl",
    "concept": "concepts.jsonl",
    "method": "methods.jsonl",
    "retrieval_case": "retrieval-cases.jsonl",
}
ID_FIELDS = {
    "source": ("source_id", "user_source_"),
    "atom": ("atom_id", "user_atom_"),
    "concept": ("concept_id", "user_concept_"),
    "method": ("method_id", "user_method_"),
    "retrieval_case": ("case_id", "user_case_"),
}
RECORD_STATUSES = {"candidate", "evidence_checked", "reviewed"}
RELATION_TYPES = {"depends_on", "supports", "refines", "contradicts"}
METHOD_FIELDS = {
    "method_id",
    "title",
    "purpose",
    "use_when",
    "inputs",
    "steps",
    "decision_gates",
    "stop_conditions",
    "outputs",
    "quality_checks",
    "pitfalls",
    "atom_ids",
    "concept_ids",
    "status",
    "rights",
}
CASE_FIELDS = {
    "case_id",
    "case_kind",
    "query",
    "relevant_atom_ids",
    "relevant_method_ids",
    "relevant_concept_ids",
}
SKILL_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_PACK_ROOT = SKILL_ROOT / "public-knowledge"
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,95}$")
SECRET_PATTERNS = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.I)),
    (
        "assigned_secret",
        re.compile(
            r"\b(?:api[_-]?key|secret|password|passwd|token)\s*[:=]\s*[\"']?[^\s\"']{12,}",
            re.I,
        ),
    ),
    ("credential_url", re.compile(r"https?://[^\s/:@]+:[^\s/@]+@", re.I)),
)
PII_PATTERNS = (
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("cn_mobile", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("cn_identity", re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")),
)


class LearningError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def normalized_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(value.split())


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LearningError(f"{label} must be an object")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise LearningError(f"{label} must be a non-empty trimmed string")
    return value


def require_string_list(value: Any, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise LearningError(f"{label} must be a {'non-empty ' if not allow_empty else ''}list")
    if not all(isinstance(item, str) and item and item == item.strip() for item in value):
        raise LearningError(f"{label} must contain non-empty trimmed strings")
    if len(value) != len(set(value)):
        raise LearningError(f"{label} must not contain duplicates")
    return value


def require_datetime(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    raw = require_string(value, label)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LearningError(f"{label} must be an ISO 8601 date-time") from exc
    if parsed.tzinfo is None:
        raise LearningError(f"{label} must include a timezone")
    return raw


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LearningError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LearningError(f"invalid JSON in {path}: {exc}") from exc
    return require_object(value, str(path))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise LearningError(f"missing pack file: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LearningError(f"invalid JSONL in {path}:{line_number}: {exc.msg}") from exc
        rows.append(require_object(row, f"{path}:{line_number}"))
    return rows


def jsonl_bytes(rows: Iterable[dict[str, Any]]) -> bytes:
    material = list(rows)
    if not material:
        return b""
    return b"".join(canonical_bytes(row) + b"\n" for row in material)


def resolve_pack(raw: str) -> Path:
    supplied = Path(raw).expanduser()
    if not supplied.is_absolute():
        raise LearningError("pack path must be absolute")
    if supplied.exists() and supplied.is_symlink():
        raise LearningError("pack path must not be a symlink")
    pack = supplied.resolve()
    try:
        pack.relative_to(SKILL_ROOT)
    except ValueError:
        pass
    else:
        raise LearningError("user-private pack must stay outside the Skill directory")
    if pack.parts[-3:-1] != (".biz-partner", "knowledge-packs"):
        raise LearningError(
            "pack path must match <project>/.biz-partner/knowledge-packs/<pack-id>"
        )
    if not SAFE_ID_RE.fullmatch(pack.name):
        raise LearningError("pack directory name must be a safe pack ID")
    if pack.exists() and not pack.is_dir():
        raise LearningError("pack path exists but is not a directory")
    return pack


def path_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def current_state(pack: Path) -> dict[str, Any]:
    pack = pack.resolve()
    active_path = pack / "active.json"
    if not active_path.exists():
        return {
            "revision": 0,
            "manifest_sha256": None,
            "pack_id": None,
            "version_dir": None,
            "action": None,
        }
    if active_path.is_symlink():
        raise LearningError("active.json must not be a symlink")
    active = load_json(active_path)
    required = {
        "schema_version",
        "pack_id",
        "pack_kind",
        "revision",
        "version_dir",
        "manifest_sha256",
        "action",
        "restores_revision",
    }
    if set(active) != required or active.get("schema_version") != ACTIVE_SCHEMA:
        raise LearningError("invalid active.json contract")
    if active.get("pack_kind") != PACK_KIND:
        raise LearningError("active pack is not user_private")
    if active.get("pack_id") != pack.name or not SAFE_ID_RE.fullmatch(pack.name):
        raise LearningError("active pack_id does not match the pack directory")
    revision = active.get("revision")
    if not isinstance(revision, int) or revision < 1:
        raise LearningError("active revision must be a positive integer")
    if active.get("version_dir") != f"versions/v{revision:06d}":
        raise LearningError("active version_dir does not match revision")
    if not HASH_RE.fullmatch(str(active.get("manifest_sha256", ""))):
        raise LearningError("active manifest hash is invalid")
    return active


def active_version_dir(pack: Path, state: dict[str, Any]) -> Path | None:
    if state["revision"] == 0:
        return None
    direct = pack / state["version_dir"]
    if direct.is_symlink():
        raise LearningError("active version directory must not be a symlink")
    version_dir = direct.resolve()
    if not path_inside(version_dir, pack / "versions") or not version_dir.is_dir():
        raise LearningError("active version directory is missing or outside the pack")
    return version_dir


def read_version_rows(version_dir: Path | None) -> dict[str, list[dict[str, Any]]]:
    if version_dir is None:
        return {name: [] for name in FILES}
    return {name: load_jsonl(version_dir / name) for name in FILES}


def validate_private_status(record: dict[str, Any], kind: str) -> None:
    if record.get("status") not in RECORD_STATUSES:
        raise LearningError(f"{kind} status must remain candidate, evidence_checked, or reviewed")
    if kind == "source":
        if record.get("rights_status") != "private_local_only":
            raise LearningError("source rights_status must be private_local_only")
        return
    rights = record.get("rights")
    if not isinstance(rights, dict) or rights.get("redistribution") != "private_local_only":
        raise LearningError(f"{kind} rights.redistribution must be private_local_only")


def validate_user_id(record: dict[str, Any], kind: str) -> str:
    field, prefix = ID_FIELDS[kind]
    identifier = require_string(record.get(field), f"{kind}.{field}")
    if not identifier.startswith(prefix) or not SAFE_ID_RE.fullmatch(identifier):
        raise LearningError(f"{kind}.{field} must use the reserved {prefix} prefix")
    return identifier


def validate_record_shape(kind: str, record: dict[str, Any]) -> None:
    if kind == "source":
        validate_user_id(record, kind)
        require_string(record.get("kind"), "source.kind")
        require_string(record.get("evidence_kind"), "source.evidence_kind")
        content_sha256 = str(record.get("content_sha256", ""))
        if not HASH_RE.fullmatch(content_sha256) or content_sha256 == "sha256:" + "0" * 64:
            raise LearningError("source.content_sha256 must be a SHA-256 digest")
        return
    if kind == "atom":
        validate_user_id(record, kind)
        try:
            validate_atom_v2(record, allow_private_local_locator=True)
        except ValueError as exc:
            raise LearningError(str(exc)) from exc
        return
    if kind == "concept":
        validate_user_id(record, kind)
        require_string(record.get("concept_kind"), "concept.concept_kind")
        require_string(record.get("term"), "concept.term")
        require_string(record.get("normalized"), "concept.normalized")
        require_string(record.get("definition"), "concept.definition")
        require_string_list(record.get("aliases", []), "concept.aliases")
        require_string_list(record.get("source_atoms", []), "concept.source_atoms")
        require_string_list(record.get("related_methods", []), "concept.related_methods")
        return
    if kind == "method":
        validate_user_id(record, kind)
        if set(record) != METHOD_FIELDS:
            raise LearningError("method fields must match the KnowledgePack runtime contract")
        require_string(record.get("title"), "method.title")
        require_string(record.get("purpose"), "method.purpose")
        for field in (
            "use_when",
            "inputs",
            "steps",
            "decision_gates",
            "stop_conditions",
            "outputs",
            "quality_checks",
            "pitfalls",
            "atom_ids",
            "concept_ids",
        ):
            require_string_list(
                record.get(field), f"method.{field}", allow_empty=field not in {"steps", "atom_ids", "concept_ids"}
            )
        return
    if kind == "retrieval_case":
        validate_user_id(record, kind)
        if set(record) != CASE_FIELDS:
            raise LearningError("retrieval case fields must match the runtime evaluation contract")
        require_string(record.get("case_kind"), "retrieval_case.case_kind")
        require_string(record.get("query"), "retrieval_case.query")
        atoms = require_string_list(record.get("relevant_atom_ids"), "relevant_atom_ids")
        methods = require_string_list(record.get("relevant_method_ids"), "relevant_method_ids")
        concepts = require_string_list(record.get("relevant_concept_ids"), "relevant_concept_ids")
        if not (atoms or methods or concepts):
            raise LearningError("retrieval case must reference an atom, method, or concept")
        return
    if kind == "atom_relation":
        if set(record) != {"source_atom_id", "type", "target_atom_id"}:
            raise LearningError("atom_relation must contain source_atom_id, type, and target_atom_id")
        for field in ("source_atom_id", "target_atom_id"):
            identifier = require_string(record.get(field), f"atom_relation.{field}")
            if not identifier.startswith("user_atom_"):
                raise LearningError("atom relations may only target user-private atom IDs")
        if record.get("type") not in RELATION_TYPES:
            raise LearningError("atom_relation.type is invalid")
        return
    raise LearningError(f"unsupported record_kind: {kind}")


def validate_change_set(value: dict[str, Any], pack: Path) -> dict[str, Any]:
    allowed = {
        "schema_version",
        "change_set_id",
        "target",
        "created_at",
        "expires_at",
        "candidates",
    }
    required = allowed - {"expires_at"}
    if set(value) - allowed or required - set(value):
        raise LearningError("change-set has unsupported or missing top-level fields")
    if value.get("schema_version") != CHANGE_SET_SCHEMA:
        raise LearningError("unsupported change-set schema")
    require_string(value.get("change_set_id"), "change_set_id")
    require_datetime(value.get("created_at"), "created_at")
    if "expires_at" in value:
        expires_at = require_datetime(value.get("expires_at"), "expires_at", nullable=True)
        if expires_at is not None:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expiry <= datetime.now(expiry.tzinfo):
                raise LearningError("change-set has expired")
    target = require_object(value.get("target"), "target")
    target_fields = {
        "pack_id",
        "pack_kind",
        "pack_path",
        "base_revision",
        "base_manifest_sha256",
    }
    if set(target) != target_fields:
        raise LearningError("target fields do not match the change-set contract")
    pack_id = require_string(target.get("pack_id"), "target.pack_id")
    if not SAFE_ID_RE.fullmatch(pack_id):
        raise LearningError("target.pack_id is invalid")
    if target.get("pack_kind") != PACK_KIND:
        raise LearningError("target.pack_kind must be user_private")
    target_path = resolve_pack(require_string(target.get("pack_path"), "target.pack_path"))
    if target_path != pack.resolve():
        raise LearningError("change-set target does not match --pack")
    if pack_id != target_path.name:
        raise LearningError("target.pack_id must match the pack directory name")
    if not isinstance(target.get("base_revision"), int) or target["base_revision"] < 0:
        raise LearningError("target.base_revision must be a non-negative integer")
    base_hash = target.get("base_manifest_sha256")
    if base_hash is not None and not HASH_RE.fullmatch(str(base_hash)):
        raise LearningError("target.base_manifest_sha256 must be null or SHA-256")
    candidates = value.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise LearningError("candidates must be a non-empty list")
    seen: set[str] = set()
    for candidate in candidates:
        candidate = require_object(candidate, "candidate")
        if set(candidate) != {"candidate_id", "record_kind", "operation", "record"}:
            raise LearningError("candidate fields do not match the change-set contract")
        candidate_id = require_string(candidate.get("candidate_id"), "candidate_id")
        if not candidate_id.startswith("candidate_") or candidate_id in seen:
            raise LearningError(f"invalid or duplicate candidate_id: {candidate_id}")
        seen.add(candidate_id)
        if candidate.get("operation") != "add":
            raise LearningError("only add candidates are supported")
        kind = require_string(candidate.get("record_kind"), "record_kind")
        validate_record_shape(kind, require_object(candidate.get("record"), "record"))
    return value


def record_id(kind: str, record: dict[str, Any]) -> str:
    if kind == "atom_relation":
        return f"{record['source_atom_id']}:{record['type']}:{record['target_atom_id']}"
    return str(record[ID_FIELDS[kind][0]])


def text_for_similarity(kind: str, record: dict[str, Any]) -> str:
    if kind == "atom":
        return str(record.get("canonical", ""))
    if kind == "concept":
        return " ".join(
            [str(record.get("term", "")), str(record.get("normalized", "")), str(record.get("definition", ""))]
            + list(record.get("aliases", []))
        )
    if kind == "method":
        return " ".join([str(record.get("purpose", ""))] + list(record.get("steps", [])))
    if kind == "retrieval_case":
        return str(record.get("query", ""))
    if kind == "source":
        return str(record.get("content_sha256", ""))
    return ""


def scan_sensitive(record: dict[str, Any]) -> tuple[list[str], list[str]]:
    material = json.dumps(record, ensure_ascii=False, sort_keys=True)
    secrets = sorted(name for name, pattern in SECRET_PATTERNS if pattern.search(material))
    pii = sorted(name for name, pattern in PII_PATTERNS if pattern.search(material))
    return secrets, pii


def public_rows() -> dict[str, list[dict[str, Any]]]:
    mapping = {
        "source": "sources.jsonl",
        "atom": "atoms.jsonl",
        "concept": "concepts.jsonl",
        "method": "methods.jsonl",
        "retrieval_case": "retrieval-cases.jsonl",
    }
    rows: dict[str, list[dict[str, Any]]] = {}
    for kind, name in mapping.items():
        path = PUBLIC_PACK_ROOT / name
        rows[kind] = load_jsonl(path) if path.is_file() else []
    return rows


def rows_by_kind(rows: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "source": rows["sources.jsonl"],
        "atom": rows["atoms.jsonl"],
        "concept": rows["concepts.jsonl"],
        "method": rows["methods.jsonl"],
        "retrieval_case": rows["retrieval-cases.jsonl"],
    }


def find_cycles(edges: dict[str, set[str]]) -> list[list[str]]:
    state: dict[str, int] = {}
    stack: list[str] = []
    found: set[tuple[str, ...]] = set()

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for target in sorted(edges.get(node, set())):
            if state.get(target, 0) == 0:
                visit(target)
            elif state.get(target) == 1:
                start = stack.index(target)
                cycle = stack[start:] + [target]
                core = cycle[:-1]
                rotations = [tuple(core[index:] + core[:index]) for index in range(len(core))]
                found.add(min(rotations) + (min(rotations)[0],))
        stack.pop()
        state[node] = 2

    for node in sorted(edges):
        if state.get(node, 0) == 0:
            visit(node)
    return [list(cycle) for cycle in sorted(found)]


def analyze_change_set(pack: Path, value: dict[str, Any]) -> dict[str, Any]:
    pack = resolve_pack(str(pack))
    validate_change_set(value, pack)
    state = current_state(pack)
    if state["revision"] > 0:
        verify_pack(pack)
    target = value["target"]
    base_matches = (
        target["base_revision"] == state["revision"]
        and target["base_manifest_sha256"] == state["manifest_sha256"]
    )
    current_rows = read_version_rows(active_version_dir(pack, state))
    existing = rows_by_kind(current_rows)
    public = public_rows()
    all_existing = {
        kind: [("user", row) for row in existing[kind]] + [("bundled_public", row) for row in public[kind]]
        for kind in existing
    }
    existing_ids = {
        kind: {record_id(kind, row) for _, row in all_existing[kind]}
        for kind in existing
    }
    candidate_records = {
        candidate["candidate_id"]: (candidate["record_kind"], candidate["record"])
        for candidate in value["candidates"]
    }
    new_atom_ids = {
        record["atom_id"] for kind, record in candidate_records.values() if kind == "atom"
    }
    current_atom_ids = {row["atom_id"] for row in existing["atom"]}
    candidate_ids_by_kind: dict[str, set[str]] = {kind: set() for kind in existing}
    reports: list[dict[str, Any]] = []
    source_evidence_kind: dict[str, str] = {
        row["source_id"]: str(row.get("evidence_kind", row.get("kind", ""))).casefold()
        for row in existing["source"]
    }
    for kind, record in candidate_records.values():
        if kind == "source":
            source_evidence_kind[record["source_id"]] = str(
                record.get("evidence_kind", record.get("kind", ""))
            ).casefold()
    available_ids = {
        "source": {row["source_id"] for row in existing["source"]}
        | {record["source_id"] for kind, record in candidate_records.values() if kind == "source"},
        "atom": current_atom_ids | new_atom_ids,
        "concept": {row["concept_id"] for row in existing["concept"]}
        | {record["concept_id"] for kind, record in candidate_records.values() if kind == "concept"},
        "method": {row["method_id"] for row in existing["method"]}
        | {record["method_id"] for kind, record in candidate_records.values() if kind == "method"},
    }
    for candidate in value["candidates"]:
        candidate_id = candidate["candidate_id"]
        kind = candidate["record_kind"]
        record = candidate["record"]
        blockers: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        exact_matches: list[dict[str, str]] = []
        near_matches: list[dict[str, Any]] = []
        secrets, pii = scan_sensitive(record)
        if secrets:
            blockers.append({"type": "credential_or_secret", "findings": secrets})
        if pii:
            blockers.append({"type": "unnecessary_personal_data", "findings": pii})
        if kind in {"source", "atom", "concept", "method"}:
            try:
                validate_private_status(record, kind)
            except LearningError as exc:
                blockers.append({"type": "private_rights_or_status", "detail": str(exc)})
        if kind != "atom_relation":
            identifier = record_id(kind, record)
            if identifier in existing_ids[kind] or identifier in candidate_ids_by_kind[kind]:
                blockers.append({"type": "id_collision", "record_id": identifier})
            candidate_ids_by_kind[kind].add(identifier)
            candidate_text = normalized_text(text_for_similarity(kind, record))
            for scope, prior in all_existing[kind]:
                prior_text = normalized_text(text_for_similarity(kind, prior))
                if not candidate_text or not prior_text:
                    continue
                prior_id = record_id(kind, prior)
                if candidate_text == prior_text:
                    exact_matches.append({"scope": scope, "record_id": prior_id})
                    continue
                ratio = SequenceMatcher(None, candidate_text, prior_text).ratio()
                if ratio >= 0.72:
                    near_matches.append(
                        {"scope": scope, "record_id": prior_id, "similarity": round(ratio, 6)}
                    )
            for other_id, (other_kind, other) in candidate_records.items():
                if other_id == candidate_id or other_kind != kind:
                    continue
                other_text = normalized_text(text_for_similarity(kind, other))
                if not candidate_text or not other_text:
                    continue
                if candidate_text == other_text:
                    blockers.append(
                        {"type": "exact_duplicate", "candidate_id": other_id}
                    )
                    continue
                ratio = SequenceMatcher(None, candidate_text, other_text).ratio()
                if ratio >= 0.72:
                    near_matches.append(
                        {"scope": "change_set", "record_id": other_id, "similarity": round(ratio, 6)}
                    )
            if exact_matches:
                blockers.append({"type": "exact_duplicate", "matches": exact_matches})
        if kind == "concept":
            forms = {
                normalized_text(record["term"]),
                normalized_text(record["normalized"]),
                *(normalized_text(alias) for alias in record.get("aliases", [])),
            }
            for scope, prior in all_existing["concept"]:
                prior_forms = {
                    normalized_text(str(prior.get("term", ""))),
                    normalized_text(str(prior.get("normalized", ""))),
                    *(normalized_text(alias) for alias in prior.get("aliases", [])),
                }
                overlap = sorted(form for form in forms & prior_forms if form)
                if overlap:
                    blockers.append(
                        {
                            "type": "concept_alias_conflict",
                            "scope": scope,
                            "record_id": str(prior.get("concept_id")),
                            "forms": overlap,
                        }
                    )
            for other_id, (other_kind, other) in candidate_records.items():
                if other_id == candidate_id or other_kind != "concept":
                    continue
                other_forms = {
                    normalized_text(other["term"]),
                    normalized_text(other["normalized"]),
                    *(normalized_text(alias) for alias in other.get("aliases", [])),
                }
                overlap = sorted(form for form in forms & other_forms if form)
                if overlap:
                    blockers.append(
                        {"type": "concept_alias_conflict", "candidate_id": other_id, "forms": overlap}
                    )
        if kind == "atom_relation":
            if record["source_atom_id"] not in new_atom_ids:
                blockers.append(
                    {"type": "relation_source_must_be_new_atom", "atom_id": record["source_atom_id"]}
                )
            if record["target_atom_id"] not in new_atom_ids | current_atom_ids:
                blockers.append(
                    {"type": "unknown_relation_target", "atom_id": record["target_atom_id"]}
                )
            for other_id, (other_kind, other) in candidate_records.items():
                if other_id != candidate_id and other_kind == "atom_relation" and other == record:
                    blockers.append({"type": "exact_duplicate_relation", "candidate_id": other_id})
            source_atom = next(
                (
                    other
                    for other_kind, other in candidate_records.values()
                    if other_kind == "atom" and other["atom_id"] == record["source_atom_id"]
                ),
                None,
            )
            if source_atom is not None and {
                "type": record["type"],
                "atom_id": record["target_atom_id"],
            } in source_atom.get("relations", []):
                blockers.append({"type": "exact_duplicate_relation", "embedded_in_atom": True})
        if kind == "atom":
            for ref in record.get("source_refs", []):
                if ref.get("source_id") not in available_ids["source"]:
                    blockers.append(
                        {"type": "unknown_source_reference", "source_id": ref.get("source_id")}
                    )
                evidence_kind = source_evidence_kind.get(ref.get("source_id"), "")
                if any(marker in evidence_kind for marker in ("conversation", "chat", "user_claim")):
                    if record.get("claim_kind") not in {"user_claim", "user_observation", "hypothesis"}:
                        blockers.append(
                            {
                                "type": "conversation_claim_promoted_as_fact",
                                "source_id": ref.get("source_id"),
                            }
                        )
            unknown_targets = sorted(
                {
                    relation.get("atom_id")
                    for relation in record.get("relations", [])
                    if relation.get("atom_id") not in available_ids["atom"]
                }
            )
            if unknown_targets:
                blockers.append({"type": "unknown_relation_targets", "atom_ids": unknown_targets})
        if kind == "concept":
            unknown_atoms = sorted(set(record.get("source_atoms", [])) - available_ids["atom"])
            unknown_methods = sorted(set(record.get("related_methods", [])) - available_ids["method"])
            if unknown_atoms:
                blockers.append({"type": "unknown_atom_references", "atom_ids": unknown_atoms})
            if unknown_methods:
                blockers.append({"type": "unknown_method_references", "method_ids": unknown_methods})
        if kind == "method":
            unknown_atoms = sorted(set(record.get("atom_ids", [])) - available_ids["atom"])
            unknown_concepts = sorted(set(record.get("concept_ids", [])) - available_ids["concept"])
            if unknown_atoms:
                blockers.append({"type": "unknown_atom_references", "atom_ids": unknown_atoms})
            if unknown_concepts:
                blockers.append({"type": "unknown_concept_references", "concept_ids": unknown_concepts})
        if kind == "retrieval_case":
            unknown_atoms = sorted(set(record.get("relevant_atom_ids", [])) - available_ids["atom"])
            unknown_methods = sorted(set(record.get("relevant_method_ids", [])) - available_ids["method"])
            unknown_concepts = sorted(set(record.get("relevant_concept_ids", [])) - available_ids["concept"])
            if unknown_atoms or unknown_methods or unknown_concepts:
                blockers.append(
                    {
                        "type": "unknown_retrieval_references",
                        "atom_ids": unknown_atoms,
                        "method_ids": unknown_methods,
                        "concept_ids": unknown_concepts,
                    }
                )
        if near_matches:
            warnings.append({"type": "near_duplicate", "matches": near_matches[:5]})
        reports.append(
            {
                "candidate_id": candidate_id,
                "candidate_hash": digest(candidate),
                "record_kind": kind,
                "record_id": record_id(kind, record),
                "blockers": blockers,
                "warnings": warnings,
            }
        )

    depends_edges: dict[str, set[str]] = {}
    for atom in existing["atom"]:
        depends_edges.setdefault(atom["atom_id"], set()).update(
            relation["atom_id"]
            for relation in atom.get("relations", [])
            if relation.get("type") == "depends_on"
        )
    for kind, record in candidate_records.values():
        if kind == "atom":
            depends_edges.setdefault(record["atom_id"], set()).update(
                relation["atom_id"]
                for relation in record.get("relations", [])
                if relation.get("type") == "depends_on"
            )
        elif kind == "atom_relation" and record["type"] == "depends_on":
            depends_edges.setdefault(record["source_atom_id"], set()).add(record["target_atom_id"])
    cycles = find_cycles(depends_edges)
    if cycles:
        involved = {atom_id for cycle in cycles for atom_id in cycle}
        for report in reports:
            kind, record = candidate_records[report["candidate_id"]]
            related = set()
            if kind == "atom":
                related.add(record["atom_id"])
            elif kind == "atom_relation":
                related.update((record["source_atom_id"], record["target_atom_id"]))
            if related & involved:
                report["blockers"].append({"type": "depends_on_cycle", "cycles": cycles})
    blocker_count = sum(len(report["blockers"]) for report in reports)
    return {
        "schema_version": "knowledge-analysis-report-v1",
        "change_set_id": value["change_set_id"],
        "change_set_hash": digest(value),
        "target": {
            "pack_id": target["pack_id"],
            "pack_path": str(pack),
            "current_revision": state["revision"],
            "current_manifest_sha256": state["manifest_sha256"],
            "base_matches": base_matches,
        },
        "candidate_count": len(reports),
        "blocker_count": blocker_count + (0 if base_matches else 1),
        "ready_for_plan": base_matches and blocker_count == 0,
        "base_conflict": None if base_matches else "change-set base is stale",
        "candidates": reports,
    }


def validate_decisions(value: dict[str, Any], report: dict[str, Any]) -> dict[str, str]:
    if set(value) != {"schema_version", "change_set_hash", "decisions"}:
        raise LearningError("decisions fields do not match the contract")
    if value.get("schema_version") != DECISIONS_SCHEMA:
        raise LearningError("unsupported decisions schema")
    if value.get("change_set_hash") != report["change_set_hash"]:
        raise LearningError("decisions are not bound to this change-set")
    rows = value.get("decisions")
    if not isinstance(rows, list):
        raise LearningError("decisions must be a list")
    expected = {row["candidate_id"]: row for row in report["candidates"]}
    selected: dict[str, str] = {}
    for row in rows:
        row = require_object(row, "decision")
        if set(row) != {"candidate_id", "candidate_hash", "decision"}:
            raise LearningError("decision fields do not match the contract")
        candidate_id = require_string(row.get("candidate_id"), "decision.candidate_id")
        if candidate_id not in expected or candidate_id in selected:
            raise LearningError(f"unknown or duplicate decision candidate: {candidate_id}")
        if row.get("candidate_hash") != expected[candidate_id]["candidate_hash"]:
            raise LearningError(f"candidate hash mismatch: {candidate_id}")
        decision = row.get("decision")
        if decision not in {"accept", "reject", "defer"}:
            raise LearningError(f"invalid decision: {candidate_id}")
        selected[candidate_id] = decision
    if set(selected) != set(expected):
        raise LearningError("every candidate needs an explicit accept, reject, or defer decision")
    return selected


def validate_graph(rows: dict[str, list[dict[str, Any]]]) -> None:
    ids = {
        "source": {row["source_id"] for row in rows["sources.jsonl"]},
        "atom": {row["atom_id"] for row in rows["atoms.jsonl"]},
        "concept": {row["concept_id"] for row in rows["concepts.jsonl"]},
        "method": {row["method_id"] for row in rows["methods.jsonl"]},
    }
    for atom in rows["atoms.jsonl"]:
        missing_sources = {ref["source_id"] for ref in atom["source_refs"]} - ids["source"]
        missing_atoms = {rel["atom_id"] for rel in atom.get("relations", [])} - ids["atom"]
        if missing_sources or missing_atoms:
            raise LearningError(f"atom graph has unknown references: {atom['atom_id']}")
    for concept in rows["concepts.jsonl"]:
        if set(concept.get("source_atoms", [])) - ids["atom"]:
            raise LearningError(f"concept references unknown atoms: {concept['concept_id']}")
        if set(concept.get("related_methods", [])) - ids["method"]:
            raise LearningError(f"concept references unknown methods: {concept['concept_id']}")
    for method in rows["methods.jsonl"]:
        if set(method["atom_ids"]) - ids["atom"] or set(method["concept_ids"]) - ids["concept"]:
            raise LearningError(f"method graph has unknown references: {method['method_id']}")
    for case in rows["retrieval-cases.jsonl"]:
        if (
            set(case["relevant_atom_ids"]) - ids["atom"]
            or set(case["relevant_method_ids"]) - ids["method"]
            or set(case["relevant_concept_ids"]) - ids["concept"]
        ):
            raise LearningError(f"retrieval case has unknown references: {case['case_id']}")


def validate_private_rows(rows: dict[str, list[dict[str, Any]]]) -> None:
    mapping = {
        "sources.jsonl": "source",
        "atoms.jsonl": "atom",
        "concepts.jsonl": "concept",
        "methods.jsonl": "method",
        "retrieval-cases.jsonl": "retrieval_case",
    }
    for name, kind in mapping.items():
        seen: set[str] = set()
        for record in rows[name]:
            validate_record_shape(kind, record)
            if kind in {"source", "atom", "concept", "method"}:
                validate_private_status(record, kind)
            identifier = record_id(kind, record)
            if identifier in seen:
                raise LearningError(f"duplicate {kind} ID in private pack: {identifier}")
            seen.add(identifier)
    validate_graph(rows)


def apply_selection(
    current_rows: dict[str, list[dict[str, Any]]],
    change_set: dict[str, Any],
    decisions: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    rows = {name: [dict(row) for row in material] for name, material in current_rows.items()}
    candidates = {candidate["candidate_id"]: candidate for candidate in change_set["candidates"]}
    accepted = [candidates[candidate_id] for candidate_id, decision in decisions.items() if decision == "accept"]
    accepted_atoms = {
        candidate["record"]["atom_id"]: dict(candidate["record"])
        for candidate in accepted
        if candidate["record_kind"] == "atom"
    }
    for candidate in accepted:
        kind = candidate["record_kind"]
        if kind in KIND_TO_FILE:
            rows[KIND_TO_FILE[kind]].append(dict(candidate["record"]))
    for candidate in accepted:
        if candidate["record_kind"] != "atom_relation":
            continue
        relation = candidate["record"]
        atom = accepted_atoms.get(relation["source_atom_id"])
        if atom is None:
            raise LearningError("accepted relation source must be an accepted new atom")
        edge = {"type": relation["type"], "atom_id": relation["target_atom_id"]}
        atom_row = next(row for row in rows["atoms.jsonl"] if row["atom_id"] == relation["source_atom_id"])
        if edge in atom_row.get("relations", []):
            raise LearningError("accepted relation is already present")
        atom_row.setdefault("relations", []).append(edge)
    validate_graph(rows)
    return rows


def build_manifest(
    *,
    pack_id: str,
    revision: int,
    parent_revision: int,
    parent_manifest_sha256: str | None,
    action: str,
    restores_revision: int | None,
    file_hashes: dict[str, str],
    counts: dict[str, int],
    change_set_hash: str | None,
    decisions_hash: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA,
        "pack_id": pack_id,
        "pack_kind": PACK_KIND,
        "revision": revision,
        "parent_revision": parent_revision,
        "parent_manifest_sha256": parent_manifest_sha256,
        "action": action,
        "restores_revision": restores_revision,
        "change_set_hash": change_set_hash,
        "decisions_hash": decisions_hash,
        "files": file_hashes,
        "counts": counts,
    }


def validate_manifest_contract(
    manifest: dict[str, Any], pack: Path, expected_revision: int
) -> None:
    fields = {
        "schema_version",
        "pack_id",
        "pack_kind",
        "revision",
        "parent_revision",
        "parent_manifest_sha256",
        "action",
        "restores_revision",
        "change_set_hash",
        "decisions_hash",
        "files",
        "counts",
    }
    if set(manifest) != fields or manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise LearningError("unsupported manifest schema")
    if manifest.get("pack_kind") != PACK_KIND:
        raise LearningError("manifest is not user_private")
    if manifest.get("pack_id") != pack.name or not SAFE_ID_RE.fullmatch(pack.name):
        raise LearningError("manifest pack_id does not match the pack directory")
    if manifest.get("revision") != expected_revision:
        raise LearningError("manifest revision does not match its version directory")
    expected_parent = expected_revision - 1
    if manifest.get("parent_revision") != expected_parent:
        raise LearningError("manifest parent revision is not the previous revision")
    parent_hash = manifest.get("parent_manifest_sha256")
    if expected_revision == 1:
        if parent_hash is not None:
            raise LearningError("first revision must not name a parent manifest")
    elif not isinstance(parent_hash, str) or not HASH_RE.fullmatch(parent_hash):
        raise LearningError("manifest parent hash is invalid")
    if manifest.get("action") not in {"apply", "rollback"}:
        raise LearningError("manifest action is invalid")
    restores_revision = manifest.get("restores_revision")
    if manifest["action"] == "apply" and restores_revision is not None:
        raise LearningError("apply manifest must not restore a revision")
    if manifest["action"] == "rollback" and (
        not isinstance(restores_revision, int)
        or not 1 <= restores_revision < expected_revision
    ):
        raise LearningError("rollback manifest has an invalid restored revision")
    file_hashes = manifest.get("files")
    if not isinstance(file_hashes, dict) or set(file_hashes) != set(FILES):
        raise LearningError("manifest file set is incomplete")
    if any(not isinstance(value, str) or not HASH_RE.fullmatch(value) for value in file_hashes.values()):
        raise LearningError("manifest contains an invalid file hash")
    count_keys = {name.removesuffix(".jsonl").replace("-", "_") for name in FILES}
    counts = manifest.get("counts")
    if (
        not isinstance(counts, dict)
        or set(counts) != count_keys
        or any(not isinstance(value, int) or value < 0 for value in counts.values())
    ):
        raise LearningError("manifest record counts are invalid")


def verify_manifest_chain(
    pack: Path, state: dict[str, Any]
) -> dict[int, dict[str, Any]]:
    expected_hash = state["manifest_sha256"]
    manifests: dict[int, dict[str, Any]] = {}
    for revision in range(state["revision"], 0, -1):
        version_dir = pack / "versions" / f"v{revision:06d}"
        manifest_path = version_dir / "manifest.json"
        if not version_dir.is_dir() or version_dir.is_symlink() or manifest_path.is_symlink():
            raise LearningError(f"version directory is missing or unsafe: v{revision:06d}")
        manifest = load_json(manifest_path)
        validate_manifest_contract(manifest, pack, revision)
        if digest(manifest) != expected_hash:
            raise LearningError(f"manifest chain hash mismatch: v{revision:06d}")
        manifests[revision] = manifest
        expected_hash = manifest["parent_manifest_sha256"]
    if expected_hash is not None:
        raise LearningError("manifest chain does not terminate at the first revision")
    return manifests


def build_apply_plan(pack: Path, change_set: dict[str, Any], decision_doc: dict[str, Any]) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    pack = resolve_pack(str(pack))
    report = analyze_change_set(pack, change_set)
    if not report["target"]["base_matches"]:
        raise LearningError("change-set base is stale; analyze again")
    decisions = validate_decisions(decision_doc, report)
    accepted_ids = {
        candidate_id for candidate_id, decision in decisions.items() if decision == "accept"
    }
    if not accepted_ids:
        raise LearningError("at least one candidate must be accepted")
    selected_change_set = dict(change_set)
    selected_change_set["candidates"] = [
        candidate
        for candidate in change_set["candidates"]
        if candidate["candidate_id"] in accepted_ids
    ]
    selected_report = analyze_change_set(pack, selected_change_set)
    blockers = {
        row["candidate_id"]: row["blockers"]
        for row in selected_report["candidates"]
        if row["blockers"]
    }
    if blockers:
        raise LearningError("accepted candidates contain blockers: " + ",".join(sorted(blockers)))
    state = current_state(pack)
    current_rows = read_version_rows(active_version_dir(pack, state))
    result_rows = apply_selection(current_rows, change_set, decisions)
    file_bytes = {name: jsonl_bytes(result_rows[name]) for name in FILES}
    file_hashes = {name: sha256_bytes(data) for name, data in file_bytes.items()}
    counts = {name.removesuffix(".jsonl").replace("-", "_"): len(result_rows[name]) for name in FILES}
    next_revision = state["revision"] + 1
    manifest = build_manifest(
        pack_id=change_set["target"]["pack_id"],
        revision=next_revision,
        parent_revision=state["revision"],
        parent_manifest_sha256=state["manifest_sha256"],
        action="apply",
        restores_revision=None,
        file_hashes=file_hashes,
        counts=counts,
        change_set_hash=report["change_set_hash"],
        decisions_hash=digest(decision_doc),
    )
    action = {
        "action": "apply_user_private_knowledge",
        "pack_path": str(pack),
        "pack_id": change_set["target"]["pack_id"],
        "expected_revision": state["revision"],
        "expected_manifest_sha256": state["manifest_sha256"],
        "next_revision": next_revision,
        "change_set_hash": report["change_set_hash"],
        "decisions_hash": digest(decision_doc),
        "result_file_hashes": file_hashes,
        "result_manifest_sha256": digest(manifest),
        "privacy_guard_sha256": sha256_bytes(PACK_GITIGNORE),
    }
    plan = {
        "schema_version": "knowledge-apply-plan-v1",
        "preview": action,
        "accepted_candidate_ids": sorted(
            candidate_id for candidate_id, decision in decisions.items() if decision == "accept"
        ),
        "rejected_candidate_ids": sorted(
            candidate_id for candidate_id, decision in decisions.items() if decision == "reject"
        ),
        "deferred_candidate_ids": sorted(
            candidate_id for candidate_id, decision in decisions.items() if decision == "defer"
        ),
        "manifest": manifest,
        "confirmation_hash": digest(action),
        "effects": {
            "writes_only_user_private_pack": True,
            "modifies_bundled_public_pack": False,
            "network_or_git_side_effects": False,
        },
    }
    return plan, result_rows


def write_file_sync(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o600)


def ensure_privacy_guard(pack: Path, *, create: bool = False) -> None:
    guard = pack / ".gitignore"
    if guard.is_symlink():
        raise LearningError("private pack .gitignore must not be a symlink")
    if guard.exists():
        if not guard.is_file() or guard.read_bytes() != PACK_GITIGNORE:
            raise LearningError("private pack .gitignore does not match the privacy guard")
        return
    if not create:
        raise LearningError("private pack .gitignore privacy guard is missing")
    write_file_sync(guard, PACK_GITIGNORE)


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical_bytes(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temp.unlink(missing_ok=True)


def write_version(pack: Path, plan: dict[str, Any], rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    pack = resolve_pack(str(pack))
    action = plan["preview"]
    if action.get("privacy_guard_sha256") != sha256_bytes(PACK_GITIGNORE):
        raise LearningError("confirmed plan does not bind the private pack privacy guard")
    revision = action["next_revision"]
    pack.mkdir(mode=0o700, parents=True, exist_ok=True)
    ensure_privacy_guard(pack, create=True)
    versions = pack / "versions"
    versions.mkdir(mode=0o700, parents=True, exist_ok=True)
    final_dir = versions / f"v{revision:06d}"
    if final_dir.exists():
        raise LearningError("revision already exists; concurrent writer or incomplete prior attempt")
    temp_dir = Path(tempfile.mkdtemp(prefix=f".v{revision:06d}.", suffix=".tmp", dir=str(versions)))
    promoted = False
    try:
        for name in FILES:
            write_file_sync(temp_dir / name, jsonl_bytes(rows[name]))
        write_file_sync(temp_dir / "manifest.json", canonical_bytes(plan["manifest"]) + b"\n")
        version_fd = os.open(temp_dir, os.O_RDONLY)
        try:
            os.fsync(version_fd)
        finally:
            os.close(version_fd)
        os.rename(temp_dir, final_dir)
        promoted = True
        versions_fd = os.open(versions, os.O_RDONLY)
        try:
            os.fsync(versions_fd)
        finally:
            os.close(versions_fd)
        pack_model = load_knowledge_pack(
            final_dir / "sources.jsonl", final_dir / "atoms.jsonl", mode="private"
        )
        if len(pack_model.sources) != len(rows["sources.jsonl"]):
            raise LearningError("private runtime excluded a committed source")
        if len(pack_model.atoms) != len(rows["atoms.jsonl"]):
            raise LearningError("private runtime excluded a committed atom")
        if len(pack_model.concepts) != len(rows["concepts.jsonl"]):
            raise LearningError("private runtime excluded a committed concept")
        if len(pack_model.methods) != len(rows["methods.jsonl"]):
            raise LearningError("private runtime excluded a committed method")
        active = {
            "schema_version": ACTIVE_SCHEMA,
            "pack_id": action["pack_id"],
            "pack_kind": PACK_KIND,
            "revision": revision,
            "version_dir": f"versions/v{revision:06d}",
            "manifest_sha256": action["result_manifest_sha256"],
            "action": plan["manifest"]["action"],
            "restores_revision": plan["manifest"]["restores_revision"],
        }
        atomic_write_json(pack / "active.json", active)
        return active
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        if promoted and final_dir.exists():
            active_revision = current_state(pack)["revision"]
            if active_revision != revision:
                shutil.rmtree(final_dir)
        raise


def verify_pack(pack: Path) -> dict[str, Any]:
    pack = resolve_pack(str(pack))
    ensure_privacy_guard(pack)
    state = current_state(pack)
    if state["revision"] == 0:
        raise LearningError("pack has no active revision")
    version_dir = active_version_dir(pack, state)
    assert version_dir is not None
    manifests = verify_manifest_chain(pack, state)
    manifest = manifests[state["revision"]]
    if manifest.get("revision") != state["revision"] or manifest.get("pack_id") != state["pack_id"]:
        raise LearningError("active pointer and manifest disagree")
    rows: dict[str, list[dict[str, Any]]] = {}
    for name in FILES:
        path = version_dir / name
        data = path.read_bytes()
        if sha256_bytes(data) != manifest["files"][name]:
            raise LearningError(f"pack file hash mismatch: {name}")
        rows[name] = load_jsonl(path)
    validate_private_rows(rows)
    actual_counts = {
        name.removesuffix(".jsonl").replace("-", "_"): len(rows[name]) for name in FILES
    }
    if manifest.get("counts") != actual_counts:
        raise LearningError("manifest counts do not match pack records")
    pack_model = load_knowledge_pack(
        version_dir / "sources.jsonl", version_dir / "atoms.jsonl", mode="private"
    )
    if len(pack_model.sources) != len(rows["sources.jsonl"]):
        raise LearningError("private runtime excluded a source")
    if len(pack_model.atoms) != len(rows["atoms.jsonl"]):
        raise LearningError("private runtime excluded an atom")
    if len(pack_model.concepts) != len(rows["concepts.jsonl"]):
        raise LearningError("private runtime excluded a concept")
    if len(pack_model.methods) != len(rows["methods.jsonl"]):
        raise LearningError("private runtime excluded a method")
    return {
        "status": "PASS",
        "pack_id": state["pack_id"],
        "pack_kind": PACK_KIND,
        "revision": state["revision"],
        "action": state["action"],
        "restores_revision": state["restores_revision"],
        "manifest_sha256": state["manifest_sha256"],
        "counts": manifest["counts"],
        "private_runtime": "validated",
    }


def read_revision(pack: Path, revision: int) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    pack = resolve_pack(str(pack))
    if revision < 1:
        raise LearningError("rollback target revision must be positive")
    state = current_state(pack)
    if state["revision"] == 0:
        raise LearningError("pack has no active revision")
    if revision > state["revision"]:
        raise LearningError("rollback target revision does not exist")
    manifests = verify_manifest_chain(pack, state)
    version_dir = pack / "versions" / f"v{revision:06d}"
    if not version_dir.is_dir() or version_dir.is_symlink():
        raise LearningError("rollback target revision does not exist")
    manifest = manifests[revision]
    rows = {name: load_jsonl(version_dir / name) for name in FILES}
    for name in FILES:
        if sha256_bytes((version_dir / name).read_bytes()) != manifest.get("files", {}).get(name):
            raise LearningError(f"rollback target file hash mismatch: {name}")
    validate_private_rows(rows)
    return manifest, rows


def build_rollback_plan(pack: Path, to_revision: int) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    pack = resolve_pack(str(pack))
    state = current_state(pack)
    if state["revision"] == 0:
        raise LearningError("cannot rollback an empty pack")
    if to_revision >= state["revision"]:
        raise LearningError("rollback target must be older than the active revision")
    target_manifest, rows = read_revision(pack, to_revision)
    file_hashes = {name: sha256_bytes(jsonl_bytes(rows[name])) for name in FILES}
    next_revision = state["revision"] + 1
    manifest = build_manifest(
        pack_id=state["pack_id"],
        revision=next_revision,
        parent_revision=state["revision"],
        parent_manifest_sha256=state["manifest_sha256"],
        action="rollback",
        restores_revision=to_revision,
        file_hashes=file_hashes,
        counts=target_manifest["counts"],
        change_set_hash=None,
        decisions_hash=None,
    )
    action = {
        "action": "rollback_user_private_knowledge",
        "pack_path": str(pack),
        "pack_id": state["pack_id"],
        "expected_revision": state["revision"],
        "expected_manifest_sha256": state["manifest_sha256"],
        "restore_revision": to_revision,
        "restore_manifest_sha256": digest(target_manifest),
        "next_revision": next_revision,
        "result_file_hashes": file_hashes,
        "result_manifest_sha256": digest(manifest),
        "privacy_guard_sha256": sha256_bytes(PACK_GITIGNORE),
    }
    return (
        {
            "schema_version": "knowledge-rollback-plan-v1",
            "preview": action,
            "manifest": manifest,
            "confirmation_hash": digest(action),
            "effects": {
                "creates_new_revision": True,
                "deletes_history": False,
                "modifies_bundled_public_pack": False,
            },
        },
        rows,
    )


def assert_expected(state: dict[str, Any], expected_revision: int, action: dict[str, Any]) -> None:
    if expected_revision != action["expected_revision"]:
        raise LearningError("expected revision does not match the confirmed plan")
    if state["revision"] != expected_revision:
        raise LearningError(
            f"revision conflict: expected {expected_revision}, current {state['revision']}"
        )
    if state["manifest_sha256"] != action["expected_manifest_sha256"]:
        raise LearningError("active manifest changed after planning")


def cmd_analyze(args: argparse.Namespace) -> int:
    pack = resolve_pack(args.pack)
    change_set = load_json(Path(args.change_set).expanduser().resolve())
    print(json.dumps(analyze_change_set(pack, change_set), ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def cmd_plan_apply(args: argparse.Namespace) -> int:
    pack = resolve_pack(args.pack)
    change_set = load_json(Path(args.change_set).expanduser().resolve())
    decisions = load_json(Path(args.decisions).expanduser().resolve())
    plan, _ = build_apply_plan(pack, change_set, decisions)
    print(json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    pack = resolve_pack(args.pack)
    change_set = load_json(Path(args.change_set).expanduser().resolve())
    decisions = load_json(Path(args.decisions).expanduser().resolve())
    plan, rows = build_apply_plan(pack, change_set, decisions)
    if args.confirmation_hash != plan["confirmation_hash"]:
        raise LearningError("confirmation hash does not match the exact apply plan")
    state = current_state(pack)
    assert_expected(state, args.expected_revision, plan["preview"])
    active = write_version(pack, plan, rows)
    result = verify_pack(pack)
    print(json.dumps({"committed": active, "verification": result}, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    pack = resolve_pack(args.pack)
    print(json.dumps(verify_pack(pack), ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def cmd_plan_rollback(args: argparse.Namespace) -> int:
    pack = resolve_pack(args.pack)
    plan, _ = build_rollback_plan(pack, args.to_revision)
    print(json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    pack = resolve_pack(args.pack)
    plan, rows = build_rollback_plan(pack, args.to_revision)
    if args.confirmation_hash != plan["confirmation_hash"]:
        raise LearningError("confirmation hash does not match the exact rollback plan")
    state = current_state(pack)
    assert_expected(state, args.expected_revision, plan["preview"])
    active = write_version(pack, plan, rows)
    result = verify_pack(pack)
    print(json.dumps({"rolled_back": active, "verification": result}, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    pack_path = resolve_pack(args.pack)
    verify_pack(pack_path)
    state = current_state(pack_path)
    version_dir = active_version_dir(pack_path, state)
    assert version_dir is not None
    pack = load_knowledge_pack(
        version_dir / "sources.jsonl", version_dir / "atoms.jsonl", mode="private"
    )
    result = search_knowledge_pack(pack, args.query, limit=args.limit)
    result["pack_id"] = state["pack_id"]
    result["pack_revision"] = state["revision"]
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze")
    analyze.add_argument("--pack", required=True)
    analyze.add_argument("--change-set", required=True)
    analyze.set_defaults(func=cmd_analyze)

    plan_apply = sub.add_parser("plan-apply")
    plan_apply.add_argument("--pack", required=True)
    plan_apply.add_argument("--change-set", required=True)
    plan_apply.add_argument("--decisions", required=True)
    plan_apply.set_defaults(func=cmd_plan_apply)

    apply = sub.add_parser("apply")
    apply.add_argument("--pack", required=True)
    apply.add_argument("--change-set", required=True)
    apply.add_argument("--decisions", required=True)
    apply.add_argument("--expected-revision", type=int, required=True)
    apply.add_argument("--confirmation-hash", required=True)
    apply.set_defaults(func=cmd_apply)

    verify = sub.add_parser("verify")
    verify.add_argument("--pack", required=True)
    verify.set_defaults(func=cmd_verify)

    plan_rollback = sub.add_parser("plan-rollback")
    plan_rollback.add_argument("--pack", required=True)
    plan_rollback.add_argument("--to-revision", type=int, required=True)
    plan_rollback.set_defaults(func=cmd_plan_rollback)

    rollback = sub.add_parser("rollback")
    rollback.add_argument("--pack", required=True)
    rollback.add_argument("--to-revision", type=int, required=True)
    rollback.add_argument("--expected-revision", type=int, required=True)
    rollback.add_argument("--confirmation-hash", required=True)
    rollback.set_defaults(func=cmd_rollback)

    search = sub.add_parser("search")
    search.add_argument("--pack", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=5)
    search.set_defaults(func=cmd_search)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (LearningError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
