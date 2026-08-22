#!/usr/bin/env python3
"""Regression tests for the shared Atom v2 runtime contract."""

from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from atom_contract import sha256_text, validate_atom_v2  # noqa: E402


def valid_atom() -> dict[str, object]:
    canonical = "客户需求必须通过当前行为证据验证"
    return {
        "atom_id": "ka_contract_001",
        "schema_version": "2.0",
        "canonical": canonical,
        "claim_kind": "decision_rule",
        "actionability": "workflow_gate",
        "domain": ["business", "customer"],
        "decision_rule": canonical,
        "limits": ["需要当前客户证据"],
        "source_refs": [
            {
                "source_id": "source_public",
                "locator": {"file": "evidence/customer.md", "lines": "4-6"},
                "quote_hash": sha256_text("source excerpt"),
            }
        ],
        "provenance_type": "reviewed_source",
        "confidence": {
            "extraction": "high",
            "attribution": "high",
            "interpretation": "medium",
            "operational": "unknown",
        },
        "source_date": "2026-08-20",
        "temporal_scope": "source-time",
        "bias_flags": [],
        "relations": [],
        "content_hash": sha256_text(canonical),
        "pipeline_run": "run_contract_test_001",
        "status": "release_eligible",
        "rights": {"redistribution": "redistribution_allowed"},
    }


class AtomContractTests(unittest.TestCase):
    def test_valid_portable_atom_passes(self) -> None:
        validate_atom_v2(valid_atom())

    def test_missing_runtime_fields_fail_closed(self) -> None:
        for field in ("content_hash", "pipeline_run", "confidence", "source_date"):
            with self.subTest(field=field):
                atom = deepcopy(valid_atom())
                del atom[field]
                with self.assertRaises(ValueError):
                    validate_atom_v2(atom)

    def test_content_hash_must_self_bind_canonical(self) -> None:
        atom = valid_atom()
        atom["canonical"] = "changed claim"
        with self.assertRaisesRegex(ValueError, "content_hash mismatch"):
            validate_atom_v2(atom)

    def test_all_confidence_dimensions_are_required(self) -> None:
        atom = valid_atom()
        del atom["confidence"]["operational"]
        with self.assertRaisesRegex(ValueError, "confidence.operational"):
            validate_atom_v2(atom)

    def test_source_ref_requires_locator_and_quote_hash(self) -> None:
        for field in ("locator", "quote_hash"):
            with self.subTest(field=field):
                atom = deepcopy(valid_atom())
                del atom["source_refs"][0][field]
                with self.assertRaises(ValueError):
                    validate_atom_v2(atom)

    def test_local_absolute_or_parent_traversal_locator_is_rejected(self) -> None:
        local_paths = (
            "/" + "Users/example/private.md",
            ".." + "/private.md",
            "C:" + "\\" + "private.md",
        )
        for file_value in local_paths:
            with self.subTest(file_value=file_value):
                atom = deepcopy(valid_atom())
                atom["source_refs"][0]["locator"]["file"] = file_value
                with self.assertRaisesRegex(ValueError, "portable"):
                    validate_atom_v2(atom)

    def test_private_local_locator_requires_explicit_opt_in(self) -> None:
        atom = deepcopy(valid_atom())
        atom["source_refs"][0]["locator"]["file"] = "/" + "Users/example/private.md"
        validate_atom_v2(atom, allow_private_local_locator=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
