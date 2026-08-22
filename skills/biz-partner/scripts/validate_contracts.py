#!/usr/bin/env python3
"""Validate minimal M0 CasePacket/Handoff invariants without external dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from state_store import validate_proposal


HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
VERSIONED_TASK_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+@[0-9]+\.[0-9]+\.[0-9]+$")
ROUTE_TASK_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+(?:@[0-9]+\.[0-9]+\.[0-9]+)?$")
ACTION_CLASSES = {"read_local", "write_local", "network_read", "external_write", "destructive", "sensitive"}
TRACE_FIELDS = {
    "action",
    "status",
    "tool",
    "approval_id",
    "target",
    "body_hash",
    "scope_hash",
    "idempotency_key",
    "occurred_at",
}


def canonical_hash(value: dict, excluded_field: str) -> str:
    body = {key: item for key, item in value.items() if key != excluded_field}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def validate_string_list(value: object, label: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{label} must be list")
    elif not all(isinstance(item, str) for item in value):
        errors.append(f"{label} must contain strings")


def bounded_score(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0 <= value <= 1
    )


def validate_route_decision(artifact: dict, handoff_task_id: object, errors: list[str]) -> None:
    top_candidates = artifact.get("top_candidates")
    if not isinstance(top_candidates, list) or len(top_candidates) != 3:
        errors.append("route_decision top_candidates must contain exactly 3 candidates")
        return

    candidate_ids: list[str] = []
    candidate_scores: list[float] = []
    score_by_task: dict[str, float] = {}
    for index, candidate in enumerate(top_candidates):
        label = f"route_decision candidate {index + 1}"
        if not isinstance(candidate, dict):
            errors.append(f"{label} must be object")
            continue
        task_id = candidate.get("task_id")
        if not isinstance(task_id, str) or not ROUTE_TASK_ID_RE.fullmatch(task_id):
            errors.append(f"{label} task_id must be a TaskSpec id")
        else:
            candidate_ids.append(task_id)
        score = candidate.get("score")
        if not bounded_score(score):
            errors.append(f"{label} score must be between 0 and 1")
        else:
            candidate_scores.append(float(score))
            if isinstance(task_id, str) and ROUTE_TASK_ID_RE.fullmatch(task_id):
                score_by_task[task_id] = float(score)
        for key in ("rejection_reason", "route_change_condition"):
            if not nonempty_string(candidate.get(key)):
                errors.append(f"{label} requires {key}")

    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("route_decision candidate task_ids must be unique")
    if len(candidate_scores) == 3 and candidate_scores != sorted(candidate_scores, reverse=True):
        errors.append("route_decision candidates must be sorted by descending score")

    selected_task = artifact.get("selected_task")
    if not isinstance(selected_task, str) or not ROUTE_TASK_ID_RE.fullmatch(selected_task):
        errors.append("route_decision selected_task must be a TaskSpec id")
    elif selected_task not in candidate_ids:
        errors.append("route_decision selected_task must appear in top_candidates")
    elif candidate_ids and selected_task != candidate_ids[0]:
        errors.append("route_decision selected_task must be the highest-scoring candidate")
    elif isinstance(handoff_task_id, str):
        selected_base = selected_task.split("@", 1)[0]
        handoff_base = handoff_task_id.split("@", 1)[0]
        if selected_base != handoff_base or ("@" in selected_task and selected_task != handoff_task_id):
            errors.append("route_decision selected_task must match handoff task_id")

    if not nonempty_string(artifact.get("route_reason")):
        errors.append("route_decision requires route_reason")
    confidence = artifact.get("confidence")
    if not bounded_score(confidence):
        errors.append("route_decision confidence must be between 0 and 1")
    elif selected_task in score_by_task:
        if abs(score_by_task[selected_task] - float(confidence)) > 1e-9:
            errors.append("route_decision confidence must equal the selected candidate score")


def validate_decision_record(artifact: dict, evidence_by_id: dict[str, dict], errors: list[str]) -> None:
    status = artifact.get("status")
    if status not in {"proposed", "confirmed"}:
        errors.append("decision_record status must be proposed or confirmed")
        return
    if status != "confirmed":
        return
    confirmation_ref = artifact.get("confirmation_ref")
    if not nonempty_string(confirmation_ref):
        errors.append("confirmed decision_record requires confirmation_ref")
        return
    evidence = evidence_by_id.get(confirmation_ref)
    if evidence is None or evidence.get("evidence_kind") != "user_input":
        errors.append("decision_record confirmation_ref must point to user_input evidence")


def errors_for(
    obj: dict,
    *,
    expected_packet_hash: str | None = None,
    expected_state_version: int | None = None,
    expected_consent: dict[str, bool] | None = None,
    expected_allowed_tools: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["contract root must be an object"]

    kind = obj.get("kind", "handoff")
    if kind == "case_packet":
        required = (
            "schema_version",
            "packet_id",
            "case_id",
            "project_id",
            "request",
            "items",
            "consent",
            "tool_policy",
            "content_hash",
        )
        for key in required:
            if key not in obj:
                errors.append(f"case_packet missing {key}")
        if obj.get("schema_version") != "1.0":
            errors.append("case_packet schema_version must be 1.0")
        request = obj.get("request")
        if not isinstance(request, dict):
            errors.append("case_packet request must be object")
        else:
            # Dynamic /biz routing legitimately has no explicit command.
            for key in ("raw_goal", "intent"):
                if not nonempty_string(request.get(key)):
                    errors.append(f"case_packet request missing {key}")
            if "explicit_command" in request and not isinstance(request.get("explicit_command"), str):
                errors.append("case_packet request explicit_command must be string")

        for key in ("packet_id", "case_id", "project_id"):
            if not nonempty_string(obj.get(key)):
                errors.append(f"case_packet {key} must be a non-empty string")
        if "parent_packet_hash" in obj and obj.get("parent_packet_hash") is not None and not isinstance(
            obj.get("parent_packet_hash"), str
        ):
            errors.append("case_packet parent_packet_hash must be a string or null")

        items = obj.get("items")
        if not isinstance(items, list):
            errors.append("case_packet items must be list")
        else:
            allowed_item_kinds = {"fact", "user_claim", "inference", "constraint", "unknown"}
            item_ids: set[str] = set()
            for item in items:
                if not isinstance(item, dict):
                    errors.append("case_packet item must be object")
                    continue
                item_id = item.get("id")
                if not isinstance(item_id, str) or not item_id:
                    errors.append("case_packet item missing id")
                elif item_id in item_ids:
                    errors.append(f"duplicate case_packet item id: {item_id}")
                else:
                    item_ids.add(item_id)
                if item.get("kind") not in allowed_item_kinds:
                    errors.append(f"invalid case_packet item kind: {item.get('kind')}")
                if "value" not in item:
                    errors.append(f"case_packet item missing value: {item_id}")
                if "source_ref" in item and not isinstance(item.get("source_ref"), str):
                    errors.append(f"case_packet item source_ref must be string: {item_id}")
                if item.get("kind") != "unknown" and not nonempty_string(item.get("source_ref")):
                    errors.append(f"case_packet item lacks source_ref: {item_id}")
                confidence = item.get("confidence")
                if confidence is not None and (
                    not isinstance(confidence, (int, float))
                    or isinstance(confidence, bool)
                    or not 0 <= confidence <= 1
                ):
                    errors.append(f"case_packet item confidence must be between 0 and 1: {item_id}")

        for key in ("acceptance_criteria", "unknowns", "negative_constraints"):
            if key in obj:
                validate_string_list(obj.get(key), f"case_packet {key}", errors)

        consent = obj.get("consent")
        if not isinstance(consent, dict):
            errors.append("case_packet consent must be object")
        else:
            allowed_actions = {"read_local", "write_local", "network_read", "external_write", "destructive", "sensitive"}
            unknown_actions = set(consent) - allowed_actions
            if unknown_actions:
                errors.append(f"case_packet consent has unknown actions: {sorted(unknown_actions)}")
            if any(not isinstance(value, bool) for value in consent.values()):
                errors.append("case_packet consent values must be booleans")
        if "tool_policy" in obj and not isinstance(obj.get("tool_policy"), dict):
            errors.append("case_packet tool_policy must be object")
        elif isinstance(obj.get("tool_policy"), dict):
            allowed_tools = obj["tool_policy"].get("allowed_tools")
            if not isinstance(allowed_tools, list) or not all(isinstance(tool, str) for tool in allowed_tools):
                errors.append("case_packet tool_policy allowed_tools must be a list of strings")
            elif any(tool not in ACTION_CLASSES for tool in allowed_tools):
                errors.append("case_packet tool_policy allowed_tools contains an unsupported action class")
        if "risk" in obj and not isinstance(obj.get("risk"), dict):
            errors.append("case_packet risk must be object")
        if "ttl" in obj and not isinstance(obj.get("ttl"), str):
            errors.append("case_packet ttl must be string")

        content_hash = obj.get("content_hash")
        if not isinstance(content_hash, str) or not HASH_RE.fullmatch(content_hash):
            errors.append("case_packet content_hash must be sha256:<64 lowercase hex>")
        elif canonical_hash(obj, "content_hash") != content_hash:
            errors.append("case_packet content_hash does not match canonical packet content")
        return errors

    if kind != "handoff":
        errors.append(f"invalid contract kind: {kind}")
        return errors

    required = ("schema_version", "run_id", "packet_hash", "state_version", "task_id", "state", "claims", "evidence_refs", "next_action", "stop_condition")
    for key in required:
        if key not in obj:
            errors.append(f"handoff missing {key}")
    state = obj.get("state")
    if obj.get("schema_version") != "1.0":
        errors.append("handoff schema_version must be 1.0")
    if not nonempty_string(obj.get("run_id")):
        errors.append("handoff run_id must be a non-empty string")
    packet_hash = obj.get("packet_hash")
    if not isinstance(packet_hash, str) or not HASH_RE.fullmatch(packet_hash):
        errors.append("handoff packet_hash must be sha256:<64 lowercase hex>")
    if expected_packet_hash is not None and packet_hash != expected_packet_hash:
        errors.append("handoff packet_hash does not match current packet lease")
    state_version = obj.get("state_version")
    if not isinstance(state_version, int) or isinstance(state_version, bool) or state_version < 1:
        errors.append("handoff state_version must be a positive integer")
    if expected_state_version is not None and state_version != expected_state_version:
        errors.append("handoff state_version does not match current project lease")
    if state not in {"completed", "blocked", "clarify", "safe_stop", "conflict", "retry_limit"}:
        errors.append(f"invalid state: {state}")
    task_id = obj.get("task_id")
    if not isinstance(task_id, str) or not VERSIONED_TASK_ID_RE.fullmatch(task_id):
        errors.append("handoff task_id must be a versioned id such as business.diagnose@1.0.0")

    claims = obj.get("claims")
    if not isinstance(claims, list):
        errors.append("handoff claims must be list")
        claims = []
    evidence_refs = obj.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        errors.append("handoff evidence_refs must be list")
        evidence_refs = []

    evidence_ids: set[str] = set()
    evidence_by_id: dict[str, dict] = {}
    for ref in evidence_refs:
        if not isinstance(ref, dict):
            errors.append("evidence ref must be object")
            continue
        ref_id = ref.get("id")
        if not nonempty_string(ref_id):
            errors.append("evidence ref missing id")
        elif ref_id in evidence_ids:
            errors.append(f"duplicate evidence id: {ref_id}")
        else:
            evidence_ids.add(ref_id)
            evidence_by_id[ref_id] = ref
        for key in ("source", "as_of"):
            if not nonempty_string(ref.get(key)):
                errors.append(f"evidence ref missing {key}: {ref_id}")
        if "locator" not in ref:
            errors.append(f"evidence ref missing locator: {ref_id}")
        evidence_kind = ref.get("evidence_kind")
        allowed_evidence_kinds = {"user_input", "external_evidence", "knowledge_atom", "project_state", "tool_result"}
        if evidence_kind is not None and evidence_kind not in allowed_evidence_kinds:
            errors.append(f"invalid evidence_kind: {ref_id}")
        atom_id = ref.get("atom_id")
        if evidence_kind == "knowledge_atom" and not nonempty_string(atom_id):
            errors.append(f"knowledge atom evidence requires atom_id: {ref_id}")
        if atom_id is not None and evidence_kind != "knowledge_atom":
            errors.append(f"atom_id requires evidence_kind=knowledge_atom: {ref_id}")

    for claim in claims:
        if not isinstance(claim, dict):
            errors.append("claim must be object")
            continue
        if not nonempty_string(claim.get("claim_id")):
            errors.append("claim missing claim_id")
        if not nonempty_string(claim.get("kind")):
            errors.append(f"claim missing kind: {claim.get('claim_id')}")
        if not nonempty_string(claim.get("assertion")):
            errors.append(f"claim missing assertion: {claim.get('claim_id')}")
        if "strength" in claim and not isinstance(claim.get("strength"), str):
            errors.append(f"claim strength must be string: {claim.get('claim_id')}")
        supporting_refs = claim.get("supporting_refs", [])
        if not isinstance(supporting_refs, list):
            errors.append(f"claim supporting_refs must be list: {claim.get('claim_id')}")
            supporting_refs = []
        invalid_supporting_refs = [ref for ref in supporting_refs if not isinstance(ref, str)]
        if invalid_supporting_refs:
            errors.append(f"claim supporting_refs must contain string ids: {claim.get('claim_id')}")
        supporting_ref_ids = {ref for ref in supporting_refs if isinstance(ref, str)}
        if claim.get("kind") != "unknown" and not supporting_ref_ids & evidence_ids:
            errors.append(f"claim lacks evidence: {claim.get('claim_id')}")

    for key in ("assumptions", "blockers", "artifacts", "rejected_options", "open_questions", "proposed_patches"):
        if key in obj and not isinstance(obj.get(key), list):
            errors.append(f"handoff {key} must be list")

    artifacts = obj.get("artifacts", [])
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                errors.append("handoff artifact must be object")
                continue
            artifact_type = artifact.get("type", artifact.get("artifact_type"))
            if artifact_type == "route_decision":
                validate_route_decision(artifact, task_id, errors)
            elif artifact_type == "decision_record":
                validate_decision_record(artifact, evidence_by_id, errors)

    next_action = obj.get("next_action")
    stop_condition = obj.get("stop_condition")
    if not isinstance(next_action, dict) or not nonempty_string(next_action.get("owner")):
        errors.append("handoff next_action owner must be a non-empty string")
    if not isinstance(stop_condition, dict) or not nonempty_string(stop_condition.get("predicate")):
        errors.append("handoff stop_condition predicate must be a non-empty string")

    if state == "completed":
        if not claims:
            errors.append("completed handoff requires claims")
        if not evidence_refs and not obj.get("no_evidence_reason"):
            errors.append("completed handoff requires evidence or no_evidence_reason")
    if state == "blocked" and not obj.get("blockers"):
        errors.append("blocked handoff requires blockers")
    if state == "safe_stop" and (obj.get("proposed_patches") or obj.get("tool_trace")):
        errors.append("safe_stop cannot include side effects")
    approvals = obj.get("approvals", [])
    if not isinstance(approvals, list):
        errors.append("approvals must be list")
        approvals = []
    external_approvals: list[dict] = []
    for approval in approvals:
        if not isinstance(approval, dict):
            errors.append("approval must be object")
            continue
        if not nonempty_string(approval.get("action")):
            errors.append("approval action must be a non-empty string")
            continue
        if approval.get("action") == "external_write":
            external_approvals.append(approval)
            for key in (
                "approval_id",
                "target",
                "body_hash",
                "scope_hash",
                "approved_at",
                "expires_at",
                "idempotency_key",
            ):
                if not nonempty_string(approval.get(key)):
                    errors.append(f"external_write approval requires {key}")
            for key in ("body_hash", "scope_hash"):
                value = approval.get(key)
                if value is not None and (not isinstance(value, str) or not HASH_RE.fullmatch(value)):
                    errors.append(f"external_write approval {key} must be sha256:<64 lowercase hex>")
            approved_at = parse_datetime(approval.get("approved_at"))
            expires_at = parse_datetime(approval.get("expires_at"))
            if approved_at is None:
                errors.append("external_write approval approved_at must be an ISO 8601 date-time with timezone")
            if expires_at is None:
                errors.append("external_write approval expires_at must be an ISO 8601 date-time with timezone")
            if approved_at is not None and expires_at is not None and expires_at <= approved_at:
                errors.append("external_write approval must expire after approval time")

    tool_trace = obj.get("tool_trace", [])
    if not isinstance(tool_trace, list):
        errors.append("tool_trace must be list")
        tool_trace = []
    for trace in tool_trace:
        if not isinstance(trace, dict):
            errors.append("tool trace item must be object")
            continue
        unexpected_trace_fields = set(trace) - TRACE_FIELDS
        if unexpected_trace_fields:
            errors.append(f"tool trace has unexpected fields: {sorted(unexpected_trace_fields)}")
        action = trace.get("action")
        if action not in ACTION_CLASSES:
            errors.append(f"tool trace action must be one of {sorted(ACTION_CLASSES)}")
            continue
        if expected_consent is not None and expected_consent.get(action) is not True:
            errors.append(f"tool trace action {action} is not consented by case_packet")
        if expected_allowed_tools is not None and action not in expected_allowed_tools:
            errors.append(f"tool trace action {action} is not allowed by case_packet tool_policy")
        if not nonempty_string(trace.get("status")):
            errors.append("tool trace status must be a non-empty string")
        tool = trace.get("tool")
        if tool is not None and not isinstance(tool, str):
            errors.append("tool trace tool must be string")
        if tool == "external_write" and action != "external_write":
            errors.append("external_write tool trace must use action external_write")
        if action != "external_write":
            continue
        for key in ("approval_id", "target", "body_hash", "scope_hash", "idempotency_key", "occurred_at"):
            if not nonempty_string(trace.get(key)):
                errors.append(f"external_write trace requires {key}")
        occurred_at = parse_datetime(trace.get("occurred_at"))
        if occurred_at is None:
            errors.append("external_write trace occurred_at must be an ISO 8601 date-time with timezone")
        matches = [
            approval
            for approval in external_approvals
            if approval.get("approval_id") == trace.get("approval_id")
            and approval.get("target") == trace.get("target")
            and approval.get("body_hash") == trace.get("body_hash")
            and approval.get("scope_hash") == trace.get("scope_hash")
            and approval.get("idempotency_key") == trace.get("idempotency_key")
        ]
        if len(matches) != 1:
            errors.append("external_write trace requires exactly one matching approval")
            continue
        expires_at = parse_datetime(matches[0].get("expires_at"))
        approved_at = parse_datetime(matches[0].get("approved_at"))
        if occurred_at is not None and (
            approved_at is None or expires_at is None or not approved_at <= occurred_at < expires_at
        ):
            errors.append("external_write trace occurred outside the approval validity window")

    memory_proposal = obj.get("memory_proposal")
    if memory_proposal is not None:
        if not isinstance(memory_proposal, dict):
            errors.append("memory_proposal must be an object or null")
        else:
            errors.extend(f"memory_proposal {error}" for error in validate_proposal(memory_proposal))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--expected-packet-hash")
    parser.add_argument("--expected-state-version", type=int)
    args = parser.parse_args()
    failures = 0
    for path in args.paths:
        try:
            obj = json.loads(path.read_text())
        except Exception as exc:  # pragma: no cover - CLI error path
            print(f"FAIL {path}: invalid JSON: {exc}")
            failures += 1
            continue
        errors = errors_for(
            obj,
            expected_packet_hash=args.expected_packet_hash,
            expected_state_version=args.expected_state_version,
        )
        if errors:
            print(f"FAIL {path}")
            for error in errors:
                print(f"  - {error}")
            failures += 1
        else:
            print(f"OK {path}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
