#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from render_source_attribution import material_attribution_segments  # noqa: E402
from validate_public_knowledge import (  # noqa: E402
    MAINTAINER_NAME,
    load_jsonl,
    validate_atoms,
    validate_concepts,
    validate_manifest,
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

    def test_bundled_pack_passes_strict_validation(self) -> None:
        result = validate_pack(SKILL_DIR)
        self.assertEqual(result["sources"], 11)
        self.assertEqual(result["atoms"], 40)
        self.assertEqual(result["recall_at_5"], 1.0)

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

    def test_project_paraphrase_requires_exact_source_boundary(self) -> None:
        sources = deepcopy(self.sources)
        book = next(row for row in sources if row["source_id"] != "maintainer_public_writing_v1")
        book["source_expression_redistribution"] = "granted"
        with self.assertRaisesRegex(ValueError, "boundary is invalid"):
            validate_sources(sources)

    def test_project_paraphrase_requires_exact_atom_boundary(self) -> None:
        sources = deepcopy(self.sources)
        atoms = deepcopy(self.atoms)
        source_ids = validate_sources(sources)
        book_atom = next(row for row in atoms if row["provenance_type"] == "public_book_idea_synthesis")
        book_atom["authorization_status"] = "public_release_authorized"
        with self.assertRaisesRegex(ValueError, "boundary is invalid"):
            validate_atoms(atoms, source_ids)

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
