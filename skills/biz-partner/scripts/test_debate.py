#!/usr/bin/env python3
"""Regression tests for the auditable debate event validator."""

from __future__ import annotations

import copy
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
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


class DebateValidatorTests(unittest.TestCase):
    def assert_invalid(self, events: list[dict], message: str) -> None:
        errors = validate_events(events)
        self.assertTrue(any(message in error for error in errors), msg=errors)

    def test_complete_four_stage_fixture(self) -> None:
        events = valid_events()
        self.assertEqual(validate_events(events), [])
        self.assertEqual(
            phase_counts(events),
            {"independent": 3, "cross_exam": 3, "synthesis": 1, "user_decision": 1},
        )

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
                "packet_hash": "sha256:ea8f62224fd0a7b3e69393d8c9195452d39f29720db24d975faff9d14d3a1d15",
                "payload": {"proposal_id": "proposal_001"},
            }
        )
        self.assert_invalid(events, "requires explicit UserDecision confirmation")

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
