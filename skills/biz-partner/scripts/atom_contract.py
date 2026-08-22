#!/usr/bin/env python3
"""Shared, source-agnostic Atom v2 runtime contract validation."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit


ATOM_SCHEMA_VERSION = "2.0"
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
LINE_RANGE_RE = re.compile(r"^([1-9][0-9]*)-([1-9][0-9]*)$")
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
CONFIDENCE_VALUES = frozenset({"unknown", "low", "medium", "high"})
CONFIDENCE_FIELDS = ("extraction", "attribution", "interpretation", "operational")


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def require_string_list(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"{label} must be a {'list' if allow_empty else 'non-empty list'}")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{label} must contain only non-empty strings")
    return value


def validate_source_date(value: Any, atom_id: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError(f"atom source_date must be null or ISO date: {atom_id}")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"atom source_date must be null or ISO date: {atom_id}") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"atom source_date must be null or ISO date: {atom_id}")


def validate_portable_locator(
    locator: Any,
    atom_id: str,
    ref_index: int,
    *,
    allow_private_local_locator: bool = False,
) -> None:
    label = f"atom portable locator: {atom_id}[{ref_index}]"
    if not isinstance(locator, dict) or not locator:
        raise ValueError(f"{label} must be a non-empty object")

    if "file" in locator:
        file_value = require_string(locator.get("file"), f"{label}.file")
        if (
            file_value.startswith("\\")
            or WINDOWS_ABSOLUTE_RE.match(file_value)
            or "\\" in file_value
            or (file_value.startswith("/") and not allow_private_local_locator)
        ):
            raise ValueError(f"{label}.file must be a portable relative POSIX path")
        relative = PurePosixPath(file_value)
        if (
            (relative.is_absolute() and not allow_private_local_locator)
            or ".." in relative.parts
            or "." in relative.parts
        ):
            raise ValueError(f"{label}.file must stay inside its portable source root")
        lines = require_string(locator.get("lines"), f"{label}.lines")
        match = LINE_RANGE_RE.fullmatch(lines)
        if match is None or int(match.group(1)) > int(match.group(2)):
            raise ValueError(f"{label}.lines must be an ordered one-based range")
        return

    if "url" in locator:
        url = require_string(locator.get("url"), f"{label}.url")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"{label}.url must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError(f"{label}.url must not contain credentials")
        require_string(locator.get("field"), f"{label}.field")
        return

    raise ValueError(f"{label} must contain file+lines or url+field")


def validate_atom_v2(atom: Any, *, allow_private_local_locator: bool = False) -> None:
    if not isinstance(atom, dict):
        raise ValueError("atom must be an object")
    atom_id = require_string(atom.get("atom_id"), "atom_id")
    if atom.get("schema_version") != ATOM_SCHEMA_VERSION:
        raise ValueError(f"unsupported atom schema: {atom_id}")

    canonical = require_string(atom.get("canonical"), f"atom canonical: {atom_id}")
    if canonical.endswith(("\n", "\r")):
        raise ValueError(f"atom canonical must not have a trailing newline: {atom_id}")
    for field in ("claim_kind", "actionability", "provenance_type", "pipeline_run", "temporal_scope"):
        require_string(atom.get(field), f"atom {field}: {atom_id}")
    require_string_list(atom.get("domain"), f"atom domain: {atom_id}")
    require_string_list(atom.get("limits"), f"atom limits: {atom_id}")
    require_string_list(atom.get("bias_flags"), f"atom bias_flags: {atom_id}", allow_empty=True)

    procedure = atom.get("procedure")
    decision_rule = atom.get("decision_rule")
    if not (isinstance(decision_rule, str) and decision_rule) and not (
        isinstance(procedure, list)
        and procedure
        and all(isinstance(step, str) and step for step in procedure)
    ):
        raise ValueError(f"atom must contain a decision_rule or procedure: {atom_id}")

    content_hash = require_string(atom.get("content_hash"), f"atom content_hash: {atom_id}")
    if not HASH_RE.fullmatch(content_hash) or content_hash != sha256_text(canonical):
        raise ValueError(f"atom content_hash mismatch: {atom_id}")

    confidence = atom.get("confidence")
    if not isinstance(confidence, dict):
        raise ValueError(f"atom confidence must be an object: {atom_id}")
    for field in CONFIDENCE_FIELDS:
        value = confidence.get(field)
        if value not in CONFIDENCE_VALUES:
            raise ValueError(f"atom confidence.{field} is invalid: {atom_id}")

    if "source_date" not in atom:
        raise ValueError(f"atom source_date is required: {atom_id}")
    validate_source_date(atom.get("source_date"), atom_id)

    relations = atom.get("relations")
    if not isinstance(relations, list):
        raise ValueError(f"atom relations must be a list: {atom_id}")

    source_refs = atom.get("source_refs")
    if not isinstance(source_refs, list) or not source_refs:
        raise ValueError(f"atom source_refs must be a non-empty list: {atom_id}")
    seen_source_ids: set[str] = set()
    for index, ref in enumerate(source_refs):
        if not isinstance(ref, dict):
            raise ValueError(f"atom source ref must be an object: {atom_id}[{index}]")
        source_id = require_string(ref.get("source_id"), f"atom source ref source_id: {atom_id}[{index}]")
        if source_id in seen_source_ids:
            raise ValueError(f"duplicate atom source ref: {atom_id} -> {source_id}")
        seen_source_ids.add(source_id)
        validate_portable_locator(
            ref.get("locator"),
            atom_id,
            index,
            allow_private_local_locator=allow_private_local_locator,
        )
        quote_hash = require_string(ref.get("quote_hash"), f"atom quote_hash: {atom_id}[{index}]")
        if not HASH_RE.fullmatch(quote_hash):
            raise ValueError(f"atom quote_hash is invalid: {atom_id}[{index}]")
