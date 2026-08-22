#!/usr/bin/env python3
"""Freeze and validate one CasePacket/Handoff bundle without persisting input."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from validate_contracts import canonical_hash, errors_for


class ContractBundleError(ValueError):
    """Raised when a bundle cannot be frozen without changing supplied evidence."""


def freeze_bundle(value: object) -> dict:
    if not isinstance(value, dict):
        raise ContractBundleError("bundle root must be an object")
    packet = value.get("case_packet")
    handoff = value.get("handoff")
    if not isinstance(packet, dict):
        raise ContractBundleError("bundle case_packet must be an object")
    if not isinstance(handoff, dict):
        raise ContractBundleError("bundle handoff must be an object")

    bundle = copy.deepcopy(value)
    packet = bundle["case_packet"]
    handoff = bundle["handoff"]
    computed_hash = canonical_hash(packet, "content_hash")

    supplied_content_hash = packet.get("content_hash")
    if supplied_content_hash in (None, ""):
        packet["content_hash"] = computed_hash

    supplied_packet_hash = handoff.get("packet_hash")
    if supplied_packet_hash in (None, ""):
        handoff["packet_hash"] = computed_hash

    packet_errors = errors_for(packet)
    if "expected_state_version" not in bundle:
        raise ContractBundleError("expected_state_version is required as an independent lease")
    expected_state_version = bundle.get("expected_state_version")
    if not isinstance(expected_state_version, int) or isinstance(expected_state_version, bool):
        raise ContractBundleError("expected_state_version must be an integer when provided")
    handoff_errors = errors_for(
        handoff,
        expected_packet_hash=computed_hash,
        expected_state_version=expected_state_version,
        expected_consent=packet.get("consent") if isinstance(packet.get("consent"), dict) else None,
        expected_allowed_tools=(
            set(packet["tool_policy"]["allowed_tools"])
            if isinstance(packet.get("tool_policy"), dict)
            and isinstance(packet["tool_policy"].get("allowed_tools"), list)
            else set()
        ),
    )
    errors = [f"case_packet: {error}" for error in packet_errors]
    errors.extend(f"handoff: {error}" for error in handoff_errors)
    if errors:
        raise ContractBundleError("\n".join(errors))
    return bundle


def read_input(path: Path | None) -> object:
    text = path.read_text(encoding="utf-8") if path is not None else sys.stdin.read()
    if not text.strip():
        raise ContractBundleError("input JSON is empty")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractBundleError(f"invalid JSON: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="read JSON from this file instead of stdin")
    args = parser.parse_args()
    try:
        frozen = freeze_bundle(read_input(args.input))
    except (OSError, ContractBundleError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    json.dump(frozen, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
