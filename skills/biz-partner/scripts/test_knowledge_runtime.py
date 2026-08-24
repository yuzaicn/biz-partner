#!/usr/bin/env python3
"""Regression tests for the local folder and KnowledgePack runtime."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from atom_contract import sha256_text  # noqa: E402
from knowledge_runtime import (  # noqa: E402
    build_folder_index,
    build_folder_index_plan,
    evaluate_recall,
    load_json,
    load_knowledge_pack,
    main,
    search_folder_index,
    search_knowledge_pack,
)


class FolderRuntimeTests(unittest.TestCase):
    def test_preview_indexes_text_without_copying_source_and_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            root.mkdir()
            source = root / "customer.md"
            source.write_text("客户访谈先记录真实购买信号。\n", encoding="utf-8")
            index_path = Path(directory) / "index.json"

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "folder-index",
                        "--root",
                        str(root),
                        "--index",
                        str(index_path),
                    ]
                )

            self.assertEqual(result, 0)
            self.assertFalse(index_path.exists())
            preview = json.loads(stdout.getvalue())
            self.assertEqual(preview["mode"], "preview")
            self.assertTrue(preview["confirmation_hash"].startswith("sha256:"))
            self.assertEqual(preview["plan"]["index_path"], str(index_path.absolute()))
            serialized = json.dumps(preview["index"], ensure_ascii=False)
            self.assertNotIn("客户访谈先记录真实购买信号", serialized)
            self.assertFalse(preview["index"]["config"]["stores_original_text"])

    def test_commit_and_search_return_verified_locator_hash_and_bounded_snippet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            root.mkdir()
            (root / "offer.txt").write_text(
                "先定义客户。\n再记录客户为什么愿意付费，以及真实购买信号。\n",
                encoding="utf-8",
            )
            index_path = Path(directory) / "index.json"
            planned = build_folder_index_plan([root], index_path=index_path)
            with redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "folder-index",
                        "--root",
                        str(root),
                        "--index",
                        str(index_path),
                        "--commit",
                        "--confirmation-hash",
                        planned["confirmation_hash"],
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(index_path.is_file())
            result = search_folder_index(load_json(index_path), "客户为什么愿意付费", limit=5)

            self.assertEqual(len(result["results"]), 1)
            hit = result["results"][0]
            self.assertEqual(hit["locator"]["path"], "offer.txt")
            self.assertEqual(hit["locator"]["lines"], "2-2")
            self.assertTrue(hit["locator"]["sha256"].startswith("sha256:"))
            self.assertEqual(hit["confidence"]["evidence"], "hash_verified_at_query_time")
            self.assertIn("真实购买信号", hit["snippet"])
            self.assertEqual(hit["source_attribution"]["atom_ids"], [])

    def test_commit_requires_exact_current_preview_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            root.mkdir()
            source = root / "case.md"
            source.write_text("客户只表达口头兴趣\n", encoding="utf-8")
            index_path = Path(directory) / "index.json"
            planned = build_folder_index_plan([root], index_path=index_path)

            source.write_text("客户已经支付订金\n", encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "folder-index",
                        "--root",
                        str(root),
                        "--index",
                        str(index_path),
                        "--commit",
                        "--confirmation-hash",
                        planned["confirmation_hash"],
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("confirmation hash", stderr.getvalue())
            self.assertFalse(index_path.exists())

    def test_commit_without_confirmation_hash_fails_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            root.mkdir()
            (root / "case.md").write_text("客户证据\n", encoding="utf-8")
            index_path = Path(directory) / "index.json"
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "folder-index",
                        "--root",
                        str(root),
                        "--index",
                        str(index_path),
                        "--commit",
                    ]
                )
            self.assertEqual(exit_code, 1)
            self.assertIn("requires --confirmation-hash", stderr.getvalue())
            self.assertFalse(index_path.exists())

    def test_incremental_update_reuses_unchanged_and_removes_deleted_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kept = root / "kept.md"
            changed = root / "changed.md"
            removed = root / "removed.md"
            kept.write_text("保持不变的客户记录", encoding="utf-8")
            changed.write_text("旧的定价记录", encoding="utf-8")
            removed.write_text("即将删除的记录", encoding="utf-8")
            first, _ = build_folder_index([root])

            changed.write_text("新的定价记录和毛利假设", encoding="utf-8")
            removed.unlink()
            second, changes = build_folder_index([root], prior_index=first)

            self.assertEqual(changes, {"added": 0, "updated": 1, "unchanged": 1, "deleted": 1})
            self.assertEqual({row["path"] for row in second["documents"]}, {"kept.md", "changed.md"})

    def test_out_of_root_symlink_is_not_followed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "allowed"
            root.mkdir()
            secret = base / "secret.txt"
            secret.write_text("outside confidential material", encoding="utf-8")
            (root / "escape.txt").symlink_to(secret)

            index, _ = build_folder_index([root])

            self.assertEqual(index["documents"], [])
            self.assertIn(
                {"root_id": index["roots"][0]["root_id"], "path": "escape.txt", "reason": "out_of_root_symlink"},
                index["skips"],
            )
            self.assertNotIn("outside confidential material", json.dumps(index))

    def test_skip_reasons_cover_hidden_binary_oversize_and_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".hidden.md").write_text("hidden", encoding="utf-8")
            (root / "binary.txt").write_bytes(b"hello\x00world")
            (root / "large.md").write_text("x" * 50, encoding="utf-8")
            (root / "image.png").write_bytes(b"png")

            index, _ = build_folder_index([root], max_bytes=16)
            reasons = {row["path"]: row["reason"] for row in index["skips"]}

            self.assertEqual(reasons[".hidden.md"], "hidden_file")
            self.assertEqual(reasons["binary.txt"], "binary_nul")
            self.assertEqual(reasons["large.md"], "exceeds_max_bytes")
            self.assertEqual(reasons["image.png"], "unsupported_extension")

    def test_changed_source_is_not_returned_until_reindexed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "decision.md"
            source.write_text("原始客户决策", encoding="utf-8")
            index, _ = build_folder_index([root])
            source.write_text("已被改变的客户决策", encoding="utf-8")

            result = search_folder_index(index, "客户决策")

            self.assertEqual(result["results"], [])
            self.assertEqual(result["warnings"][0]["reason"], "stale_hash_mismatch")


class KnowledgePackRuntimeTests(unittest.TestCase):
    @staticmethod
    def source(source_id: str, *, public: bool = False, status: str | None = None) -> dict[str, object]:
        row: dict[str, object] = {
            "source_id": source_id,
            "status": status or ("release_eligible" if public else "candidate"),
            "rights_status": "open_license" if public else "internal_use_only",
        }
        if public:
            row["license"] = {
                "id": "CC-BY",
                "version": "4.0",
                "scope": "redistribution_and_derivatives",
            }
            row["release_decision"] = "approved_for_public_release"
        return row

    @staticmethod
    def atom(
        atom_id: str,
        source_id: str,
        canonical: str,
        *,
        public: bool = False,
        status: str | None = None,
        relations: list[dict[str, str]] | None = None,
    ) -> dict[str, object]:
        rights: dict[str, object] = {
            "redistribution": "open_license" if public else "internal_use_only"
        }
        if public:
            rights["license"] = {
                "id": "CC-BY",
                "version": "4.0",
                "scope": "redistribution_and_derivatives",
            }
        row: dict[str, object] = {
            "atom_id": atom_id,
            "schema_version": "2.0",
            "canonical": canonical,
            "claim_kind": "decision_rule",
            "actionability": "diagnostic_rule",
            "domain": ["business"],
            "decision_rule": canonical,
            "procedure": ["检查当前证据", "记录验证结果"],
            "limits": ["需要当前证据验证"],
            "source_refs": [
                {
                    "source_id": source_id,
                    "locator": {"file": "evidence.md", "lines": "1-1"},
                    "quote_hash": sha256_text(f"evidence:{atom_id}"),
                }
            ],
            "provenance_type": "reviewed_source",
            "confidence": {
                "extraction": "high",
                "attribution": "high",
                "interpretation": "medium",
                "operational": "unknown",
            },
            "rights": rights,
            "source_date": "2026-08-20",
            "temporal_scope": "source-time",
            "bias_flags": [],
            "relations": relations or [],
            "content_hash": sha256_text(canonical),
            "pipeline_run": "run_knowledge_runtime_test",
            "status": status or ("release_eligible" if public else "candidate"),
        }
        if public:
            row["release_decision"] = "approved_for_public_release"
        return row

    @staticmethod
    def supporting_rights(*, public: bool) -> dict[str, object]:
        rights: dict[str, object] = {
            "redistribution": "open_license" if public else "internal_use_only"
        }
        if public:
            rights["license"] = {
                "id": "CC-BY",
                "version": "4.0",
                "scope": "redistribution_and_derivatives",
            }
        return rights

    @classmethod
    def concept(
        cls,
        concept_id: str,
        atom_ids: list[str],
        method_ids: list[str],
        *,
        public: bool = True,
        aliases: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "concept_id": concept_id,
            "term": "付费信号",
            "normalized": "payment_signal",
            "definition": "客户用可观察承诺表达真实购买意愿",
            "anti_definition": "不是口头认可或点赞",
            "common_misuse": "把礼貌回应当成付费证据",
            "aliases": aliases or ["愿不愿掏钱"],
            "source_atoms": atom_ids,
            "related_methods": method_ids,
            "status": "release_eligible" if public else "candidate",
            "rights": cls.supporting_rights(public=public),
        }

    @classmethod
    def method(
        cls,
        method_id: str,
        atom_ids: list[str],
        concept_ids: list[str],
        *,
        public: bool = True,
    ) -> dict[str, object]:
        return {
            "method_id": method_id,
            "title": "客户付费验证",
            "purpose": "用真实承诺验证购买意愿",
            "use_when": ["只有口头兴趣"],
            "inputs": ["目标客户", "待验证报价"],
            "steps": ["提出窄报价", "请求可观察承诺"],
            "decision_gates": ["没有承诺则保持未验证"],
            "stop_conditions": ["达到事前停止条件"],
            "outputs": ["验证记录"],
            "quality_checks": ["承诺可回溯"],
            "pitfalls": ["把点赞当购买"],
            "atom_ids": atom_ids,
            "concept_ids": concept_ids,
            "status": "release_eligible" if public else "candidate",
            "rights": cls.supporting_rights(public=public),
        }

    @staticmethod
    def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    def write_pack(
        self,
        root: Path,
        sources: list[dict[str, object]],
        atoms: list[dict[str, object]],
        *,
        concepts: list[dict[str, object]] | None = None,
        methods: list[dict[str, object]] | None = None,
    ) -> tuple[Path, Path]:
        source_path = root / "sources.jsonl"
        atom_path = root / "atoms.jsonl"
        self.write_jsonl(source_path, sources)
        self.write_jsonl(atom_path, atoms)
        if concepts is not None:
            self.write_jsonl(root / "concepts.jsonl", concepts)
        if methods is not None:
            self.write_jsonl(root / "methods.jsonl", methods)
        return source_path, atom_path

    def test_public_mode_fails_closed_and_private_mode_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = [
                self.source("public", public=True),
                self.source("private"),
                self.source("blocked", status="blocked"),
            ]
            atoms = [
                self.atom("ka_public", "public", "公开客户验证方法", public=True),
                self.atom("ka_private", "private", "私有客户验证方法"),
                self.atom("ka_blocked", "blocked", "禁止使用的客户方法"),
            ]
            source_path, atom_path = self.write_pack(root, sources, atoms)

            public_pack = load_knowledge_pack(source_path, atom_path)
            private_pack = load_knowledge_pack(source_path, atom_path, mode="private")

            self.assertEqual(set(public_pack.atoms), {"ka_public"})
            self.assertIn("ka_private", public_pack.excluded_atoms)
            self.assertIn("private", public_pack.excluded_sources)
            self.assertEqual(set(private_pack.atoms), {"ka_public", "ka_private"})
            self.assertNotIn("ka_blocked", private_pack.atoms)
            self.assertTrue(private_pack.excluded_sources["blocked"].startswith("blocked_status"))

    def test_public_status_without_public_rights_or_license_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source("pending", status="release_eligible")
            atom = self.atom("ka_pending", "pending", "待审核方法", status="release_eligible")
            source_path, atom_path = self.write_pack(root, [source], [atom])

            pack = load_knowledge_pack(source_path, atom_path)

            self.assertEqual(pack.sources, {})
            self.assertEqual(pack.atoms, {})
            self.assertIn("not_public_rights", pack.excluded_sources["pending"])

    def test_unknown_source_edge_fails_pack_loading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path, atom_path = self.write_pack(
                root,
                [self.source("known")],
                [self.atom("ka_broken", "missing", "断裂的来源链")],
            )

            with self.assertRaisesRegex(ValueError, "unknown source"):
                load_knowledge_pack(source_path, atom_path, mode="private")

    def test_missing_atom_runtime_provenance_fails_pack_loading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source("public", public=True)
            atom = self.atom("ka_missing_locator", "public", "客户需求必须验证", public=True)
            del atom["source_refs"][0]["locator"]
            source_path, atom_path = self.write_pack(root, [source], [atom])

            with self.assertRaisesRegex(ValueError, "portable locator"):
                load_knowledge_pack(source_path, atom_path)

    def test_search_is_deterministic_and_exposes_confidence_time_conflict_and_atom_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = [self.source("public", public=True)]
            atoms = [
                self.atom(
                    "ka_alpha",
                    "public",
                    "客户访谈需要记录真实购买信号",
                    public=True,
                    relations=[{"type": "contradicts", "atom_id": "ka_beta"}],
                ),
                self.atom(
                    "ka_beta",
                    "public",
                    "客户访谈只需要记录口头兴趣",
                    public=True,
                    relations=[{"type": "contradicts", "atom_id": "ka_alpha"}],
                ),
            ]
            source_path, atom_path = self.write_pack(root, sources, atoms)
            pack = load_knowledge_pack(source_path, atom_path)

            first = search_knowledge_pack(pack, "客户真实购买信号", limit=2)
            second = search_knowledge_pack(pack, "客户真实购买信号", limit=2)

            self.assertEqual(first, second)
            hit = first["results"][0]
            self.assertEqual(hit["atom_id"], "ka_alpha")
            self.assertEqual(hit["source_attribution"]["atom_ids"], ["ka_alpha"])
            self.assertEqual(hit["conflicts"], ["ka_beta"])
            self.assertEqual(hit["temporal"]["source_date"], "2026-08-20")
            self.assertIn("knowledge", hit["confidence"])

    def test_eval_rejects_answer_bearing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path, atom_path = self.write_pack(
                root,
                [self.source("public", public=True)],
                [self.atom("ka_one", "public", "客户需求必须验证", public=True)],
            )
            cases_path = root / "cases.jsonl"
            self.write_jsonl(
                cases_path,
                [
                    {
                        "case_id": "leak",
                        "query": "怎么核实需求",
                        "relevant_atom_ids": ["ka_one"],
                        "expected_answer": "客户需求必须验证",
                    }
                ],
            )

            with self.assertRaisesRegex(ValueError, "answer-leaking"):
                evaluate_recall(load_knowledge_pack(source_path, atom_path), cases_path)

    def test_concept_alias_expands_atoms_and_recommends_method(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atom = self.atom(
                "ka_payment", "public", "客户访谈需要记录真实购买承诺", public=True
            )
            concept = self.concept(
                "oc_payment", ["ka_payment"], ["M-001"], aliases=["愿不愿掏钱"]
            )
            method = self.method("M-001", ["ka_payment"], ["oc_payment"])
            source_path, atom_path = self.write_pack(
                root,
                [self.source("public", public=True)],
                [atom],
                concepts=[concept],
                methods=[method],
            )

            result = search_knowledge_pack(
                load_knowledge_pack(source_path, atom_path), "先找人聊聊愿不愿掏钱", limit=5
            )

            self.assertEqual(result["matched_concepts"][0]["concept_id"], "oc_payment")
            self.assertEqual(result["results"][0]["atom_id"], "ka_payment")
            self.assertEqual(result["recommended_methods"][0]["method_id"], "M-001")
            self.assertIn("oc_payment", result["results"][0]["matched_concept_ids"])
            hit = result["results"][0]
            self.assertEqual(hit["status"], "release_eligible")
            self.assertEqual(hit["decision_rule"], atom["decision_rule"])
            self.assertEqual(hit["procedure"], atom["procedure"])
            self.assertEqual(hit["source_refs"], atom["source_refs"])
            matched_concept = result["matched_concepts"][0]
            self.assertEqual(matched_concept["definition"], concept["definition"])
            self.assertEqual(matched_concept["anti_definition"], concept["anti_definition"])
            self.assertEqual(matched_concept["common_misuse"], concept["common_misuse"])
            recommended = result["recommended_methods"][0]
            self.assertEqual(recommended["inputs"], method["inputs"])
            self.assertEqual(recommended["steps"], method["steps"])
            self.assertEqual(recommended["decision_gates"], method["decision_gates"])
            self.assertEqual(recommended["quality_checks"], method["quality_checks"])

    def test_initial_atom_exposes_one_hop_concept_and_method_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atom = self.atom(
                "ka_inventory", "public", "库存周转必须先核对滞销记录", public=True
            )
            concept = self.concept("oc_payment", ["ka_inventory"], ["M-001"])
            method = self.method("M-001", ["ka_inventory"], ["oc_payment"])
            source_path, atom_path = self.write_pack(
                root,
                [self.source("public", public=True)],
                [atom],
                concepts=[concept],
                methods=[method],
            )

            result = search_knowledge_pack(
                load_knowledge_pack(source_path, atom_path), "怎么核对库存周转", limit=5
            )

            linked = next(
                row for row in result["matched_concepts"] if row["concept_id"] == "oc_payment"
            )
            self.assertEqual(linked["inference"], "linked_atom")
            self.assertEqual(linked["linked_atom_ids"], ["ka_inventory"])
            self.assertEqual(linked["definition"], concept["definition"])
            self.assertEqual(linked["anti_definition"], concept["anti_definition"])
            self.assertEqual(linked["common_misuse"], concept["common_misuse"])
            self.assertEqual(
                result["recommended_methods"][0]["matched_atom_ids"], ["ka_inventory"]
            )

    def test_search_returns_all_allowed_relation_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relations = [
                {"type": relation_type, "atom_id": "ka_target"}
                for relation_type in ("depends_on", "supports", "refines", "contradicts")
            ]
            atoms = [
                self.atom(
                    "ka_primary",
                    "public",
                    "客户验证主张",
                    public=True,
                    relations=relations,
                ),
                self.atom("ka_target", "public", "客户验证边界", public=True),
            ]
            source_path, atom_path = self.write_pack(
                root, [self.source("public", public=True)], atoms
            )

            result = search_knowledge_pack(
                load_knowledge_pack(source_path, atom_path), "客户验证主张", limit=1
            )

            self.assertEqual(
                {row["type"] for row in result["results"][0]["relations"]},
                {"depends_on", "supports", "refines", "contradicts"},
            )
            self.assertEqual(result["results"][0]["conflicts"], ["ka_target"])

    def test_eval_reports_atom_method_and_concept_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atom = self.atom(
                "ka_payment", "public", "客户访谈需要记录真实购买承诺", public=True
            )
            concept = self.concept("oc_payment", ["ka_payment"], ["M-001"])
            method = self.method("M-001", ["ka_payment"], ["oc_payment"])
            source_path, atom_path = self.write_pack(
                root,
                [self.source("public", public=True)],
                [atom],
                concepts=[concept],
                methods=[method],
            )
            cases_path = root / "cases.jsonl"
            self.write_jsonl(
                cases_path,
                [
                    {
                        "case_id": "colloquial",
                        "case_kind": "colloquial_alias",
                        "query": "这人到底愿不愿掏钱",
                        "relevant_atom_ids": ["ka_payment"],
                        "relevant_method_ids": ["M-001"],
                        "relevant_concept_ids": ["oc_payment"],
                    }
                ],
            )

            result = evaluate_recall(load_knowledge_pack(source_path, atom_path), cases_path)

            self.assertEqual(result["atom_recall_at_5"], 1.0)
            self.assertEqual(result["atom_top1"], 1.0)
            self.assertEqual(result["atom_mrr"], 1.0)
            self.assertEqual(result["method_recall_at_3"], 1.0)
            self.assertEqual(result["concept_match_recall"], 1.0)
            self.assertTrue(result["passed"])

    def test_public_mode_excludes_private_concepts_and_methods(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atom = self.atom("ka_public", "public", "公开客户方法", public=True)
            concept = self.concept(
                "oc_private", ["ka_public"], ["M-PRIVATE"], public=False
            )
            method = self.method(
                "M-PRIVATE", ["ka_public"], ["oc_private"], public=False
            )
            source_path, atom_path = self.write_pack(
                root,
                [self.source("public", public=True)],
                [atom],
                concepts=[concept],
                methods=[method],
            )

            pack = load_knowledge_pack(source_path, atom_path)

            self.assertEqual(pack.concepts, {})
            self.assertEqual(pack.methods, {})
            self.assertIn("oc_private", pack.excluded_concepts)
            self.assertIn("M-PRIVATE", pack.excluded_methods)


if __name__ == "__main__":
    unittest.main(verbosity=2)
