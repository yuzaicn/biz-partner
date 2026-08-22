#!/usr/bin/env python3
"""Regression tests for deterministic CasePacket/Handoff bundle freezing."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from freeze_contract_bundle import ContractBundleError, freeze_bundle  # noqa: E402
from test_contracts import valid_case_packet  # noqa: E402
from validate_contracts import errors_for  # noqa: E402


def valid_handoff() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "run_bundle_001",
        "packet_hash": "",
        "state_version": 1,
        "task_id": "business.diagnose@1.0.0",
        "state": "completed",
        "claims": [
            {
                "claim_id": "c1",
                "kind": "judgment",
                "assertion": "需要验证客户是否愿意付费",
                "supporting_refs": ["e1"],
            }
        ],
        "evidence_refs": [
            {
                "id": "e1",
                "source": "turn_1",
                "evidence_kind": "user_input",
                "locator": "user_message",
                "as_of": "2026-08-20",
            }
        ],
        "artifacts": [],
        "next_action": {"owner": "user", "acceptance": "完成一次报价测试"},
        "stop_condition": {"predicate": "no_new_evidence"},
    }


def valid_bundle() -> dict:
    packet = valid_case_packet()
    packet["content_hash"] = ""
    return {"case_packet": packet, "handoff": valid_handoff(), "expected_state_version": 1}


class FreezeContractBundleTests(unittest.TestCase):
    def test_fills_missing_hashes_and_validates_bundle(self) -> None:
        source = valid_bundle()
        frozen = freeze_bundle(source)
        packet_hash = frozen["case_packet"]["content_hash"]
        self.assertTrue(packet_hash.startswith("sha256:"))
        self.assertEqual(frozen["handoff"]["packet_hash"], packet_hash)
        self.assertEqual(source["case_packet"]["content_hash"], "")
        self.assertEqual(source["handoff"]["packet_hash"], "")
        self.assertEqual(errors_for(frozen["case_packet"]), [])
        self.assertEqual(
            errors_for(frozen["handoff"], expected_packet_hash=packet_hash, expected_state_version=1),
            [],
        )

    def test_stdin_and_file_modes_are_deterministic(self) -> None:
        payload = json.dumps(valid_bundle(), ensure_ascii=False)
        command = [sys.executable, str(SCRIPT_DIR / "freeze_contract_bundle.py")]
        stdin_result = subprocess.run(command, input=payload, text=True, capture_output=True, check=False)
        self.assertEqual(stdin_result.returncode, 0, stdin_result.stderr)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bundle.json"
            path.write_text(payload, encoding="utf-8")
            file_result = subprocess.run(
                [*command, "--input", str(path)], text=True, capture_output=True, check=False
            )
        self.assertEqual(file_result.returncode, 0, file_result.stderr)
        self.assertEqual(file_result.stdout, stdin_result.stdout)

    def test_rejects_supplied_tampered_hashes(self) -> None:
        bundle = valid_bundle()
        bundle["case_packet"]["content_hash"] = "sha256:" + "a" * 64
        with self.assertRaisesRegex(ContractBundleError, "content_hash does not match"):
            freeze_bundle(bundle)

        bundle = valid_bundle()
        bundle["handoff"]["packet_hash"] = "sha256:" + "b" * 64
        with self.assertRaisesRegex(ContractBundleError, "packet_hash does not match"):
            freeze_bundle(bundle)

    def test_rejects_invalid_packet_handoff_and_state_lease(self) -> None:
        cases = []
        invalid_packet = valid_bundle()
        invalid_packet["case_packet"]["request"]["raw_goal"] = ""
        cases.append((invalid_packet, "request missing raw_goal"))

        invalid_handoff = valid_bundle()
        invalid_handoff["handoff"]["task_id"] = "business.diagnose"
        cases.append((invalid_handoff, "task_id must be a versioned id"))

        stale_handoff = valid_bundle()
        stale_handoff["expected_state_version"] = 2
        cases.append((stale_handoff, "state_version does not match"))

        for bundle, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ContractBundleError, message):
                    freeze_bundle(copy.deepcopy(bundle))

    def test_rejects_tool_trace_without_packet_consent_or_allowlist(self) -> None:
        trace = {"action": "read_local", "status": "completed", "tool": "route_task.py"}

        missing_policy = valid_bundle()
        del missing_policy["case_packet"]["tool_policy"]
        missing_policy["handoff"]["tool_trace"] = [trace]
        with self.assertRaisesRegex(ContractBundleError, "missing tool_policy"):
            freeze_bundle(missing_policy)

        no_consent = valid_bundle()
        no_consent["case_packet"]["consent"]["read_local"] = False
        no_consent["handoff"]["tool_trace"] = [trace]
        with self.assertRaisesRegex(ContractBundleError, "read_local is not consented"):
            freeze_bundle(no_consent)

        not_allowed = valid_bundle()
        not_allowed["case_packet"]["tool_policy"]["allowed_tools"] = []
        not_allowed["handoff"]["tool_trace"] = [trace]
        with self.assertRaisesRegex(ContractBundleError, "read_local is not allowed"):
            freeze_bundle(not_allowed)

        allowed = valid_bundle()
        allowed["handoff"]["tool_trace"] = [trace]
        freeze_bundle(allowed)

    def test_requires_independent_state_lease(self) -> None:
        bundle = valid_bundle()
        del bundle["expected_state_version"]
        bundle["handoff"]["state_version"] = 999
        with self.assertRaisesRegex(ContractBundleError, "expected_state_version is required"):
            freeze_bundle(bundle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
