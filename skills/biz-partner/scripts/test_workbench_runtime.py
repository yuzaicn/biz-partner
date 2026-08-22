#!/usr/bin/env python3
"""End-to-end tests for the local workbench runtime."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import workbench_runtime  # noqa: E402


class WorkbenchRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.canonical = self.root / "canonical"
        self.consumer_a = self.root / "consumer-a"
        self.consumer_b = self.root / "consumer-b"
        self.canonical.mkdir()
        self.consumer_a.mkdir()
        self.consumer_b.mkdir()
        (self.canonical / "assets").mkdir()
        self.source = self.canonical / "assets" / "offer.md"
        self.source.write_text("PRIVATE OFFER BODY\n", encoding="utf-8")
        self.config_path = self.root / "workbench-config.json"
        self.write_config()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def config(self) -> dict:
        return {
            "schema": workbench_runtime.CONFIG_SCHEMA,
            "schema_version": "1.0",
            "canonical_root": str(self.canonical),
            "canonical_owner": "content-team",
            "sync_direction": "canonical_to_consumer",
            "assets": [
                {
                    "id": "offer-playbook",
                    "path": "assets/offer.md",
                    "version": "1.0.0",
                    "classification": "private",
                }
            ],
            "consumers": [
                {
                    "id": "research-agent",
                    "root": str(self.consumer_a),
                    "owner": "research-team",
                    "discovery_path": ".agent/bridge.json",
                    "consumer_version": "2.1.0",
                    "capabilities": ["manifest-discovery", "markdown-read"],
                    "supported_schema_versions": ["1.0"],
                    "adapter_mode": "read_only",
                },
                {
                    "id": "offline-index",
                    "root": str(self.consumer_b),
                    "owner": "operations-team",
                    "discovery_path": "config/workbench.json",
                    "consumer_version": "1.4.0",
                    "capabilities": ["manifest-discovery", "hash-verify"],
                    "supported_schema_versions": ["1.0"],
                },
            ],
        }

    def write_config(self, value: dict | None = None) -> None:
        self.config_path.write_text(
            json.dumps(value or self.config(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def apply_current_plan(self) -> dict:
        planned = workbench_runtime.build_plan(self.config_path)
        return workbench_runtime.apply_plan(
            self.config_path,
            expected_version=planned["plan"]["expected_version"],
            confirmation_hash=planned["confirmation_hash"],
        )

    def test_plan_is_read_only_and_lists_exact_targets(self) -> None:
        source_before = self.source.read_bytes()
        planned = workbench_runtime.build_plan(self.config_path)
        self.assertEqual(planned["plan"]["expected_version"], 0)
        self.assertEqual(planned["plan"]["next_version"], 1)
        self.assertEqual(len(planned["plan"]["adapters"]), 2)
        self.assertTrue(all(item["mode"] == "read_only" for item in planned["plan"]["adapters"]))
        self.assertTrue(all(item["sync_direction"] == "canonical_to_consumer" for item in planned["plan"]["adapters"]))
        self.assertFalse((self.canonical / workbench_runtime.WORKBENCH_DIR).exists())
        self.assertFalse((self.consumer_a / ".agent").exists())
        self.assertEqual(self.source.read_bytes(), source_before)

    def test_wrong_confirmation_and_version_do_not_write(self) -> None:
        planned = workbench_runtime.build_plan(self.config_path)
        with self.assertRaisesRegex(workbench_runtime.WorkbenchError, "version conflict"):
            workbench_runtime.apply_plan(
                self.config_path,
                expected_version=9,
                confirmation_hash=planned["confirmation_hash"],
            )
        with self.assertRaisesRegex(workbench_runtime.WorkbenchError, "confirmation hash"):
            workbench_runtime.apply_plan(
                self.config_path,
                expected_version=0,
                confirmation_hash="sha256:wrong",
            )
        self.assertFalse((self.canonical / workbench_runtime.WORKBENCH_DIR).exists())
        self.assertFalse((self.consumer_a / ".agent").exists())

    def test_apply_creates_thin_bridges_and_verify_is_repeatable(self) -> None:
        source_before = self.source.read_bytes()
        result = self.apply_current_plan()
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(result["workbench_version"], 1)
        self.assertTrue(Path(result["manifest"]).is_file())
        self.assertTrue(Path(result["rollback_manifest"]).is_file())

        bridge_a = json.loads(
            (self.consumer_a / ".agent" / "bridge.json").read_text(encoding="utf-8")
        )
        bridge_b = json.loads(
            (self.consumer_b / "config" / "workbench.json").read_text(encoding="utf-8")
        )
        self.assertEqual(bridge_a["schema"], workbench_runtime.BRIDGE_SCHEMA)
        self.assertEqual(bridge_b["adapter_mode"], "read_only")
        self.assertNotIn("assets", bridge_a)
        self.assertNotIn("PRIVATE OFFER BODY", json.dumps(bridge_a))
        self.assertNotIn("PRIVATE OFFER BODY", json.dumps(bridge_b))
        self.assertEqual(self.source.read_bytes(), source_before)

        first = workbench_runtime.verify_workbench(self.config_path)
        second = workbench_runtime.verify_workbench(self.config_path)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "PASS")
        self.assertTrue(all(item["status"] == "PASS" for item in first["consumers"]))

    def test_verify_detects_canonical_and_bridge_drift(self) -> None:
        self.apply_current_plan()
        self.source.write_text("CHANGED PRIVATE BODY\n", encoding="utf-8")
        canonical_drift = workbench_runtime.verify_workbench(self.config_path)
        self.assertEqual(canonical_drift["status"], "FAIL")
        failed = {
            item["check"]
            for item in canonical_drift["canonical"]["checks"]
            if item["status"] == "FAIL"
        }
        self.assertIn("canonical_hash", failed)

        self.source.write_text("PRIVATE OFFER BODY\n", encoding="utf-8")
        bridge_path = self.consumer_a / ".agent" / "bridge.json"
        bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
        bridge["canonical_hash"] = "sha256:" + "0" * 64
        bridge_path.write_text(json.dumps(bridge), encoding="utf-8")
        bridge_drift = workbench_runtime.verify_workbench(self.config_path)
        research = next(item for item in bridge_drift["consumers"] if item["id"] == "research-agent")
        self.assertEqual(research["status"], "FAIL")
        self.assertTrue(
            any(
                item["check"] in {"bridge_canonical_hash", "bridge_drift"}
                and item["status"] == "FAIL"
                for item in research["checks"]
            )
        )

    def test_out_of_boundary_discovery_symlink_is_rejected_and_reported(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        linked_parent = self.consumer_a / "linked"
        os.symlink(outside, linked_parent)
        config = self.config()
        config["consumers"][0]["discovery_path"] = "linked/bridge.json"
        self.write_config(config)
        with self.assertRaisesRegex(workbench_runtime.WorkbenchError, "escapes"):
            workbench_runtime.build_plan(self.config_path)

        linked_parent.unlink()
        self.write_config()
        self.apply_current_plan()
        bridge = self.consumer_a / ".agent" / "bridge.json"
        bridge.unlink()
        (self.consumer_a / ".agent").rmdir()
        os.symlink(outside, self.consumer_a / ".agent")
        report = workbench_runtime.verify_workbench(self.config_path)
        research = next(item for item in report["consumers"] if item["id"] == "research-agent")
        self.assertEqual(research["status"], "FAIL")
        boundary = next(item for item in research["checks"] if item["check"] == "discovery_boundary")
        self.assertEqual(boundary["status"], "FAIL")

    def test_update_increments_version_and_generates_rollback_manifest(self) -> None:
        self.apply_current_plan()
        planned = workbench_runtime.build_plan(self.config_path)
        self.assertEqual(planned["plan"]["expected_version"], 1)
        result = workbench_runtime.apply_plan(
            self.config_path,
            expected_version=1,
            confirmation_hash=planned["confirmation_hash"],
        )
        self.assertEqual(result["workbench_version"], 2)
        rollback = json.loads(Path(result["rollback_manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(rollback["previous_version"], 1)
        self.assertEqual(rollback["applied_version"], 2)
        self.assertTrue((self.canonical / workbench_runtime.WORKBENCH_DIR / "releases" / "v000001").is_dir())
        self.assertTrue((self.canonical / workbench_runtime.WORKBENCH_DIR / "releases" / "v000002").is_dir())
        self.assertEqual(workbench_runtime.verify_workbench(self.config_path)["status"], "PASS")

    def test_bidirectional_or_writable_adapter_is_rejected(self) -> None:
        config = self.config()
        config["sync_direction"] = "bidirectional"
        self.write_config(config)
        with self.assertRaisesRegex(workbench_runtime.WorkbenchError, "bidirectional"):
            workbench_runtime.build_plan(self.config_path)

        config = self.config()
        config["consumers"][0]["adapter_mode"] = "read_write"
        self.write_config(config)
        with self.assertRaisesRegex(workbench_runtime.WorkbenchError, "read_only"):
            workbench_runtime.build_plan(self.config_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
