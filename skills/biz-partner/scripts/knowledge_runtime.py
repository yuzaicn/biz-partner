#!/usr/bin/env python3
"""Deterministic local folder indexing and Atom v2 knowledge retrieval."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from atom_contract import validate_atom_v2


FOLDER_INDEX_SCHEMA = "biz-partner-folder-index-v1"
ATOM_SCHEMA = "2.0"
DEFAULT_MAX_BYTES = 1_048_576
DEFAULT_RECALL_THRESHOLD = 0.85
DEFAULT_EXTENSIONS = frozenset(
    {
        ".adoc",
        ".cfg",
        ".conf",
        ".css",
        ".csv",
        ".fish",
        ".htm",
        ".html",
        ".ini",
        ".js",
        ".json",
        ".jsonl",
        ".jsx",
        ".log",
        ".md",
        ".markdown",
        ".py",
        ".rst",
        ".sh",
        ".sql",
        ".toml",
        ".ts",
        ".tsv",
        ".tsx",
        ".txt",
        ".yaml",
        ".yml",
        ".zsh",
    }
)
PUBLIC_RECORD_STATUSES = frozenset({"release_eligible", "published"})
PRIVATE_RECORD_STATUSES = PUBLIC_RECORD_STATUSES | frozenset(
    {"candidate", "evidence_checked", "reviewed"}
)
BLOCKED_RECORD_STATUSES = frozenset({"blocked", "rejected", "unresolved", "archived"})
PUBLIC_RIGHTS_STATUSES = frozenset(
    {
        "licensed_for_redistribution",
        "open_license",
        "owner_authorized_public_release",
        "project_paraphrase_only",
        "public_domain",
        "redistribution_allowed",
    }
)
PUBLIC_LICENSE_SCOPES = frozenset(
    {"redistribution", "redistribution_and_derivatives", "public_domain"}
)
PRIVATE_DENIED_RIGHTS = frozenset(
    {"denied", "no_permission", "restricted", "unknown", "use_prohibited"}
)
DISALLOWED_LICENSE_MARKERS = frozenset(
    {
        "n/a",
        "na",
        "none",
        "not applicable",
        "not verified",
        "pending",
        "rights pending",
        "tbd",
        "unknown",
        "unverified",
    }
)
PUBLIC_DECISION_VALUES = {
    "authorization_status": frozenset(
        {
            "owner_authorized_public_release",
            "project_owner_authorized_public_paraphrase",
            "public_release_authorized",
            "redistribution_authorized",
        }
    ),
    "release_decision": frozenset(
        {
            "approved_for_public_release",
            "public_release_approved",
            "release_eligible",
            "published",
        }
    ),
}
EVAL_FIELDS = frozenset(
    {
        "case_id",
        "case_kind",
        "query",
        "relevant_atom_ids",
        "relevant_method_ids",
        "relevant_concept_ids",
    }
)
ALLOWED_RELATION_TYPES = frozenset(
    {"depends_on", "supports", "refines", "contradicts"}
)
METHOD_RUNTIME_FIELDS = frozenset(
    {
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
)
ASCII_WORD_RE = re.compile(r"[a-z0-9]+(?:[._+-][a-z0-9]+)*")


@dataclass(frozen=True)
class KnowledgePack:
    mode: str
    sources: dict[str, dict[str, Any]]
    atoms: dict[str, dict[str, Any]]
    concepts: dict[str, dict[str, Any]]
    methods: dict[str, dict[str, Any]]
    all_atoms: dict[str, dict[str, Any]]
    excluded_sources: dict[str, str]
    excluded_atoms: dict[str, str]
    excluded_concepts: dict[str, str]
    excluded_methods: dict[str, str]


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{label} must not contain leading or trailing whitespace")
    return value


def require_string_list(
    value: Any, label: str, *, allow_empty: bool = True
) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        qualifier = "non-empty " if not allow_empty else ""
        raise ValueError(f"{label} must be a {qualifier}list")
    if not all(isinstance(item, str) and item.strip() == item and item for item in value):
        raise ValueError(f"{label} must contain only non-empty trimmed strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must not contain duplicates")
    return value


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {label} line {line_number}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"non-object row in {label} line {line_number}")
        rows.append(value)
    return rows


def is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
    )


def lexical_terms(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    terms = ["w:" + match.group(0) for match in ASCII_WORD_RE.finditer(normalized)]
    run: list[str] = []

    def flush() -> None:
        if not run:
            return
        for size in (1, 2, 3):
            if len(run) < size:
                continue
            terms.extend(
                f"c{size}:" + "".join(run[index : index + size])
                for index in range(len(run) - size + 1)
            )
        run.clear()

    for char in normalized:
        if is_cjk(char):
            run.append(char)
        else:
            flush()
    flush()
    return terms


def term_weight(term: str) -> float:
    if term.startswith("c1:"):
        return 0.2
    if term.startswith("c2:"):
        return 1.0
    if term.startswith("c3:"):
        return 1.35
    return 1.1


def hashed_term(term: str) -> str:
    kind, _, value = term.partition(":")
    return kind + ":" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def hashed_term_counts(text: str) -> dict[str, int]:
    return dict(sorted(Counter(hashed_term(term) for term in lexical_terms(text)).items()))


def query_counts(query: str, *, hashed: bool) -> Counter[str]:
    require_string(query, "query")
    terms = lexical_terms(query)
    if not terms:
        raise ValueError("query contains no searchable terms")
    if hashed:
        terms = [hashed_term(term) for term in terms]
    return Counter(terms)


def _kind_from_key(key: str) -> str:
    return key.split(":", 1)[0] + ":"


def rank_counters(
    query: Counter[str], documents: dict[str, Counter[str]]
) -> list[tuple[str, float, float]]:
    if not documents:
        return []
    document_frequency: Counter[str] = Counter()
    for counter in documents.values():
        document_frequency.update(counter.keys())
    total_documents = len(documents)
    query_weight = sum(term_weight(_kind_from_key(key)) for key in query)
    ranked: list[tuple[str, float, float]] = []
    for document_id, counter in documents.items():
        matched_weight = 0.0
        raw_score = 0.0
        for key, query_frequency in query.items():
            document_frequency_for_term = counter.get(key, 0)
            if not document_frequency_for_term:
                continue
            weight = term_weight(_kind_from_key(key))
            matched_weight += weight
            inverse_frequency = math.log(
                (total_documents + 1) / (document_frequency[key] + 1)
            ) + 1.0
            raw_score += (
                weight
                * inverse_frequency
                * min(query_frequency, document_frequency_for_term)
                * (1.0 + math.log(document_frequency_for_term))
            )
        if raw_score <= 0:
            continue
        coverage = matched_weight / query_weight if query_weight else 0.0
        ranked.append((document_id, round(raw_score + 2.0 * coverage, 8), coverage))
    ranked.sort(key=lambda row: (-row[1], -row[2], row[0]))
    return ranked


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def root_id(root: Path) -> str:
    return "root_" + hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]


def document_id(root_identifier: str, relative_path: str) -> str:
    payload = f"{root_identifier}\0{relative_path}".encode("utf-8")
    return "doc_" + hashlib.sha256(payload).hexdigest()[:24]


def canonical_roots(raw_roots: Iterable[str | Path]) -> list[Path]:
    roots: list[Path] = []
    for raw_root in raw_roots:
        root = Path(raw_root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError(f"allowlisted root is not a directory: {root}")
        if root not in roots:
            roots.append(root)
    if not roots:
        raise ValueError("at least one explicit allowlisted root is required")
    return sorted(roots, key=str)


def normalize_extensions(extensions: Iterable[str] | None) -> frozenset[str]:
    if extensions is None:
        return DEFAULT_EXTENSIONS
    normalized: set[str] = set()
    for value in extensions:
        extension = require_string(value, "extension").casefold()
        if not extension.startswith("."):
            extension = "." + extension
        normalized.add(extension)
    if not normalized:
        raise ValueError("at least one extension is required")
    return frozenset(normalized)


def _skip(root_identifier: str, relative_path: str, reason: str) -> dict[str, str]:
    return {
        "root_id": root_identifier,
        "path": relative_path,
        "reason": reason,
    }


def scan_root(
    root: Path,
    *,
    extensions: frozenset[str],
    max_bytes: int,
    excluded_paths: frozenset[Path],
    prior_documents: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, int]]:
    identifier = root_id(root)
    documents: list[dict[str, Any]] = []
    skips: list[dict[str, str]] = []
    changes = Counter({"added": 0, "updated": 0, "unchanged": 0})
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            relative = directory.relative_to(root).as_posix() or "."
            skips.append(_skip(identifier, relative, f"directory_read_error:{exc.errno}"))
            continue
        for entry in entries:
            entry_path = Path(entry.path)
            relative_path = entry_path.relative_to(root).as_posix()
            if any(part.startswith(".") for part in Path(relative_path).parts):
                reason = "hidden_directory" if entry.is_dir(follow_symlinks=False) else "hidden_file"
                skips.append(_skip(identifier, relative_path, reason))
                continue
            if entry.is_symlink():
                try:
                    target = entry_path.resolve(strict=True)
                except OSError:
                    skips.append(_skip(identifier, relative_path, "broken_symlink"))
                    continue
                if not is_within(target, root):
                    skips.append(_skip(identifier, relative_path, "out_of_root_symlink"))
                    continue
                if target.is_dir():
                    skips.append(_skip(identifier, relative_path, "symlink_directory_not_traversed"))
                    continue
                if not target.is_file():
                    skips.append(_skip(identifier, relative_path, "non_regular_file"))
                    continue
                read_path = target
            elif entry.is_dir(follow_symlinks=False):
                stack.append(entry_path)
                continue
            elif entry.is_file(follow_symlinks=False):
                read_path = entry_path
            else:
                skips.append(_skip(identifier, relative_path, "non_regular_file"))
                continue
            try:
                resolved_read_path = read_path.resolve(strict=True)
            except OSError:
                skips.append(_skip(identifier, relative_path, "file_disappeared"))
                continue
            if not is_within(resolved_read_path, root):
                skips.append(_skip(identifier, relative_path, "out_of_root_resolution"))
                continue
            if resolved_read_path in excluded_paths or entry_path.absolute() in excluded_paths:
                skips.append(_skip(identifier, relative_path, "index_target"))
                continue
            if entry_path.suffix.casefold() not in extensions:
                skips.append(_skip(identifier, relative_path, "unsupported_extension"))
                continue
            try:
                stat = resolved_read_path.stat()
            except OSError as exc:
                skips.append(_skip(identifier, relative_path, f"stat_error:{exc.errno}"))
                continue
            if stat.st_size > max_bytes:
                skips.append(_skip(identifier, relative_path, "exceeds_max_bytes"))
                continue
            try:
                data = resolved_read_path.read_bytes()
            except OSError as exc:
                skips.append(_skip(identifier, relative_path, f"file_read_error:{exc.errno}"))
                continue
            if len(data) > max_bytes:
                skips.append(_skip(identifier, relative_path, "exceeds_max_bytes"))
                continue
            if b"\x00" in data:
                skips.append(_skip(identifier, relative_path, "binary_nul"))
                continue
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                skips.append(_skip(identifier, relative_path, "invalid_utf8"))
                continue
            content_hash = sha256_bytes(data)
            doc_identifier = document_id(identifier, relative_path)
            prior = prior_documents.get(doc_identifier)
            if prior is not None and prior.get("sha256") == content_hash:
                term_counts = prior.get("term_counts")
                if not isinstance(term_counts, dict):
                    term_counts = hashed_term_counts(text)
                changes["unchanged"] += 1
            else:
                term_counts = hashed_term_counts(text)
                changes["updated" if prior is not None else "added"] += 1
            documents.append(
                {
                    "document_id": doc_identifier,
                    "root_id": identifier,
                    "path": relative_path,
                    "sha256": content_hash,
                    "size": len(data),
                    "mtime_ns": stat.st_mtime_ns,
                    "line_count": len(text.splitlines()),
                    "term_counts": term_counts,
                }
            )
    return documents, skips, dict(changes)


def validate_folder_index(index: dict[str, Any]) -> None:
    if index.get("schema_version") != FOLDER_INDEX_SCHEMA:
        raise ValueError("unsupported folder index schema")
    roots = index.get("roots")
    documents = index.get("documents")
    if not isinstance(roots, list) or not roots:
        raise ValueError("folder index roots must be a non-empty list")
    if not isinstance(documents, list):
        raise ValueError("folder index documents must be a list")
    root_ids: set[str] = set()
    for row in roots:
        if not isinstance(row, dict):
            raise ValueError("folder index root row must be an object")
        identifier = require_string(row.get("root_id"), "folder index root_id")
        root = Path(require_string(row.get("path"), f"folder index root path: {identifier}"))
        if not root.is_absolute():
            raise ValueError(f"folder index root must be absolute: {identifier}")
        if identifier in root_ids:
            raise ValueError(f"duplicate folder index root: {identifier}")
        root_ids.add(identifier)
    document_ids: set[str] = set()
    for row in documents:
        if not isinstance(row, dict):
            raise ValueError("folder index document row must be an object")
        identifier = require_string(row.get("document_id"), "folder index document_id")
        if identifier in document_ids:
            raise ValueError(f"duplicate folder index document: {identifier}")
        document_ids.add(identifier)
        if row.get("root_id") not in root_ids:
            raise ValueError(f"document references unknown root: {identifier}")
        relative_path = Path(require_string(row.get("path"), f"document path: {identifier}"))
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"unsafe document path: {identifier}")
        require_string(row.get("sha256"), f"document sha256: {identifier}")
        term_counts = row.get("term_counts")
        if not isinstance(term_counts, dict) or not all(
            isinstance(key, str) and isinstance(value, int) and value > 0
            for key, value in term_counts.items()
        ):
            raise ValueError(f"invalid term_counts: {identifier}")


def build_folder_index(
    roots: Iterable[str | Path],
    *,
    prior_index: dict[str, Any] | None = None,
    extensions: Iterable[str] | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    excluded_paths: Iterable[str | Path] = (),
) -> tuple[dict[str, Any], dict[str, int]]:
    if not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")
    resolved_roots = canonical_roots(roots)
    selected_extensions = normalize_extensions(extensions)
    prior_documents: dict[str, dict[str, Any]] = {}
    prior_ids: set[str] = set()
    if prior_index is not None:
        validate_folder_index(prior_index)
        prior_documents = {row["document_id"]: row for row in prior_index["documents"]}
        prior_ids = set(prior_documents)
    excluded = frozenset(Path(path).expanduser().absolute() for path in excluded_paths)
    documents: list[dict[str, Any]] = []
    skips: list[dict[str, str]] = []
    changes = Counter({"added": 0, "updated": 0, "unchanged": 0, "deleted": 0})
    for root in resolved_roots:
        root_documents, root_skips, root_changes = scan_root(
            root,
            extensions=selected_extensions,
            max_bytes=max_bytes,
            excluded_paths=excluded,
            prior_documents=prior_documents,
        )
        documents.extend(root_documents)
        skips.extend(root_skips)
        changes.update(root_changes)
    current_ids = {row["document_id"] for row in documents}
    changes["deleted"] = len(prior_ids - current_ids)
    index = {
        "schema_version": FOLDER_INDEX_SCHEMA,
        "roots": [
            {"root_id": root_id(root), "path": str(root)} for root in resolved_roots
        ],
        "config": {
            "extensions": sorted(selected_extensions),
            "max_bytes": max_bytes,
            "stores_original_text": False,
            "term_representation": "sha256-hashed-unicode-lexical-features",
        },
        "documents": sorted(documents, key=lambda row: (row["root_id"], row["path"])),
        "skips": sorted(skips, key=lambda row: (row["root_id"], row["path"], row["reason"])),
    }
    validate_folder_index(index)
    return index, dict(changes)


def build_folder_index_plan(
    roots: Iterable[str | Path],
    *,
    index_path: Path,
    prior_index: dict[str, Any] | None = None,
    extensions: Iterable[str] | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    target = index_path.expanduser().absolute()
    index, changes = build_folder_index(
        roots,
        prior_index=prior_index,
        extensions=extensions,
        max_bytes=max_bytes,
        excluded_paths=[target],
    )
    plan = {
        "action": "commit_folder_index",
        "index_path": str(target),
        "roots": index["roots"],
        "options": index["config"],
        "prior_index_sha256": (
            sha256_bytes(canonical_json_bytes(prior_index)) if prior_index is not None else None
        ),
        "result_index_sha256": sha256_bytes(canonical_json_bytes(index)),
        "changes": changes,
    }
    return {
        "plan": plan,
        "confirmation_hash": sha256_bytes(canonical_json_bytes(plan)),
        "index": index,
    }


def atomic_write_json(path: Path, value: Any) -> str:
    target = path.expanduser().absolute()
    if target.exists() and target.is_symlink():
        raise ValueError(f"refusing to replace symlink index target: {target}")
    if not target.parent.is_dir():
        raise ValueError(f"index parent directory does not exist: {target.parent}")
    payload = canonical_json_bytes(value)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent, prefix=".knowledge-index-", delete=False
        ) as handle:
            temporary_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
        temporary_name = None
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
    return sha256_bytes(payload)


def confidence_label(coverage: float) -> str:
    if coverage >= 0.75:
        return "high"
    if coverage >= 0.4:
        return "medium"
    return "low"


def best_snippet(text: str, query: str, *, max_chars: int = 280) -> tuple[int, str]:
    query_terms_set = set(lexical_terms(query))
    lines = text.splitlines() or [text]
    best_index = 0
    best_score = -1.0
    for index, line in enumerate(lines):
        line_terms = Counter(lexical_terms(line))
        score = sum(
            term_weight(term) for term in query_terms_set if line_terms.get(term, 0)
        )
        if score > best_score:
            best_index = index
            best_score = score
    snippet = " ".join(lines[best_index].strip().split())
    if len(snippet) > max_chars:
        snippet = snippet[: max_chars - 1].rstrip() + "…"
    return best_index + 1, snippet


def search_folder_index(
    index: dict[str, Any], query: str, *, limit: int = 5
) -> dict[str, Any]:
    validate_folder_index(index)
    if limit <= 0:
        raise ValueError("limit must be positive")
    roots = {row["root_id"]: Path(row["path"]) for row in index["roots"]}
    documents = {row["document_id"]: row for row in index["documents"]}
    counters = {
        identifier: Counter(row["term_counts"]) for identifier, row in documents.items()
    }
    ranking = rank_counters(query_counts(query, hashed=True), counters)
    results: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    for identifier, score, coverage in ranking:
        row = documents[identifier]
        root = roots[row["root_id"]]
        locator_path = root / row["path"]
        try:
            resolved_path = locator_path.resolve(strict=True)
        except OSError:
            warnings.append({"document_id": identifier, "reason": "source_missing"})
            continue
        if not is_within(resolved_path, root.resolve(strict=True)) or not resolved_path.is_file():
            warnings.append({"document_id": identifier, "reason": "source_outside_allowlist"})
            continue
        try:
            data = resolved_path.read_bytes()
        except OSError:
            warnings.append({"document_id": identifier, "reason": "source_read_error"})
            continue
        if sha256_bytes(data) != row["sha256"]:
            warnings.append({"document_id": identifier, "reason": "stale_hash_mismatch"})
            continue
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            warnings.append({"document_id": identifier, "reason": "source_not_utf8"})
            continue
        line_number, snippet = best_snippet(text, query)
        results.append(
            {
                "kind": "folder_document",
                "document_id": identifier,
                "score": score,
                "locator": {
                    "root_id": row["root_id"],
                    "path": row["path"],
                    "lines": f"{line_number}-{line_number}",
                    "sha256": row["sha256"],
                },
                "snippet": snippet,
                "confidence": {
                    "retrieval": confidence_label(coverage),
                    "query_term_coverage": round(coverage, 6),
                    "evidence": "hash_verified_at_query_time",
                },
                "temporal": {
                    "indexed_mtime_ns": row["mtime_ns"],
                    "freshness": "hash_verified_at_query_time",
                },
                "conflicts": [],
                "source_attribution": {"atom_ids": []},
            }
        )
        if len(results) >= limit:
            break
    return {
        "query": query,
        "results": results,
        "warnings": sorted(warnings, key=lambda row: (row["document_id"], row["reason"])),
    }


def valid_public_license(record: Any) -> bool:
    if not isinstance(record, dict):
        return False
    try:
        license_id = require_string(record.get("id"), "license.id")
        version = require_string(record.get("version"), "license.version")
        scope = require_string(record.get("scope"), "license.scope")
    except ValueError:
        return False
    return (
        license_id.casefold() not in DISALLOWED_LICENSE_MARKERS
        and version.casefold() not in DISALLOWED_LICENSE_MARKERS
        and scope in PUBLIC_LICENSE_SCOPES
    )


def public_decisions_allowed(record: dict[str, Any]) -> bool:
    for field, allowed in PUBLIC_DECISION_VALUES.items():
        value = record.get(field)
        if value is not None and (
            not isinstance(value, str) or value.strip().casefold() not in allowed
        ):
            return False
    return True


def project_paraphrase_source_allowed(source: dict[str, Any]) -> bool:
    """Keep the special status narrower than source-expression redistribution."""
    license_record = source.get("license")
    return (
        source.get("kind") == "curated_source_for_public_paraphrase"
        and source.get("source_expression_redistribution") == "not_granted_or_claimed"
        and source.get("authorization_status")
        == "project_owner_authorized_public_paraphrase"
        and isinstance(license_record, dict)
        and license_record.get("applies_to")
        == "public-pack original paraphrases and compilation only"
    )


def project_paraphrase_atom_allowed(atom: dict[str, Any], rights: dict[str, Any]) -> bool:
    """Allow only independently worded curated records under this status."""
    license_record = rights.get("license")
    return (
        atom.get("provenance_type") == "public_curated_idea_synthesis"
        and atom.get("authorization_status")
        == "project_owner_authorized_public_paraphrase"
        and rights.get("boundary")
        == "license covers this pack's original paraphrase, not source-book expression"
        and isinstance(license_record, dict)
        and license_record.get("applies_to")
        == "public-pack original paraphrases and compilation only"
    )


def source_policy(source: dict[str, Any], mode: str) -> tuple[bool, str]:
    source_id = require_string(source.get("source_id"), "source_id")
    status = require_string(source.get("status"), f"source status: {source_id}")
    rights = require_string(source.get("rights_status"), f"source rights_status: {source_id}")
    if status in BLOCKED_RECORD_STATUSES:
        return False, f"blocked_status:{status}"
    if mode == "private":
        if status not in PRIVATE_RECORD_STATUSES:
            return False, f"unsupported_private_status:{status}"
        if rights.casefold() in PRIVATE_DENIED_RIGHTS:
            return False, f"private_rights_denied:{rights}"
        return True, "eligible_private"
    if status not in PUBLIC_RECORD_STATUSES:
        return False, f"not_public_status:{status}"
    if rights not in PUBLIC_RIGHTS_STATUSES:
        return False, f"not_public_rights:{rights}"
    if rights == "project_paraphrase_only" and not project_paraphrase_source_allowed(source):
        return False, "invalid_project_paraphrase_boundary"
    if not valid_public_license(source.get("license")):
        return False, "missing_or_invalid_public_license"
    if not public_decisions_allowed(source):
        return False, "public_decision_not_approved"
    return True, "eligible_public"


def atom_policy(atom: dict[str, Any], mode: str) -> tuple[bool, str]:
    atom_id = require_string(atom.get("atom_id"), "atom_id")
    status = require_string(atom.get("status"), f"atom status: {atom_id}")
    rights = atom.get("rights")
    if not isinstance(rights, dict):
        raise ValueError(f"atom rights must be an object: {atom_id}")
    redistribution = require_string(
        rights.get("redistribution"), f"atom rights.redistribution: {atom_id}"
    )
    if status in BLOCKED_RECORD_STATUSES:
        return False, f"blocked_status:{status}"
    if mode == "private":
        if status not in PRIVATE_RECORD_STATUSES:
            return False, f"unsupported_private_status:{status}"
        if redistribution.casefold() in PRIVATE_DENIED_RIGHTS:
            return False, f"private_rights_denied:{redistribution}"
        return True, "eligible_private"
    if status not in PUBLIC_RECORD_STATUSES:
        return False, f"not_public_status:{status}"
    if redistribution not in PUBLIC_RIGHTS_STATUSES:
        return False, f"not_public_rights:{redistribution}"
    if redistribution == "project_paraphrase_only" and not project_paraphrase_atom_allowed(
        atom, rights
    ):
        return False, "invalid_project_paraphrase_boundary"
    if not valid_public_license(rights.get("license")):
        return False, "missing_or_invalid_public_license"
    if not public_decisions_allowed(atom):
        return False, "public_decision_not_approved"
    return True, "eligible_public"


def supporting_record_policy(
    record: dict[str, Any], record_id: str, mode: str
) -> tuple[bool, str]:
    """Apply the same fail-closed rights boundary to concepts and methods."""
    status = require_string(record.get("status"), f"supporting record status: {record_id}")
    rights = record.get("rights")
    if not isinstance(rights, dict):
        raise ValueError(f"supporting record rights must be an object: {record_id}")
    redistribution = require_string(
        rights.get("redistribution"),
        f"supporting record rights.redistribution: {record_id}",
    )
    if status in BLOCKED_RECORD_STATUSES:
        return False, f"blocked_status:{status}"
    if mode == "private":
        if status not in PRIVATE_RECORD_STATUSES:
            return False, f"unsupported_private_status:{status}"
        if redistribution.casefold() in PRIVATE_DENIED_RIGHTS:
            return False, f"private_rights_denied:{redistribution}"
        return True, "eligible_private"
    if status not in PUBLIC_RECORD_STATUSES:
        return False, f"not_public_status:{status}"
    if redistribution not in PUBLIC_RIGHTS_STATUSES:
        return False, f"not_public_rights:{redistribution}"
    if redistribution == "project_paraphrase_only" and (
        rights.get("boundary")
        != "license covers this pack's original paraphrase, not source-book expression"
        or not isinstance(rights.get("license"), dict)
        or rights["license"].get("applies_to")
        != "public-pack original paraphrases and compilation only"
    ):
        return False, "invalid_project_paraphrase_boundary"
    if not valid_public_license(rights.get("license")):
        return False, "missing_or_invalid_public_license"
    if not public_decisions_allowed(record):
        return False, "public_decision_not_approved"
    return True, "eligible_public"


def validate_named_source(source: dict[str, Any]) -> None:
    source_id = source["source_id"]
    attribution_mode = source.get("attribution_mode")
    display_name = source.get("public_attribution_name")
    if attribution_mode is None and display_name is None:
        return
    if attribution_mode != "when_materially_used":
        raise ValueError(f"named source has invalid attribution_mode: {source_id}")
    require_string(display_name, f"named source public_attribution_name: {source_id}")
    if source.get("relationship_to_runtime_user") != "external_named_source":
        raise ValueError(f"named source must be external to runtime user: {source_id}")
    if source.get("ownership_status") != "not_claimed":
        raise ValueError(f"named source ownership must be not_claimed: {source_id}")


def load_knowledge_pack(
    source_registry_path: Path, atoms_path: Path, *, mode: str = "public"
) -> KnowledgePack:
    if mode not in {"public", "private"}:
        raise ValueError("mode must be public or private")
    source_rows = load_jsonl(source_registry_path, "source registry")
    atom_rows = load_jsonl(atoms_path, "atoms")
    concepts_path = atoms_path.parent / "concepts.jsonl"
    methods_path = atoms_path.parent / "methods.jsonl"
    concept_rows = load_jsonl(concepts_path, "concepts") if concepts_path.is_file() else []
    method_rows = load_jsonl(methods_path, "methods") if methods_path.is_file() else []
    all_sources: dict[str, dict[str, Any]] = {}
    excluded_sources: dict[str, str] = {}
    eligible_sources: dict[str, dict[str, Any]] = {}
    for row in source_rows:
        source_id = require_string(row.get("source_id"), "source_id")
        if source_id in all_sources:
            raise ValueError(f"duplicate source id: {source_id}")
        validate_named_source(row)
        all_sources[source_id] = row
        allowed, reason = source_policy(row, mode)
        if allowed:
            eligible_sources[source_id] = row
        else:
            excluded_sources[source_id] = reason
    all_atoms: dict[str, dict[str, Any]] = {}
    for row in atom_rows:
        atom_id = require_string(row.get("atom_id"), "atom_id")
        if atom_id in all_atoms:
            raise ValueError(f"duplicate atom id: {atom_id}")
        validate_atom_v2(row, allow_private_local_locator=mode == "private")
        source_refs = row.get("source_refs")
        seen_source_ids: set[str] = set()
        for index, ref in enumerate(source_refs):
            if not isinstance(ref, dict):
                raise ValueError(f"atom source ref is not an object: {atom_id}[{index}]")
            source_id = require_string(
                ref.get("source_id"), f"atom source ref source_id: {atom_id}[{index}]"
            )
            if source_id in seen_source_ids:
                raise ValueError(f"duplicate atom source ref: {atom_id} -> {source_id}")
            if source_id not in all_sources:
                raise ValueError(f"atom references unknown source: {atom_id} -> {source_id}")
            seen_source_ids.add(source_id)
        all_atoms[atom_id] = row
    for atom_id, atom in all_atoms.items():
        relations = atom.get("relations", [])
        if not isinstance(relations, list):
            raise ValueError(f"atom relations must be a list: {atom_id}")
        for index, relation in enumerate(relations):
            if not isinstance(relation, dict):
                raise ValueError(f"atom relation is not an object: {atom_id}[{index}]")
            target = require_string(
                relation.get("atom_id"), f"atom relation target: {atom_id}[{index}]"
            )
            relation_type = require_string(
                relation.get("type"), f"atom relation type: {atom_id}[{index}]"
            )
            if set(relation) != {"type", "atom_id"}:
                raise ValueError(f"atom relation has unsupported fields: {atom_id}[{index}]")
            if relation_type not in ALLOWED_RELATION_TYPES:
                raise ValueError(
                    f"atom relation type is not allowed: {atom_id}[{index}] -> {relation_type}"
                )
            if target not in all_atoms:
                raise ValueError(f"atom relation references unknown atom: {atom_id} -> {target}")
    eligible_atoms: dict[str, dict[str, Any]] = {}
    excluded_atoms: dict[str, str] = {}
    for atom_id, atom in all_atoms.items():
        allowed, reason = atom_policy(atom, mode)
        source_ids = [ref["source_id"] for ref in atom["source_refs"]]
        denied_sources = sorted(source_id for source_id in source_ids if source_id not in eligible_sources)
        if not allowed:
            excluded_atoms[atom_id] = reason
        elif denied_sources:
            excluded_atoms[atom_id] = "source_policy:" + ",".join(denied_sources)
        else:
            eligible_atoms[atom_id] = atom
    all_concepts: dict[str, dict[str, Any]] = {}
    excluded_concepts: dict[str, str] = {}
    eligible_concepts: dict[str, dict[str, Any]] = {}
    for raw_row in concept_rows:
        row = dict(raw_row)
        concept_id = require_string(row.get("concept_id"), "concept_id")
        if concept_id in all_concepts:
            raise ValueError(f"duplicate concept id: {concept_id}")
        require_string(row.get("term"), f"concept term: {concept_id}")
        require_string(row.get("definition"), f"concept definition: {concept_id}")
        if row.get("normalized") is None:
            row["normalized"] = row["term"]
        else:
            require_string(row.get("normalized"), f"concept normalized: {concept_id}")
        row.setdefault("aliases", [])
        row.setdefault("source_atoms", [])
        row.setdefault("related_methods", [])
        require_string_list(row["aliases"], f"concept aliases: {concept_id}")
        source_atoms = require_string_list(
            row["source_atoms"], f"concept source_atoms: {concept_id}"
        )
        require_string_list(
            row["related_methods"], f"concept related_methods: {concept_id}"
        )
        unknown_atoms = sorted(set(source_atoms) - set(all_atoms))
        if unknown_atoms:
            raise ValueError(
                f"concept references unknown atoms: {concept_id} -> {','.join(unknown_atoms)}"
            )
        all_concepts[concept_id] = row
        allowed, reason = supporting_record_policy(row, concept_id, mode)
        denied_atoms = sorted(atom_id for atom_id in source_atoms if atom_id not in eligible_atoms)
        if not allowed:
            excluded_concepts[concept_id] = reason
        elif denied_atoms:
            excluded_concepts[concept_id] = "atom_policy:" + ",".join(denied_atoms)
        else:
            eligible_concepts[concept_id] = row

    all_methods: dict[str, dict[str, Any]] = {}
    excluded_methods: dict[str, str] = {}
    eligible_methods: dict[str, dict[str, Any]] = {}
    method_list_fields = (
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
    )
    for row in method_rows:
        method_id = require_string(row.get("method_id"), "method_id")
        if method_id in all_methods:
            raise ValueError(f"duplicate method id: {method_id}")
        unknown_fields = set(row) - METHOD_RUNTIME_FIELDS
        missing_fields = METHOD_RUNTIME_FIELDS - set(row)
        if unknown_fields or missing_fields:
            detail = []
            if unknown_fields:
                detail.append("unknown=" + ",".join(sorted(unknown_fields)))
            if missing_fields:
                detail.append("missing=" + ",".join(sorted(missing_fields)))
            raise ValueError(f"invalid method fields: {method_id} ({'; '.join(detail)})")
        require_string(row.get("title"), f"method title: {method_id}")
        require_string(row.get("purpose"), f"method purpose: {method_id}")
        for field in method_list_fields:
            require_string_list(
                row.get(field),
                f"method {field}: {method_id}",
                allow_empty=field not in {"steps", "atom_ids", "concept_ids"},
            )
        unknown_atoms = sorted(set(row["atom_ids"]) - set(all_atoms))
        unknown_concepts = sorted(set(row["concept_ids"]) - set(all_concepts))
        if unknown_atoms:
            raise ValueError(
                f"method references unknown atoms: {method_id} -> {','.join(unknown_atoms)}"
            )
        if unknown_concepts:
            raise ValueError(
                f"method references unknown concepts: {method_id} -> {','.join(unknown_concepts)}"
            )
        all_methods[method_id] = row
        allowed, reason = supporting_record_policy(row, method_id, mode)
        denied_atoms = sorted(atom_id for atom_id in row["atom_ids"] if atom_id not in eligible_atoms)
        denied_concepts = sorted(
            concept_id for concept_id in row["concept_ids"] if concept_id not in eligible_concepts
        )
        if not allowed:
            excluded_methods[method_id] = reason
        elif denied_atoms:
            excluded_methods[method_id] = "atom_policy:" + ",".join(denied_atoms)
        elif denied_concepts:
            excluded_methods[method_id] = "concept_policy:" + ",".join(denied_concepts)
        else:
            eligible_methods[method_id] = row

    for concept_id, concept in all_concepts.items():
        unknown_methods = sorted(set(concept["related_methods"]) - set(all_methods))
        if unknown_methods:
            raise ValueError(
                f"concept references unknown methods: {concept_id} -> {','.join(unknown_methods)}"
            )
    changed = True
    while changed:
        changed = False
        for concept_id, concept in list(eligible_concepts.items()):
            denied_methods = sorted(
                method_id
                for method_id in concept["related_methods"]
                if method_id not in eligible_methods
            )
            if denied_methods:
                excluded_concepts[concept_id] = "method_policy:" + ",".join(denied_methods)
                del eligible_concepts[concept_id]
                changed = True
        for method_id, method in list(eligible_methods.items()):
            denied_concepts = sorted(
                concept_id
                for concept_id in method["concept_ids"]
                if concept_id not in eligible_concepts
            )
            if denied_concepts:
                excluded_methods[method_id] = "concept_policy:" + ",".join(denied_concepts)
                del eligible_methods[method_id]
                changed = True

    return KnowledgePack(
        mode=mode,
        sources=eligible_sources,
        atoms=eligible_atoms,
        concepts=eligible_concepts,
        methods=eligible_methods,
        all_atoms=all_atoms,
        excluded_sources=excluded_sources,
        excluded_atoms=excluded_atoms,
        excluded_concepts=excluded_concepts,
        excluded_methods=excluded_methods,
    )


def add_weighted_terms(counter: Counter[str], value: Any, weight: int) -> None:
    if isinstance(value, str):
        for term in lexical_terms(value):
            counter[term] += weight
    elif isinstance(value, list):
        for child in value:
            add_weighted_terms(counter, child, weight)


def atom_terms(atom: dict[str, Any]) -> Counter[str]:
    counter: Counter[str] = Counter()
    add_weighted_terms(counter, atom.get("canonical"), 5)
    add_weighted_terms(counter, atom.get("decision_rule"), 4)
    add_weighted_terms(counter, atom.get("procedure"), 4)
    add_weighted_terms(counter, atom.get("domain"), 3)
    add_weighted_terms(counter, atom.get("claim_kind"), 1)
    add_weighted_terms(counter, atom.get("actionability"), 1)
    add_weighted_terms(counter, atom.get("limits"), 1)
    return counter


def concept_terms(concept: dict[str, Any]) -> Counter[str]:
    counter: Counter[str] = Counter()
    add_weighted_terms(counter, concept.get("term"), 6)
    add_weighted_terms(counter, concept.get("aliases", []), 6)
    add_weighted_terms(counter, concept.get("normalized"), 4)
    add_weighted_terms(counter, concept.get("definition"), 2)
    add_weighted_terms(counter, concept.get("anti_definition"), 1)
    add_weighted_terms(counter, concept.get("common_misuse"), 1)
    add_weighted_terms(counter, concept.get("use_when"), 1)
    return counter


def method_terms(method: dict[str, Any]) -> Counter[str]:
    counter: Counter[str] = Counter()
    add_weighted_terms(counter, method.get("method_id"), 7)
    add_weighted_terms(counter, method.get("title"), 6)
    add_weighted_terms(counter, method.get("purpose"), 5)
    add_weighted_terms(counter, method.get("use_when"), 4)
    add_weighted_terms(counter, method.get("inputs"), 2)
    add_weighted_terms(counter, method.get("steps"), 2)
    add_weighted_terms(counter, method.get("outputs"), 2)
    add_weighted_terms(counter, method.get("pitfalls"), 1)
    return counter


def normalized_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def matched_concept_records(
    pack: KnowledgePack, query: str
) -> list[dict[str, Any]]:
    query_normalized = normalized_text(query)
    counters = {
        concept_id: concept_terms(concept)
        for concept_id, concept in pack.concepts.items()
    }
    lexical = {
        concept_id: (score, coverage)
        for concept_id, score, coverage in rank_counters(
            query_counts(query, hashed=False), counters
        )
    }
    matches: list[dict[str, Any]] = []
    for concept_id, concept in pack.concepts.items():
        forms = [("term", concept["term"])]
        forms.extend(("alias", alias) for alias in concept.get("aliases", []))
        normalized = concept.get("normalized")
        if isinstance(normalized, str):
            forms.append(("normalized", normalized))
        exact = [
            {"field": field, "value": value}
            for field, value in forms
            if normalized_text(value) in query_normalized
        ]
        score, coverage = lexical.get(concept_id, (0.0, 0.0))
        if not exact and (coverage < 0.35 or score <= 0):
            continue
        matches.append(
            {
                "concept_id": concept_id,
                "term": concept["term"],
                "group": concept.get("group"),
                "definition": concept["definition"],
                "anti_definition": concept.get("anti_definition"),
                "common_misuse": concept.get("common_misuse"),
                "matched_on": exact or [{"field": "definition", "value": "lexical_overlap"}],
                "score": round(score + (30.0 if exact else 0.0), 8),
                "query_term_coverage": round(coverage, 6),
                "source_atom_ids": list(concept.get("source_atoms", [])),
                "related_method_ids": list(concept.get("related_methods", [])),
            }
        )
    matches.sort(
        key=lambda row: (-row["score"], -row["query_term_coverage"], row["concept_id"])
    )
    return matches


def confidence_score(confidence: Any) -> int:
    if not isinstance(confidence, dict):
        return 0
    points = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
    values = [points.get(str(value).casefold(), 0) for value in confidence.values()]
    return min(values) if values else 0


def source_date_score(value: Any) -> int:
    if not isinstance(value, str):
        return 0
    compact = value.replace("-", "")
    return int(compact) if len(compact) == 8 and compact.isdigit() else 0


def search_knowledge_pack(
    pack: KnowledgePack, query: str, *, limit: int = 5
) -> dict[str, Any]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    query_counter = query_counts(query, hashed=False)
    counters = {atom_id: atom_terms(atom) for atom_id, atom in pack.atoms.items()}
    lexical_ranking = rank_counters(query_counter, counters)
    ranking_by_id = {
        atom_id: [score, coverage, []]
        for atom_id, score, coverage in lexical_ranking
    }
    initial_atom_ids = [atom_id for atom_id, _, _ in lexical_ranking[:5]]

    # One bounded graph hop makes the result explainable without turning the
    # knowledge graph into a recursive answer-expansion mechanism.  Concepts
    # can be found directly from the query or inferred from the initial lexical
    # Top-5 atoms.  Inferred rows retain the atom evidence that caused them to
    # appear.
    direct_concept_matches = matched_concept_records(pack, query)
    concept_by_id = {
        row["concept_id"]: dict(row, inference="direct_lexical", linked_atom_ids=[])
        for row in direct_concept_matches
    }
    for atom_rank, atom_id in enumerate(initial_atom_ids, 1):
        for concept_id, concept in pack.concepts.items():
            if atom_id not in concept.get("source_atoms", []):
                continue
            evidence_score = 18.0 / atom_rank
            existing = concept_by_id.get(concept_id)
            if existing is None:
                concept_by_id[concept_id] = {
                    "concept_id": concept_id,
                    "term": concept["term"],
                    "group": concept.get("group"),
                    "definition": concept["definition"],
                    "anti_definition": concept.get("anti_definition"),
                    "common_misuse": concept.get("common_misuse"),
                    "matched_on": [{"field": "source_atom", "value": atom_id}],
                    "inference": "linked_atom",
                    "linked_atom_ids": [atom_id],
                    "score": round(evidence_score, 8),
                    "query_term_coverage": 0.0,
                    "source_atom_ids": list(concept.get("source_atoms", [])),
                    "related_method_ids": list(concept.get("related_methods", [])),
                }
                continue
            existing["score"] = round(float(existing["score"]) + evidence_score, 8)
            existing["linked_atom_ids"].append(atom_id)
            existing["linked_atom_ids"] = sorted(set(existing["linked_atom_ids"]))
    concept_matches = sorted(
        concept_by_id.values(),
        key=lambda row: (
            -float(row["score"]),
            -float(row["query_term_coverage"]),
            row["concept_id"],
        ),
    )
    matched_concept_ids = {row["concept_id"] for row in concept_matches}
    for concept_rank, concept in enumerate(direct_concept_matches[:5], 1):
        # Only concepts matched from the query may expand atom candidates.
        # Concepts inferred from an initial atom remain visible evidence, but
        # feeding them back into the same ranking would merely amplify the
        # first lexical guess.
        alias_hits = sum(
            item.get("field") == "alias" for item in concept.get("matched_on", [])
        )
        if alias_hits:
            boost = min(45.0, 26.0 + 8.0 * alias_hits)
        elif len(str(concept["term"])) <= 2:
            boost = 8.0
        else:
            boost = min(30.0, 10.0 + 0.25 * float(concept["score"]))
        for atom_id in concept["source_atom_ids"]:
            if atom_id not in pack.atoms:
                continue
            entry = ranking_by_id.setdefault(atom_id, [0.0, 0.0, []])
            entry[0] += boost
            entry[1] = max(entry[1], float(concept["query_term_coverage"]))
            entry[2].append(concept["concept_id"])

    method_counters = {
        method_id: method_terms(method) for method_id, method in pack.methods.items()
    }
    method_lexical = {
        method_id: [score, coverage, []]
        for method_id, score, coverage in rank_counters(query_counter, method_counters)
    }
    for atom_rank, atom_id in enumerate(initial_atom_ids, 1):
        atom_coverage = float(ranking_by_id[atom_id][1])
        for method_id, method in pack.methods.items():
            if atom_id not in method.get("atom_ids", []):
                continue
            entry = method_lexical.setdefault(method_id, [0.0, 0.0, []])
            entry[0] += 18.0 / atom_rank
            entry[1] = max(entry[1], atom_coverage)
            entry[2].append(atom_id)

    # Direct concept language can name the right workflow even when the query
    # shares few literal words with the method prose.  This is the same bounded
    # one-hop graph: query -> concept -> method, with no recursive expansion.
    for concept_rank, concept in enumerate(direct_concept_matches[:5], 1):
        related_methods = set(concept.get("related_method_ids", []))
        related_methods.update(
            method_id
            for method_id, method in pack.methods.items()
            if concept["concept_id"] in method.get("concept_ids", [])
        )
        for method_id in related_methods:
            if method_id not in pack.methods:
                continue
            entry = method_lexical.setdefault(method_id, [0.0, 0.0, []])
            alias_hits = sum(
                item.get("field") == "alias"
                for item in concept.get("matched_on", [])
            )
            entry[0] += (
                min(36.0, 24.0 + 6.0 * alias_hits)
                if alias_hits
                else 6.0 / concept_rank
            )
            entry[1] = max(entry[1], float(concept["query_term_coverage"]))

    ranked_method_ids = sorted(
        method_lexical,
        key=lambda method_id: (
            -method_lexical[method_id][0],
            -method_lexical[method_id][1],
            method_id,
        ),
    )
    recommended_methods: list[dict[str, Any]] = []
    for method_id in ranked_method_ids[:3]:
        method = pack.methods[method_id]
        score, coverage, matched_atom_ids = method_lexical[method_id]
        recommended_methods.append(
            {
                "method_id": method_id,
                "title": method["title"],
                "purpose": method["purpose"],
                "score": round(score, 8),
                "query_term_coverage": round(coverage, 6),
                "inference": "lexical_plus_one_hop_evidence",
                "matched_atom_ids": sorted(set(matched_atom_ids)),
                "matched_concept_ids": sorted(set(method["concept_ids"]) & matched_concept_ids),
                "atom_ids": list(method["atom_ids"]),
                "concept_ids": list(method["concept_ids"]),
                "inputs": list(method["inputs"]),
                "steps": list(method["steps"]),
                "decision_gates": list(method["decision_gates"]),
                "outputs": list(method["outputs"]),
                "stop_conditions": list(method["stop_conditions"]),
                "quality_checks": list(method["quality_checks"]),
            }
        )
        method_boost = 2.0 / len(recommended_methods)
        for atom_id in method["atom_ids"]:
            if atom_id not in pack.atoms:
                continue
            entry = ranking_by_id.setdefault(atom_id, [0.0, 0.0, []])
            entry[0] += method_boost
            entry[1] = max(entry[1], float(coverage))

    ranked_ids = sorted(
        ranking_by_id,
        key=lambda atom_id: (
            -ranking_by_id[atom_id][0],
            -ranking_by_id[atom_id][1],
            -confidence_score(pack.atoms[atom_id].get("confidence")),
            -source_date_score(pack.atoms[atom_id].get("source_date")),
            atom_id,
        ),
    )
    reverse_conflicts: dict[str, list[str]] = defaultdict(list)
    for source_id, atom in pack.atoms.items():
        for relation in atom.get("relations", []):
            if relation.get("type") == "contradicts" and relation.get("atom_id") in pack.atoms:
                reverse_conflicts[relation["atom_id"]].append(source_id)
    results: list[dict[str, Any]] = []
    for atom_id in ranked_ids[:limit]:
        atom = pack.atoms[atom_id]
        score, coverage, concept_ids = ranking_by_id[atom_id]
        source_ids = sorted({ref["source_id"] for ref in atom["source_refs"]})
        relations = sorted(
            (
                {"type": relation["type"], "atom_id": relation["atom_id"]}
                for relation in atom.get("relations", [])
                if relation.get("type") in ALLOWED_RELATION_TYPES
                and relation.get("atom_id") in pack.atoms
            ),
            key=lambda row: (row["type"], row["atom_id"]),
        )
        declared_conflicts = sorted(
            relation["atom_id"] for relation in relations if relation["type"] == "contradicts"
        )
        conflicts = sorted(set(declared_conflicts + reverse_conflicts.get(atom_id, [])))
        results.append(
            {
                "kind": "knowledge_atom",
                "atom_id": atom_id,
                "canonical": atom["canonical"],
                "status": atom["status"],
                "decision_rule": atom.get("decision_rule"),
                "procedure": list(atom.get("procedure", [])),
                "score": score,
                "matched_concept_ids": sorted(set(concept_ids)),
                "source_ids": source_ids,
                "source_refs": list(atom["source_refs"]),
                "source_attribution": {
                    "atom_ids": [atom_id],
                    "source_ids": source_ids,
                },
                "confidence": {
                    "retrieval": confidence_label(coverage),
                    "query_term_coverage": round(coverage, 6),
                    "knowledge": atom.get("confidence", {}),
                },
                "temporal": {
                    "source_date": atom.get("source_date"),
                    "temporal_scope": atom.get("temporal_scope", "unknown"),
                    "freshness": (
                        "unverified"
                        if not atom.get("source_date")
                        or "unverified" in str(atom.get("temporal_scope", ""))
                        else "source_dated"
                    ),
                },
                "relations": relations,
                "conflicts": conflicts,
                "limits": atom.get("limits", []),
            }
        )
    return {
        "mode": pack.mode,
        "query": query,
        "eligible_source_count": len(pack.sources),
        "eligible_atom_count": len(pack.atoms),
        "eligible_concept_count": len(pack.concepts),
        "eligible_method_count": len(pack.methods),
        "results": results,
        "matched_concepts": concept_matches,
        "recommended_methods": recommended_methods,
    }


def evaluate_recall(
    pack: KnowledgePack,
    cases_path: Path,
    *,
    k: int = 5,
    threshold: float = DEFAULT_RECALL_THRESHOLD,
) -> dict[str, Any]:
    if k <= 0:
        raise ValueError("k must be positive")
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    cases = load_jsonl(cases_path, "retrieval cases")
    if not cases:
        raise ValueError("retrieval fixture must contain at least one case")
    total_relevant_atoms = 0
    total_retrieved_atoms = 0
    atom_top1_total = 0
    atom_mrr_total = 0.0
    atom_case_count = 0
    total_relevant_methods = 0
    total_retrieved_methods = 0
    total_relevant_concepts = 0
    total_matched_concepts = 0
    case_results: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for row in cases:
        unknown_fields = set(row) - EVAL_FIELDS
        required_runtime_fields = {"case_id", "query", "relevant_atom_ids"}
        missing_fields = required_runtime_fields - set(row)
        if unknown_fields or missing_fields:
            details = []
            if unknown_fields:
                details.append("unsupported=" + ",".join(sorted(unknown_fields)))
            if missing_fields:
                details.append("missing=" + ",".join(sorted(missing_fields)))
            raise ValueError(
                "retrieval case contains answer-leaking, unsupported, or missing fields: "
                + "; ".join(details)
            )
        case_id = require_string(row.get("case_id"), "retrieval case_id")
        if case_id in seen_case_ids:
            raise ValueError(f"duplicate retrieval case_id: {case_id}")
        seen_case_ids.add(case_id)
        case_kind = require_string(
            row.get("case_kind", "legacy_atom"), f"retrieval case_kind: {case_id}"
        )
        query = require_string(row.get("query"), f"retrieval query: {case_id}")
        relevant_atoms = require_string_list(
            row.get("relevant_atom_ids"), f"relevant_atom_ids: {case_id}"
        )
        relevant_methods = require_string_list(
            row.get("relevant_method_ids", []), f"relevant_method_ids: {case_id}"
        )
        relevant_concepts = require_string_list(
            row.get("relevant_concept_ids", []), f"relevant_concept_ids: {case_id}"
        )
        if not (relevant_atoms or relevant_methods or relevant_concepts):
            raise ValueError(f"retrieval case must contain at least one relevant id: {case_id}")
        if any(atom_id not in pack.atoms for atom_id in relevant_atoms):
            raise ValueError(f"retrieval case references ineligible or unknown atom: {case_id}")
        if any(method_id not in pack.methods for method_id in relevant_methods):
            raise ValueError(f"retrieval case references ineligible or unknown method: {case_id}")
        if any(concept_id not in pack.concepts for concept_id in relevant_concepts):
            raise ValueError(f"retrieval case references ineligible or unknown concept: {case_id}")
        for atom_id in relevant_atoms:
            canonical = pack.atoms[atom_id]["canonical"]
            if unicodedata.normalize("NFKC", canonical).casefold() in unicodedata.normalize(
                "NFKC", query
            ).casefold():
                raise ValueError(f"retrieval query leaks canonical answer text: {case_id}")
        result = search_knowledge_pack(pack, query, limit=max(k, 5))
        retrieved_atoms = [item["atom_id"] for item in result["results"][:5]]
        retrieved_methods = [
            item["method_id"] for item in result["recommended_methods"][:3]
        ]
        matched_concepts = [item["concept_id"] for item in result["matched_concepts"]]
        relevant_atom_set = set(relevant_atoms)
        relevant_method_set = set(relevant_methods)
        relevant_concept_set = set(relevant_concepts)
        atom_hits = sorted(relevant_atom_set.intersection(retrieved_atoms))
        method_hits = sorted(relevant_method_set.intersection(retrieved_methods))
        concept_hits = sorted(relevant_concept_set.intersection(matched_concepts))
        atom_recall = len(atom_hits) / len(relevant_atom_set) if relevant_atom_set else None
        method_recall = (
            len(method_hits) / len(relevant_method_set) if relevant_method_set else None
        )
        concept_recall = (
            len(concept_hits) / len(relevant_concept_set) if relevant_concept_set else None
        )
        reciprocal_rank = 0.0
        if relevant_atom_set:
            atom_case_count += 1
            if retrieved_atoms and retrieved_atoms[0] in relevant_atom_set:
                atom_top1_total += 1
            for rank, atom_id in enumerate(retrieved_atoms, 1):
                if atom_id in relevant_atom_set:
                    reciprocal_rank = 1.0 / rank
                    break
            atom_mrr_total += reciprocal_rank
        total_relevant_atoms += len(relevant_atom_set)
        total_retrieved_atoms += len(atom_hits)
        total_relevant_methods += len(relevant_method_set)
        total_retrieved_methods += len(method_hits)
        total_relevant_concepts += len(relevant_concept_set)
        total_matched_concepts += len(concept_hits)
        case_results.append(
            {
                "case_id": case_id,
                "case_kind": case_kind,
                "retrieved_atom_ids": retrieved_atoms,
                "recommended_method_ids": retrieved_methods,
                "matched_concept_ids": matched_concepts,
                "relevant_atom_ids": relevant_atoms,
                "relevant_method_ids": relevant_methods,
                "relevant_concept_ids": relevant_concepts,
                "atom_hits": atom_hits,
                "method_hits": method_hits,
                "concept_hits": concept_hits,
                "atom_recall_at_5": round(atom_recall, 6) if atom_recall is not None else None,
                "atom_top1": (
                    bool(retrieved_atoms and retrieved_atoms[0] in relevant_atom_set)
                    if relevant_atom_set
                    else None
                ),
                "atom_reciprocal_rank": round(reciprocal_rank, 6) if relevant_atom_set else None,
                "method_recall_at_3": (
                    round(method_recall, 6) if method_recall is not None else None
                ),
                "concept_match_recall": (
                    round(concept_recall, 6) if concept_recall is not None else None
                ),
            }
        )
    atom_recall_at_5 = (
        total_retrieved_atoms / total_relevant_atoms if total_relevant_atoms else None
    )
    atom_top1 = atom_top1_total / atom_case_count if atom_case_count else None
    atom_mrr = atom_mrr_total / atom_case_count if atom_case_count else None
    method_recall_at_3 = (
        total_retrieved_methods / total_relevant_methods if total_relevant_methods else None
    )
    concept_match_recall = (
        total_matched_concepts / total_relevant_concepts if total_relevant_concepts else None
    )
    gated_metrics = [
        value
        for value in (atom_recall_at_5, method_recall_at_3, concept_match_recall)
        if value is not None
    ]
    return {
        "mode": pack.mode,
        "atom_k": 5,
        "method_k": 3,
        "case_count": len(cases),
        "total_relevant_atoms": total_relevant_atoms,
        "total_relevant_methods": total_relevant_methods,
        "total_relevant_concepts": total_relevant_concepts,
        "atom_recall_at_5": (
            round(atom_recall_at_5, 6) if atom_recall_at_5 is not None else None
        ),
        "atom_top1": round(atom_top1, 6) if atom_top1 is not None else None,
        "atom_mrr": round(atom_mrr, 6) if atom_mrr is not None else None,
        "method_recall_at_3": (
            round(method_recall_at_3, 6) if method_recall_at_3 is not None else None
        ),
        "concept_match_recall": (
            round(concept_match_recall, 6) if concept_match_recall is not None else None
        ),
        "recall_at_k": (
            round(atom_recall_at_5, 6) if atom_recall_at_5 is not None else None
        ),
        "threshold": threshold,
        "passed": bool(gated_metrics) and all(value >= threshold for value in gated_metrics),
        "cases": case_results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    folder_index = subparsers.add_parser("folder-index")
    folder_index.add_argument("--root", action="append", required=True)
    folder_index.add_argument("--index", type=Path, required=True)
    folder_index.add_argument("--commit", action="store_true")
    folder_index.add_argument("--confirmation-hash")
    folder_index.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    folder_index.add_argument("--extension", action="append")

    folder_search = subparsers.add_parser("folder-search")
    folder_search.add_argument("--index", type=Path, required=True)
    folder_search.add_argument("--query", required=True)
    folder_search.add_argument("--limit", type=int, default=5)

    pack_search = subparsers.add_parser("pack-search")
    pack_search.add_argument("--sources", type=Path, required=True)
    pack_search.add_argument("--atoms", type=Path, required=True)
    pack_search.add_argument("--query", required=True)
    pack_search.add_argument("--mode", choices=("public", "private"), default="public")
    pack_search.add_argument("--limit", type=int, default=5)

    evaluate = subparsers.add_parser("eval")
    evaluate.add_argument("--sources", type=Path, required=True)
    evaluate.add_argument("--atoms", type=Path, required=True)
    evaluate.add_argument("--cases", type=Path, required=True)
    evaluate.add_argument("--mode", choices=("public", "private"), default="public")
    evaluate.add_argument("--k", type=int, default=5)
    evaluate.add_argument("--threshold", type=float, default=DEFAULT_RECALL_THRESHOLD)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "folder-index":
            if args.index.is_symlink():
                raise ValueError(f"index target must not be a symlink: {args.index}")
            prior = load_json(args.index) if args.index.is_file() else None
            planned = build_folder_index_plan(
                args.root,
                index_path=args.index,
                prior_index=prior,
                extensions=args.extension,
                max_bytes=args.max_bytes,
            )
            if args.commit:
                if not args.confirmation_hash:
                    raise ValueError("--commit requires --confirmation-hash from the exact preview")
                if args.confirmation_hash != planned["confirmation_hash"]:
                    raise ValueError("confirmation hash does not match the exact current folder index plan")
                index_hash = atomic_write_json(args.index, planned["index"])
                result = {
                    "mode": "commit",
                    "index_path": str(args.index.expanduser().absolute()),
                    "index_sha256": index_hash,
                    "confirmation_hash": planned["confirmation_hash"],
                    "changes": planned["plan"]["changes"],
                    "documents": len(planned["index"]["documents"]),
                    "skips": planned["index"]["skips"],
                }
            else:
                result = {"mode": "preview", **planned}
        elif args.command == "folder-search":
            result = search_folder_index(load_json(args.index), args.query, limit=args.limit)
        elif args.command == "pack-search":
            pack = load_knowledge_pack(args.sources, args.atoms, mode=args.mode)
            result = search_knowledge_pack(pack, args.query, limit=args.limit)
            result["excluded_sources"] = pack.excluded_sources
            result["excluded_atoms"] = pack.excluded_atoms
            result["excluded_concepts"] = pack.excluded_concepts
            result["excluded_methods"] = pack.excluded_methods
        else:
            pack = load_knowledge_pack(args.sources, args.atoms, mode=args.mode)
            result = evaluate_recall(
                pack,
                args.cases,
                k=args.k,
                threshold=args.threshold,
            )
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0 if result["passed"] else 2
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
