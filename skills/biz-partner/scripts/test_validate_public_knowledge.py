#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from render_source_attribution import material_attribution_segments  # noqa: E402
from validate_public_knowledge import (  # noqa: E402
    MAINTAINER_NAME,
    MINIMUM_COUNTS,
    load_jsonl,
    validate_atoms,
    validate_concepts,
    validate_cross_references,
    validate_manifest,
    validate_methods,
    validate_knowledge_network,
    validate_pack,
    validate_sources,
)


class PublicKnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pack_root = SKILL_DIR / "public-knowledge"
        cls.sources = load_jsonl(cls.pack_root / "sources.jsonl")
        cls.atoms = load_jsonl(cls.pack_root / "atoms.jsonl")
        cls.concepts = load_jsonl(cls.pack_root / "concepts.jsonl")
        cls.methods = load_jsonl(cls.pack_root / "methods.jsonl")

    def test_bundled_pack_passes_strict_validation(self) -> None:
        result = validate_pack(SKILL_DIR)
        self.assertGreaterEqual(result["sources"], MINIMUM_COUNTS["sources"])
        self.assertGreaterEqual(result["atoms"], MINIMUM_COUNTS["atoms"])
        self.assertGreaterEqual(result["methods"], MINIMUM_COUNTS["methods"])
        self.assertGreaterEqual(result["recall_at_5"], 0.85)
        self.assertGreaterEqual(result["method_recall_at_3"], 0.85)
        self.assertGreaterEqual(result["concept_match_recall"], 0.85)
        self.assertGreaterEqual(result["knowledge_nodes"], MINIMUM_COUNTS["knowledge_nodes"])
        self.assertGreaterEqual(result["knowledge_edges"], MINIMUM_COUNTS["knowledge_edges"])

    def test_generated_knowledge_network_must_match_structured_pack(self) -> None:
        manifest = json.loads((self.pack_root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            validate_knowledge_network(self.pack_root, manifest),
            {
                "knowledge_nodes": manifest["counts"]["knowledge_nodes"],
                "knowledge_edges": manifest["counts"]["knowledge_edges"],
            },
        )
        with tempfile.TemporaryDirectory() as raw:
            copied = Path(raw) / "public-knowledge"
            shutil.copytree(self.pack_root, copied)
            (copied / "knowledge-network.md").write_text("stale\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing or stale"):
                validate_knowledge_network(copied, manifest)

    def test_human_readable_pack_has_no_generated_punctuation_artifacts(self) -> None:
        for name in ("USAGE.md", "methods.md", "concept-dictionary.md"):
            text = (self.pack_root / name).read_text(encoding="utf-8")
            self.assertNotIn("。。", text, name)
            self.assertNotIn("用在：用于", text, name)

    def test_public_atom_field_whitelist_rejects_raw_material(self) -> None:
        sources = deepcopy(self.sources)
        atoms = deepcopy(self.atoms)
        source_ids = validate_sources(sources)
        atoms[0]["raw_text"] = "excluded source prose"
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            validate_atoms(atoms, source_ids)

    def test_source_identity_cannot_enter_atom_payload(self) -> None:
        sources = deepcopy(self.sources)
        atoms = deepcopy(self.atoms)
        source_ids = validate_sources(sources)
        atoms[0]["limits"][0] = MAINTAINER_NAME + " is the runtime user"
        with self.assertRaisesRegex(ValueError, "identity leaked"):
            validate_atoms(atoms, source_ids)

    def test_atom_nested_rights_whitelist_rejects_unknown_field(self) -> None:
        sources = deepcopy(self.sources)
        atoms = deepcopy(self.atoms)
        source_ids = validate_sources(sources)
        atoms[0]["rights"]["unexpected_nested_field"] = True
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            validate_atoms(atoms, source_ids)

    def test_atom_nested_confidence_whitelist_rejects_unknown_field(self) -> None:
        sources = deepcopy(self.sources)
        atoms = deepcopy(self.atoms)
        source_ids = validate_sources(sources)
        atoms[0]["confidence"]["unexpected_nested_field"] = "high"
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            validate_atoms(atoms, source_ids)

    def test_atom_locator_whitelist_rejects_unknown_field(self) -> None:
        sources = deepcopy(self.sources)
        atoms = deepcopy(self.atoms)
        source_ids = validate_sources(sources)
        atoms[0]["source_refs"][0]["locator"]["unexpected_nested_field"] = True
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            validate_atoms(atoms, source_ids)

    def test_concept_nested_rights_whitelist_rejects_unknown_field(self) -> None:
        sources = deepcopy(self.sources)
        atoms = deepcopy(self.atoms)
        concepts = deepcopy(self.concepts)
        source_ids = validate_sources(sources)
        atom_ids = validate_atoms(atoms, source_ids)
        concepts[0]["rights"]["unexpected_nested_field"] = True
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            validate_concepts(concepts, atom_ids, source_ids)

    def test_manifest_whitelist_rejects_unknown_field(self) -> None:
        manifest = json.loads((self.pack_root / "manifest.json").read_text(encoding="utf-8"))
        manifest["unexpected_top_level_field"] = True
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            validate_manifest(self.pack_root, manifest)

    def test_manifest_enforces_minimums_but_uses_dynamic_actual_counts(self) -> None:
        manifest = json.loads((self.pack_root / "manifest.json").read_text(encoding="utf-8"))
        actual = dict(manifest["counts"])
        validate_manifest(self.pack_root, manifest, actual)
        below = deepcopy(manifest)
        below["counts"]["atoms"] = MINIMUM_COUNTS["atoms"] - 1
        below["atom_count"] = MINIMUM_COUNTS["atoms"] - 1
        with self.assertRaisesRegex(ValueError, "below minimum"):
            validate_manifest(self.pack_root, below, dict(below["counts"]))

    def test_concept_aliases_field_is_required_but_may_be_empty(self) -> None:
        sources = deepcopy(self.sources)
        atoms = deepcopy(self.atoms)
        concepts = deepcopy(self.concepts)
        source_ids = validate_sources(sources)
        atom_ids = validate_atoms(atoms, source_ids)
        concepts[0]["aliases"] = []
        validate_concepts(concepts, atom_ids, source_ids)
        del concepts[0]["aliases"]
        with self.assertRaisesRegex(ValueError, "missing fields.*aliases"):
            validate_concepts(concepts, atom_ids, source_ids)

    def test_concept_method_edges_must_not_dangle(self) -> None:
        sources = deepcopy(self.sources)
        atoms = deepcopy(self.atoms)
        concepts = deepcopy(self.concepts)
        methods = deepcopy(self.methods)
        source_ids = validate_sources(sources)
        atom_ids = validate_atoms(atoms, source_ids)
        concept_ids = validate_concepts(concepts, atom_ids, source_ids)
        method_ids = validate_methods(methods, atom_ids, concept_ids)
        concepts[0]["related_methods"] = ["M-999"]
        with self.assertRaisesRegex(ValueError, "unknown methods"):
            validate_cross_references(concepts, methods, method_ids)

    def test_method_concept_ids_must_not_contain_duplicates(self) -> None:
        sources = deepcopy(self.sources)
        atoms = deepcopy(self.atoms)
        concepts = deepcopy(self.concepts)
        methods = deepcopy(self.methods)
        source_ids = validate_sources(sources)
        atom_ids = validate_atoms(atoms, source_ids)
        concept_ids = validate_concepts(concepts, atom_ids, source_ids)
        methods[0]["concept_ids"] = [
            methods[0]["concept_ids"][0],
            methods[0]["concept_ids"][0],
        ]
        with self.assertRaisesRegex(ValueError, "must not contain duplicates"):
            validate_methods(methods, atom_ids, concept_ids)

    def test_project_paraphrase_requires_exact_source_boundary(self) -> None:
        sources = deepcopy(self.sources)
        curated = next(row for row in sources if row["source_id"] != "maintainer_public_writing_v1")
        curated["source_expression_redistribution"] = "granted"
        with self.assertRaisesRegex(ValueError, "boundary is invalid"):
            validate_sources(sources)

    def test_curated_source_rejects_bibliographic_identity_fields(self) -> None:
        sources = deepcopy(self.sources)
        curated = next(row for row in sources if row["source_id"] != "maintainer_public_writing_v1")
        curated["title"] = "must not be public"
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            validate_sources(sources)

    def test_project_paraphrase_requires_exact_atom_boundary(self) -> None:
        sources = deepcopy(self.sources)
        atoms = deepcopy(self.atoms)
        source_ids = validate_sources(sources)
        curated_atom = next(
            row for row in atoms if row["provenance_type"] == "public_curated_idea_synthesis"
        )
        curated_atom["authorization_status"] = "public_release_authorized"
        with self.assertRaisesRegex(ValueError, "boundary is invalid"):
            validate_atoms(atoms, source_ids)

    def test_material_curated_atom_has_no_named_attribution(self) -> None:
        atom = next(
            row for row in self.atoms if row["provenance_type"] == "public_curated_idea_synthesis"
        )
        source_id = atom["source_refs"][0]["source_id"]
        handoff = {
            "claims": [{"claim_id": "c1", "supporting_refs": ["e1"]}],
            "evidence_refs": [
                {
                    "id": "e1",
                    "source": source_id,
                    "evidence_kind": "knowledge_atom",
                    "atom_id": atom["atom_id"],
                }
            ],
        }
        self.assertEqual(material_attribution_segments(handoff, self.sources, self.atoms), [])

    def test_material_maintainer_atom_attributes_fish_once(self) -> None:
        atom_id = "ka_maintainer_post_006"
        source_id = "maintainer_public_writing_v1"
        handoff = {
            "claims": [{"claim_id": "c1", "supporting_refs": ["e1"]}],
            "evidence_refs": [
                {
                    "id": "e1",
                    "source": source_id,
                    "evidence_kind": "knowledge_atom",
                    "atom_id": atom_id,
                }
            ],
        }
        segments = material_attribution_segments(handoff, self.sources, self.atoms)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["source_role"], "external_named_source")
        self.assertEqual(segments[0]["text"].count(MAINTAINER_NAME), 1)

    def test_retrieved_but_unused_atom_produces_no_attribution(self) -> None:
        handoff = {
            "claims": [{"claim_id": "c1", "supporting_refs": ["user_fact"]}],
            "evidence_refs": [
                {"id": "user_fact", "source": "turn_1", "evidence_kind": "user_input"},
                {
                    "id": "unused",
                    "source": "maintainer_public_writing_v1",
                    "evidence_kind": "knowledge_atom",
                    "atom_id": "ka_maintainer_post_006",
                },
            ],
        }
        self.assertEqual(material_attribution_segments(handoff, self.sources, self.atoms), [])

    def test_maintainer_source_cannot_be_runtime_user(self) -> None:
        sources = deepcopy(self.sources)
        maintainer = next(row for row in sources if row["source_id"] == "maintainer_public_writing_v1")
        maintainer["relationship_to_runtime_user"] = "runtime_user"
        handoff = {
            "claims": [{"claim_id": "c1", "supporting_refs": ["e1"]}],
            "evidence_refs": [
                {
                    "id": "e1",
                    "source": "maintainer_public_writing_v1",
                    "evidence_kind": "knowledge_atom",
                    "atom_id": "ka_maintainer_post_006",
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "external to runtime user"):
            material_attribution_segments(handoff, sources, self.atoms)


if __name__ == "__main__":
    unittest.main()
