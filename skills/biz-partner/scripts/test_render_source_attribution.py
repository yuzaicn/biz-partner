#!/usr/bin/env python3

from __future__ import annotations

import json
import inspect
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from atom_contract import sha256_text  # noqa: E402
import render_source_attribution as attribution_module  # noqa: E402
from render_source_attribution import material_attribution_segments, material_attributions  # noqa: E402



class SourceAttributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sources = [
            {
                "source_id": "source_named_author",
                "public_attribution_name": "Named Author",
                "attribution_mode": "when_materially_used",
                "relationship_to_runtime_user": "external_named_source",
                "ownership_status": "not_claimed",
                "rights_status": "redistribution_allowed",
                "license": {
                    "id": "CC-BY-4.0",
                    "version": "4.0",
                    "scope": "redistribution_and_derivatives",
                },
                "status": "release_eligible",
                "authorization_status": "public_release_authorized",
                "release_decision": "approved_for_public_release",
            }
        ]
        canonical = "Attribute a named source when its knowledge atom materially supports a claim."
        source_quote = "Named source attribution evidence."
        self.atoms = [
            {
                "schema_version": "2.0",
                "atom_id": "ka_named_author_001",
                "canonical": canonical,
                "claim_kind": "decision_rule",
                "actionability": "operational",
                "domain": ["source_attribution"],
                "decision_rule": canonical,
                "limits": ["Applies only when a registered knowledge atom materially supports a claim."],
                "source_refs": [
                    {
                        "source_id": "source_named_author",
                        "locator": {
                            "file": "references/source-attribution.md",
                            "lines": "1-1",
                        },
                        "quote_hash": sha256_text(source_quote),
                    }
                ],
                "provenance_type": "curated_source",
                "confidence": {
                    "extraction": "high",
                    "attribution": "high",
                    "interpretation": "high",
                    "operational": "high",
                },
                "source_date": None,
                "temporal_scope": "general",
                "bias_flags": [],
                "relations": [],
                "content_hash": sha256_text(canonical),
                "pipeline_run": "test-render-source-attribution",
                "rights": {
                    "redistribution": "redistribution_allowed",
                    "license": {
                        "id": "CC-BY-4.0",
                        "version": "4.0",
                        "scope": "redistribution_and_derivatives",
                    },
                },
                "status": "release_eligible",
                "authorization_status": "redistribution_authorized",
                "release_decision": "public_release_approved",
            }
        ]
        self.handoff = {
            "claims": [{"claim_id": "c1", "supporting_refs": ["e1"]}],
            "evidence_refs": [
                {
                    "id": "e1",
                    "source": "source_named_author",
                    "evidence_kind": "knowledge_atom",
                    "atom_id": "ka_named_author_001",
                }
            ],
        }

    def test_material_source_is_attributed_once_with_audit_chain(self) -> None:
        handoff = {
            "claims": [
                {"claim_id": "c1", "supporting_refs": ["e1"]},
                {"claim_id": "c2", "supporting_refs": ["e1", "e2"]},
            ],
            "evidence_refs": [
                {
                    "id": "e1",
                    "source": "source_named_author",
                    "evidence_kind": "knowledge_atom",
                    "atom_id": "ka_named_author_001",
                },
                {"id": "e2", "source": "turn_12", "evidence_kind": "user_input"},
            ],
        }
        self.assertEqual(
            material_attributions(handoff, self.sources, self.atoms),
            [
                {
                    "source_id": "source_named_author",
                    "display_name": "Named Author",
                    "source_role": "external_named_source",
                    "claim_ids": ["c1", "c2"],
                    "evidence_ids": ["e1"],
                    "atom_ids": ["ka_named_author_001"],
                    "first_claim_id": "c1",
                }
            ],
        )

    def test_unused_source_evidence_is_not_attributed(self) -> None:
        handoff = {
            "claims": [{"claim_id": "c1", "supporting_refs": ["user_fact"]}],
            "evidence_refs": [
                {"id": "user_fact", "source": "turn_12", "evidence_kind": "user_input"},
                {
                    "id": "unused",
                    "source": "source_named_author",
                    "evidence_kind": "knowledge_atom",
                    "atom_id": "ka_named_author_001",
                },
            ],
        }
        self.assertEqual(material_attributions(handoff, self.sources, self.atoms), [])

    def test_material_attribution_renders_one_typed_segment(self) -> None:
        segments = material_attribution_segments(self.handoff, self.sources, self.atoms)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["kind"], "source_attribution")
        self.assertEqual(segments[0]["source_id"], "source_named_author")
        self.assertEqual(segments[0]["source_role"], "external_named_source")
        self.assertEqual(segments[0]["first_claim_id"], "c1")
        self.assertEqual(segments[0]["claim_ids"], ["c1"])
        self.assertEqual(segments[0]["evidence_ids"], ["e1"])
        self.assertEqual(segments[0]["atom_ids"], ["ka_named_author_001"])
        self.assertNotIn("display_name", segments[0])
        self.assertEqual(segments[0]["text"].count("Named Author"), 1)

    def test_raw_segment_renderer_is_not_public_api(self) -> None:
        self.assertFalse(hasattr(attribution_module, "render_attribution_segments"))

    def test_segment_api_rejects_runtime_user_role(self) -> None:
        sources = deepcopy(self.sources)
        sources[0]["relationship_to_runtime_user"] = "runtime_user"
        with self.assertRaisesRegex(ValueError, "external to runtime user"):
            material_attribution_segments(self.handoff, sources, self.atoms)

    def test_segment_api_cannot_bypass_source_registry(self) -> None:
        sources = deepcopy(self.sources)
        sources[0]["source_id"] = "unregistered_source"
        with self.assertRaisesRegex(ValueError, "unknown source"):
            material_attribution_segments(self.handoff, sources, self.atoms)

    def test_named_source_must_be_external_to_runtime_user(self) -> None:
        sources = deepcopy(self.sources)
        sources[0]["relationship_to_runtime_user"] = "runtime_user"
        with self.assertRaisesRegex(ValueError, "external to runtime user"):
            material_attributions(self.handoff, sources, self.atoms)

    def test_named_source_ownership_must_not_be_claimed(self) -> None:
        sources = deepcopy(self.sources)
        sources[0]["ownership_status"] = "claimed_by_runtime_user"
        with self.assertRaisesRegex(ValueError, "ownership must be not_claimed"):
            material_attributions(self.handoff, sources, self.atoms)

    def test_missing_display_name_fails_for_named_source(self) -> None:
        sources = deepcopy(self.sources)
        del sources[0]["public_attribution_name"]
        with self.assertRaisesRegex(ValueError, "public_attribution_name"):
            material_attributions(self.handoff, sources, self.atoms)

    def test_public_mode_rejects_candidate_source(self) -> None:
        sources = self.private_candidate_sources()
        with self.assertRaisesRegex(ValueError, "not public-release eligible"):
            material_attributions(self.handoff, sources, self.atoms)

    def test_public_mode_rejects_private_rights(self) -> None:
        sources = deepcopy(self.sources)
        sources[0]["rights_status"] = "private" + "_research_only"
        with self.assertRaisesRegex(ValueError, "rights are not public-release eligible"):
            material_attributions(self.handoff, sources, self.atoms)

    def test_public_mode_requires_source_license(self) -> None:
        sources = deepcopy(self.sources)
        del sources[0]["license"]
        with self.assertRaisesRegex(ValueError, "source license must be an object"):
            material_attributions(self.handoff, sources, self.atoms)

    def test_public_mode_rejects_unknown_source_license(self) -> None:
        for license_id in (
            "unknown",
            " UNKNOWN ",
            "pending",
            "unverified\t",
            "TBD",
            "N/A",
            "not verified",
            "rights pending",
        ):
            with self.subTest(license_id=license_id):
                sources = deepcopy(self.sources)
                sources[0]["license"]["id"] = license_id
                with self.assertRaises(ValueError):
                    material_attributions(self.handoff, sources, self.atoms)

    def test_public_mode_rejects_unverified_source_license_version(self) -> None:
        for version in (
            "unknown",
            " UNKNOWN ",
            "pending",
            "unverified\t",
            "TBD",
            "N/A",
            "not verified",
            "rights pending",
        ):
            with self.subTest(version=version):
                sources = deepcopy(self.sources)
                sources[0]["license"]["version"] = version
                with self.assertRaises(ValueError):
                    material_attributions(self.handoff, sources, self.atoms)

    def test_public_mode_rejects_pending_authorization(self) -> None:
        sources = deepcopy(self.sources)
        sources[0]["authorization_status"] = "pending_source_rights_review"
        with self.assertRaisesRegex(ValueError, "authorization_status blocks public release"):
            material_attributions(self.handoff, sources, self.atoms)

    def test_public_mode_rejects_unapproved_source_decisions(self) -> None:
        for field, value in (
            ("authorization_status", "denied"),
            ("authorization_status", "not_authorized"),
            ("release_decision", "no_go"),
            ("release_decision", "revoked"),
        ):
            with self.subTest(field=field, value=value):
                sources = deepcopy(self.sources)
                sources[0][field] = value
                with self.assertRaisesRegex(ValueError, f"source {field} blocks public release"):
                    material_attributions(self.handoff, sources, self.atoms)

    def test_public_mode_rejects_candidate_atom_even_with_public_source(self) -> None:
        atoms = self.private_candidate_atoms()
        with self.assertRaisesRegex(ValueError, "atom is not public-release eligible"):
            material_attributions(self.handoff, self.sources, atoms)

    def test_runtime_contract_fields_are_required(self) -> None:
        for field, message in (
            ("content_hash", "atom content_hash"),
            ("pipeline_run", "atom pipeline_run"),
            ("confidence", "atom confidence"),
        ):
            with self.subTest(field=field):
                atoms = deepcopy(self.atoms)
                del atoms[0][field]
                with self.assertRaisesRegex(ValueError, message):
                    material_attributions(self.handoff, self.sources, atoms)

    def test_public_mode_rejects_private_atom_rights(self) -> None:
        atoms = deepcopy(self.atoms)
        atoms[0]["rights"]["redistribution"] = "private" + "_research_only"
        with self.assertRaisesRegex(ValueError, "atom rights are not public-release eligible"):
            material_attributions(self.handoff, self.sources, atoms)

    def test_missing_atom_status_fails_closed(self) -> None:
        atoms = deepcopy(self.atoms)
        del atoms[0]["status"]
        with self.assertRaisesRegex(ValueError, "atom status"):
            material_attributions(self.handoff, self.sources, atoms)

    def test_missing_atom_rights_fail_closed(self) -> None:
        atoms = deepcopy(self.atoms)
        del atoms[0]["rights"]
        with self.assertRaisesRegex(ValueError, "atom rights must be an object"):
            material_attributions(self.handoff, self.sources, atoms)

    def test_public_mode_requires_atom_license(self) -> None:
        atoms = deepcopy(self.atoms)
        del atoms[0]["rights"]["license"]
        with self.assertRaisesRegex(ValueError, "atom license must be an object"):
            material_attributions(self.handoff, self.sources, atoms)

    def test_public_mode_rejects_invalid_atom_license_scope(self) -> None:
        for license_id in (
            "unknown",
            " UNKNOWN ",
            "pending",
            "unverified\t",
            "TBD",
            "N/A",
            "not verified",
            "rights pending",
        ):
            with self.subTest(license_id=license_id):
                atoms = deepcopy(self.atoms)
                atoms[0]["rights"]["license"]["id"] = license_id
                with self.assertRaises(ValueError):
                    material_attributions(self.handoff, self.sources, atoms)

        atoms = deepcopy(self.atoms)
        atoms[0]["rights"]["license"]["scope"] = "attribution_only"
        with self.assertRaisesRegex(ValueError, "atom license scope blocks public release"):
            material_attributions(self.handoff, self.sources, atoms)

    def test_public_mode_rejects_unverified_atom_license_version(self) -> None:
        for version in (
            "unknown",
            " UNKNOWN ",
            "pending",
            "unverified\t",
            "TBD",
            "N/A",
            "not verified",
            "rights pending",
        ):
            with self.subTest(version=version):
                atoms = deepcopy(self.atoms)
                atoms[0]["rights"]["license"]["version"] = version
                with self.assertRaises(ValueError):
                    material_attributions(self.handoff, self.sources, atoms)

    def test_public_mode_rejects_pending_atom_authorization(self) -> None:
        atoms = deepcopy(self.atoms)
        atoms[0]["authorization_status"] = "pending_atom_rights_review"
        with self.assertRaisesRegex(ValueError, "atom authorization_status blocks public release"):
            material_attributions(self.handoff, self.sources, atoms)

    def test_public_mode_rejects_unapproved_atom_decisions(self) -> None:
        for field, value in (
            ("authorization_status", "denied"),
            ("authorization_status", "not_authorized"),
            ("release_decision", "no_go"),
            ("release_decision", "revoked"),
        ):
            with self.subTest(field=field, value=value):
                atoms = deepcopy(self.atoms)
                atoms[0][field] = value
                with self.assertRaisesRegex(ValueError, f"atom {field} blocks public release"):
                    material_attributions(self.handoff, self.sources, atoms)

    def test_named_source_evidence_requires_atom_provenance(self) -> None:
        handoff = deepcopy(self.handoff)
        del handoff["evidence_refs"][0]["evidence_kind"]
        del handoff["evidence_refs"][0]["atom_id"]
        with self.assertRaisesRegex(ValueError, "not a knowledge atom"):
            material_attributions(handoff, self.sources, self.atoms)

    def test_atom_must_be_registered_to_the_same_source(self) -> None:
        sources = self.sources + [
            {
                "source_id": "source_other",
                "rights_status": "redistribution_allowed",
                "license": {
                    "id": "CC-BY-4.0",
                    "version": "4.0",
                    "scope": "redistribution_and_derivatives",
                },
                "status": "published",
            }
        ]
        atoms = deepcopy(self.atoms)
        atoms[0]["source_refs"][0]["source_id"] = "source_other"
        with self.assertRaisesRegex(ValueError, "atom/source mismatch"):
            material_attributions(self.handoff, sources, atoms)

    def test_unknown_atom_fails_closed(self) -> None:
        handoff = deepcopy(self.handoff)
        handoff["evidence_refs"][0]["atom_id"] = "ka_unknown"
        with self.assertRaisesRegex(ValueError, "unknown atom"):
            material_attributions(handoff, self.sources, self.atoms)

    def test_unknown_knowledge_source_fails_closed(self) -> None:
        handoff = deepcopy(self.handoff)
        handoff["evidence_refs"][0]["source"] = "source_unknown"
        with self.assertRaisesRegex(ValueError, "unknown source"):
            material_attributions(handoff, self.sources, self.atoms)

    def test_atom_reference_to_unknown_source_fails_closed(self) -> None:
        atoms = deepcopy(self.atoms)
        atoms[0]["source_refs"][0]["source_id"] = "source_unknown"
        with self.assertRaisesRegex(ValueError, "atom references unknown source"):
            material_attributions(self.handoff, self.sources, atoms)

    def test_missing_supporting_evidence_fails_closed(self) -> None:
        handoff = deepcopy(self.handoff)
        handoff["claims"][0]["supporting_refs"] = ["e_missing"]
        with self.assertRaisesRegex(ValueError, "missing supporting evidence"):
            material_attributions(handoff, self.sources, self.atoms)

    def test_empty_supporting_refs_fail_closed(self) -> None:
        handoff = deepcopy(self.handoff)
        handoff["claims"][0]["supporting_refs"] = []
        with self.assertRaisesRegex(ValueError, "non-empty list"):
            material_attributions(handoff, self.sources, self.atoms)

    def test_non_list_supporting_refs_fail_closed(self) -> None:
        handoff = deepcopy(self.handoff)
        handoff["claims"][0]["supporting_refs"] = "e1"
        with self.assertRaisesRegex(ValueError, "non-empty list"):
            material_attributions(handoff, self.sources, self.atoms)

    def test_non_string_supporting_ref_fails_closed(self) -> None:
        handoff = deepcopy(self.handoff)
        handoff["claims"][0]["supporting_refs"] = [1]
        with self.assertRaisesRegex(ValueError, "must be a non-empty string"):
            material_attributions(handoff, self.sources, self.atoms)

    def test_malformed_claims_fail_closed(self) -> None:
        handoff = deepcopy(self.handoff)
        handoff["claims"] = ["not-an-object"]
        with self.assertRaisesRegex(ValueError, "claim row 0 is not an object"):
            material_attributions(handoff, self.sources, self.atoms)

    def test_malformed_evidence_fails_closed(self) -> None:
        handoff = deepcopy(self.handoff)
        handoff["evidence_refs"] = ["not-an-object"]
        with self.assertRaisesRegex(ValueError, "evidence row 0 is not an object"):
            material_attributions(handoff, self.sources, self.atoms)

    def test_evidence_missing_source_fails_closed(self) -> None:
        handoff = deepcopy(self.handoff)
        del handoff["evidence_refs"][0]["source"]
        with self.assertRaisesRegex(ValueError, "evidence source"):
            material_attributions(handoff, self.sources, self.atoms)

    def test_malformed_atom_source_refs_fail_closed(self) -> None:
        atoms = deepcopy(self.atoms)
        atoms[0]["source_refs"] = "source_named_author"
        with self.assertRaisesRegex(ValueError, "source_refs must be a non-empty list"):
            material_attributions(self.handoff, self.sources, atoms)

    def test_duplicate_source_ids_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate source id"):
            material_attributions(self.handoff, self.sources * 2, self.atoms)

    def test_duplicate_atom_ids_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate atom id"):
            material_attributions(self.handoff, self.sources, self.atoms * 2)

    def test_duplicate_evidence_ids_fail_closed(self) -> None:
        handoff = deepcopy(self.handoff)
        handoff["evidence_refs"].append(deepcopy(handoff["evidence_refs"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate evidence id"):
            material_attributions(handoff, self.sources, self.atoms)

    def test_duplicate_claim_ids_fail_closed(self) -> None:
        handoff = deepcopy(self.handoff)
        handoff["claims"].append(deepcopy(handoff["claims"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate claim id"):
            material_attributions(handoff, self.sources, self.atoms)

    def test_duplicate_supporting_refs_fail_closed(self) -> None:
        handoff = deepcopy(self.handoff)
        handoff["claims"][0]["supporting_refs"] = ["e1", "e1"]
        with self.assertRaisesRegex(ValueError, "duplicate claim supporting ref"):
            material_attributions(handoff, self.sources, self.atoms)
    def test_public_material_api_parameter_set(self) -> None:
        self.assertEqual(
            set(inspect.signature(material_attributions).parameters),
            {"handoff", "source_rows", "atom_rows"},
        )

    def test_public_cli_help_exposes_registry_atom_handoff_inputs(self) -> None:
        command = [
            sys.executable,
            str(SCRIPT_DIR / "render_source_attribution.py"),
            "--help",
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn("source_registry", result.stdout)
        self.assertIn("atoms", result.stdout)
        self.assertIn("handoff", result.stdout)

    def private_candidate_sources(self) -> list[dict[str, object]]:
        sources = deepcopy(self.sources)
        sources[0]["status"] = "candidate"
        sources[0]["rights_status"] = "private" + "_research_only"
        sources[0]["authorization_status"] = "pending_source_rights_review"
        return sources

    def private_candidate_atoms(self) -> list[dict[str, object]]:
        atoms = deepcopy(self.atoms)
        atoms[0]["status"] = "candidate"
        atoms[0]["rights"]["redistribution"] = "private" + "_research_only"
        atoms[0]["authorization_status"] = "pending_atom_rights_review"
        return atoms


if __name__ == "__main__":
    unittest.main(verbosity=2)
