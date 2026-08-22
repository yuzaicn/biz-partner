#!/usr/bin/env python3
"""Build advisory runtime context from confirmed, active biz-partner state."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import state_store


SCHEMA_VERSION = "1.0"
CONSTRAINT_SUBJECTS = {
    "availability",
    "budget",
    "deadline",
    "risk_tolerance",
    "weekly_time_budget",
}
CADENCE_SUBJECTS = {
    "cadence",
    "preferred_cadence",
    "review_cadence",
    "work_cadence",
}
STYLE_SUBJECTS = {
    "communication_style",
    "output_style",
    "preferred_style",
    "style",
}


def matches_subject(subject: str, exact: set[str], prefixes: tuple[str, ...]) -> bool:
    return subject in exact or subject.startswith(prefixes)


def record_value(record: dict[str, Any]) -> Any:
    return record["value"]


def sorted_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda record: (
            str(record.get("subject", "")),
            str(record.get("created_at", "")),
            str(record.get("proposal_id", "")),
        ),
    )


def runtime_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "subject": record["subject"],
        "value": record["value"],
        "confidence": record["confidence"],
        "scope": record["scope"],
        "source_refs": record["source_refs"],
        "proposal_id": record["proposal_id"],
        "created_at": record["created_at"],
        "expires_at": record["expires_at"],
    }


def build_adaptive_context(
    state: dict[str, Any],
    *,
    as_of: str | datetime | None = None,
) -> dict[str, Any]:
    """Project confirmed state into non-authoritative conversation context."""

    instant = state_store.resolve_as_of(as_of)
    visible = state_store.visible_state(state, as_of=instant)
    profile = visible["user_profile"]

    constraints = {
        subject: record_value(record)
        for subject, record in sorted(profile.items())
        if matches_subject(
            subject,
            CONSTRAINT_SUBJECTS,
            ("constraint.", "constraints.", "limit.", "limits."),
        )
    }
    cadence = {
        subject: record_value(record)
        for subject, record in sorted(profile.items())
        if matches_subject(subject, CADENCE_SUBJECTS, ("cadence.", "preferences.cadence."))
    }
    style = {
        subject: record_value(record)
        for subject, record in sorted(profile.items())
        if matches_subject(subject, STYLE_SUBJECTS, ("style.", "preferences.style."))
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "state_version": visible["state_version"],
        "as_of": instant.isoformat(),
        "advisory_only": True,
        "profile": {
            subject: runtime_record(record)
            for subject, record in sorted(profile.items())
        },
        "profile_constraints": constraints,
        "preferences": {
            "cadence": cadence,
            "style": style,
        },
        "project_context": {
            subject: runtime_record(record)
            for subject, record in sorted(visible["project_state"].items())
        },
        "decision_context": [runtime_record(record) for record in sorted_records(visible["decision_log"])],
        "asset_context": [runtime_record(record) for record in sorted_records(visible["asset_index"])],
        "playbook_feedback": [
            runtime_record(record) for record in sorted_records(visible["playbook_feedback"])
        ],
        "authority_limits": {
            "may_inform_conversation": True,
            "may_rewrite_skill": False,
            "may_change_safety_policy": False,
            "may_expand_permissions": False,
            "may_decide_final_route": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--as-of")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        root = state_store.resolve_root(args.root)
        state = state_store.load_state(root)
        context = build_adaptive_context(state, as_of=args.as_of)
    except state_store.StateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(context, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
