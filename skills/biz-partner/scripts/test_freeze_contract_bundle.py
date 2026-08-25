#!/usr/bin/env python3
"""Regression tests for deterministic CasePacket/Handoff bundle freezing."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
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


VALIDATION_TIME = datetime.fromisoformat("2026-08-21T00:00:00+08:00")


class FreezeContractBundleTests(unittest.TestCase):
    def test_fills_missing_hashes_and_validates_bundle(self) -> None:
        source = valid_bundle()
        frozen = freeze_bundle(source, validation_time=VALIDATION_TIME)
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
        command = [
            sys.executable,
            str(SCRIPT_DIR / "freeze_contract_bundle.py"),
            "--validation-time",
            VALIDATION_TIME.isoformat(),
        ]
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
            freeze_bundle(bundle, validation_time=VALIDATION_TIME)

        bundle = valid_bundle()
        bundle["handoff"]["packet_hash"] = "sha256:" + "b" * 64
        with self.assertRaisesRegex(ContractBundleError, "packet_hash does not match"):
            freeze_bundle(bundle, validation_time=VALIDATION_TIME)

    def test_rejects_expired_packet_at_freeze_boundary(self) -> None:
        with self.assertRaisesRegex(ContractBundleError, "ttl has expired"):
            freeze_bundle(
                valid_bundle(),
                validation_time=datetime.fromisoformat("2026-09-03T00:00:00+08:00"),
            )

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
                    freeze_bundle(copy.deepcopy(bundle), validation_time=VALIDATION_TIME)

    def test_rejects_tool_trace_without_packet_consent_or_allowlist(self) -> None:
        trace = {"action": "read_local", "status": "completed", "tool": "route_task.py"}

        missing_policy = valid_bundle()
        del missing_policy["case_packet"]["tool_policy"]
        missing_policy["handoff"]["tool_trace"] = [trace]
        with self.assertRaisesRegex(ContractBundleError, "missing tool_policy"):
            freeze_bundle(missing_policy, validation_time=VALIDATION_TIME)

        no_consent = valid_bundle()
        no_consent["case_packet"]["consent"]["read_local"] = False
        no_consent["handoff"]["tool_trace"] = [trace]
        with self.assertRaisesRegex(ContractBundleError, "read_local is not consented"):
            freeze_bundle(no_consent, validation_time=VALIDATION_TIME)

        not_allowed = valid_bundle()
        not_allowed["case_packet"]["tool_policy"]["allowed_tools"] = []
        not_allowed["handoff"]["tool_trace"] = [trace]
        with self.assertRaisesRegex(ContractBundleError, "read_local is not allowed"):
            freeze_bundle(not_allowed, validation_time=VALIDATION_TIME)

        allowed = valid_bundle()
        allowed["handoff"]["tool_trace"] = [trace]
        freeze_bundle(allowed, validation_time=VALIDATION_TIME)

    def test_rejects_side_effect_trace_outside_case_packet_window(self) -> None:
        bundle = valid_bundle()
        bundle["case_packet"]["consent"]["write_local"] = True
        bundle["case_packet"]["tool_policy"]["allowed_tools"].append("write_local")
        bundle["handoff"]["approvals"] = [
            {
                "action": "write_local",
                "approval_id": "approval-window-1",
                "authorization_ref": "e1",
                "target": "project-state.json",
                "scope_hash": "sha256:" + "c" * 64,
                "approved_at": "2026-08-20T00:00:00+08:00",
                "expires_at": "2099-01-01T00:00:00+08:00",
                "rollback_ref": "rollback:before-write",
            }
        ]
        bundle["handoff"]["tool_trace"] = [
            {
                "action": "write_local",
                "status": "completed",
                "approval_id": "approval-window-1",
                "authorization_ref": "e1",
                "target": "project-state.json",
                "scope_hash": "sha256:" + "c" * 64,
                "occurred_at": "2026-09-03T00:00:00+08:00",
                "rollback_ref": "rollback:before-write",
            }
        ]
        with self.assertRaisesRegex(ContractBundleError, "outside the CasePacket execution window"):
            freeze_bundle(bundle, validation_time=VALIDATION_TIME)

    def test_requires_independent_state_lease(self) -> None:
        bundle = valid_bundle()
        del bundle["expected_state_version"]
        bundle["handoff"]["state_version"] = 999
        with self.assertRaisesRegex(ContractBundleError, "expected_state_version is required"):
            freeze_bundle(bundle, validation_time=VALIDATION_TIME)


if __name__ == "__main__":
    unittest.main(verbosity=2)
