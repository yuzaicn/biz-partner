#!/usr/bin/env python3

from __future__ import annotations

import copy
import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from build_knowledge_network import (
    GRAPH_FILE,
    NETWORK_FILE,
    build_artifacts,
    build_knowledge_graph,
    check_artifacts,
    main,
    render_knowledge_network,
    stable_anchor,
    write_artifacts,
)
from knowledge_runtime import load_knowledge_pack


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
PACK_ROOT = SKILL_ROOT / "public-knowledge"


class KnowledgeNetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pack = load_knowledge_pack(
            PACK_ROOT / "sources.jsonl", PACK_ROOT / "atoms.jsonl", mode="public"
        )
        cls.metadata = {
            "pack_id": "test-pack",
            "pack_version": "1.0.0",
            "mode": "public",
        }
        cls.graph = build_knowledge_graph(cls.pack, cls.metadata)

    def test_each_eligible_record_has_one_unique_node(self) -> None:
        expected = {
            *(f"source:{record_id}" for record_id in self.pack.sources),
            *(f"atom:{record_id}" for record_id in self.pack.atoms),
            *(f"concept:{record_id}" for record_id in self.pack.concepts),
            *(f"method:{record_id}" for record_id in self.pack.methods),
        }
        actual = [row["node_id"] for row in self.graph["nodes"]]
        self.assertEqual(set(actual), expected)
        self.assertEqual(len(actual), len(set(actual)))
        self.assertEqual(self.graph["counts"]["nodes"], len(actual))

    def test_edges_are_unique_complete_and_not_dangling(self) -> None:
        expected: set[tuple[str, str, str, bool]] = set()
        for atom_id, atom in self.pack.atoms.items():
            for ref in atom["source_refs"]:
                expected.add(
                    (f"atom:{atom_id}", "derived_from", f"source:{ref['source_id']}", True)
                )
            for relation in atom["relations"]:
                if relation["atom_id"] in self.pack.atoms:
                    expected.add(
                        (
                            f"atom:{atom_id}",
                            relation["type"],
                            f"atom:{relation['atom_id']}",
                            relation["type"] != "contradicts",
                        )
                    )
        for concept_id, concept in self.pack.concepts.items():
            for atom_id in concept["source_atoms"]:
                expected.add(
                    (f"concept:{concept_id}", "grounded_by", f"atom:{atom_id}", True)
                )
            for method_id in concept["related_methods"]:
                expected.add(
                    (
                        f"concept:{concept_id}",
                        "related_to_method",
                        f"method:{method_id}",
                        True,
                    )
                )
        for method_id, method in self.pack.methods.items():
            for atom_id in method["atom_ids"]:
                expected.add(
                    (f"method:{method_id}", "uses_atom", f"atom:{atom_id}", True)
                )
            for concept_id in method["concept_ids"]:
                expected.add(
                    (
                        f"method:{method_id}",
                        "uses_concept",
                        f"concept:{concept_id}",
                        True,
                    )
                )

        actual = [
            (row["from"], row["type"], row["to"], row["directed"])
            for row in self.graph["edges"]
        ]
        node_ids = {row["node_id"] for row in self.graph["nodes"]}
        self.assertEqual(set(actual), expected)
        self.assertEqual(len(actual), len(set(actual)))
        self.assertTrue(
            all(source in node_ids and target in node_ids for source, _, target, _ in actual)
        )
        self.assertEqual(self.graph["counts"]["edges"], len(actual))

    def test_all_relative_hrefs_resolve_to_unique_markdown_anchors(self) -> None:
        markdown = render_knowledge_network(self.pack, self.graph)
        anchors = re.findall(r"(?m)^### ([a-z0-9_-]+)$", markdown)
        self.assertEqual(len(anchors), len(set(anchors)))
        hrefs = [row["href"] for row in self.graph["nodes"]]
        self.assertEqual(len(hrefs), len(set(hrefs)))
        for href in hrefs:
            filename, fragment = href.split("#", 1)
            self.assertEqual(filename, NETWORK_FILE)
            self.assertIn(fragment, anchors)

    def test_generation_is_byte_deterministic(self) -> None:
        first = build_artifacts(PACK_ROOT, "public")
        second = build_artifacts(PACK_ROOT, "public")
        self.assertEqual(first, second)
        self.assertEqual(
            json.loads(first[GRAPH_FILE])["nodes"],
            sorted(
                json.loads(first[GRAPH_FILE])["nodes"],
                key=lambda row: (
                    {"source": 0, "atom": 1, "concept": 2, "method": 3}[row["kind"]],
                    row["record_id"],
                ),
            ),
        )

    def test_untrusted_record_text_is_plain_markdown_not_executable_html(self) -> None:
        pack = copy.deepcopy(self.pack)
        malicious = (
            '<script>alert(1)</script> <img src=x onerror=alert(2)> '
            '[click](javascript:alert(3)) ![image](javascript:alert(4))'
        )
        source = next(iter(pack.sources.values()))
        source["title"] = malicious
        atom = next(iter(pack.atoms.values()))
        atom["canonical"] = malicious
        concept = next(iter(pack.concepts.values()))
        concept["term"] = malicious
        concept["definition"] = malicious
        method = next(iter(pack.methods.values()))
        method["title"] = malicious
        method["purpose"] = malicious
        graph = build_knowledge_graph(pack, self.metadata)
        markdown = render_knowledge_network(pack, graph)
        lowered = markdown.casefold()
        self.assertNotIn("<script", lowered)
        self.assertNotIn("</script>", lowered)
        self.assertNotIn("<img", lowered)
        self.assertNotIn("](javascript:", lowered)
        self.assertNotIn("![image]", lowered)
        self.assertIn("&lt;script&gt;", markdown)
        self.assertIn("javascript:alert", lowered)

    def test_unsafe_ids_cannot_enter_fragment_markup(self) -> None:
        anchor = stable_anchor("atom", '\"><script>alert(1)</script>')
        self.assertRegex(anchor, r"^[a-z0-9_-]+$")
        self.assertNotIn("script>", anchor)

    def test_check_mode_detects_missing_and_stale_outputs(self) -> None:
        artifacts = build_artifacts(PACK_ROOT, "public")
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw)
            self.assertEqual(set(check_artifacts(output, artifacts)), set(artifacts))
            write_artifacts(output, artifacts)
            self.assertEqual(check_artifacts(output, artifacts), [])
            (output / NETWORK_FILE).write_text("stale\n", encoding="utf-8")
            self.assertEqual(check_artifacts(output, artifacts), [NETWORK_FILE])

    def test_cli_generate_then_check(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            args = [str(PACK_ROOT), "--output-dir", raw]
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(main(args), 0)
                self.assertEqual(main([*args, "--check"]), 0)
                (Path(raw) / GRAPH_FILE).write_text("{}\n", encoding="utf-8")
                self.assertEqual(main([*args, "--check"]), 1)
            self.assertIn("DRIFT knowledge-graph.json", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
