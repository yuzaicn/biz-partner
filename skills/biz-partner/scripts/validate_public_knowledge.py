#!/usr/bin/env python3
"""Validate the built-in, redistribution-safe public knowledge pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from atom_contract import sha256_text
from build_knowledge_network import GRAPH_FILE, NETWORK_FILE, build_artifacts
from knowledge_runtime import (
    ALLOWED_RELATION_TYPES,
    evaluate_recall,
    load_knowledge_pack,
)


MINIMUM_COUNTS = {
    "sources": 11,
    "atoms": 60,
    "methods": 12,
    "operational_concepts": 30,
    "curated_concepts": 50,
    "retrieval_cases": 84,
    "direct_retrieval_cases": 60,
    "colloquial_retrieval_cases": 24,
    "knowledge_nodes": 163,
    "knowledge_edges": 477,
}
PACK_FILES = {
    "USAGE.md",
    "atoms.jsonl",
    "concept-dictionary.md",
    "concepts.jsonl",
    GRAPH_FILE,
    NETWORK_FILE,
    "methods.md",
    "methods.jsonl",
    "retrieval-cases.jsonl",
    "sources.jsonl",
}
SOURCE_COMMON_FIELDS = {
    "source_id", "kind", "status",
    "rights_status", "license", "authorization_status", "release_decision",
    "rights_basis", "source_expression_redistribution",
}
NAMED_SOURCE_FIELDS = SOURCE_COMMON_FIELDS | {
    "title", "author_or_account", "public_attribution_name", "attribution_mode",
    "relationship_to_runtime_user", "ownership_status",
}
ATOM_FIELDS = {
    "atom_id", "schema_version", "canonical", "claim_kind", "actionability", "domain",
    "decision_rule", "procedure", "limits", "bias_flags", "provenance_type", "pipeline_run",
    "temporal_scope", "source_date", "confidence", "relations", "content_hash", "source_refs",
    "status", "rights", "authorization_status", "release_decision",
}
OPERATIONAL_CONCEPT_FIELDS = {
    "concept_id", "concept_kind", "term", "normalized", "definition", "anti_definition",
    "common_misuse", "aliases", "group", "source_atoms", "salience", "related_methods",
    "status", "rights",
}
CURATED_CONCEPT_FIELDS = {
    "concept_id", "concept_kind", "term", "normalized", "definition", "use_when", "limit",
    "aliases", "group", "source_atoms", "salience", "related_methods", "source_id",
    "expression_status", "map_boundary", "status", "rights",
}
METHOD_FIELDS = {
    "method_id", "title", "purpose", "use_when", "inputs", "steps", "decision_gates",
    "stop_conditions", "outputs", "quality_checks", "pitfalls", "atom_ids", "concept_ids",
    "status", "rights",
}
LICENSE_FIELDS = {"id", "version", "scope", "applies_to"}
RIGHTS_FIELDS = {"redistribution", "license", "boundary"}
CONFIDENCE_FIELDS = {"attribution", "extraction", "interpretation", "operational"}
LOCATOR_FIELDS = {"file", "lines"}
RETRIEVAL_FIELDS = {
    "case_id", "case_kind", "query", "relevant_atom_ids", "relevant_method_ids",
    "relevant_concept_ids",
}
MANIFEST_FIELDS = {
    "schema_version", "pack_id", "as_of", "pack_version", "mode", "status",
    "license", "counts", "source_count", "atom_count", "excluded",
    "contains_raw_source_text", "contains_private_working_material",
    "contains_machine_local_paths", "files",
}
MANIFEST_FILE_FIELDS = {"path", "sha256", "line_count"}
FORBIDDEN_KEYS = {
    "raw_text", "authored" + "Text", "capture_filter", "skill_refs", "evidence", "evidence" + "_paths",
    "manifest" + "_paths", "source_confirmation", "classification_conflict", "concept_dictionary_path",
    "full_text_path", "epub_path", "review_status", "disposition", "source_excerpt",
}
FORBIDDEN_CONTENT_TERMS = {
    "SB7", "StoryBrand", "TRAC", "三座山峰", "认知三重限制",
}
MACHINE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_])/(?:Users|home|private/var|var/folders|Volumes)/[^\s`\"')\]]+"
)
WINDOWS_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:\\[^\s`\"')\]]+")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ATOM_REF_RE = re.compile(r"`(ka_[a-z0-9_]+)`")
MAINTAINER_NAME = "鱼" + "仔"
MAINTAINER_HANDLE = "Exp" + "Lang_Cn"
CURATED_SOURCE_IDS = {f"curated_source_{index:02d}" for index in range(1, 11)}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"non-object JSONL row: {path.name}:{line_number}")
        rows.append(value)
    return rows


def file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def exact_fields(row: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(row) - allowed
    if unknown:
        raise ValueError(f"unsupported fields in {label}: {','.join(sorted(unknown))}")


def require_fields(row: dict[str, Any], required: set[str], label: str) -> None:
    missing = required - set(row)
    if missing:
        raise ValueError(f"missing fields in {label}: {','.join(sorted(missing))}")


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
    return value


def require_string_list(
    value: Any, label: str, *, allow_empty: bool = False
) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        qualifier = "non-empty " if not allow_empty else ""
        raise ValueError(f"{label} must be a {qualifier}list")
    if not all(isinstance(item, str) and item and item == item.strip() for item in value):
        raise ValueError(f"{label} must contain only non-empty trimmed strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must not contain duplicates")
    return value


def walk(value: Any, label: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                raise ValueError(f"private/raw field in {label}: {key}")
            walk(child, f"{label}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk(child, f"{label}[{index}]")
    elif isinstance(value, str):
        if "file://" in value.casefold() or MACHINE_PATH_RE.search(value) or WINDOWS_PATH_RE.search(value):
            raise ValueError(f"machine-local locator in {label}")


def validate_license(record: Any, label: str) -> None:
    if not isinstance(record, dict):
        raise ValueError(f"license must be an object: {label}")
    exact_fields(record, LICENSE_FIELDS, f"{label}.license")
    if record != {
        "id": "PolyForm-Noncommercial-1.0.0",
        "version": "1.0.0",
        "scope": "redistribution_and_derivatives",
        "applies_to": "public-pack original paraphrases and compilation only",
    }:
        raise ValueError(f"unexpected public-pack license: {label}")


def validate_sources(rows: list[dict[str, Any]]) -> set[str]:
    if not rows:
        raise ValueError("source registry must not be empty")
    ids: set[str] = set()
    maintainer_count = 0
    for row in rows:
        source_id = row.get("source_id")
        if not isinstance(source_id, str) or not source_id or source_id in ids:
            raise ValueError(f"invalid or duplicate source_id: {source_id!r}")
        ids.add(source_id)
        exact_fields(
            row,
            NAMED_SOURCE_FIELDS
            if source_id == "maintainer_public_writing_v1"
            else SOURCE_COMMON_FIELDS,
            f"source:{source_id}",
        )
        if row.get("status") != "release_eligible" or row.get("release_decision") != "approved_for_public_release":
            raise ValueError(f"source is not release-eligible: {source_id}")
        validate_license(row.get("license"), f"source:{source_id}")
        identity_text = json.dumps(row, ensure_ascii=False)
        has_maintainer_identity = MAINTAINER_NAME in identity_text or MAINTAINER_HANDLE in identity_text
        if source_id == "maintainer_public_writing_v1":
            maintainer_count += 1
            if row.get("attribution_mode") != "when_materially_used":
                raise ValueError("maintainer attribution mode mismatch")
            if row.get("relationship_to_runtime_user") != "external_named_source":
                raise ValueError("maintainer source may not be inferred as runtime user")
            if row.get("ownership_status") != "not_claimed":
                raise ValueError("maintainer source ownership is not separated")
            if row.get("public_attribution_name") != MAINTAINER_NAME:
                raise ValueError("maintainer public attribution name mismatch")
            if row.get("author_or_account") != f"{MAINTAINER_NAME}（@{MAINTAINER_HANDLE}）":
                raise ValueError("maintainer public account identity mismatch")
            if row.get("rights_status") != "owner_authorized_public_release":
                raise ValueError("maintainer source lacks owner authorization")
            if row.get("authorization_status") != "owner_authorized_public_release":
                raise ValueError("maintainer source authorization mismatch")
        elif has_maintainer_identity:
            raise ValueError(f"maintainer identity escaped source row: {source_id}")
        elif source_id not in CURATED_SOURCE_IDS:
            raise ValueError(f"unexpected curated source id: {source_id}")
        elif row.get("rights_status") != "project_paraphrase_only":
            raise ValueError(f"curated synthesis record has invalid rights status: {source_id}")
        elif (
            row.get("kind") != "curated_source_for_public_paraphrase"
            or row.get("authorization_status") != "project_owner_authorized_public_paraphrase"
            or row.get("source_expression_redistribution") != "not_granted_or_claimed"
            or row.get("license", {}).get("applies_to")
            != "public-pack original paraphrases and compilation only"
        ):
            raise ValueError(f"curated synthesis boundary is invalid: {source_id}")
        if row.get("source_expression_redistribution") not in {
            "not_granted_or_claimed", "derived atoms only; raw source material excluded"
        }:
            raise ValueError(f"source-expression boundary missing: {source_id}")
    if maintainer_count != 1:
        raise ValueError(f"expected one maintainer source, got {maintainer_count}")
    return ids


def validate_atoms(rows: list[dict[str, Any]], source_ids: set[str]) -> set[str]:
    if not rows:
        raise ValueError("atom registry must not be empty")
    atom_ids: set[str] = set()
    for line_number, row in enumerate(rows, 1):
        atom_id = row.get("atom_id")
        if not isinstance(atom_id, str) or not atom_id or atom_id in atom_ids:
            raise ValueError(f"invalid or duplicate atom_id: {atom_id!r}")
        atom_ids.add(atom_id)
        exact_fields(row, ATOM_FIELDS, f"atom:{atom_id}")
        if row.get("status") != "release_eligible" or row.get("release_decision") != "approved_for_public_release":
            raise ValueError(f"atom is not release-eligible: {atom_id}")
        rights = row.get("rights")
        if not isinstance(rights, dict):
            raise ValueError(f"atom rights must be an object: {atom_id}")
        exact_fields(rights, RIGHTS_FIELDS, f"atom:{atom_id}.rights")
        validate_license(rights.get("license"), f"atom:{atom_id}")
        confidence = row.get("confidence")
        if not isinstance(confidence, dict):
            raise ValueError(f"atom confidence must be an object: {atom_id}")
        exact_fields(confidence, CONFIDENCE_FIELDS, f"atom:{atom_id}.confidence")
        if rights.get("redistribution") == "project_paraphrase_only":
            if (
                row.get("provenance_type") != "public_curated_idea_synthesis"
                or row.get("authorization_status")
                != "project_owner_authorized_public_paraphrase"
                or rights.get("boundary")
                != "license covers this pack's original paraphrase, not source-book expression"
            ):
                raise ValueError(f"atom curated-paraphrase boundary is invalid: {atom_id}")
        elif rights.get("redistribution") != "owner_authorized_public_release":
            raise ValueError(f"atom rights status is invalid: {atom_id}")
        refs = row.get("source_refs")
        if not isinstance(refs, list) or len(refs) != 1:
            raise ValueError(f"atom must have exactly one public source ref: {atom_id}")
        ref = refs[0]
        if not isinstance(ref, dict):
            raise ValueError(f"atom source ref is not an object: {atom_id}")
        exact_fields(ref, {"source_id", "locator", "quote_hash"}, f"source_ref:{atom_id}")
        locator = ref.get("locator")
        if not isinstance(locator, dict):
            raise ValueError(f"atom locator is not an object: {atom_id}")
        exact_fields(locator, LOCATOR_FIELDS, f"source_ref:{atom_id}.locator")
        if ref.get("source_id") not in source_ids:
            raise ValueError(f"atom references unknown source: {atom_id}")
        if locator != {"file": "public-knowledge/atoms.jsonl", "lines": f"{line_number}-{line_number}"}:
            raise ValueError(f"atom locator is not its portable public row: {atom_id}")
        if ref.get("quote_hash") != row.get("content_hash") or row.get("content_hash") != sha256_text(row.get("canonical", "")):
            raise ValueError(f"public synthesis hash mismatch: {atom_id}")
        if not HASH_RE.fullmatch(str(row.get("content_hash", ""))):
            raise ValueError(f"invalid atom hash: {atom_id}")
        atom_text = json.dumps(row, ensure_ascii=False)
        if MAINTAINER_NAME in atom_text or MAINTAINER_HANDLE in atom_text:
            raise ValueError(f"source identity leaked into atom: {atom_id}")
    for row in rows:
        for relation in row.get("relations", []):
            if not isinstance(relation, dict) or set(relation) != {"type", "atom_id"}:
                raise ValueError(f"invalid relation fields: {row['atom_id']}")
            if relation["type"] not in ALLOWED_RELATION_TYPES:
                raise ValueError(
                    f"unsupported relation type: {row['atom_id']} -> {relation['type']}"
                )
            if relation["atom_id"] not in atom_ids:
                raise ValueError(f"relation target missing: {row['atom_id']}")
    return atom_ids


def validate_concepts(
    rows: list[dict[str, Any]], atom_ids: set[str], source_ids: set[str]
) -> set[str]:
    operational = [row for row in rows if row.get("concept_kind") == "operational_dictionary"]
    curated = [row for row in rows if row.get("concept_kind") == "curated_concept"]
    if len(operational) + len(curated) != len(rows):
        raise ValueError(
            "concept_kind must be operational_dictionary or curated_concept"
        )
    seen: set[str] = set()
    normalized_values: set[str] = set()
    for row in rows:
        concept_id = row.get("concept_id")
        if not isinstance(concept_id, str) or concept_id in seen:
            raise ValueError(f"invalid or duplicate concept_id: {concept_id!r}")
        seen.add(concept_id)
        if row.get("status") != "release_eligible":
            raise ValueError(f"concept is not release-eligible: {concept_id}")
        rights = row.get("rights")
        if not isinstance(rights, dict):
            raise ValueError(f"concept rights must be an object: {concept_id}")
        exact_fields(rights, RIGHTS_FIELDS, f"concept:{concept_id}.rights")
        validate_license(rights.get("license"), f"concept:{concept_id}")
        if (
            rights.get("redistribution") != "project_paraphrase_only"
            or rights.get("boundary")
            != "license covers this pack's original paraphrase, not source-book expression"
        ):
            raise ValueError(f"concept paraphrase boundary is invalid: {concept_id}")
        if row.get("concept_kind") == "operational_dictionary":
            exact_fields(row, OPERATIONAL_CONCEPT_FIELDS, f"concept:{concept_id}")
            require_fields(row, OPERATIONAL_CONCEPT_FIELDS, f"concept:{concept_id}")
        else:
            exact_fields(row, CURATED_CONCEPT_FIELDS, f"concept:{concept_id}")
            require_fields(row, CURATED_CONCEPT_FIELDS, f"concept:{concept_id}")
            if row.get("source_id") not in source_ids or row.get("source_id") not in CURATED_SOURCE_IDS:
                raise ValueError(f"curated concept references unknown source: {concept_id}")
            if row.get("expression_status") != "independently_worded_project_definition":
                raise ValueError(f"curated concept expression boundary missing: {concept_id}")
        require_string(row.get("term"), f"concept term: {concept_id}")
        normalized = require_string(row.get("normalized"), f"concept normalized: {concept_id}")
        normalized_key = normalized.casefold()
        if normalized_key in normalized_values:
            raise ValueError(f"duplicate concept normalized value: {normalized}")
        normalized_values.add(normalized_key)
        require_string(row.get("definition"), f"concept definition: {concept_id}")
        require_string(row.get("group"), f"concept group: {concept_id}")
        require_string(row.get("salience"), f"concept salience: {concept_id}")
        require_string_list(
            row.get("aliases"), f"concept aliases: {concept_id}", allow_empty=True
        )
        source_atoms = require_string_list(
            row.get("source_atoms"), f"concept source_atoms: {concept_id}"
        )
        related_methods = require_string_list(
            row.get("related_methods"),
            f"concept related_methods: {concept_id}",
            allow_empty=True,
        )
        if any(atom_id not in atom_ids for atom_id in source_atoms):
            raise ValueError(f"concept references unknown atom: {concept_id}")
        if row.get("term") in {"情绪体", "信念体"}:
            raise ValueError(f"source-specific framework term in concept: {concept_id}")
        text = json.dumps(row, ensure_ascii=False)
        if MAINTAINER_NAME in text or MAINTAINER_HANDLE in text:
            raise ValueError(f"maintainer identity leaked into concept: {concept_id}")
        for term in FORBIDDEN_CONTENT_TERMS:
            if term.casefold() in text.casefold():
                raise ValueError(f"source-specific framework term in concept: {concept_id} ({term})")
    return seen


def validate_methods(
    rows: list[dict[str, Any]], atom_ids: set[str], concept_ids: set[str]
) -> set[str]:
    seen: set[str] = set()
    list_fields = (
        "use_when", "inputs", "steps", "decision_gates", "stop_conditions", "outputs",
        "quality_checks", "pitfalls", "atom_ids", "concept_ids",
    )
    for row in rows:
        method_id = row.get("method_id")
        if (
            not isinstance(method_id, str)
            or re.fullmatch(r"M-[0-9]{3}", method_id) is None
            or method_id in seen
        ):
            raise ValueError(f"invalid or duplicate method_id: {method_id!r}")
        seen.add(method_id)
        exact_fields(row, METHOD_FIELDS, f"method:{method_id}")
        require_fields(row, METHOD_FIELDS, f"method:{method_id}")
        require_string(row.get("title"), f"method title: {method_id}")
        require_string(row.get("purpose"), f"method purpose: {method_id}")
        for field in list_fields:
            require_string_list(
                row.get(field),
                f"method {field}: {method_id}",
                allow_empty=field not in {"steps", "atom_ids", "concept_ids"},
            )
        if any(atom_id not in atom_ids for atom_id in row["atom_ids"]):
            raise ValueError(f"method references unknown atom: {method_id}")
        if any(concept_id not in concept_ids for concept_id in row["concept_ids"]):
            raise ValueError(f"method references unknown concept: {method_id}")
        if row.get("status") != "release_eligible":
            raise ValueError(f"method is not release-eligible: {method_id}")
        rights = row.get("rights")
        if not isinstance(rights, dict):
            raise ValueError(f"method rights must be an object: {method_id}")
        exact_fields(rights, RIGHTS_FIELDS, f"method:{method_id}.rights")
        validate_license(rights.get("license"), f"method:{method_id}")
        if (
            rights.get("redistribution") != "project_paraphrase_only"
            or rights.get("boundary")
            != "license covers this pack's original paraphrase, not source-book expression"
        ):
            raise ValueError(f"method paraphrase boundary is invalid: {method_id}")
        text = json.dumps(row, ensure_ascii=False)
        if MAINTAINER_NAME in text or MAINTAINER_HANDLE in text:
            raise ValueError(f"maintainer identity leaked into method: {method_id}")
        for term in FORBIDDEN_CONTENT_TERMS:
            if term.casefold() in text.casefold():
                raise ValueError(f"source-specific framework term in method: {method_id} ({term})")
    return seen


def validate_cross_references(
    concepts: list[dict[str, Any]], methods: list[dict[str, Any]], method_ids: set[str]
) -> None:
    for concept in concepts:
        concept_id = concept["concept_id"]
        unknown = sorted(set(concept["related_methods"]) - method_ids)
        if unknown:
            raise ValueError(
                f"concept references unknown methods: {concept_id} -> {','.join(unknown)}"
            )


def _method_steps_from_markdown(block: str) -> list[str]:
    match = re.search(
        r"(?ms)^\*\*(?:步骤|怎么做)：\*\*\s*(.+?)(?=^\*\*[^\n]+：\*\*|^## |\Z)",
        block,
    )
    if match is None:
        return []
    payload = match.group(1).strip()
    numbered = re.findall(r"(?m)^\s*(?:[0-9]+[.)、]|[-*])\s+(.+?)\s*$", payload)
    if numbered:
        return [item.strip() for item in numbered]
    return [item.strip() for item in re.split(r"[；\n]+", payload) if item.strip()]


def validate_methods_markdown(path: Path, methods: list[dict[str, Any]]) -> None:
    text = path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"(?m)^## (M-[0-9]{3}) (.+?)\s*$", text))
    actual_ids = [match.group(1) for match in matches]
    expected_ids = [row["method_id"] for row in methods]
    if actual_ids != expected_ids:
        raise ValueError("methods.md method order or ids differ from methods.jsonl")
    for index, match in enumerate(matches):
        method = methods[index]
        if match.group(2).strip() != method["title"]:
            raise ValueError(f"methods.md title differs from methods.jsonl: {method['method_id']}")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end() : end]
        steps = _method_steps_from_markdown(block)
        if len(steps) != len(method["steps"]):
            raise ValueError(f"methods.md step count differs from methods.jsonl: {method['method_id']}")
        refs = set(ATOM_REF_RE.findall(block))
        if refs != set(method["atom_ids"]):
            raise ValueError(f"methods.md atom refs differ from methods.jsonl: {method['method_id']}")
    for term in FORBIDDEN_CONTENT_TERMS:
        if term.casefold() in text.casefold():
            raise ValueError(f"source-specific framework term in methods: {term}")


def _normalized_markdown_text(value: str) -> str:
    value = re.sub(r"[`*_]", "", value)
    value = re.sub(r"\s+", "", value)
    return value.rstrip("。.!！")


def validate_concept_dictionary(path: Path, concepts: list[dict[str, Any]]) -> None:
    text = path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"(?m)^#### ([a-z]{2}_[0-9]{3}) (.+?)\s*$", text))
    actual_pairs = [(match.group(1), match.group(2).strip()) for match in matches]
    expected_pairs = [(row["concept_id"], row["term"]) for row in concepts]
    if actual_pairs != expected_pairs:
        raise ValueError("concept-dictionary.md concept order differs from concepts.jsonl")
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end() : end]
        definition_match = re.search(r"(?m)^\*\*定义：\*\*\s*(.+?)\s*$", block)
        if definition_match is None:
            raise ValueError(f"concept dictionary definition missing: {concepts[index]['concept_id']}")
        markdown_definition = definition_match.group(1)
        if _normalized_markdown_text(markdown_definition) != _normalized_markdown_text(
            concepts[index]["definition"]
        ):
            raise ValueError(
                f"concept dictionary definition differs from concepts.jsonl: "
                f"{concepts[index]['concept_id']}"
            )
    if "词频" in text and "不包含" not in text and "不包括" not in text:
        raise ValueError("concept dictionary exposes frequency material")
    for term in FORBIDDEN_CONTENT_TERMS:
        if term.casefold() in text.casefold():
            raise ValueError(f"source-specific framework term in dictionary: {term}")


def validate_knowledge_network(
    pack_root: Path, manifest: dict[str, Any]
) -> dict[str, int]:
    expected = build_artifacts(
        pack_root,
        "public",
        metadata={
            "pack_id": require_string(manifest.get("pack_id"), "manifest pack_id"),
            "pack_version": require_string(
                manifest.get("pack_version"), "manifest pack_version"
            ),
            "mode": "public",
        },
    )
    for name, text in expected.items():
        path = pack_root / name
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            raise ValueError(f"generated knowledge network is missing or stale: {name}")
    graph = json.loads(expected[GRAPH_FILE])
    counts = graph.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("knowledge graph counts must be an object")
    nodes = counts.get("nodes")
    edges = counts.get("edges")
    if not isinstance(nodes, int) or isinstance(nodes, bool) or nodes <= 0:
        raise ValueError("knowledge graph node count is invalid")
    if not isinstance(edges, int) or isinstance(edges, bool) or edges <= 0:
        raise ValueError("knowledge graph edge count is invalid")
    return {"knowledge_nodes": nodes, "knowledge_edges": edges}


def validate_manifest(
    pack_root: Path,
    manifest: dict[str, Any],
    actual_counts: dict[str, int] | None = None,
) -> None:
    exact_fields(manifest, MANIFEST_FIELDS, "manifest")
    require_fields(manifest, MANIFEST_FIELDS, "manifest")
    schema_version = require_string(manifest.get("schema_version"), "manifest schema_version")
    pack_version = require_string(manifest.get("pack_version"), "manifest pack_version")
    if re.fullmatch(r"[0-9]+\.[0-9]+", schema_version) is None or re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+", pack_version
    ) is None:
        raise ValueError("manifest schema or pack version mismatch")
    if manifest.get("mode") != "public" or manifest.get("status") != "release_eligible":
        raise ValueError("manifest is not a release-eligible public pack")
    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("manifest counts must be an object")
    exact_fields(counts, set(MINIMUM_COUNTS), "manifest.counts")
    for key, minimum in MINIMUM_COUNTS.items():
        value = counts.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise ValueError(f"manifest count below minimum: {key}={value!r} minimum={minimum}")
    if manifest.get("source_count") != counts["sources"]:
        raise ValueError("manifest source_count differs from detailed counts")
    if manifest.get("atom_count") != counts["atoms"]:
        raise ValueError("manifest atom_count differs from detailed counts")
    if actual_counts is not None and counts != actual_counts:
        raise ValueError(
            f"manifest detailed counts differ from files: manifest={counts!r} actual={actual_counts!r}"
        )
    for flag in (
        "contains_raw_source_text", "contains_private_working_material", "contains_machine_local_paths"
    ):
        if manifest.get(flag) is not False:
            raise ValueError(f"manifest boundary flag is not false: {flag}")
    validate_license(manifest.get("license"), "manifest")
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != PACK_FILES:
        raise ValueError("manifest file set mismatch")
    for name, record in files.items():
        if not isinstance(record, dict):
            raise ValueError(f"invalid manifest file record: {name}")
        exact_fields(record, MANIFEST_FILE_FIELDS, f"manifest.files.{name}")
        path = pack_root / name
        if record.get("path") != name or not path.is_file() or path.is_symlink():
            raise ValueError(f"missing or unsafe pack file: {name}")
        if record.get("sha256") != file_hash(path):
            raise ValueError(f"manifest hash mismatch: {name}")
        if record.get("line_count") != len(path.read_text(encoding="utf-8").splitlines()):
            raise ValueError(f"manifest line count mismatch: {name}")


def validate_pack(skill_root: Path) -> dict[str, Any]:
    pack_root = skill_root / "public-knowledge"
    if not pack_root.is_dir() or pack_root.is_symlink():
        raise ValueError("public-knowledge directory is missing or unsafe")
    manifest = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest root is not an object")
    sources = load_jsonl(pack_root / "sources.jsonl")
    atoms = load_jsonl(pack_root / "atoms.jsonl")
    concepts = load_jsonl(pack_root / "concepts.jsonl")
    methods = load_jsonl(pack_root / "methods.jsonl")
    retrieval_cases = load_jsonl(pack_root / "retrieval-cases.jsonl")
    graph = json.loads((pack_root / GRAPH_FILE).read_text(encoding="utf-8"))
    if not isinstance(graph, dict) or not isinstance(graph.get("counts"), dict):
        raise ValueError("knowledge graph root or counts are invalid")
    actual_counts = {
        "sources": len(sources),
        "atoms": len(atoms),
        "methods": len(methods),
        "operational_concepts": sum(
            row.get("concept_kind") == "operational_dictionary" for row in concepts
        ),
        "curated_concepts": sum(
            row.get("concept_kind") == "curated_concept" for row in concepts
        ),
        "retrieval_cases": len(retrieval_cases),
        "direct_retrieval_cases": sum(
            row.get("case_kind") == "direct" for row in retrieval_cases
        ),
        "colloquial_retrieval_cases": sum(
            row.get("case_kind") == "colloquial_paraphrase" for row in retrieval_cases
        ),
        "knowledge_nodes": graph["counts"].get("nodes"),
        "knowledge_edges": graph["counts"].get("edges"),
    }
    validate_manifest(pack_root, manifest, actual_counts)
    for label, value in (
        ("manifest", manifest),
        ("sources", sources),
        ("atoms", atoms),
        ("concepts", concepts),
        ("methods", methods),
        ("retrieval", retrieval_cases),
        ("knowledge_graph", graph),
    ):
        walk(value, label)
    network_counts = validate_knowledge_network(pack_root, manifest)
    if network_counts != {
        "knowledge_nodes": actual_counts["knowledge_nodes"],
        "knowledge_edges": actual_counts["knowledge_edges"],
    }:
        raise ValueError("knowledge network counts differ from generated graph")
    source_ids = validate_sources(sources)
    atom_ids = validate_atoms(atoms, source_ids)
    concept_ids = validate_concepts(concepts, atom_ids, source_ids)
    method_ids = validate_methods(methods, atom_ids, concept_ids)
    validate_cross_references(concepts, methods, method_ids)
    validate_methods_markdown(pack_root / "methods.md", methods)
    validate_concept_dictionary(pack_root / "concept-dictionary.md", concepts)
    seen_case_ids: set[str] = set()
    covered_atoms: set[str] = set()
    covered_methods: set[str] = set()
    covered_concepts: set[str] = set()
    for row in retrieval_cases:
        exact_fields(row, RETRIEVAL_FIELDS, f"retrieval:{row.get('case_id')}")
        require_fields(row, RETRIEVAL_FIELDS, f"retrieval:{row.get('case_id')}")
        case_id = require_string(row.get("case_id"), "retrieval case_id")
        if case_id in seen_case_ids:
            raise ValueError(f"duplicate retrieval case_id: {case_id}")
        seen_case_ids.add(case_id)
        require_string(row.get("case_kind"), f"retrieval case_kind: {case_id}")
        require_string(row.get("query"), f"retrieval query: {case_id}")
        relevant_atoms = require_string_list(
            row.get("relevant_atom_ids"), f"retrieval relevant_atom_ids: {case_id}", allow_empty=True
        )
        relevant_methods = require_string_list(
            row.get("relevant_method_ids"),
            f"retrieval relevant_method_ids: {case_id}",
            allow_empty=True,
        )
        relevant_concepts = require_string_list(
            row.get("relevant_concept_ids"),
            f"retrieval relevant_concept_ids: {case_id}",
            allow_empty=True,
        )
        if not (relevant_atoms or relevant_methods or relevant_concepts):
            raise ValueError(f"retrieval case has no relevant ids: {case_id}")
        if set(relevant_atoms) - atom_ids:
            raise ValueError(f"retrieval case references unknown atom: {case_id}")
        if set(relevant_methods) - method_ids:
            raise ValueError(f"retrieval case references unknown method: {case_id}")
        if set(relevant_concepts) - concept_ids:
            raise ValueError(f"retrieval case references unknown concept: {case_id}")
        covered_atoms.update(relevant_atoms)
        covered_methods.update(relevant_methods)
        covered_concepts.update(relevant_concepts)
    if covered_atoms != atom_ids:
        raise ValueError("retrieval fixture does not cover every atom")
    if covered_methods != method_ids:
        raise ValueError("retrieval fixture does not cover every method")
    if covered_concepts != concept_ids:
        raise ValueError("retrieval fixture does not cover every concept")
    pack = load_knowledge_pack(pack_root / "sources.jsonl", pack_root / "atoms.jsonl", mode="public")
    if (
        len(pack.sources) != len(sources)
        or len(pack.atoms) != len(atoms)
        or len(pack.concepts) != len(concepts)
        or len(pack.methods) != len(methods)
        or pack.excluded_sources
        or pack.excluded_atoms
        or pack.excluded_concepts
        or pack.excluded_methods
    ):
        raise ValueError("public runtime excluded a bundled source, atom, concept, or method")
    recall = evaluate_recall(pack, pack_root / "retrieval-cases.jsonl", k=5, threshold=0.85)
    if not recall.get("passed"):
        raise ValueError(
            "public retrieval gate failed: "
            f"atom={recall.get('atom_recall_at_5')} "
            f"method={recall.get('method_recall_at_3')} "
            f"concept={recall.get('concept_match_recall')}"
        )
    return {
        "sources": len(sources),
        "atoms": len(atoms),
        "methods": len(methods),
        "concepts": len(concepts),
        "retrieval_cases": len(retrieval_cases),
        "knowledge_nodes": network_counts["knowledge_nodes"],
        "knowledge_edges": network_counts["knowledge_edges"],
        "atom_recall_at_5": recall["atom_recall_at_5"],
        "atom_top1": recall["atom_top1"],
        "atom_mrr": recall["atom_mrr"],
        "method_recall_at_3": recall["method_recall_at_3"],
        "concept_match_recall": recall["concept_match_recall"],
        "recall_at_5": recall["atom_recall_at_5"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill", type=Path, nargs="?", default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    try:
        result = validate_pack(args.skill.resolve())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL {exc}")
        return 1
    print("OK " + " ".join(f"{key}={value}" for key, value in result.items()) + " raw_source_text=false private_working_material=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
