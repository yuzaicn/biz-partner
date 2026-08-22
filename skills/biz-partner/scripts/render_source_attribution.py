#!/usr/bin/env python3
"""Resolve material source attributions from a Handoff and source registry."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atom_contract import validate_atom_v2


PUBLIC_RECORD_STATUSES = frozenset({"release_eligible", "published"})
BLOCKED_RECORD_STATUSES = frozenset({"blocked", "rejected", "unresolved"})
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


@dataclass(frozen=True)
class ReleasePolicy:
    source_statuses: frozenset[str]
    atom_statuses: frozenset[str]
    require_public_rights: bool
    mode_label: str


PUBLIC_RELEASE_POLICY = ReleasePolicy(
    source_statuses=PUBLIC_RECORD_STATUSES,
    atom_statuses=PUBLIC_RECORD_STATUSES,
    require_public_rights=True,
    mode_label="public",
)



def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"registry line {line_number} is not an object")
        rows.append(value)
    return rows


def require_nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def require_license_string(value: Any, label: str) -> str:
    normalized = require_nonempty_string(value, label).strip()
    if value != normalized:
        raise ValueError(f"{label} must not contain leading or trailing whitespace")
    return normalized


def validate_public_decision_fields(record_id: str, record: dict[str, Any], kind: str) -> None:
    for field in ("authorization_status", "release_decision"):
        value = record.get(field)
        if value is None:
            continue
        normalized = require_nonempty_string(value, f"{kind} {field}: {record_id}").casefold()
        if normalized not in PUBLIC_DECISION_VALUES[field]:
            allowed = ", ".join(sorted(PUBLIC_DECISION_VALUES[field]))
            raise ValueError(
                f"{kind} {field} blocks public release: {record_id} ({value}); "
                f"expected one of: {allowed}"
            )


def validate_public_license(record_id: str, license_record: Any, kind: str) -> None:
    if not isinstance(license_record, dict):
        raise ValueError(f"{kind} license must be an object: {record_id}")
    license_id = require_license_string(
        license_record.get("id"), f"{kind} license.id: {record_id}"
    )
    license_version = require_license_string(
        license_record.get("version"), f"{kind} license.version: {record_id}"
    )
    scope = require_nonempty_string(
        license_record.get("scope"), f"{kind} license.scope: {record_id}"
    )
    if license_id.casefold() in DISALLOWED_LICENSE_MARKERS:
        raise ValueError(f"{kind} license id is not release eligible: {record_id} ({license_id})")
    if license_version.casefold() in DISALLOWED_LICENSE_MARKERS:
        raise ValueError(
            f"{kind} license version is not release eligible: {record_id} ({license_version})"
        )
    if scope not in PUBLIC_LICENSE_SCOPES:
        allowed = ", ".join(sorted(PUBLIC_LICENSE_SCOPES))
        raise ValueError(
            f"{kind} license scope blocks public release: {record_id} ({scope}); "
            f"expected one of: {allowed}"
        )


def validate_project_paraphrase_source(source_id: str, source: dict[str, Any]) -> None:
    license_record = source.get("license")
    if not (
        source.get("kind") == "curated_source_for_public_paraphrase"
        and source.get("source_expression_redistribution") == "not_granted_or_claimed"
        and source.get("authorization_status")
        == "project_owner_authorized_public_paraphrase"
        and isinstance(license_record, dict)
        and license_record.get("applies_to")
        == "public-pack original paraphrases and compilation only"
    ):
        raise ValueError(f"source project-paraphrase boundary is invalid: {source_id}")


def validate_project_paraphrase_atom(
    atom_id: str, atom: dict[str, Any], rights: dict[str, Any]
) -> None:
    license_record = rights.get("license")
    if not (
        atom.get("provenance_type") == "public_curated_idea_synthesis"
        and atom.get("authorization_status")
        == "project_owner_authorized_public_paraphrase"
        and rights.get("boundary")
        == "license covers this pack's original paraphrase, not source-book expression"
        and isinstance(license_record, dict)
        and license_record.get("applies_to")
        == "public-pack original paraphrases and compilation only"
    ):
        raise ValueError(f"atom project-paraphrase boundary is invalid: {atom_id}")


def validate_source_release(
    source_id: str,
    source: dict[str, Any],
    *,
    policy: ReleasePolicy,
) -> None:
    status = require_nonempty_string(source.get("status"), f"source status: {source_id}")
    rights_status = require_nonempty_string(
        source.get("rights_status"), f"source rights_status: {source_id}"
    )
    if status not in policy.source_statuses:
        if policy.require_public_rights:
            raise ValueError(f"source is not public-release eligible: {source_id} ({status})")
        raise ValueError(f"unsupported {policy.mode_label} source status: {source_id} ({status})")
    if not policy.require_public_rights:
        return
    if rights_status not in PUBLIC_RIGHTS_STATUSES:
        raise ValueError(f"source rights are not public-release eligible: {source_id} ({rights_status})")
    if rights_status == "project_paraphrase_only":
        validate_project_paraphrase_source(source_id, source)
    validate_public_license(source_id, source.get("license"), "source")
    validate_public_decision_fields(source_id, source, "source")


def validate_atom_release(
    atom_id: str,
    atom: dict[str, Any],
    *,
    policy: ReleasePolicy,
) -> None:
    status = require_nonempty_string(atom.get("status"), f"atom status: {atom_id}")
    if status in BLOCKED_RECORD_STATUSES:
        raise ValueError(f"blocked atom cannot be registered: {atom_id} ({status})")
    if status not in policy.atom_statuses:
        if policy.require_public_rights:
            raise ValueError(f"atom is not public-release eligible: {atom_id} ({status})")
        raise ValueError(f"unsupported {policy.mode_label} atom status: {atom_id} ({status})")
    rights = atom.get("rights")
    if not isinstance(rights, dict):
        raise ValueError(f"atom rights must be an object: {atom_id}")
    redistribution = require_nonempty_string(
        rights.get("redistribution"), f"atom rights.redistribution: {atom_id}"
    )
    if not policy.require_public_rights:
        return
    if redistribution not in PUBLIC_RIGHTS_STATUSES:
        raise ValueError(
            f"atom rights are not public-release eligible: {atom_id} ({redistribution})"
        )
    if redistribution == "project_paraphrase_only":
        validate_project_paraphrase_atom(atom_id, atom, rights)
    validate_public_license(atom_id, rights.get("license"), "atom")
    validate_public_decision_fields(atom_id, atom, "atom")


def index_sources(
    source_rows: list[dict[str, Any]],
    *,
    policy: ReleasePolicy,
) -> dict[str, dict[str, Any]]:
    if not isinstance(source_rows, list):
        raise ValueError("source registry must be a list")
    sources: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(source_rows):
        if not isinstance(row, dict):
            raise ValueError(f"source row {index} is not an object")
        source_id = require_nonempty_string(row.get("source_id"), f"source row {index} source_id")
        if source_id in sources:
            raise ValueError(f"duplicate source id: {source_id}")
        validate_source_release(source_id, row, policy=policy)
        attribution_mode = row.get("attribution_mode")
        display_name = row.get("public_attribution_name")
        is_named_source = attribution_mode is not None or display_name is not None
        if is_named_source:
            if attribution_mode != "when_materially_used":
                raise ValueError(f"named source has invalid attribution_mode: {source_id}")
            require_nonempty_string(display_name, f"named source public_attribution_name: {source_id}")
            if row.get("relationship_to_runtime_user") != "external_named_source":
                raise ValueError(
                    f"named source must be external to runtime user: {source_id}"
                )
            if row.get("ownership_status") != "not_claimed":
                raise ValueError(f"named source ownership must be not_claimed: {source_id}")
        sources[source_id] = row
    return sources


def index_atoms(
    atom_rows: list[dict[str, Any]],
    sources: dict[str, dict[str, Any]],
    *,
    policy: ReleasePolicy,
) -> dict[str, dict[str, Any]]:
    if not isinstance(atom_rows, list):
        raise ValueError("atom registry must be a list")
    atoms: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(atom_rows):
        if not isinstance(row, dict):
            raise ValueError(f"atom row {index} is not an object")
        atom_id = require_nonempty_string(row.get("atom_id"), f"atom row {index} atom_id")
        if atom_id in atoms:
            raise ValueError(f"duplicate atom id: {atom_id}")
        validate_atom_v2(
            row,
            allow_private_local_locator=not policy.require_public_rights,
        )
        validate_atom_release(atom_id, row, policy=policy)
        source_refs = row.get("source_refs")
        seen_source_ids: set[str] = set()
        for ref_index, ref in enumerate(source_refs):
            if not isinstance(ref, dict):
                raise ValueError(f"atom source ref is not an object: {atom_id}[{ref_index}]")
            source_id = require_nonempty_string(
                ref.get("source_id"), f"atom source ref source_id: {atom_id}[{ref_index}]"
            )
            if source_id in seen_source_ids:
                raise ValueError(f"duplicate atom source ref: {atom_id} -> {source_id}")
            if source_id not in sources:
                raise ValueError(f"atom references unknown source: {atom_id} -> {source_id}")
            seen_source_ids.add(source_id)
        atoms[atom_id] = row
    return atoms


def validate_evidence_rows(
    handoff: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    atoms: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    evidence_rows = handoff.get("evidence_refs")
    if not isinstance(evidence_rows, list):
        raise ValueError("Handoff evidence_refs must be a list")
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(evidence_rows):
        if not isinstance(row, dict):
            raise ValueError(f"evidence row {index} is not an object")
        evidence_id = require_nonempty_string(row.get("id"), f"evidence row {index} id")
        if evidence_id in evidence_by_id:
            raise ValueError(f"duplicate evidence id: {evidence_id}")
        source_id = require_nonempty_string(row.get("source"), f"evidence source: {evidence_id}")
        evidence_kind = row.get("evidence_kind")
        atom_id = row.get("atom_id")
        if evidence_kind is not None and not isinstance(evidence_kind, str):
            raise ValueError(f"evidence_kind must be a string: {evidence_id}")
        if atom_id is not None and evidence_kind != "knowledge_atom":
            raise ValueError(f"atom_id requires evidence_kind=knowledge_atom: {evidence_id}")
        if evidence_kind != "knowledge_atom":
            if source_id in sources and sources[source_id].get("attribution_mode") == "when_materially_used":
                raise ValueError(f"named-source evidence is not a knowledge atom: {evidence_id}")
            evidence_by_id[evidence_id] = row
            continue
        atom_id = require_nonempty_string(atom_id, f"knowledge atom evidence atom_id: {evidence_id}")
        source = sources.get(source_id)
        if source is None:
            raise ValueError(f"knowledge atom evidence references unknown source: {evidence_id} -> {source_id}")
        atom = atoms.get(atom_id)
        if atom is None:
            raise ValueError(f"material evidence references unknown atom: {atom_id}")
        if source["status"] in BLOCKED_RECORD_STATUSES:
            raise ValueError(f"blocked source cannot support evidence: {source_id}")
        atom_source_ids = {ref["source_id"] for ref in atom["source_refs"]}
        if source_id not in atom_source_ids:
            raise ValueError(f"atom/source mismatch for evidence {evidence_id}: {atom_id} != {source_id}")
        evidence_by_id[evidence_id] = row
    return evidence_by_id


def validate_claim_rows(
    handoff: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    claims = handoff.get("claims")
    if not isinstance(claims, list):
        raise ValueError("Handoff claims must be a list")
    seen_claim_ids: set[str] = set()
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            raise ValueError(f"claim row {index} is not an object")
        claim_id = require_nonempty_string(claim.get("claim_id"), f"claim row {index} claim_id")
        if claim_id in seen_claim_ids:
            raise ValueError(f"duplicate claim id: {claim_id}")
        seen_claim_ids.add(claim_id)
        supporting_refs = claim.get("supporting_refs")
        if not isinstance(supporting_refs, list) or not supporting_refs:
            raise ValueError(f"claim supporting_refs must be a non-empty list: {claim_id}")
        seen_evidence_ids: set[str] = set()
        for ref_index, evidence_id in enumerate(supporting_refs):
            evidence_id = require_nonempty_string(
                evidence_id, f"claim supporting ref: {claim_id}[{ref_index}]"
            )
            if evidence_id in seen_evidence_ids:
                raise ValueError(f"duplicate claim supporting ref: {claim_id} -> {evidence_id}")
            if evidence_id not in evidence_by_id:
                raise ValueError(f"claim references missing supporting evidence: {claim_id} -> {evidence_id}")
            seen_evidence_ids.add(evidence_id)
    return claims


def _material_attributions(
    handoff: dict[str, Any],
    source_rows: list[dict[str, Any]],
    atom_rows: list[dict[str, Any]],
    *,
    policy: ReleasePolicy,
) -> list[dict[str, Any]]:
    if not isinstance(handoff, dict):
        raise ValueError("Handoff root is not an object")
    sources = index_sources(source_rows, policy=policy)
    atoms = index_atoms(atom_rows, sources, policy=policy)
    evidence_by_id = validate_evidence_rows(handoff, sources, atoms)
    claims = validate_claim_rows(handoff, evidence_by_id)

    ordered_source_ids: list[str] = []
    audit_by_source: dict[str, dict[str, list[str]]] = {}
    for claim in claims:
        claim_id = claim["claim_id"]
        for evidence_id in claim["supporting_refs"]:
            evidence = evidence_by_id[evidence_id]
            if evidence.get("evidence_kind") != "knowledge_atom":
                continue
            source_id = evidence["source"]
            source = sources[source_id]
            if source.get("attribution_mode") != "when_materially_used":
                continue
            if source_id not in audit_by_source:
                ordered_source_ids.append(source_id)
                audit_by_source[source_id] = {"claim_ids": [], "evidence_ids": [], "atom_ids": []}
            audit = audit_by_source[source_id]
            for key, value in (
                ("claim_ids", claim_id),
                ("evidence_ids", evidence_id),
                ("atom_ids", evidence["atom_id"]),
            ):
                if value not in audit[key]:
                    audit[key].append(value)
    return [
        {
            "source_id": source_id,
            "display_name": sources[source_id]["public_attribution_name"],
            "source_role": sources[source_id]["relationship_to_runtime_user"],
            "claim_ids": audit_by_source[source_id]["claim_ids"],
            "evidence_ids": audit_by_source[source_id]["evidence_ids"],
            "atom_ids": audit_by_source[source_id]["atom_ids"],
            "first_claim_id": audit_by_source[source_id]["claim_ids"][0],
        }
        for source_id in ordered_source_ids
    ]


# BEGIN BUILD-SPECIFIC API
def material_attributions(
    handoff: dict[str, Any],
    source_rows: list[dict[str, Any]],
    atom_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _material_attributions(
        handoff,
        source_rows,
        atom_rows,
        policy=PUBLIC_RELEASE_POLICY,
    )


def material_attribution_segments(
    handoff: dict[str, Any],
    source_rows: list[dict[str, Any]],
    atom_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    attributions = material_attributions(handoff, source_rows, atom_rows)
    segments: list[dict[str, Any]] = []
    for attribution in attributions:
        display_name = attribution["display_name"]
        segments.append(
            {
                "kind": "source_attribution",
                "source_id": attribution["source_id"],
                "source_role": "external_named_source",
                "first_claim_id": attribution["first_claim_id"],
                "claim_ids": list(attribution["claim_ids"]),
                "evidence_ids": list(attribution["evidence_ids"]),
                "atom_ids": list(attribution["atom_ids"]),
                "text": (
                    f"这一判断参考了{display_name}的相关观点；是否适用于你的情况，"
                    "仍需结合当前证据验证。"
                ),
            }
        )
    return segments


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_registry", type=Path)
    parser.add_argument("atoms", type=Path)
    parser.add_argument("handoff", type=Path)
    args = parser.parse_args()
    try:
        sources = load_jsonl(args.source_registry)
        atoms = load_jsonl(args.atoms)
        handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
        if not isinstance(handoff, dict):
            raise ValueError("Handoff root is not an object")
        segments = material_attribution_segments(handoff, sources, atoms)
        result = {
            "attribution_segments": segments,
        }
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0
# END BUILD-SPECIFIC API


if __name__ == "__main__":
    raise SystemExit(main())
