#!/usr/bin/env python3
"""Regression tests for the user-private knowledge learning workflow."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import knowledge_learning as kl


def text_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def source(source_id: str = "user_source_notes", **extra: object) -> dict[str, object]:
    row: dict[str, object] = {
        "source_id": source_id,
        "kind": "user_supplied_snapshot",
        "evidence_kind": "external_evidence",
        "content_sha256": text_hash(source_id),
        "rights_status": "private_local_only",
        "status": "candidate",
    }
    row.update(extra)
    return row


def atom(
    atom_id: str,
    canonical: str,
    source_id: str = "user_source_notes",
    *,
    relations: list[dict[str, str]] | None = None,
    claim_kind: str = "decision_rule",
) -> dict[str, object]:
    return {
        "atom_id": atom_id,
        "schema_version": "2.0",
        "canonical": canonical,
        "claim_kind": claim_kind,
        "actionability": "decision_rule",
        "domain": ["business", "learning"],
        "decision_rule": canonical,
        "limits": ["只适用于当前用户私有项目，仍需现实结果验证"],
        "source_refs": [
            {
                "source_id": source_id,
                "locator": {"file": "/private/approved/source.txt", "lines": "1-1"},
                "quote_hash": text_hash(canonical),
            }
        ],
        "provenance_type": "user_private_agent_candidate",
        "confidence": {
            "extraction": "high",
            "attribution": "high",
            "interpretation": "medium",
            "operational": "unknown",
        },
        "rights": {"redistribution": "private_local_only"},
        "source_date": None,
        "temporal_scope": "user-private-source-time-unverified",
        "bias_flags": ["user_private", "result_unverified"],
        "relations": relations or [],
        "content_hash": text_hash(canonical),
        "pipeline_run": "user_private_learning_test",
        "status": "candidate",
    }


def concept(
    concept_id: str,
    term: str,
    atom_id: str,
    *,
    aliases: list[str] | None = None,
) -> dict[str, object]:
    return {
        "concept_id": concept_id,
        "concept_kind": "operational_dictionary",
        "term": term,
        "normalized": term.casefold(),
        "definition": f"当前项目中对{term}的工作定义",
        "anti_definition": "不是未经验证的普遍规律",
        "common_misuse": "脱离项目范围使用",
        "aliases": aliases or [],
        "group": "用户私有",
        "source_atoms": [atom_id],
        "salience": "user_private",
        "related_methods": [],
        "rights": {"redistribution": "private_local_only"},
        "status": "candidate",
    }


def method(method_id: str, atom_ids: list[str], concept_ids: list[str]) -> dict[str, object]:
    return {
        "method_id": method_id,
        "title": "每周报价复盘",
        "purpose": "用客户反馈检查报价是否需要调整",
        "use_when": ["已经收集到真实报价反馈"],
        "inputs": ["客户异议记录"],
        "steps": ["归类异议", "检查证据", "决定保持或调整报价"],
        "decision_gates": ["没有真实反馈时不调整"],
        "stop_conditions": ["样本不足"],
        "outputs": ["下一周报价决定"],
        "quality_checks": ["结论绑定具体反馈"],
        "pitfalls": ["把单个意见当成市场结论"],
        "atom_ids": atom_ids,
        "concept_ids": concept_ids,
        "status": "candidate",
        "rights": {"redistribution": "private_local_only"},
    }


class KnowledgeLearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pack = self.root / ".biz-partner" / "knowledge-packs" / "my-business"
        self.source_files: dict[str, Path] = {}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def change_set(
        self,
        candidates: list[dict[str, object]],
        *,
        base_revision: int = 0,
        base_hash: str | None = None,
        suffix: str = "one",
    ) -> dict[str, object]:
        candidate_sources: dict[str, dict[str, object]] = {}
        for candidate in candidates:
            if candidate["record_kind"] == "source":
                record = candidate["record"]
                source_id = str(record["source_id"])
                candidate_sources[source_id] = record
                path = self.root / "source-material" / f"{source_id}.txt"
                path.parent.mkdir(parents=True, exist_ok=True)
                self.source_files[source_id] = path
        local_refs: dict[str, list[tuple[str, dict[str, object]]]] = {}
        for candidate in candidates:
            if candidate["record_kind"] != "atom":
                continue
            canonical = str(candidate["record"]["canonical"])
            for ref in candidate["record"].get("source_refs", []):
                locator = ref.get("locator", {})
                if "file" not in locator:
                    continue
                source_id = str(ref["source_id"])
                path = self.source_files.get(source_id)
                if path is None:
                    path = self.root / "source-material" / f"{source_id}.txt"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if not path.exists():
                        path.write_text(source_id, encoding="utf-8")
                    self.source_files[source_id] = path
                locator["file"] = str(path)
                local_refs.setdefault(source_id, []).append((canonical, ref))
        for source_id, record in candidate_sources.items():
            references = local_refs.get(source_id, [])
            content = "\n".join(canonical for canonical, _ in references) or source_id
            path = self.source_files[source_id]
            path.write_text(content, encoding="utf-8")
            record["content_sha256"] = kl.sha256_bytes(path.read_bytes())
            for line_number, (canonical, ref) in enumerate(references, 1):
                ref["locator"]["lines"] = f"{line_number}-{line_number}"
                ref["quote_hash"] = text_hash(canonical)
        return {
            "schema_version": kl.CHANGE_SET_SCHEMA,
            "change_set_id": f"kcs_{suffix}",
            "target": {
                "pack_id": "my-business",
                "pack_kind": "user_private",
                "pack_path": str(self.pack),
                "base_revision": base_revision,
                "base_manifest_sha256": base_hash,
            },
            "created_at": "2026-08-23T12:00:00+08:00",
            "candidates": candidates,
        }

    def candidate(self, candidate_id: str, kind: str, record: dict[str, object]) -> dict[str, object]:
        return {
            "candidate_id": candidate_id,
            "record_kind": kind,
            "operation": "add",
            "record": record,
        }

    def decisions(self, change_set: dict[str, object], decision: str = "accept") -> dict[str, object]:
        report = kl.analyze_change_set(self.pack, change_set)
        return {
            "schema_version": kl.DECISIONS_SCHEMA,
            "change_set_hash": report["change_set_hash"],
            "decisions": [
                {
                    "candidate_id": row["candidate_id"],
                    "candidate_hash": row["candidate_hash"],
                    "decision": decision,
                }
                for row in report["candidates"]
            ],
        }

    def save_docs(
        self, change_set: dict[str, object], decisions: dict[str, object]
    ) -> tuple[Path, Path]:
        change_path = self.root / "change-set.json"
        decision_path = self.root / "decisions.json"
        change_path.write_text(json.dumps(change_set, ensure_ascii=False), encoding="utf-8")
        decision_path.write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")
        return change_path, decision_path

    def run_main(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = kl.main(argv)
        return result, stdout.getvalue(), stderr.getvalue()

    def commit(self, change_set: dict[str, object]) -> dict[str, object]:
        decisions = self.decisions(change_set)
        change_path, decision_path = self.save_docs(change_set, decisions)
        plan, _ = kl.build_apply_plan(self.pack, change_set, decisions)
        result, _, error = self.run_main(
            [
                "apply",
                "--pack",
                str(self.pack),
                "--change-set",
                str(change_path),
                "--decisions",
                str(decision_path),
                "--expected-revision",
                str(plan["preview"]["expected_revision"]),
                "--confirmation-hash",
                plan["confirmation_hash"],
            ]
        )
        self.assertEqual(result, 0, error)
        return kl.current_state(self.pack)

    def replace_revision_content(self, target_revision: int, source_revision: int) -> None:
        target_dir = self.pack / "versions" / f"v{target_revision:06d}"
        source_dir = self.pack / "versions" / f"v{source_revision:06d}"
        source_manifest = kl.load_json(source_dir / "manifest.json")
        target_manifest = kl.load_json(target_dir / "manifest.json")
        for name in kl.FILES:
            shutil.copyfile(source_dir / name, target_dir / name)
        target_manifest["files"] = source_manifest["files"]
        target_manifest["counts"] = source_manifest["counts"]
        (target_dir / "manifest.json").write_bytes(kl.canonical_bytes(target_manifest) + b"\n")
        active_path = self.pack / "active.json"
        active = kl.load_json(active_path)
        active["manifest_sha256"] = kl.digest(target_manifest)
        active_path.write_bytes(kl.canonical_bytes(active) + b"\n")

    def first_change_set(self) -> dict[str, object]:
        return self.change_set(
            [
                self.candidate("candidate_source_one", "source", source()),
                self.candidate(
                    "candidate_atom_one",
                    "atom",
                    atom(
                        "user_atom_quote_review",
                        "每周按客户异议分类复查报价，再决定是否调整价格",
                    ),
                ),
            ]
        )

    def test_pack_path_is_confined_and_pack_id_matches_directory(self) -> None:
        with self.assertRaisesRegex(kl.LearningError, "must match"):
            kl.resolve_pack(str(self.root / "user-pack"))
        with self.assertRaisesRegex(kl.LearningError, "must match"):
            kl.resolve_pack("/")

        change_set = self.first_change_set()
        change_set["target"]["pack_id"] = "another-pack"
        with self.assertRaisesRegex(kl.LearningError, "directory name"):
            kl.analyze_change_set(self.pack, change_set)

    def test_expired_change_set_is_rejected(self) -> None:
        change_set = self.first_change_set()
        change_set["expires_at"] = "2000-01-01T00:00:00+00:00"
        with self.assertRaisesRegex(kl.LearningError, "expired"):
            kl.analyze_change_set(self.pack, change_set)

    def test_analyze_reports_verified_local_evidence_and_keeps_compatibility_field(self) -> None:
        report = kl.analyze_change_set(self.pack, self.first_change_set())
        self.assertTrue(report["structurally_ready"])
        self.assertTrue(report["ready_for_plan"])
        self.assertEqual(report["evidence_verification"]["status"], "verified")
        self.assertEqual(report["evidence_verification"]["verified"], 1)

    def test_local_file_locator_verifies_one_based_inclusive_quote_hash(self) -> None:
        change_set = self.first_change_set()
        material = b"first line\r\nsecond line\r\nthird line"
        source_path = self.source_files["user_source_notes"]
        source_path.write_bytes(material)
        change_set["candidates"][0]["record"]["content_sha256"] = kl.sha256_bytes(material)
        source_ref = change_set["candidates"][1]["record"]["source_refs"][0]
        source_ref["locator"]["lines"] = "1-2"
        source_ref["quote_hash"] = text_hash("first line\nsecond line")

        report = kl.analyze_change_set(self.pack, change_set)
        finding = report["evidence_verification"]["findings"][0]
        self.assertEqual(finding["status"], "verified")
        self.assertEqual(finding["reason"], "sha256_and_quote_match")

    def test_local_file_locator_rejects_bad_ranges_and_quote_hash(self) -> None:
        material = b"first line\nsecond line\nthird line"
        cases = {
            "malformed": ("second", text_hash("second line"), "locator_lines_invalid"),
            "zero_based": ("0-1", text_hash("first line"), "locator_lines_invalid"),
            "reversed": ("3-2", text_hash("second line"), "locator_lines_invalid"),
            "oversized": ("1-" + "9" * 5000, text_hash("first line"), "locator_lines_invalid"),
            "out_of_bounds": ("2-4", text_hash("second line\nthird line"), "locator_lines_out_of_bounds"),
            "quote_mismatch": ("2-2", text_hash("different"), "quote_hash_mismatch"),
        }
        for name, (lines, quote_hash, reason) in cases.items():
            with self.subTest(name=name):
                change_set = self.first_change_set()
                source_path = self.source_files["user_source_notes"]
                source_path.write_bytes(material)
                change_set["candidates"][0]["record"]["content_sha256"] = kl.sha256_bytes(material)
                source_ref = change_set["candidates"][1]["record"]["source_refs"][0]
                source_ref["locator"]["lines"] = lines
                source_ref["quote_hash"] = quote_hash
                report = kl.analyze_change_set(self.pack, change_set)
                finding = report["evidence_verification"]["findings"][0]
                self.assertEqual(finding["status"], "failed")
                self.assertEqual(finding["reason"], reason)

    def test_analyze_fails_missing_or_hash_mismatched_local_evidence(self) -> None:
        missing = self.first_change_set()
        self.source_files["user_source_notes"].unlink()
        report = kl.analyze_change_set(self.pack, missing)
        self.assertTrue(report["structurally_ready"])
        self.assertFalse(report["ready_for_plan"])
        self.assertEqual(report["evidence_verification"]["status"], "failed")
        self.assertEqual(report["evidence_verification"]["findings"][0]["reason"], "file_missing")

        mismatched = self.first_change_set()
        self.source_files["user_source_notes"].write_text("changed", encoding="utf-8")
        report = kl.analyze_change_set(self.pack, mismatched)
        self.assertEqual(report["evidence_verification"]["status"], "failed")
        self.assertEqual(report["evidence_verification"]["findings"][0]["reason"], "sha256_mismatch")

    def test_analyze_marks_url_and_conversation_evidence_unverified(self) -> None:
        network = self.first_change_set()
        network["candidates"][1]["record"]["source_refs"][0]["locator"] = {
            "url": "https://example.com/source",
            "field": "body",
        }
        report = kl.analyze_change_set(self.pack, network)
        self.assertTrue(report["ready_for_plan"])
        self.assertEqual(report["evidence_verification"]["status"], "unverified")
        self.assertEqual(report["evidence_verification"]["findings"][0]["reason"], "network_locator")

        conversation = self.first_change_set()
        conversation["candidates"][0]["record"]["evidence_kind"] = "conversation"
        conversation["candidates"][1]["record"]["claim_kind"] = "user_claim"
        report = kl.analyze_change_set(self.pack, conversation)
        self.assertEqual(report["evidence_verification"]["status"], "unverified")
        self.assertEqual(report["evidence_verification"]["findings"][0]["reason"], "session_source")

    def test_apply_requires_exact_confirmation_and_writes_nothing_before_it(self) -> None:
        change_set = self.first_change_set()
        decisions = self.decisions(change_set)
        change_path, decision_path = self.save_docs(change_set, decisions)
        plan, _ = kl.build_apply_plan(self.pack, change_set, decisions)
        self.assertFalse(self.pack.exists())

        result, _, error = self.run_main(
            [
                "apply",
                "--pack",
                str(self.pack),
                "--change-set",
                str(change_path),
                "--decisions",
                str(decision_path),
                "--expected-revision",
                "0",
                "--confirmation-hash",
                "sha256:" + "0" * 64,
            ]
        )
        self.assertEqual(result, 1)
        self.assertIn("confirmation hash", error)
        self.assertFalse(self.pack.exists())

        result, _, error = self.run_main(
            [
                "apply",
                "--pack",
                str(self.pack),
                "--change-set",
                str(change_path),
                "--decisions",
                str(decision_path),
                "--expected-revision",
                "0",
                "--confirmation-hash",
                plan["confirmation_hash"],
            ]
        )
        self.assertEqual(result, 0, error)
        self.assertEqual(kl.verify_pack(self.pack)["revision"], 1)
        self.assertEqual((self.pack / ".gitignore").read_bytes(), kl.PACK_GITIGNORE)

    def test_missing_or_changed_privacy_guard_is_rejected(self) -> None:
        self.commit(self.first_change_set())
        guard = self.pack / ".gitignore"
        guard.write_text("not-protective\n", encoding="utf-8")
        with self.assertRaisesRegex(kl.LearningError, "privacy guard"):
            kl.verify_pack(self.pack)

    def test_changed_candidate_invalidates_decision_and_confirmation(self) -> None:
        change_set = self.first_change_set()
        decisions = self.decisions(change_set)
        plan, _ = kl.build_apply_plan(self.pack, change_set, decisions)
        change_set["candidates"][1]["record"]["canonical"] = "被修改但未重新确认的内容"
        change_set["candidates"][1]["record"]["decision_rule"] = "被修改但未重新确认的内容"
        change_set["candidates"][1]["record"]["content_hash"] = text_hash("被修改但未重新确认的内容")
        change_path, decision_path = self.save_docs(change_set, decisions)
        result, _, error = self.run_main(
            [
                "apply",
                "--pack",
                str(self.pack),
                "--change-set",
                str(change_path),
                "--decisions",
                str(decision_path),
                "--expected-revision",
                "0",
                "--confirmation-hash",
                plan["confirmation_hash"],
            ]
        )
        self.assertEqual(result, 1)
        self.assertIn("not bound", error)
        self.assertFalse(self.pack.exists())

    def test_exact_duplicate_is_blocked_and_near_duplicate_is_reported(self) -> None:
        state = self.commit(self.first_change_set())
        canonical = "每周按客户异议分类复查报价，再决定是否调整价格"
        exact = self.change_set(
            [self.candidate("candidate_atom_exact", "atom", atom("user_atom_exact_copy", canonical))],
            base_revision=1,
            base_hash=state["manifest_sha256"],
            suffix="exact",
        )
        report = kl.analyze_change_set(self.pack, exact)
        self.assertIn("exact_duplicate", {item["type"] for item in report["candidates"][0]["blockers"]})

        near = self.change_set(
            [
                self.candidate(
                    "candidate_atom_near",
                    "atom",
                    atom("user_atom_quote_review_near", "每周把客户的报价异议分类复查，再考虑是否调价格"),
                )
            ],
            base_revision=1,
            base_hash=state["manifest_sha256"],
            suffix="near",
        )
        near_report = kl.analyze_change_set(self.pack, near)
        self.assertIn("near_duplicate", {item["type"] for item in near_report["candidates"][0]["warnings"]})

    def test_alias_conflict_is_blocking(self) -> None:
        initial = self.first_change_set()
        initial["candidates"].append(
            self.candidate(
                "candidate_concept_one",
                "concept",
                concept("user_concept_price_signal", "价格信号", "user_atom_quote_review", aliases=["报价反馈"]),
            )
        )
        state = self.commit(initial)
        change_set = self.change_set(
            [
                self.candidate(
                    "candidate_concept_collision",
                    "concept",
                    concept("user_concept_feedback_collision", "反馈分类", "user_atom_quote_review", aliases=["报价反馈"]),
                )
            ],
            base_revision=1,
            base_hash=state["manifest_sha256"],
            suffix="alias",
        )
        report = kl.analyze_change_set(self.pack, change_set)
        self.assertIn(
            "concept_alias_conflict",
            {item["type"] for item in report["candidates"][0]["blockers"]},
        )

    def test_dependency_cycle_is_blocking(self) -> None:
        change_set = self.change_set(
            [
                self.candidate("candidate_source_cycle", "source", source()),
                self.candidate("candidate_atom_a", "atom", atom("user_atom_cycle_a", "先验证约束甲")),
                self.candidate("candidate_atom_b", "atom", atom("user_atom_cycle_b", "再验证约束乙")),
                self.candidate(
                    "candidate_relation_ab",
                    "atom_relation",
                    {"source_atom_id": "user_atom_cycle_a", "type": "depends_on", "target_atom_id": "user_atom_cycle_b"},
                ),
                self.candidate(
                    "candidate_relation_ba",
                    "atom_relation",
                    {"source_atom_id": "user_atom_cycle_b", "type": "depends_on", "target_atom_id": "user_atom_cycle_a"},
                ),
            ],
            suffix="cycle",
        )
        report = kl.analyze_change_set(self.pack, change_set)
        blocker_types = {
            blocker["type"] for row in report["candidates"] for blocker in row["blockers"]
        }
        self.assertIn("depends_on_cycle", blocker_types)

    def test_private_rights_and_credentials_fail_closed(self) -> None:
        secret_source = source(api_key="api_key=abcdefghijklmnopqrstuvwxyz")
        change_set = self.change_set(
            [self.candidate("candidate_secret", "source", secret_source)], suffix="secret"
        )
        report = kl.analyze_change_set(self.pack, change_set)
        self.assertIn(
            "credential_or_secret",
            {item["type"] for item in report["candidates"][0]["blockers"]},
        )

        bad_rights = source()
        bad_rights["rights_status"] = "published"
        invalid = self.change_set(
            [self.candidate("candidate_public_rights", "source", bad_rights)], suffix="rights"
        )
        rights_report = kl.analyze_change_set(self.pack, invalid)
        self.assertIn(
            "private_rights_or_status",
            {item["type"] for item in rights_report["candidates"][0]["blockers"]},
        )

    def test_stale_revision_is_a_concurrency_conflict(self) -> None:
        change_set = self.first_change_set()
        decisions = self.decisions(change_set)
        plan, rows = kl.build_apply_plan(self.pack, change_set, decisions)
        kl.write_version(self.pack, plan, rows)
        with self.assertRaisesRegex(kl.LearningError, "base is stale"):
            kl.build_apply_plan(self.pack, change_set, decisions)

    def test_write_version_rejects_versions_directory_symlink(self) -> None:
        change_set = self.first_change_set()
        decisions = self.decisions(change_set)
        plan, rows = kl.build_apply_plan(self.pack, change_set, decisions)
        self.pack.mkdir(parents=True)
        outside = self.root / "outside-versions"
        outside.mkdir()
        (self.pack / "versions").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(kl.LearningError, "versions directory must not be a symlink"):
            kl.write_version(self.pack, plan, rows)

    def test_write_version_rejects_target_revision_symlink(self) -> None:
        change_set = self.first_change_set()
        decisions = self.decisions(change_set)
        plan, rows = kl.build_apply_plan(self.pack, change_set, decisions)
        versions = self.pack / "versions"
        versions.mkdir(parents=True)
        outside = self.root / "outside-revision"
        outside.mkdir()
        (versions / "v000001").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(kl.LearningError, "target revision must not be a symlink"):
            kl.write_version(self.pack, plan, rows)

    def test_rollback_creates_new_revision_and_preserves_history(self) -> None:
        state_one = self.commit(self.first_change_set())
        change_two = self.change_set(
            [
                self.candidate("candidate_source_two", "source", source("user_source_followup")),
                self.candidate(
                    "candidate_atom_two",
                    "atom",
                    atom(
                        "user_atom_followup",
                        "复盘结论要绑定本周的真实结果",
                        source_id="user_source_followup",
                    ),
                ),
            ],
            base_revision=1,
            base_hash=state_one["manifest_sha256"],
            suffix="two",
        )
        self.commit(change_two)
        rollback_plan, rows = kl.build_rollback_plan(self.pack, 1)
        current = kl.current_state(self.pack)
        kl.assert_expected(current, 2, rollback_plan["preview"])
        kl.write_version(self.pack, rollback_plan, rows)
        verified = kl.verify_pack(self.pack)
        self.assertEqual(verified["revision"], 3)
        self.assertEqual(verified["restores_revision"], 1)
        self.assertTrue((self.pack / "versions/v000001").is_dir())
        self.assertTrue((self.pack / "versions/v000002").is_dir())
        self.assertTrue((self.pack / "versions/v000003").is_dir())
        self.assertEqual(verified["counts"]["atoms"], 1)

    def test_rollback_to_revision_zero_creates_empty_revision_and_preserves_history(self) -> None:
        self.commit(self.first_change_set())
        plan, rows = kl.build_rollback_plan(self.pack, 0)
        self.assertEqual(plan["preview"]["restore_revision"], 0)
        self.assertIsNone(plan["preview"]["restore_manifest_sha256"])
        self.assertTrue(all(rows[name] == [] for name in kl.FILES))
        current = kl.current_state(self.pack)
        kl.assert_expected(current, 1, plan["preview"])
        kl.write_version(self.pack, plan, rows)
        verified = kl.verify_pack(self.pack)
        self.assertEqual(verified["revision"], 2)
        self.assertEqual(verified["restores_revision"], 0)
        self.assertTrue((self.pack / "versions/v000001").is_dir())
        self.assertTrue((self.pack / "versions/v000002").is_dir())
        self.assertTrue(all(value == 0 for value in verified["counts"].values()))

    def test_verify_rejects_rollback_zero_with_nonempty_content(self) -> None:
        self.commit(self.first_change_set())
        plan, rows = kl.build_rollback_plan(self.pack, 0)
        kl.write_version(self.pack, plan, rows)
        self.replace_revision_content(2, 1)
        with self.assertRaisesRegex(
            kl.LearningError,
            "rollback revision 0 must contain empty files and zero counts",
        ):
            kl.verify_pack(self.pack)

    def test_verify_rejects_rollback_content_different_from_restored_revision(self) -> None:
        state_one = self.commit(self.first_change_set())
        change_two = self.change_set(
            [
                self.candidate("candidate_source_two", "source", source("user_source_followup")),
                self.candidate(
                    "candidate_atom_two",
                    "atom",
                    atom(
                        "user_atom_followup",
                        "复盘结论要绑定本周的真实结果",
                        source_id="user_source_followup",
                    ),
                ),
            ],
            base_revision=1,
            base_hash=state_one["manifest_sha256"],
            suffix="rollback_semantics",
        )
        self.commit(change_two)
        plan, rows = kl.build_rollback_plan(self.pack, 1)
        kl.write_version(self.pack, plan, rows)
        self.replace_revision_content(3, 2)
        with self.assertRaisesRegex(
            kl.LearningError,
            "rollback content does not match restored revision 1",
        ):
            kl.verify_pack(self.pack)

    def test_manifest_chain_detects_an_edited_older_revision(self) -> None:
        state_one = self.commit(self.first_change_set())
        change_two = self.change_set(
            [
                self.candidate("candidate_source_two", "source", source("user_source_followup")),
                self.candidate(
                    "candidate_atom_two",
                    "atom",
                    atom(
                        "user_atom_followup",
                        "复盘结论要绑定本周的真实结果",
                        source_id="user_source_followup",
                    ),
                ),
            ],
            base_revision=1,
            base_hash=state_one["manifest_sha256"],
            suffix="chain",
        )
        self.commit(change_two)
        old_manifest_path = self.pack / "versions/v000001/manifest.json"
        old_manifest = json.loads(old_manifest_path.read_text(encoding="utf-8"))
        old_manifest["change_set_hash"] = "sha256:" + "f" * 64
        old_manifest_path.write_text(
            json.dumps(old_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(kl.LearningError, "manifest chain hash mismatch"):
            kl.verify_pack(self.pack)

    def test_private_search_and_public_pack_are_unchanged(self) -> None:
        before = {
            path.relative_to(kl.PUBLIC_PACK_ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in kl.PUBLIC_PACK_ROOT.rglob("*")
            if path.is_file()
        }
        self.commit(self.first_change_set())
        verified = kl.verify_pack(self.pack)
        self.assertEqual(verified["private_runtime"], "validated")
        state = kl.current_state(self.pack)
        version = kl.active_version_dir(self.pack, state)
        assert version is not None
        pack = kl.load_knowledge_pack(version / "sources.jsonl", version / "atoms.jsonl", mode="private")
        result = kl.search_knowledge_pack(pack, "客户报价异议怎么复查", limit=5)
        self.assertEqual(result["mode"], "private")
        self.assertEqual(result["results"][0]["atom_id"], "user_atom_quote_review")
        after = {
            path.relative_to(kl.PUBLIC_PACK_ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in kl.PUBLIC_PACK_ROOT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)

    def test_full_candidate_set_fills_atoms_dictionary_method_relation_and_case(self) -> None:
        change_set = self.change_set(
            [
                self.candidate("candidate_source_full", "source", source()),
                self.candidate(
                    "candidate_atom_signal",
                    "atom",
                    atom("user_atom_price_signal", "报价异议要先分类，再判断是否需要调价"),
                ),
                self.candidate(
                    "candidate_atom_evidence",
                    "atom",
                    atom("user_atom_price_evidence", "调价决定必须绑定真实客户反馈"),
                ),
                self.candidate(
                    "candidate_concept_signal",
                    "concept",
                    concept(
                        "user_concept_price_signal",
                        "报价信号",
                        "user_atom_price_signal",
                        aliases=["价格反馈"],
                    )
                    | {"related_methods": ["user_method_price_review"]},
                ),
                self.candidate(
                    "candidate_method_review",
                    "method",
                    method(
                        "user_method_price_review",
                        ["user_atom_price_signal", "user_atom_price_evidence"],
                        ["user_concept_price_signal"],
                    ),
                ),
                self.candidate(
                    "candidate_relation_support",
                    "atom_relation",
                    {
                        "source_atom_id": "user_atom_price_signal",
                        "type": "supports",
                        "target_atom_id": "user_atom_price_evidence",
                    },
                ),
                self.candidate(
                    "candidate_case_price_review",
                    "retrieval_case",
                    {
                        "case_id": "user_case_price_review",
                        "case_kind": "direct",
                        "query": "客户嫌贵时怎么复盘报价",
                        "relevant_atom_ids": ["user_atom_price_signal"],
                        "relevant_method_ids": ["user_method_price_review"],
                        "relevant_concept_ids": ["user_concept_price_signal"],
                    },
                ),
            ],
            suffix="full",
        )
        self.commit(change_set)
        verified = kl.verify_pack(self.pack)
        self.assertEqual(
            verified["counts"],
            {"sources": 1, "atoms": 2, "concepts": 1, "methods": 1, "retrieval_cases": 1},
        )
        state = kl.current_state(self.pack)
        version = kl.active_version_dir(self.pack, state)
        assert version is not None
        rows = kl.read_version_rows(version)
        self.assertEqual(
            rows["atoms.jsonl"][0]["relations"],
            [{"type": "supports", "atom_id": "user_atom_price_evidence"}],
        )

    def test_decisions_template_covers_current_change_set_with_exact_hashes(self) -> None:
        change_set = kl.load_json(kl.SKILL_ROOT / "templates" / "knowledge-change-set.json")
        decisions = kl.load_json(kl.SKILL_ROOT / "templates" / "knowledge-decisions.json")
        expected = {
            candidate["candidate_id"]: kl.digest(candidate)
            for candidate in change_set["candidates"]
        }
        actual = {
            decision["candidate_id"]: decision["candidate_hash"]
            for decision in decisions["decisions"]
        }
        self.assertEqual(len(expected), 7)
        self.assertEqual(decisions["change_set_hash"], kl.digest(change_set))
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
