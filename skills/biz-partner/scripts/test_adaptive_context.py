#!/usr/bin/env python3
"""Longitudinal tests for confirmed adaptive runtime context."""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import adaptive_context  # noqa: E402
import state_store  # noqa: E402


def args(**values: object) -> argparse.Namespace:
    return argparse.Namespace(**values)


class AdaptiveContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        action = state_store.init_action(self.root)
        state_store.cmd_init(
            args(root=str(self.root), confirmation_hash=state_store.digest(action))
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def proposal(
        self,
        *,
        namespace: str,
        subject: str,
        value: object,
        operation: str = "add",
        expires_at: str | None = None,
    ) -> dict:
        return {
            "proposal_id": f"proposal_{namespace}_{subject}_{operation}",
            "namespace": namespace,
            "operation": operation,
            "subject": subject,
            "value": value,
            "source_refs": ["turn_1"],
            "confidence": 0.9,
            "scope": "project_only",
            "created_at": "2026-08-20T00:00:00+00:00",
            "expires_at": expires_at,
            "deletion_key": f"delete_{namespace}_{subject}",
            "requires_confirmation": True,
            "user_confirmation": None,
        }

    def write_proposal(self, proposal: dict) -> Path:
        path = self.root / f"{proposal['proposal_id']}.json"
        path.write_text(json.dumps(proposal, ensure_ascii=False), encoding="utf-8")
        return path

    def commit(self, proposal: dict, version: int) -> None:
        path = self.write_proposal(proposal)
        action = state_store.commit_action(self.root, state_store.digest(proposal), version)
        rc = state_store.cmd_commit(
            args(
                root=str(self.root),
                proposal=str(path),
                expected_version=version,
                confirmation_hash=state_store.digest(action),
                confirmed_at="2026-08-20T00:01:00+00:00",
            )
        )
        self.assertEqual(rc, 0)

    def context(self, as_of: str) -> dict:
        return adaptive_context.build_adaptive_context(
            state_store.load_state(self.root),
            as_of=as_of,
        )

    def test_confirmed_state_changes_the_next_runtime_context(self) -> None:
        before = self.context("2026-08-20T00:30:00+00:00")
        self.assertEqual(before["preferences"]["style"], {})
        self.assertEqual(before["playbook_feedback"], [])

        self.commit(
            self.proposal(
                namespace="user_profile",
                subject="preferred_style",
                value="concise with explicit tradeoffs",
            ),
            1,
        )
        self.commit(
            self.proposal(
                namespace="playbook_feedback",
                subject="weekly_review",
                value={"useful": True, "reason": "keeps experiments moving"},
            ),
            2,
        )

        after = self.context("2026-08-20T00:30:00+00:00")
        self.assertEqual(
            after["preferences"]["style"]["preferred_style"],
            "concise with explicit tradeoffs",
        )
        self.assertEqual(after["playbook_feedback"][0]["subject"], "weekly_review")
        self.assertTrue(after["advisory_only"])
        self.assertFalse(after["authority_limits"]["may_decide_final_route"])

    def test_unconfirmed_proposal_never_enters_runtime_context(self) -> None:
        proposal = self.proposal(
            namespace="user_profile",
            subject="preferred_cadence",
            value="daily",
        )
        path = self.write_proposal(proposal)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                state_store.cmd_plan_commit(args(root=str(self.root), proposal=str(path))),
                0,
            )
        self.assertIn("confirmation_hash", output.getvalue())
        self.assertEqual(
            self.context("2026-08-20T00:30:00+00:00")["preferences"]["cadence"],
            {},
        )
        self.assertEqual(state_store.load_state(self.root)["state_version"], 1)

    def test_expiry_and_suppression_remove_later_runtime_influence(self) -> None:
        self.commit(
            self.proposal(
                namespace="user_profile",
                subject="weekly_time_budget",
                value="6 hours",
                expires_at="2026-08-20T01:00:00+00:00",
            ),
            1,
        )
        before_expiry = self.context("2026-08-20T00:59:59+00:00")
        self.assertEqual(before_expiry["profile_constraints"]["weekly_time_budget"], "6 hours")
        after_expiry = self.context("2026-08-20T01:00:00+00:00")
        self.assertNotIn("weekly_time_budget", after_expiry["profile_constraints"])

        self.commit(
            self.proposal(
                namespace="playbook_feedback",
                subject="fast_validation",
                value={"useful": False},
            ),
            2,
        )
        self.assertEqual(
            self.context("2026-08-20T00:30:00+00:00")["playbook_feedback"][0]["subject"],
            "fast_validation",
        )
        self.commit(
            self.proposal(
                namespace="playbook_feedback",
                subject="fast_validation",
                value=None,
                operation="suppress",
            ),
            3,
        )
        after_delete = self.context("2026-08-20T00:30:00+00:00")
        self.assertEqual(after_delete["playbook_feedback"], [])
        self.assertNotIn("useful", json.dumps(after_delete))


if __name__ == "__main__":
    unittest.main(verbosity=2)
