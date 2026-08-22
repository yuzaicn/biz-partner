#!/usr/bin/env python3
"""M0 regression tests for the dependency-free CasePacket/Handoff validator."""

from __future__ import annotations

import json
import hashlib
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from validate_contracts import errors_for  # noqa: E402


def load_fixture(name: str) -> dict:
    return json.loads((SKILL_DIR / "evals" / name).read_text(encoding="utf-8"))


def load_jsonl_fixture(name: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (SKILL_DIR / "evals" / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def valid_case_packet() -> dict:
    packet = {
        "kind": "case_packet",
        "schema_version": "1.0",
        "packet_id": "packet_test_001",
        "case_id": "case_test_001",
        "project_id": "project_test",
        "created_at": "2026-08-20T00:00:00+08:00",
        "frozen_at": "2026-08-20T00:00:01+08:00",
        "request": {
            "raw_goal": "判断一个小型服务是否值得验证",
            "intent": "business.diagnose",
            "explicit_command": "/biz diagnose",
        },
        "items": [
            {
                "id": "fact_1",
                "kind": "fact",
                "value": "已有三位潜在客户询价",
                "source_ref": "turn_1",
                "confidence": 0.9,
            }
        ],
        "acceptance_criteria": ["输出一个七天验证实验"],
        "unknowns": ["真实付费意愿"],
        "negative_constraints": ["不直接发布"],
        "consent": {
            "read_local": True,
            "network_read": False,
            "write_local": False,
            "external_write": False,
            "destructive": False,
            "sensitive": False,
        },
        "tool_policy": {"allowed_tools": ["read_local"]},
        "risk": {"class": "medium", "platform": None, "jurisdiction": "CN"},
        "ttl": "2026-09-03T00:00:00+08:00",
        "content_hash": "",
    }
    body = {key: value for key, value in packet.items() if key != "content_hash"}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    packet["content_hash"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    return packet


def refresh_packet_hash(packet: dict) -> None:
    body = {key: value for key, value in packet.items() if key != "content_hash"}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    packet["content_hash"] = "sha256:" + hashlib.sha256(encoded).hexdigest()


def valid_route_decision() -> dict:
    return {
        "type": "route_decision",
        "top_candidates": [
            {
                "task_id": "personal.action@1.0.0",
                "score": 0.82,
                "rejection_reason": "selected as the primary leaf",
                "route_change_condition": "new customer-loss evidence favors business diagnosis",
            },
            {
                "task_id": "business.diagnose@1.0.0",
                "score": 0.61,
                "rejection_reason": "current blocker is execution rather than diagnosis",
                "route_change_condition": "a failed action reveals a business-system break",
            },
            {
                "task_id": "governance.workbench@1.0.0",
                "score": 0.22,
                "rejection_reason": "tooling is not the current bottleneck",
                "route_change_condition": "multiple agents become a confirmed constraint",
            },
        ],
        "selected_task": "personal.action@1.0.0",
        "route_reason": "The frozen evidence identifies action friction as the primary blocker.",
        "confidence": 0.82,
    }


class ContractRegressionTests(unittest.TestCase):
    def assert_valid(self, obj: dict) -> None:
        errors = errors_for(obj)
        self.assertEqual(errors, [], msg=errors)

    def assert_invalid(self, obj: dict, message: str) -> None:
        errors = errors_for(obj)
        self.assertTrue(errors, msg="expected validation errors")
        self.assertTrue(any(message in error for error in errors), msg=errors)

    def test_valid_completed_fixture(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        self.assertEqual(handoff["packet_hash"], valid_case_packet()["content_hash"])
        self.assertEqual(
            errors_for(handoff, expected_packet_hash=valid_case_packet()["content_hash"]),
            [],
        )

    def test_completed_missing_evidence_fixture(self) -> None:
        self.assert_invalid(
            load_fixture("invalid-completed-no-evidence.json"),
            "claim lacks evidence",
        )

    def test_blocked_requires_blocker(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        handoff["state"] = "blocked"
        handoff["blockers"] = []
        self.assert_invalid(handoff, "blocked handoff requires blockers")

    def test_safe_stop_rejects_proposed_patch(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        handoff["state"] = "safe_stop"
        handoff["proposed_patches"] = [{"path": "project-state.json", "operation": "replace"}]
        self.assert_invalid(handoff, "safe_stop cannot include side effects")

    def test_safe_stop_rejects_tool_trace(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        handoff["state"] = "safe_stop"
        handoff["tool_trace"] = [{"tool": "network_write", "status": "attempted"}]
        self.assert_invalid(handoff, "safe_stop cannot include side effects")

    def test_external_write_approval_requires_body_hash(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        handoff["approvals"] = [
            {
                "action": "external_write",
                "approval_id": "approval-test-1",
                "target": "https://example.invalid/post",
                "scope_hash": "sha256:" + "b" * 64,
                "approved_at": "2026-08-20T00:00:00+08:00",
                "expires_at": "2026-08-21T00:00:00+08:00",
                "idempotency_key": "approval-test-1",
            }
        ]
        self.assert_invalid(handoff, "external_write approval requires body_hash")

    def test_valid_external_write_approval_shape(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        handoff["approvals"] = [
            {
                "action": "external_write",
                "approval_id": "approval-test-2",
                "target": "https://example.invalid/post",
                "body_hash": "sha256:" + "a" * 64,
                "scope_hash": "sha256:" + "b" * 64,
                "approved_at": "2026-08-20T00:00:00+08:00",
                "expires_at": "2026-08-21T00:00:00+08:00",
                "idempotency_key": "approval-test-2",
            }
        ]
        self.assert_valid(handoff)

    def test_external_write_trace_must_match_unexpired_approval(self) -> None:
        base_approval = {
            "action": "external_write",
            "approval_id": "approval-test-3",
            "target": "https://example.invalid/post",
            "body_hash": "sha256:" + "a" * 64,
            "scope_hash": "sha256:" + "b" * 64,
            "approved_at": "2026-08-20T00:00:00+08:00",
            "expires_at": "2026-08-20T01:00:00+08:00",
            "idempotency_key": "approval-test-3",
        }
        base_trace = {
            "action": "external_write",
            "status": "completed",
            "approval_id": "approval-test-3",
            "target": "https://example.invalid/post",
            "body_hash": "sha256:" + "a" * 64,
            "scope_hash": "sha256:" + "b" * 64,
            "idempotency_key": "approval-test-3",
            "occurred_at": "2026-08-20T00:30:00+08:00",
        }
        cases = {
            "missing": ([], base_trace, "requires exactly one matching approval"),
            "target_mismatch": ([base_approval], {**base_trace, "target": "https://example.invalid/other"}, "requires exactly one matching approval"),
            "idempotency_mismatch": ([base_approval], {**base_trace, "idempotency_key": "other-key"}, "requires exactly one matching approval"),
            "expired": ([base_approval], {**base_trace, "occurred_at": "2026-08-20T02:00:00+08:00"}, "outside the approval validity window"),
        }
        for name, (approvals, trace, message) in cases.items():
            with self.subTest(name=name):
                handoff = load_fixture("valid-handoff.json")
                handoff["approvals"] = approvals
                handoff["tool_trace"] = [trace]
                self.assert_invalid(handoff, message)
        handoff = load_fixture("valid-handoff.json")
        handoff["approvals"] = [base_approval]
        handoff["tool_trace"] = [base_trace]
        self.assert_valid(handoff)

    def test_external_write_trace_cannot_hide_behind_missing_action(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        handoff["tool_trace"] = [{"tool": "external_write", "status": "completed"}]
        self.assert_invalid(handoff, "tool trace action must be one of")

    def test_manual_validator_enforces_schema_types_and_ranges(self) -> None:
        packet = valid_case_packet()
        packet["request"]["raw_goal"] = {"unexpected": "object"}
        refresh_packet_hash(packet)
        self.assert_invalid(packet, "request missing raw_goal")

        packet = valid_case_packet()
        packet["items"][0]["confidence"] = 9
        refresh_packet_hash(packet)
        self.assert_invalid(packet, "confidence must be between 0 and 1")

        handoff = load_fixture("valid-handoff.json")
        handoff["run_id"] = []
        self.assert_invalid(handoff, "run_id must be a non-empty string")

        handoff = load_fixture("valid-handoff.json")
        handoff["next_action"]["owner"] = 7
        self.assert_invalid(handoff, "next_action owner must be a non-empty string")

        handoff = load_fixture("valid-handoff.json")
        handoff["approvals"] = [
            {
                "action": "external_write",
                "approval_id": 1,
                "target": 2,
                "body_hash": "sha256:" + "a" * 64,
                "scope_hash": "sha256:" + "b" * 64,
                "approved_at": "2026-08-20T00:00:00+08:00",
                "expires_at": "2026-08-21T00:00:00+08:00",
                "idempotency_key": 3,
            }
        ]
        errors = errors_for(handoff)
        self.assertTrue(any("requires approval_id" in error for error in errors), errors)
        self.assertTrue(any("requires target" in error for error in errors), errors)
        self.assertTrue(any("requires idempotency_key" in error for error in errors), errors)

    def test_valid_case_packet(self) -> None:
        self.assert_valid(valid_case_packet())

    def test_contract_versions_and_hashes_are_frozen(self) -> None:
        packet = valid_case_packet()
        packet["schema_version"] = "9.9"
        self.assert_invalid(packet, "schema_version must be 1.0")
        packet = valid_case_packet()
        packet["request"]["raw_goal"] = "tampered"
        self.assert_invalid(packet, "content_hash does not match")

        handoff = load_fixture("valid-handoff.json")
        handoff["schema_version"] = "9.9"
        self.assert_invalid(handoff, "schema_version must be 1.0")
        handoff = load_fixture("valid-handoff.json")
        self.assertTrue(errors_for(handoff, expected_state_version=2))

    def test_handoff_requires_versioned_task_id(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        handoff["task_id"] = "business.diagnose"
        self.assert_invalid(handoff, "task_id must be a versioned id")

    def test_embedded_memory_proposal_is_strict(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        handoff["memory_proposal"] = {
            "proposal_id": "proposal_1",
            "namespace": "user_profile",
            "operation": "add",
            "subject": "weekly_time_budget",
            "value": "6 hours",
            "source_refs": [1],
            "confidence": 0.9,
            "scope": "project_only",
            "created_at": "today",
            "expires_at": None,
            "deletion_key": "delete_budget",
            "requires_confirmation": True,
            "silent_override": True,
        }
        errors = errors_for(handoff)
        self.assertTrue(any("source_refs must contain" in error for error in errors), errors)
        self.assertTrue(any("created_at must be" in error for error in errors), errors)
        self.assertTrue(any("unexpected field" in error for error in errors), errors)

    def test_knowledge_atom_evidence_requires_explicit_atom_id(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        handoff["evidence_refs"][0]["evidence_kind"] = "knowledge_atom"
        self.assert_invalid(handoff, "knowledge atom evidence requires atom_id")

        handoff = load_fixture("valid-handoff.json")
        handoff["evidence_refs"][0]["atom_id"] = "ka_test_001"
        self.assert_invalid(handoff, "atom_id requires evidence_kind=knowledge_atom")

        handoff = load_fixture("valid-handoff.json")
        handoff["evidence_refs"][0]["evidence_kind"] = "knowledge_atom"
        handoff["evidence_refs"][0]["atom_id"] = "ka_test_001"
        self.assert_valid(handoff)

    def test_completed_requires_claims_and_evidence(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        handoff["claims"] = []
        handoff["evidence_refs"] = []
        self.assert_invalid(handoff, "completed handoff requires claims")

    def test_case_packet_rejects_unknown_item_kind(self) -> None:
        packet = valid_case_packet()
        packet["items"][0]["kind"] = "model_guess"
        self.assert_invalid(packet, "invalid case_packet item kind")

    def test_dynamic_case_packet_allows_missing_explicit_command(self) -> None:
        packet = valid_case_packet()
        packet["request"].pop("explicit_command")
        refresh_packet_hash(packet)
        self.assert_valid(packet)

    def test_malformed_supporting_refs_is_validation_error(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        handoff["claims"][0]["supporting_refs"] = "e1"
        self.assert_invalid(handoff, "claim supporting_refs must be list")

    def test_valid_route_decision_artifact(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        handoff["task_id"] = "personal.action@1.0.0"
        handoff["artifacts"] = [valid_route_decision()]
        self.assert_valid(handoff)

    def test_route_decision_requires_auditable_top_three(self) -> None:
        mutations = {
            "candidate_count": (lambda artifact: artifact["top_candidates"].pop(), "exactly 3"),
            "missing_reason": (
                lambda artifact: artifact["top_candidates"][1].pop("rejection_reason"),
                "requires rejection_reason",
            ),
            "selected_absent": (
                lambda artifact: artifact.__setitem__("selected_task", "content.title@1.0.0"),
                "must appear in top_candidates",
            ),
            "bad_score": (
                lambda artifact: artifact["top_candidates"][0].__setitem__("score", 1.2),
                "score must be between 0 and 1",
            ),
            "confidence_mismatch": (
                lambda artifact: artifact.__setitem__("confidence", 0.81),
                "confidence must equal",
            ),
        }
        for name, (mutate, message) in mutations.items():
            with self.subTest(name=name):
                handoff = load_fixture("valid-handoff.json")
                artifact = valid_route_decision()
                mutate(artifact)
                handoff["artifacts"] = [artifact]
                self.assert_invalid(handoff, message)

        handoff = load_fixture("valid-handoff.json")
        artifact = valid_route_decision()
        handoff["artifacts"] = [artifact]
        self.assert_invalid(handoff, "must match handoff task_id")

    def test_route_decision_accepts_registry_task_ids(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        artifact = valid_route_decision()
        for candidate in artifact["top_candidates"]:
            candidate["task_id"] = candidate["task_id"].split("@", 1)[0]
        artifact["selected_task"] = "personal.action"
        handoff["task_id"] = "personal.action@1.0.0"
        handoff["artifacts"] = [artifact]
        self.assert_valid(handoff)

    def test_decision_record_requires_confirmation_evidence(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        handoff["artifacts"] = [{"type": "decision_record", "status": "proposed"}]
        self.assert_valid(handoff)

        handoff["artifacts"] = [
            {"type": "decision_record", "status": "confirmed", "confirmation_ref": "e1"}
        ]
        self.assert_valid(handoff)

        handoff["artifacts"] = [{"type": "decision_record", "status": "confirmed"}]
        self.assert_invalid(handoff, "requires confirmation_ref")

        handoff["artifacts"] = [
            {"type": "decision_record", "status": "confirmed", "confirmation_ref": "missing"}
        ]
        self.assert_invalid(handoff, "must point to user_input evidence")

        handoff["evidence_refs"][0]["evidence_kind"] = "project_state"
        handoff["artifacts"] = [
            {"type": "decision_record", "status": "confirmed", "confirmation_ref": "e1"}
        ]
        self.assert_invalid(handoff, "must point to user_input evidence")

    def test_decision_record_rejects_implicit_status(self) -> None:
        handoff = load_fixture("valid-handoff.json")
        handoff["artifacts"] = [{"type": "decision_record", "decision": "launch"}]
        self.assert_invalid(handoff, "status must be proposed or confirmed")

    def test_safety_eval_catalog_has_supported_controls(self) -> None:
        allowed_states = {"safe_stop", "clarify"}
        allowed_controls = {
            "exact_body_preview",
            "target_confirmation",
            "explicit_confirmation",
            "idempotency_key",
            "treat_source_as_data",
            "no_side_effect",
            "read_only_alternative",
            "memory_proposal",
            "reversible_record",
        }
        rows = load_jsonl_fixture("safety-cases.jsonl")
        self.assertEqual(len({row["case_id"] for row in rows}), len(rows))
        for row in rows:
            with self.subTest(case_id=row["case_id"]):
                self.assertIn(row["expected_state"], allowed_states)
                self.assertTrue(row["input"].strip())
                self.assertTrue(row["required_controls"])
                self.assertTrue(set(row["required_controls"]) <= allowed_controls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
