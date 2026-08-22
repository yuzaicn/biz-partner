#!/usr/bin/env python3
"""Regression tests for the consent-gated local state store."""

from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from contextlib import redirect_stdout
from unittest import mock
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import state_store  # noqa: E402


def args(**values: object) -> argparse.Namespace:
    return argparse.Namespace(**values)


class StateStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        action = state_store.init_action(self.root)
        rc = state_store.cmd_init(args(root=str(self.root), confirmation_hash=state_store.digest(action)))
        self.assertEqual(rc, 0)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def proposal(
        self,
        operation: str = "add",
        *,
        namespace: str = "user_profile",
        subject: str = "weekly_time_budget",
        value: object = "6 hours",
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

    def write_proposal(self, value: dict) -> Path:
        path = self.root / "proposal.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def commit(self, proposal: dict, expected_version: int) -> int:
        path = self.write_proposal(proposal)
        proposal_hash = state_store.digest(proposal)
        action = state_store.commit_action(self.root, proposal_hash, expected_version)
        return state_store.cmd_commit(
            args(
                root=str(self.root),
                proposal=str(path),
                expected_version=expected_version,
                confirmation_hash=state_store.digest(action),
                confirmed_at="2026-08-20T00:01:00+00:00",
            )
        )

    def test_init_creates_state_and_event(self) -> None:
        paths = state_store.paths_for(self.root)
        self.assertTrue(paths["database"].is_file())
        self.assertEqual(state_store.load_state(self.root)["state_version"], 1)
        self.assertEqual(len(state_store.load_events(self.root)), 1)
        self.assertEqual(state_store.replay_state(self.root), state_store.load_state(self.root))

    def test_init_rejects_wrong_confirmation_hash(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaises(state_store.StateError):
                state_store.cmd_init(args(root=other, confirmation_hash="sha256:wrong"))

    def test_valid_proposal_commits_and_increments_version(self) -> None:
        self.assertEqual(self.commit(self.proposal(), 1), 0)
        state = state_store.load_state(self.root)
        self.assertEqual(state["state_version"], 2)
        self.assertEqual(state["user_profile"]["weekly_time_budget"]["value"], "6 hours")

    def test_stale_version_is_rejected(self) -> None:
        self.assertEqual(self.commit(self.proposal(), 1), 0)
        with self.assertRaises(state_store.StateError):
            self.commit(self.proposal(), 1)

    def test_wrong_commit_confirmation_is_rejected(self) -> None:
        proposal = self.proposal()
        path = self.write_proposal(proposal)
        with self.assertRaises(state_store.StateError):
            state_store.cmd_commit(
                args(
                    root=str(self.root),
                    proposal=str(path),
                    expected_version=1,
                    confirmation_hash="sha256:wrong",
                    confirmed_at="2026-08-20T00:01:00+00:00",
                )
            )

    def test_suppress_removes_profile_and_records_deletion_key(self) -> None:
        self.assertEqual(self.commit(self.proposal(), 1), 0)
        suppress = self.proposal("suppress")
        self.assertEqual(self.commit(suppress, 2), 0)
        state = state_store.load_state(self.root)
        self.assertNotIn("weekly_time_budget", state["user_profile"])
        self.assertEqual(
            state["suppressions"][-1]["deletion_key"],
            "delete_user_profile_weekly_time_budget",
        )

    def test_suppress_hides_records_in_every_namespace(self) -> None:
        version = 1
        for namespace in sorted(state_store.NAMESPACES):
            subject = f"subject_{namespace}"
            self.assertEqual(
                self.commit(
                    self.proposal(namespace=namespace, subject=subject, value={"active": True}),
                    version,
                ),
                0,
            )
            version += 1
            self.assertEqual(
                self.commit(
                    self.proposal("suppress", namespace=namespace, subject=subject, value=None),
                    version,
                ),
                0,
            )
            version += 1

        raw = state_store.load_state(self.root)
        visible = state_store.visible_state(raw, as_of="2026-08-20T02:00:00+00:00")
        for namespace in state_store.NAMESPACES:
            self.assertNotIn(f"subject_{namespace}", json.dumps(visible[namespace]))
        self.assertEqual(len(visible["suppressions"]), len(state_store.NAMESPACES))
        self.assertNotIn("active", json.dumps(visible["suppressions"]))

    def test_visible_state_excludes_expired_records_in_every_namespace(self) -> None:
        state = state_store.initial_state(self.root)
        for namespace in state_store.NAMESPACES:
            record = {
                "subject": f"expired_{namespace}",
                "value": "must not appear",
                "source_refs": ["turn_1"],
                "confidence": 1,
                "scope": "project_only",
                "proposal_id": f"proposal_{namespace}",
                "created_at": "2026-08-20T00:00:00+00:00",
                "expires_at": "2026-08-20T01:00:00+00:00",
                "deletion_key": f"delete_{namespace}",
            }
            if namespace in {"user_profile", "project_state"}:
                state[namespace][record["subject"]] = record
            else:
                state[namespace].append(record)

        visible = state_store.visible_state(state, as_of="2026-08-20T01:00:00+00:00")
        for namespace in state_store.NAMESPACES:
            self.assertNotIn("must not appear", json.dumps(visible[namespace]))

    def test_show_and_export_default_to_visible_state(self) -> None:
        expired = self.proposal(expires_at="2026-08-20T01:00:00+00:00")
        self.assertEqual(self.commit(expired, 1), 0)
        for command in (state_store.cmd_show, state_store.cmd_export):
            with self.subTest(command=command.__name__):
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(
                        command(
                            args(
                                root=str(self.root),
                                as_of="2026-08-20T01:00:00+00:00",
                            )
                        ),
                        0,
                    )
                self.assertNotIn("6 hours", output.getvalue())

    def test_proposal_requires_evidence_and_confirmation(self) -> None:
        proposal = self.proposal()
        proposal["source_refs"] = []
        proposal["requires_confirmation"] = False
        errors = state_store.validate_proposal(proposal)
        self.assertIn("source_refs must be a non-empty list", errors)
        self.assertIn("requires_confirmation must be true", errors)

    def test_proposal_rejects_schema_drift(self) -> None:
        cases = {
            "non_string_source": ("source_refs", [1], "source_refs must contain non-empty strings"),
            "invalid_date": ("created_at", "today", "created_at must be an ISO 8601"),
            "extra_field": ("silent_override", True, "unexpected field: silent_override"),
        }
        for _, (field, value, message) in cases.items():
            with self.subTest(field=field):
                proposal = self.proposal()
                proposal[field] = value
                self.assertTrue(any(message in error for error in state_store.validate_proposal(proposal)))

    def test_transaction_rolls_back_state_and_event_together(self) -> None:
        before_state = state_store.load_state(self.root)
        before_events = state_store.load_events(self.root)
        with mock.patch.object(state_store, "insert_event", side_effect=OSError("injected event failure")):
            with self.assertRaises(state_store.StateError):
                self.commit(self.proposal(), 1)
        self.assertEqual(state_store.load_state(self.root), before_state)
        self.assertEqual(state_store.load_events(self.root), before_events)
        self.assertEqual(state_store.replay_state(self.root), before_state)

    def test_tampered_materialized_state_hash_is_rejected(self) -> None:
        database = state_store.paths_for(self.root)["database"]
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                "UPDATE project_state SET state_hash = ? WHERE singleton = 1",
                ("sha256:" + "0" * 64,),
            )
        with self.assertRaisesRegex(state_store.StateError, "state hash mismatch"):
            state_store.load_state(self.root)
        with self.assertRaisesRegex(state_store.StateError, "state hash mismatch"):
            self.commit(self.proposal(), 1)

    def test_missing_event_blocks_reads_and_future_commits(self) -> None:
        self.assertEqual(self.commit(self.proposal(), 1), 0)
        database = state_store.paths_for(self.root)["database"]
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("DELETE FROM events WHERE state_version = 2")
        with self.assertRaisesRegex(state_store.StateError, "does not match event replay"):
            state_store.load_state(self.root)
        with self.assertRaisesRegex(state_store.StateError, "does not match event replay"):
            self.commit(self.proposal("supersede"), 2)

    def test_rehashed_materialized_tampering_is_rejected_by_replay(self) -> None:
        database = state_store.paths_for(self.root)["database"]
        state = state_store.load_state(self.root)
        state["project_state"]["tampered"] = True
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                "UPDATE project_state SET state_json = ?, state_hash = ? WHERE singleton = 1",
                (
                    state_store.canonical_bytes(state).decode("utf-8"),
                    state_store.digest(state),
                ),
            )
        with self.assertRaisesRegex(state_store.StateError, "does not match event replay"):
            state_store.load_state(self.root)

    def test_load_state_uses_one_snapshot_during_concurrent_commit(self) -> None:
        database = state_store.paths_for(self.root)["database"]
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL")

        original_connect_store = state_store.connect_store
        connection_count = 0

        class CursorWithHook:
            def __init__(self, cursor: sqlite3.Cursor, hook: object) -> None:
                self.cursor = cursor
                self.hook = hook

            def fetchone(self) -> sqlite3.Row | None:
                row = self.cursor.fetchone()
                self.cursor.close()
                self.hook()
                return row

        class ConnectionWithHook:
            def __init__(self, connection: sqlite3.Connection, hook: object) -> None:
                self.connection = connection
                self.hook = hook
                self.hooked = False

            def __enter__(self) -> "ConnectionWithHook":
                self.connection.__enter__()
                return self

            def __exit__(self, *exc_info: object) -> object:
                return self.connection.__exit__(*exc_info)

            def close(self) -> None:
                self.connection.close()

            def execute(self, statement: str, *parameters: object) -> sqlite3.Cursor | CursorWithHook:
                cursor = self.connection.execute(statement, *parameters)
                if not self.hooked and statement.startswith("SELECT state_version"):
                    self.hooked = True
                    return CursorWithHook(cursor, self.hook)
                return cursor

        def connect_with_interleaving(root: Path) -> sqlite3.Connection | ConnectionWithHook:
            nonlocal connection_count
            connection_count += 1
            connection = original_connect_store(root)
            if connection_count == 1:
                return ConnectionWithHook(
                    connection,
                    lambda: self.assertEqual(self.commit(self.proposal(), 1), 0),
                )
            return connection

        with mock.patch.object(state_store, "connect_store", side_effect=connect_with_interleaving):
            snapshot = state_store.load_state(self.root)

        self.assertEqual(snapshot["state_version"], 1)
        self.assertEqual(state_store.load_state(self.root)["state_version"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
