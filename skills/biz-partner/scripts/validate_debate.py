#!/usr/bin/env python3
"""Validate the auditable multi-agent debate JSONL event flow."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from validate_contracts import errors_for as contract_errors_for  # noqa: E402


EVENT_TYPES = {
    "DebateStarted",
    "PacketFrozen",
    "WorkerStarted",
    "WorkerCompleted",
    "CrossExamStarted",
    "CrossExamCompleted",
    "Synthesis",
    "UserDecision",
    "MemoryCommit",
}
DEFAULT_ROLES = {"business_economics", "user_product", "contrarian_risk"}
DECISION_OPTIONS = {"accept", "reject", "defer", "add_facts", "rerun_agent", "stop"}
IDENTITY_KEYS = {"worker_id", "role", "agent_id", "author", "output_hash"}
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def load_events(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], [f"cannot read file: {exc}"]
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(value, dict):
            errors.append(f"line {line_number}: event must be object")
            continue
        events.append(value)
    if not events and not errors:
        errors.append("event stream is empty")
    return events, errors


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _parse_timestamp(value: Any) -> datetime | None:
    if not _is_nonempty_string(value):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("payload")
    return value if isinstance(value, dict) else {}


def _content_hash(value: dict[str, Any], excluded_field: str) -> str:
    canonical = dict(value)
    canonical.pop(excluded_field, None)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _has_identity_key(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(set(value) & IDENTITY_KEYS) or any(_has_identity_key(child) for child in value.values())
    if isinstance(value, list):
        return any(_has_identity_key(child) for child in value)
    return False


def _single(events: list[dict[str, Any]], event_type: str, errors: list[str]) -> dict[str, Any] | None:
    matches = [event for event in events if event.get("event_type") == event_type]
    if len(matches) != 1:
        errors.append(f"requires exactly one {event_type}, found {len(matches)}")
        return None
    return matches[0]


def _event_index(events: list[dict[str, Any]], event: dict[str, Any] | None) -> int:
    return events.index(event) if event in events else -1


def validate_events(events: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not events:
        return ["event stream is empty"]

    event_ids: set[str] = set()
    debate_ids: set[str] = set()
    case_ids: set[str] = set()
    last_timestamp: datetime | None = None
    for expected_sequence, event in enumerate(events, 1):
        for field in ("schema_version", "event_id", "debate_id", "case_id", "event_type", "payload"):
            if field not in event:
                errors.append(f"event {expected_sequence} missing {field}")
        if event.get("schema_version") != "1.0":
            errors.append(f"event {expected_sequence} invalid schema_version")
        event_id = event.get("event_id")
        if not _is_nonempty_string(event_id):
            errors.append(f"event {expected_sequence} invalid event_id")
        elif event_id in event_ids:
            errors.append(f"duplicate event_id: {event_id}")
        else:
            event_ids.add(event_id)
        if event.get("sequence") != expected_sequence:
            errors.append(f"event {event_id} expected sequence {expected_sequence}")
        if event.get("event_type") not in EVENT_TYPES:
            errors.append(f"event {event_id} invalid event_type: {event.get('event_type')}")
        if not isinstance(event.get("payload"), dict):
            errors.append(f"event {event_id} payload must be object")
        if _is_nonempty_string(event.get("debate_id")):
            debate_ids.add(event["debate_id"])
        if _is_nonempty_string(event.get("case_id")):
            case_ids.add(event["case_id"])
        timestamp = _parse_timestamp(event.get("timestamp"))
        if timestamp is None:
            errors.append(f"event {event_id} timestamp must be timezone-aware ISO-8601")
        elif last_timestamp is not None and timestamp < last_timestamp:
            errors.append(f"event {event_id} timestamp is earlier than previous event")
        else:
            last_timestamp = timestamp
    if len(debate_ids) != 1:
        errors.append(f"stream must have one debate_id, found {sorted(debate_ids)}")
    if len(case_ids) != 1:
        errors.append(f"stream must have one case_id, found {sorted(case_ids)}")

    started = _single(events, "DebateStarted", errors)
    frozen = _single(events, "PacketFrozen", errors)
    cross_started = _single(events, "CrossExamStarted", errors)
    synthesis = _single(events, "Synthesis", errors)
    decision = _single(events, "UserDecision", errors)
    memory_commits = [event for event in events if event.get("event_type") == "MemoryCommit"]
    if len(memory_commits) > 1:
        errors.append("at most one MemoryCommit is allowed")

    roles: set[str] = set()
    knowledge_allowlist: set[str] = set()
    if started:
        payload = _payload(started)
        raw_roles = payload.get("roles")
        if not isinstance(raw_roles, list) or not raw_roles or any(not _is_nonempty_string(role) for role in raw_roles):
            errors.append("DebateStarted roles must be a non-empty string list")
        else:
            roles = set(raw_roles)
            if len(roles) != len(raw_roles):
                errors.append("DebateStarted roles must be unique")
            missing_defaults = DEFAULT_ROLES - roles
            if missing_defaults:
                errors.append(f"DebateStarted missing default roles: {sorted(missing_defaults)}")
        raw_allowlist = payload.get("knowledge_allowlist", [])
        if not isinstance(raw_allowlist, list) or any(not _is_nonempty_string(item) for item in raw_allowlist):
            errors.append("DebateStarted knowledge_allowlist must be a string list")
        else:
            knowledge_allowlist = set(raw_allowlist)
        budget = payload.get("budget")
        if not isinstance(budget, dict):
            errors.append("DebateStarted requires budget")
        else:
            max_rounds = budget.get("max_rounds")
            if not isinstance(max_rounds, int) or isinstance(max_rounds, bool) or not 1 <= max_rounds <= 2:
                errors.append("DebateStarted max_rounds must be between 1 and 2")
            for field in ("token_limit", "time_limit_seconds"):
                value = budget.get(field)
                if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                    errors.append(f"DebateStarted {field} must be a positive integer")
        if not _is_nonempty_string(payload.get("decision_question")):
            errors.append("DebateStarted requires decision_question")

    if started:
        budget = _payload(started).get("budget", {})
        timed_events = [
            event for event in events
            if event.get("event_type") in {"WorkerCompleted", "CrossExamCompleted", "Synthesis"}
        ]
        token_total = 0
        for event in timed_events:
            usage = _payload(event).get("usage_tokens")
            if not isinstance(usage, int) or isinstance(usage, bool) or usage < 0:
                errors.append(f"event {event.get('event_id')} usage_tokens must be a non-negative integer")
            else:
                token_total += usage
        token_limit = budget.get("token_limit") if isinstance(budget, dict) else None
        if isinstance(token_limit, int) and not isinstance(token_limit, bool) and token_total > token_limit:
            errors.append(f"debate token budget exceeded: {token_total} > {token_limit}")
        first_time = _parse_timestamp(events[0].get("timestamp"))
        last_time = _parse_timestamp(events[-1].get("timestamp"))
        time_limit = budget.get("time_limit_seconds") if isinstance(budget, dict) else None
        if first_time and last_time and isinstance(time_limit, int) and not isinstance(time_limit, bool):
            elapsed = (last_time - first_time).total_seconds()
            if elapsed > time_limit:
                errors.append(f"debate time budget exceeded: {elapsed:.0f}s > {time_limit}s")

    packet_hash: str | None = None
    packet_item_ids: set[str] = set()
    if frozen:
        packet_hash = frozen.get("packet_hash")
        if not isinstance(packet_hash, str) or not HASH_RE.fullmatch(packet_hash):
            errors.append("PacketFrozen packet_hash must be sha256:<64 lowercase hex>")
        payload = _payload(frozen)
        packet = payload.get("packet")
        if not isinstance(packet, dict):
            errors.append("PacketFrozen requires packet object")
        else:
            for error in contract_errors_for(packet):
                errors.append(f"PacketFrozen {error}")
            if packet.get("content_hash") != packet_hash:
                errors.append("PacketFrozen packet content_hash must match packet_hash")
            elif _content_hash(packet, "content_hash") != packet_hash:
                errors.append("PacketFrozen packet_hash does not match canonical packet content")
            if packet.get("case_id") != frozen.get("case_id"):
                errors.append("PacketFrozen packet case_id must match stream case_id")
            packet_item_ids = {
                item.get("id") for item in packet.get("items", [])
                if isinstance(item, dict) and _is_nonempty_string(item.get("id"))
            }

    if packet_hash:
        for event in events:
            if event.get("event_type") != "DebateStarted" and event.get("packet_hash") != packet_hash:
                errors.append(f"event {event.get('event_id')} packet_hash does not match frozen packet")

    worker_started = [event for event in events if event.get("event_type") == "WorkerStarted"]
    worker_completed = [event for event in events if event.get("event_type") == "WorkerCompleted"]
    cross_completed = [event for event in events if event.get("event_type") == "CrossExamCompleted"]

    def role_map(group: list[dict[str, Any]], event_type: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for event in group:
            role = event.get("worker_id")
            if not _is_nonempty_string(role):
                errors.append(f"{event_type} {event.get('event_id')} missing worker_id")
            elif role in result:
                errors.append(f"duplicate {event_type} for role: {role}")
            else:
                result[role] = event
        return result

    started_by_role = role_map(worker_started, "WorkerStarted")
    completed_by_role = role_map(worker_completed, "WorkerCompleted")
    cross_by_role = role_map(cross_completed, "CrossExamCompleted")
    for label, actual in (
        ("WorkerStarted", set(started_by_role)),
        ("WorkerCompleted", set(completed_by_role)),
        ("CrossExamCompleted", set(cross_by_role)),
    ):
        if roles and actual != roles:
            errors.append(f"{label} roles must match DebateStarted roles: expected {sorted(roles)}, found {sorted(actual)}")

    for role, event in started_by_role.items():
        payload = _payload(event)
        if payload.get("round") != 1:
            errors.append(f"WorkerStarted {role} must be round 1")
        if payload.get("input_packet_hash") != packet_hash:
            errors.append(f"WorkerStarted {role} must read frozen packet hash")
        visible = payload.get("visible_worker_outputs")
        if visible != []:
            errors.append(f"WorkerStarted {role} violates independent round: visible_worker_outputs must be empty")
        allowlist = payload.get("knowledge_allowlist")
        if not isinstance(allowlist, list) or any(not _is_nonempty_string(item) for item in allowlist):
            errors.append(f"WorkerStarted {role} knowledge_allowlist must be a string list")
        elif not set(allowlist).issubset(knowledge_allowlist):
            errors.append(f"WorkerStarted {role} knowledge_allowlist exceeds debate allowlist")

    worker_output_event_ids: set[str] = set()
    worker_output_hashes: set[str] = set()
    for role, event in completed_by_role.items():
        if _is_nonempty_string(event.get("event_id")):
            worker_output_event_ids.add(event["event_id"])
        payload = _payload(event)
        if payload.get("round") != 1:
            errors.append(f"WorkerCompleted {role} must be round 1")
        for field in ("position", "output_hash"):
            if not _is_nonempty_string(payload.get(field)):
                errors.append(f"WorkerCompleted {role} requires {field}")
        output_hash = payload.get("output_hash")
        if _is_nonempty_string(output_hash):
            if not HASH_RE.fullmatch(output_hash):
                errors.append(f"WorkerCompleted {role} output_hash must be sha256:<64 lowercase hex>")
            elif _content_hash(payload, "output_hash") != output_hash:
                errors.append(f"WorkerCompleted {role} output_hash does not match canonical payload")
            if output_hash in worker_output_hashes:
                errors.append(f"WorkerCompleted {role} output_hash must be unique")
            worker_output_hashes.add(output_hash)
        for field in ("claims", "evidence_refs", "assumptions", "counterexamples", "falsifiers"):
            if not isinstance(payload.get(field), list):
                errors.append(f"WorkerCompleted {role} {field} must be list")
        for field in ("counterexamples", "falsifiers"):
            if isinstance(payload.get(field), list) and not payload[field]:
                errors.append(f"WorkerCompleted {role} requires at least one {field}")
        confidence = payload.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            errors.append(f"WorkerCompleted {role} confidence must be between 0 and 1")
        proposed_test = payload.get("proposed_test")
        if not isinstance(proposed_test, dict) or not proposed_test:
            errors.append(f"WorkerCompleted {role} requires proposed_test")
        else:
            for field in ("action", "success_signal", "cost_limit"):
                if not _is_nonempty_string(proposed_test.get(field)):
                    errors.append(f"WorkerCompleted {role} proposed_test requires {field}")
        evidence_ids: set[str] = set()
        for ref in payload.get("evidence_refs", []) if isinstance(payload.get("evidence_refs"), list) else []:
            if not isinstance(ref, dict) or not _is_nonempty_string(ref.get("id")):
                errors.append(f"WorkerCompleted {role} has invalid evidence ref")
                continue
            evidence_ids.add(ref["id"])
            if ref.get("packet_item_id") not in packet_item_ids:
                errors.append(f"WorkerCompleted {role} evidence {ref['id']} does not resolve to CasePacket")
        for claim in payload.get("claims", []) if isinstance(payload.get("claims"), list) else []:
            if not isinstance(claim, dict) or not _is_nonempty_string(claim.get("claim_id")):
                errors.append(f"WorkerCompleted {role} has invalid claim")
                continue
            if not _is_nonempty_string(claim.get("assertion")):
                errors.append(f"WorkerCompleted {role} claim {claim.get('claim_id')} requires assertion")
            supporting = claim.get("supporting_refs")
            if not isinstance(supporting, list) or any(not _is_nonempty_string(ref) for ref in supporting):
                errors.append(f"WorkerCompleted {role} claim {claim.get('claim_id')} supporting_refs must be a string list")
            elif not set(supporting) & evidence_ids:
                errors.append(f"WorkerCompleted {role} claim {claim.get('claim_id')} lacks local evidence")
        own_start = started_by_role.get(role)
        if own_start and _event_index(events, own_start) >= _event_index(events, event):
            errors.append(f"WorkerCompleted {role} must follow its WorkerStarted")

    if cross_started:
        payload = _payload(cross_started)
        if payload.get("round") != 2:
            errors.append("CrossExamStarted must be round 2")
        summaries = payload.get("deidentified_summaries")
        if not isinstance(summaries, list) or len(summaries) < 2:
            errors.append("CrossExamStarted requires at least two deidentified summaries")
        elif _has_identity_key(payload):
            errors.append("CrossExamStarted deidentified input leaks worker identity")
        conflicts = payload.get("conflicting_claims")
        if not isinstance(conflicts, list) or not conflicts:
            errors.append("CrossExamStarted requires conflicting_claims")
        if any(_event_index(events, event) >= _event_index(events, cross_started) for event in worker_completed):
            errors.append("CrossExamStarted must follow all WorkerCompleted events")

    cross_output_event_ids: set[str] = set()
    for role, event in cross_by_role.items():
        if _is_nonempty_string(event.get("event_id")):
            cross_output_event_ids.add(event["event_id"])
        payload = _payload(event)
        if payload.get("round") != 2:
            errors.append(f"CrossExamCompleted {role} must be round 2")
        if cross_started and payload.get("input_event_id") != cross_started.get("event_id"):
            errors.append(f"CrossExamCompleted {role} must reference CrossExamStarted")
        for field in ("weakest_premise", "missing_evidence", "disconfirming_observation", "lower_cost_test"):
            if not _is_nonempty_string(payload.get(field)):
                errors.append(f"CrossExamCompleted {role} requires {field}")
        if cross_started and _event_index(events, cross_started) >= _event_index(events, event):
            errors.append(f"CrossExamCompleted {role} must follow CrossExamStarted")

    if synthesis:
        payload = _payload(synthesis)
        for field in ("consensus", "disagreements", "blind_spots", "evidence_strength", "alternatives", "actions"):
            if not isinstance(payload.get(field), list):
                errors.append(f"Synthesis {field} must be list")
        if not isinstance(payload.get("current_judgment"), dict) or not _is_nonempty_string(payload["current_judgment"].get("assertion")):
            errors.append("Synthesis requires one current_judgment")
        else:
            supporting = payload["current_judgment"].get("supporting_refs")
            if not isinstance(supporting, list) or any(not _is_nonempty_string(ref) for ref in supporting):
                errors.append("Synthesis current_judgment supporting_refs must be a string list")
            elif not supporting or not set(supporting).issubset(packet_item_ids):
                errors.append("Synthesis current_judgment must resolve to CasePacket evidence")
        for field in ("consensus", "disagreements", "blind_spots"):
            values = payload.get(field)
            if isinstance(values, list) and any(not _is_nonempty_string(value) for value in values):
                errors.append(f"Synthesis {field} must contain strings")
        evidence_strength = payload.get("evidence_strength")
        if isinstance(evidence_strength, list):
            for item in evidence_strength:
                if not isinstance(item, dict) or not _is_nonempty_string(item.get("conclusion")):
                    errors.append("Synthesis has invalid evidence_strength item")
                    continue
                refs = item.get("evidence_refs")
                if not isinstance(refs, list) or any(not _is_nonempty_string(ref) for ref in refs):
                    errors.append("Synthesis evidence_strength refs must be a string list")
                elif not refs or not set(refs).issubset(packet_item_ids):
                    errors.append("Synthesis evidence_strength must resolve to CasePacket evidence")
        actions = payload.get("actions")
        if isinstance(actions, list) and not 2 <= len(actions) <= 3:
            errors.append("Synthesis requires 2 to 3 actions or experiments")
        elif isinstance(actions, list):
            for action in actions:
                if not isinstance(action, dict) or not all(
                    _is_nonempty_string(action.get(field)) for field in ("action", "acceptance")
                ):
                    errors.append("Synthesis action requires action and acceptance")
        alternatives = payload.get("alternatives")
        if isinstance(alternatives, list) and len(alternatives) < 2:
            errors.append("Synthesis requires at least two reasonable alternatives")
        elif isinstance(alternatives, list):
            for alternative in alternatives:
                if not isinstance(alternative, dict) or not all(
                    _is_nonempty_string(alternative.get(field)) for field in ("option", "reason")
                ):
                    errors.append("Synthesis alternative requires option and reason")
        stop_condition = payload.get("stop_condition")
        if not isinstance(stop_condition, dict) or not _is_nonempty_string(stop_condition.get("predicate")):
            errors.append("Synthesis requires stop_condition predicate")
        if payload.get("decision_method") == "majority_vote" or payload.get("majority_vote_used") is not False:
            errors.append("Synthesis cannot use majority vote as truth")
        required_sources = worker_output_event_ids | cross_output_event_ids
        source_ids = payload.get("source_event_ids")
        if not isinstance(source_ids, list) or any(not _is_nonempty_string(item) for item in source_ids):
            errors.append("Synthesis source_event_ids must be a string list")
        elif set(source_ids) != required_sources:
            errors.append("Synthesis source_event_ids must exactly match completed worker and cross-exam events")
        risk_class = _payload(started).get("risk_class") if started else None
        if risk_class in {"high", "sensitive"} and payload.get("risk_agent_pass") is not True:
            errors.append("high-risk Synthesis requires risk_agent_pass")
        if any(_event_index(events, event) >= _event_index(events, synthesis) for event in cross_completed):
            errors.append("Synthesis must follow all CrossExamCompleted events")

    if decision:
        payload = _payload(decision)
        choice = payload.get("choice")
        if choice not in DECISION_OPTIONS:
            errors.append(f"UserDecision invalid choice: {choice}")
        offered = payload.get("offered_options")
        if not isinstance(offered, list) or any(not _is_nonempty_string(item) for item in offered):
            errors.append("UserDecision offered_options must be a string list")
        elif set(offered) != DECISION_OPTIONS or len(offered) != len(DECISION_OPTIONS):
            errors.append("UserDecision must offer exactly every protocol option once")
        if synthesis and payload.get("synthesis_event_id") != synthesis.get("event_id"):
            errors.append("UserDecision must reference Synthesis")
        if not isinstance(payload.get("memory_commit_confirmed"), bool):
            errors.append("UserDecision memory_commit_confirmed must be boolean")
        if synthesis and _event_index(events, synthesis) >= _event_index(events, decision):
            errors.append("UserDecision must follow Synthesis")

    confirmed = bool(decision and _payload(decision).get("memory_commit_confirmed") is True)
    if memory_commits and not confirmed:
        errors.append("MemoryCommit requires explicit UserDecision confirmation")
    if confirmed and len(memory_commits) != 1:
        errors.append("confirmed memory commit requires exactly one MemoryCommit event")
    if memory_commits and decision and _event_index(events, decision) >= _event_index(events, memory_commits[0]):
        errors.append("MemoryCommit must follow UserDecision")

    if started and _event_index(events, started) != 0:
        errors.append("DebateStarted must be first")
    if started and frozen and _event_index(events, started) >= _event_index(events, frozen):
        errors.append("PacketFrozen must follow DebateStarted")
    if frozen and any(_event_index(events, frozen) >= _event_index(events, event) for event in worker_started):
        errors.append("all WorkerStarted events must follow PacketFrozen")

    return errors


def phase_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "independent": sum(event.get("event_type") == "WorkerCompleted" for event in events),
        "cross_exam": sum(event.get("event_type") == "CrossExamCompleted" for event in events),
        "synthesis": sum(event.get("event_type") == "Synthesis" for event in events),
        "user_decision": sum(event.get("event_type") == "UserDecision" for event in events),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    failures = 0
    for path in args.paths:
        events, errors = load_events(path)
        errors.extend(validate_events(events) if events else [])
        if errors:
            print(f"FAIL {path}")
            for error in errors:
                print(f"  - {error}")
            failures += 1
        else:
            counts = phase_counts(events)
            rendered = ", ".join(f"{name}={count}" for name, count in counts.items())
            print(f"OK {path}: {rendered}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
