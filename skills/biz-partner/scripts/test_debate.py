#!/usr/bin/env python3
"""Regression tests for the auditable debate event validator."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from validate_debate import load_events, main, phase_counts, validate_events  # noqa: E402


FIXTURE = SKILL_DIR / "evals" / "debate-events-valid.jsonl"


def valid_events() -> list[dict]:
    events, errors = load_events(FIXTURE)
    if errors:
        raise AssertionError(errors)
    return events


def event_of(events: list[dict], event_type: str, worker_id: str | None = None) -> dict:
    for event in events:
        if event.get("event_type") == event_type and (worker_id is None or event.get("worker_id") == worker_id):
            return event
    raise AssertionError(f"missing {event_type} {worker_id}")


def canonical_hash(value: dict, excluded_field: str | None = None) -> str:
    canonical = copy.deepcopy(value)
    if excluded_field:
        canonical.pop(excluded_field, None)
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def as_real_workers(events: list[dict]) -> None:
    started = event_of(events, "DebateStarted")
    started["payload"]["execution_mode"] = "real_workers"
    receipts = []
    for index, worker_id in enumerate(started["payload"]["roles"], 1):
        receipt_id = f"host_receipt_{index:03d}"
        run_id = f"host_run_{index:03d}"
        event_of(events, "WorkerStarted", worker_id)["payload"]["host_receipt_id"] = receipt_id
        completed = event_of(events, "WorkerCompleted", worker_id)
        completed["payload"]["host_receipt_id"] = receipt_id
        completed["payload"]["host_run_id"] = run_id
        refresh_worker_hash(completed)
        receipts.append(
            {
                "worker_id": worker_id,
                "receipt_id": receipt_id,
                "run_id": run_id,
                "output_hash": completed["payload"]["output_hash"],
            }
        )
    started["payload"]["host_receipts"] = receipts


def refresh_worker_hash(event: dict) -> None:
    event["payload"]["output_hash"] = canonical_hash(event["payload"], "output_hash")


def append_confirmed_memory_commit(events: list[dict]) -> dict:
    decision = event_of(events, "UserDecision")
    decision["payload"]["memory_commit_confirmed"] = True
    proposal = {"proposal_id": "proposal_001", "subject": "controlled_trial", "value": "accepted"}
    proposal_hash = canonical_hash(proposal)
    confirmation_hash = canonical_hash(decision)
    state_ref = {
        "event_id": "state_evt_001",
        "state_version": 7,
        "proposal_hash": proposal_hash,
        "confirmation_hash": confirmation_hash,
    }
    state_ref["content_hash"] = canonical_hash(state_ref, "content_hash")
    memory = {
        "schema_version": "1.0",
        "event_id": "evt_015",
        "debate_id": "debate_001",
        "case_id": "case_debate_001",
        "sequence": 15,
        "timestamp": "2026-08-20T10:00:32+08:00",
        "event_type": "MemoryCommit",
        "packet_hash": event_of(events, "PacketFrozen")["packet_hash"],
        "payload": {
            "proposal": proposal,
            "proposal_hash": proposal_hash,
            "confirmation_event_id": decision["event_id"],
            "confirmation_hash": confirmation_hash,
            "state_version": 7,
            "state_event_ref": state_ref,
        },
    }
    events.append(memory)
    return memory


class DebateValidatorTests(unittest.TestCase):
    def assert_invalid(self, events: list[dict], message: str) -> None:
        errors = validate_events(events)
        self.assertTrue(any(message in error for error in errors), msg=errors)

    def test_complete_four_stage_fixture(self) -> None:
        events = valid_events()
        self.assertEqual(validate_events(events), [])
        self.assertEqual(
            phase_counts(events),
            {"worker_outputs": 3, "cross_exam": 3, "synthesis": 1, "user_decision": 1},
        )

    def test_debate_started_requires_execution_mode(self) -> None:
        events = copy.deepcopy(valid_events())
        del event_of(events, "DebateStarted")["payload"]["execution_mode"]
        self.assert_invalid(events, "execution_mode")

    def test_real_workers_require_host_receipts_bound_to_every_worker(self) -> None:
        events = copy.deepcopy(valid_events())
        event_of(events, "DebateStarted")["payload"]["execution_mode"] = "real_workers"
        self.assert_invalid(events, "host_receipts")

    def test_real_worker_receipt_binding_is_validated(self) -> None:
        events = copy.deepcopy(valid_events())
        as_real_workers(events)
        self.assertEqual(validate_events(events), [])
        event_of(events, "WorkerStarted", "user_product")["payload"]["host_receipt_id"] = "wrong_receipt"
        self.assert_invalid(events, "host receipt")

    def test_real_worker_receipt_output_hash_binding_is_validated(self) -> None:
        events = copy.deepcopy(valid_events())
        as_real_workers(events)
        receipt = next(
            item
            for item in event_of(events, "DebateStarted")["payload"]["host_receipts"]
            if item["worker_id"] == "user_product"
        )
        receipt["output_hash"] = "sha256:" + "0" * 64
        self.assert_invalid(events, "output hash does not match host receipt binding")

    def test_real_worker_host_run_binding_is_validated(self) -> None:
        events = copy.deepcopy(valid_events())
        as_real_workers(events)
        completed = event_of(events, "WorkerCompleted", "user_product")
        completed["payload"]["host_run_id"] = "wrong_run"
        refresh_worker_hash(completed)
        receipt = next(
            item
            for item in event_of(events, "DebateStarted")["payload"]["host_receipts"]
            if item["worker_id"] == "user_product"
        )
        receipt["output_hash"] = completed["payload"]["output_hash"]
        self.assert_invalid(events, "host run does not match DebateStarted binding")

    def test_fixture_mode_does_not_claim_independent_workers_in_cli(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([str(FIXTURE)]), 0)
        self.assertIn("claimed_mode=contract_fixture", output.getvalue())
        self.assertIn("worker_outputs=3", output.getvalue())
        self.assertNotIn("independent=", output.getvalue())

    def test_real_workers_cli_discloses_internal_only_receipt_binding(self) -> None:
        events = copy.deepcopy(valid_events())
        as_real_workers(events)
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", encoding="utf-8") as fixture:
            for event in events:
                fixture.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            fixture.flush()
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main([fixture.name]), 0)
        rendered = output.getvalue()
        self.assertIn("claimed_mode=real_workers receipt_binding=internal_only", rendered)
        self.assertNotIn("verified", rendered.lower())
        self.assertNotIn("proven", rendered.lower())

    def test_round_one_workers_cannot_see_peer_outputs(self) -> None:
        events = copy.deepcopy(valid_events())
        worker = event_of(events, "WorkerStarted", "user_product")
        worker["payload"]["visible_worker_outputs"] = ["sha256:round1-business"]
        self.assert_invalid(events, "violates independent round")

    def test_round_one_claim_requires_packet_evidence(self) -> None:
        events = copy.deepcopy(valid_events())
        worker = event_of(events, "WorkerCompleted", "business_economics")
        worker["payload"]["evidence_refs"][0]["packet_item_id"] = "missing_fact"
        self.assert_invalid(events, "does not resolve to CasePacket")

    def test_packet_hash_detects_content_tampering(self) -> None:
        events = copy.deepcopy(valid_events())
        packet = event_of(events, "PacketFrozen")["payload"]["packet"]
        packet["unknowns"].append("被篡改的新未知项")
        self.assert_invalid(events, "does not match canonical packet content")

    def test_expired_packet_is_rejected_at_validation_time(self) -> None:
        events = copy.deepcopy(valid_events())
        errors = validate_events(events, datetime.fromisoformat("2100-01-01T00:00:00+00:00"))
        self.assertTrue(any("ttl has expired" in error for error in errors), msg=errors)

    def test_event_at_packet_ttl_is_rejected(self) -> None:
        events = copy.deepcopy(valid_events())
        event_of(events, "UserDecision")["timestamp"] = "2099-09-03T10:00:00+08:00"
        errors = validate_events(events, datetime.fromisoformat("2026-08-24T00:00:00+00:00"))
        self.assertTrue(any("[frozen_at, ttl)" in error for error in errors), msg=errors)

    def test_worker_hash_detects_content_tampering(self) -> None:
        events = copy.deepcopy(valid_events())
        worker = event_of(events, "WorkerCompleted", "business_economics")
        worker["payload"]["position"] = "tampered_position"
        self.assert_invalid(events, "output_hash does not match canonical payload")

    def test_cross_exam_input_must_be_deidentified(self) -> None:
        events = copy.deepcopy(valid_events())
        cross = event_of(events, "CrossExamStarted")
        cross["payload"]["deidentified_summaries"][0]["worker_id"] = "business_economics"
        self.assert_invalid(events, "leaks worker identity")

    def test_cross_exam_requires_all_four_challenges(self) -> None:
        events = copy.deepcopy(valid_events())
        cross = event_of(events, "CrossExamCompleted", "contrarian_risk")
        del cross["payload"]["lower_cost_test"]
        self.assert_invalid(events, "requires lower_cost_test")

    def test_synthesis_rejects_majority_vote(self) -> None:
        events = copy.deepcopy(valid_events())
        synthesis = event_of(events, "Synthesis")
        synthesis["payload"]["decision_method"] = "majority_vote"
        synthesis["payload"]["majority_vote_used"] = True
        self.assert_invalid(events, "cannot use majority vote")

    def test_synthesis_requires_all_worker_sources(self) -> None:
        events = copy.deepcopy(valid_events())
        synthesis = event_of(events, "Synthesis")
        synthesis["payload"]["source_event_ids"].remove("evt_008")
        self.assert_invalid(events, "must exactly match completed worker")

    def test_synthesis_judgment_requires_packet_evidence(self) -> None:
        events = copy.deepcopy(valid_events())
        synthesis = event_of(events, "Synthesis")
        synthesis["payload"]["current_judgment"]["supporting_refs"] = ["invented_fact"]
        self.assert_invalid(events, "current_judgment must resolve to CasePacket evidence")

    def test_simple_decision_allows_one_action_without_alternatives(self) -> None:
        events = copy.deepcopy(valid_events())
        event_of(events, "CrossExamStarted")["payload"]["conflicting_claims"] = []
        synthesis = event_of(events, "Synthesis")["payload"]
        synthesis["disagreements"] = []
        synthesis["alternatives"] = []
        synthesis["actions"] = [synthesis["actions"][0]]
        self.assertEqual(validate_events(events), [])

    def test_real_disagreement_still_requires_two_alternatives(self) -> None:
        events = copy.deepcopy(valid_events())
        event_of(events, "Synthesis")["payload"]["alternatives"] = []
        self.assert_invalid(events, "real disagreement requires at least two reasonable alternatives")

    def test_synthesis_still_requires_at_least_one_action(self) -> None:
        events = copy.deepcopy(valid_events())
        event_of(events, "Synthesis")["payload"]["actions"] = []
        self.assert_invalid(events, "at least one action")

    def test_malformed_allowlist_returns_error_instead_of_crashing(self) -> None:
        events = copy.deepcopy(valid_events())
        worker = event_of(events, "WorkerStarted", "business_economics")
        worker["payload"]["knowledge_allowlist"] = [{"atom_id": "demo_reasoning_001"}]
        self.assert_invalid(events, "knowledge_allowlist must be a string list")

    def test_malformed_payload_returns_error_instead_of_crashing(self) -> None:
        events = copy.deepcopy(valid_events())
        event_of(events, "Synthesis")["payload"] = []
        self.assert_invalid(events, "payload must be object")

    def test_token_budget_is_enforced(self) -> None:
        events = copy.deepcopy(valid_events())
        event_of(events, "Synthesis")["payload"]["usage_tokens"] = 20000
        self.assert_invalid(events, "token budget exceeded")

    def test_user_decision_must_follow_synthesis(self) -> None:
        events = copy.deepcopy(valid_events())
        synthesis_index = next(index for index, event in enumerate(events) if event["event_type"] == "Synthesis")
        decision_index = next(index for index, event in enumerate(events) if event["event_type"] == "UserDecision")
        events[synthesis_index], events[decision_index] = events[decision_index], events[synthesis_index]
        events[synthesis_index]["sequence"] = synthesis_index + 1
        events[decision_index]["sequence"] = decision_index + 1
        self.assert_invalid(events, "UserDecision must follow Synthesis")

    def test_memory_commit_requires_confirmation(self) -> None:
        events = copy.deepcopy(valid_events())
        events.append(
            {
                "schema_version": "1.0",
                "event_id": "evt_015",
                "debate_id": "debate_001",
                "case_id": "case_debate_001",
                "sequence": 15,
                "timestamp": "2026-08-20T10:00:32+08:00",
                "event_type": "MemoryCommit",
                "packet_hash": event_of(events, "PacketFrozen")["packet_hash"],
                "payload": {"proposal_id": "proposal_001"},
            }
        )
        self.assert_invalid(events, "requires explicit UserDecision confirmation")

    def test_confirmed_memory_commit_requires_bound_proposal_confirmation_and_state(self) -> None:
        events = copy.deepcopy(valid_events())
        memory = append_confirmed_memory_commit(events)
        self.assertEqual(validate_events(events), [])
        del memory["payload"]["state_event_ref"]
        self.assert_invalid(events, "state_event_ref")

    def test_memory_commit_detects_confirmation_and_state_binding_tampering(self) -> None:
        events = copy.deepcopy(valid_events())
        memory = append_confirmed_memory_commit(events)
        memory["payload"]["confirmation_hash"] = "sha256:" + "0" * 64
        self.assert_invalid(events, "confirmation_hash")

        events = copy.deepcopy(valid_events())
        memory = append_confirmed_memory_commit(events)
        memory["payload"]["state_event_ref"]["state_version"] = 8
        self.assert_invalid(events, "state_version")

    def test_missing_risk_worker_fails_role_completeness(self) -> None:
        events = [
            event for event in copy.deepcopy(valid_events())
            if not (
                event.get("worker_id") == "contrarian_risk"
                and event.get("event_type") in {"WorkerStarted", "WorkerCompleted", "CrossExamCompleted"}
            )
        ]
        for sequence, event in enumerate(events, 1):
            event["sequence"] = sequence
        self.assert_invalid(events, "roles must match DebateStarted roles")

    def test_cli_exit_codes_are_ci_usable(self) -> None:
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(FIXTURE)]), 0)
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", encoding="utf-8") as invalid:
            invalid.write("{}\n")
            invalid.flush()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([invalid.name]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
