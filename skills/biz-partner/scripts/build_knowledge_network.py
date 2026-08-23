#!/usr/bin/env python3
"""Render a deterministic, linkable view of a Biz Partner KnowledgePack."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from knowledge_runtime import KnowledgePack, load_knowledge_pack


GRAPH_FILE = "knowledge-graph.json"
NETWORK_FILE = "knowledge-network.md"
GRAPH_SCHEMA_VERSION = "1.0"
KIND_ORDER = {"source": 0, "atom": 1, "concept": 2, "method": 3}
SAFE_FRAGMENT_RE = re.compile(r"^[a-z0-9_-]+$")
MARKDOWN_SPECIAL_RE = re.compile(r"([\\`*_[\]{}()#+\-.!|>])")
EDGE_LABELS = {
    "derived_from": "来源",
    "depends_on": "依赖",
    "supports": "支持",
    "refines": "细化",
    "contradicts": "冲突",
    "grounded_by": "由原子支撑",
    "related_to_method": "关联方法",
    "uses_atom": "使用原子",
    "uses_concept": "使用概念",
}


def stable_anchor(kind: str, record_id: str) -> str:
    """Return a portable fragment while keeping current public IDs readable."""
    raw = f"{kind}-{record_id}".casefold()
    if SAFE_FRAGMENT_RE.fullmatch(raw):
        return raw
    slug = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-_") or "record"
    digest = hashlib.sha256(record_id.encode("utf-8")).hexdigest()[:10]
    return f"{kind}-{slug}-{digest}"


def markdown_text(value: Any) -> str:
    """Render untrusted record text as plain Markdown text, never raw HTML."""
    text = "" if value is None else str(value)
    text = " ".join(text.replace("\r", "\n").splitlines())
    text = html.escape(text, quote=True)
    return MARKDOWN_SPECIAL_RE.sub(r"\\\1", text)


def _source_label(row: dict[str, Any], source_id: str) -> str:
    for field in ("public_attribution_name", "title"):
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return source_id


def _node(kind: str, record_id: str, label: str) -> dict[str, str]:
    anchor = stable_anchor(kind, record_id)
    return {
        "node_id": f"{kind}:{record_id}",
        "kind": kind,
        "record_id": record_id,
        "label": label,
        "href": f"{NETWORK_FILE}#{anchor}",
    }


def _edge(
    source: str, target: str, relation_type: str, *, directed: bool = True
) -> dict[str, Any]:
    return {
        "from": source,
        "to": target,
        "type": relation_type,
        "directed": directed,
    }


def _pack_metadata(pack_root: Path, mode: str) -> dict[str, str]:
    pack_id = pack_root.name
    pack_version = "unversioned"
    manifest_path = pack_root / "manifest.json"
    if manifest_path.is_file():
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("manifest root must be an object")
        manifest_pack_id = value.get("pack_id")
        manifest_pack_version = value.get("pack_version")
        if isinstance(manifest_pack_id, str) and manifest_pack_id.strip():
            pack_id = manifest_pack_id
        if isinstance(manifest_pack_version, str) and manifest_pack_version.strip():
            pack_version = manifest_pack_version
    return {"pack_id": pack_id, "pack_version": pack_version, "mode": mode}


def build_knowledge_graph(
    pack: KnowledgePack, metadata: dict[str, str]
) -> dict[str, Any]:
    """Project eligible records and their declared relationships into a graph."""
    nodes: list[dict[str, str]] = []
    for source_id, row in pack.sources.items():
        nodes.append(_node("source", source_id, _source_label(row, source_id)))
    for atom_id, row in pack.atoms.items():
        nodes.append(_node("atom", atom_id, str(row["canonical"])))
    for concept_id, row in pack.concepts.items():
        nodes.append(_node("concept", concept_id, str(row["term"])))
    for method_id, row in pack.methods.items():
        nodes.append(_node("method", method_id, str(row["title"])))
    nodes.sort(key=lambda row: (KIND_ORDER[row["kind"]], row["record_id"]))

    node_ids = {row["node_id"] for row in nodes}
    if len(node_ids) != len(nodes):
        raise ValueError("knowledge graph contains duplicate node IDs")
    hrefs = {row["href"] for row in nodes}
    if len(hrefs) != len(nodes):
        raise ValueError("knowledge graph contains duplicate anchors")

    edge_rows: list[dict[str, Any]] = []
    for atom_id, atom in pack.atoms.items():
        atom_node = f"atom:{atom_id}"
        for ref in atom.get("source_refs", []):
            target = f"source:{ref['source_id']}"
            if target in node_ids:
                edge_rows.append(_edge(atom_node, target, "derived_from"))
        for relation in atom.get("relations", []):
            target = f"atom:{relation['atom_id']}"
            if target in node_ids:
                relation_type = relation["type"]
                edge_rows.append(
                    _edge(
                        atom_node,
                        target,
                        relation_type,
                        directed=relation_type != "contradicts",
                    )
                )

    for concept_id, concept in pack.concepts.items():
        concept_node = f"concept:{concept_id}"
        for atom_id in concept.get("source_atoms", []):
            target = f"atom:{atom_id}"
            if target in node_ids:
                edge_rows.append(_edge(concept_node, target, "grounded_by"))
        for method_id in concept.get("related_methods", []):
            target = f"method:{method_id}"
            if target in node_ids:
                edge_rows.append(_edge(concept_node, target, "related_to_method"))

    for method_id, method in pack.methods.items():
        method_node = f"method:{method_id}"
        for atom_id in method.get("atom_ids", []):
            target = f"atom:{atom_id}"
            if target in node_ids:
                edge_rows.append(_edge(method_node, target, "uses_atom"))
        for concept_id in method.get("concept_ids", []):
            target = f"concept:{concept_id}"
            if target in node_ids:
                edge_rows.append(_edge(method_node, target, "uses_concept"))

    unique_edges = {
        (row["from"], row["type"], row["to"], row["directed"]): row
        for row in edge_rows
    }
    edges = sorted(
        unique_edges.values(),
        key=lambda row: (row["from"], row["type"], row["to"], row["directed"]),
    )
    for row in edges:
        if row["from"] not in node_ids or row["to"] not in node_ids:
            raise ValueError(
                f"knowledge graph contains dangling edge: {row['from']} -> {row['to']}"
            )

    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "pack_id": metadata["pack_id"],
        "pack_version": metadata["pack_version"],
        "mode": metadata["mode"],
        "counts": {"nodes": len(nodes), "edges": len(edges)},
        "nodes": nodes,
        "edges": edges,
    }


def _markdown_list(values: Iterable[Any]) -> str:
    rows = [markdown_text(value) for value in values]
    return "、".join(value for value in rows if value) or "无"


def _node_link(node: dict[str, str]) -> str:
    return f"[{markdown_text(node['record_id'])}]({node['href']})"


def _append_edge_list(
    lines: list[str],
    title: str,
    edges: list[dict[str, Any]],
    node_by_id: dict[str, dict[str, str]],
    target_field: str,
) -> None:
    lines.extend([f"**{title}：**", ""])
    if not edges:
        lines.extend(["- 无", ""])
        return
    for edge in edges:
        other = node_by_id[edge[target_field]]
        relation = EDGE_LABELS.get(edge["type"], edge["type"])
        suffix = "（双向）" if not edge["directed"] else ""
        lines.append(f"- {markdown_text(relation)}{suffix}：{_node_link(other)}")
    lines.append("")


def _append_record_details(
    lines: list[str], kind: str, record_id: str, row: dict[str, Any]
) -> None:
    if kind == "source":
        lines.extend(
            [
                f"**名称：** {markdown_text(_source_label(row, record_id))}",
                "",
                f"**类型：** {markdown_text(row.get('kind', 'unknown'))}",
                "",
                f"**状态：** {markdown_text(row.get('status', 'unknown'))}",
                "",
            ]
        )
        return
    if kind == "atom":
        lines.extend(
            [
                f"**内容：** {markdown_text(row.get('canonical'))}",
                "",
                f"**领域：** {_markdown_list(row.get('domain', []))}",
                "",
            ]
        )
        if isinstance(row.get("decision_rule"), str):
            lines.extend(
                [f"**判断规则：** {markdown_text(row['decision_rule'])}", ""]
            )
        if isinstance(row.get("procedure"), list):
            lines.extend(["**做法：**", ""])
            lines.extend(
                f"{index}. {markdown_text(step)}"
                for index, step in enumerate(row["procedure"], 1)
            )
            lines.append("")
        lines.extend(
            [f"**适用边界：** {_markdown_list(row.get('limits', []))}", ""]
        )
        return
    if kind == "concept":
        lines.extend(
            [
                f"**概念：** {markdown_text(row.get('term'))}",
                "",
                f"**定义：** {markdown_text(row.get('definition'))}",
                "",
                f"**别名：** {_markdown_list(row.get('aliases', []))}",
                "",
            ]
        )
        for label, field in (
            ("不是什么", "anti_definition"),
            ("常见误用", "common_misuse"),
            ("适用时机", "use_when"),
            ("边界", "limit"),
        ):
            value = row.get(field)
            if isinstance(value, str) and value:
                lines.extend([f"**{label}：** {markdown_text(value)}", ""])
        return
    if kind == "method":
        lines.extend(
            [
                f"**方法：** {markdown_text(row.get('title'))}",
                "",
                f"**用途：** {markdown_text(row.get('purpose'))}",
                "",
                f"**适用时：** {_markdown_list(row.get('use_when', []))}",
                "",
                "**步骤：**",
                "",
            ]
        )
        lines.extend(
            f"{index}. {markdown_text(step)}"
            for index, step in enumerate(row.get("steps", []), 1)
        )
        lines.extend(
            [
                "",
                f"**停止条件：** {_markdown_list(row.get('stop_conditions', []))}",
                "",
                f"**产出：** {_markdown_list(row.get('outputs', []))}",
                "",
            ]
        )


def render_knowledge_network(
    pack: KnowledgePack, graph: dict[str, Any]
) -> str:
    """Render graph nodes with deterministic outgoing and incoming links."""
    node_by_id = {row["node_id"]: row for row in graph["nodes"]}
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph["edges"]:
        outgoing[edge["from"]].append(edge)
        incoming[edge["to"]].append(edge)

    records: dict[str, dict[str, dict[str, Any]]] = {
        "source": pack.sources,
        "atom": pack.atoms,
        "concept": pack.concepts,
        "method": pack.methods,
    }
    section_titles = {
        "source": "来源",
        "atom": "知识原子",
        "concept": "概念与词典",
        "method": "方法",
    }
    lines = [
        "# 知识网络",
        "",
        "这是一份从结构化知识包确定性生成的浏览页。链接表示数据中已经声明的关系，不代表自动推导出的结论。",
        "",
        f"知识包：{markdown_text(graph['pack_id'])} · 版本：{markdown_text(graph['pack_version'])} · 模式：{markdown_text(graph['mode'])}",
        "",
        f"节点：{graph['counts']['nodes']} · 关系：{graph['counts']['edges']}",
        "",
        "[来源](#来源) · [知识原子](#知识原子) · [概念与词典](#概念与词典) · [方法](#方法)",
        "",
    ]

    for kind in ("source", "atom", "concept", "method"):
        lines.extend([f"## {section_titles[kind]}", ""])
        for node in (row for row in graph["nodes"] if row["kind"] == kind):
            anchor = node["href"].split("#", 1)[1]
            record_id = node["record_id"]
            lines.extend(
                [
                    f"### {anchor}",
                    "",
                    f"**ID：** {markdown_text(record_id)}",
                    "",
                ]
            )
            _append_record_details(lines, kind, record_id, records[kind][record_id])
            _append_edge_list(
                lines,
                "关联出去",
                outgoing.get(node["node_id"], []),
                node_by_id,
                "to",
            )
            _append_edge_list(
                lines,
                "被以下节点关联",
                incoming.get(node["node_id"], []),
                node_by_id,
                "from",
            )
    return "\n".join(lines).rstrip() + "\n"


def build_artifacts(
    pack_root: Path,
    mode: str = "public",
    *,
    metadata: dict[str, str] | None = None,
) -> dict[str, str]:
    pack_root = pack_root.resolve()
    pack = load_knowledge_pack(
        pack_root / "sources.jsonl", pack_root / "atoms.jsonl", mode=mode
    )
    resolved_metadata = metadata or _pack_metadata(pack_root, mode)
    if resolved_metadata.get("mode") != mode:
        raise ValueError("knowledge graph metadata mode does not match requested mode")
    graph = build_knowledge_graph(pack, resolved_metadata)
    graph_text = json.dumps(
        graph, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    return {
        GRAPH_FILE: graph_text,
        NETWORK_FILE: render_knowledge_network(pack, graph),
    }


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def write_artifacts(output_dir: Path, artifacts: dict[str, str]) -> None:
    for name in sorted(artifacts):
        _atomic_write(output_dir / name, artifacts[name])


def check_artifacts(output_dir: Path, artifacts: dict[str, str]) -> list[str]:
    drift: list[str] = []
    for name in sorted(artifacts):
        path = output_dir / name
        if not path.is_file() or path.read_text(encoding="utf-8") != artifacts[name]:
            drift.append(name)
    return drift


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack_root", type=Path)
    parser.add_argument("--mode", choices=("public", "private"), default="public")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--check", action="store_true", help="fail when generated files are missing or stale"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        pack_root = args.pack_root.resolve()
        output_dir = (
            args.output_dir.resolve() if args.output_dir is not None else pack_root
        )
        artifacts = build_artifacts(pack_root, args.mode)
        if args.check:
            drift = check_artifacts(output_dir, artifacts)
            if drift:
                print("DRIFT " + " ".join(drift), file=sys.stderr)
                return 1
        else:
            write_artifacts(output_dir, artifacts)
        graph = json.loads(artifacts[GRAPH_FILE])
        print(
            f"OK nodes={graph['counts']['nodes']} edges={graph['counts']['edges']} "
            f"mode={args.mode} check={str(args.check).lower()}"
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
