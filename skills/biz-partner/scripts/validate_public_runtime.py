#!/usr/bin/env python3
"""Validate that a biz-partner package contains only portable open-runtime assets."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


TEXT_SUFFIXES = {
    ".md", ".py", ".json", ".jsonl", ".yaml", ".yml", ".txt", ".toml",
    ".csv", ".tsv", ".html", ".htm", ".css", ".js", ".ts", ".tsx", ".jsx",
    ".xml", ".ini", ".cfg", ".conf", ".sh",
}
FORBIDDEN_TEXT = {
    "/" + "Users/",
    "private" + "_research_only",
    "evidence" + "_paths",
    "manifest" + "_paths",
    "authored" + "Text",
    "db" + "skill",
    "dontbe" + "silent",
    "yu" + "zai",
    "x" + ".com/",
    "twit" + "ter",
    "twe" + "et",
    "推" + "特",
    "social" + "-media archive",
    "account" + " timelines",
    "source-" + "account locator",
}
SOURCE_IDENTITY_TEXT = {"鱼" + "仔", "Exp" + "Lang_Cn"}
SOURCE_IDENTITY_FILES = {
    "public-knowledge/sources.jsonl",
    "public-knowledge/knowledge-graph.json",
    "public-knowledge/knowledge-network.md",
}
FORBIDDEN_PATH_PARTS = {"knowledge", "__pycache__"}
LINK_RE = re.compile(r"\[[^\]]+\]\((?!https?://|mailto:|#)([^)]+)\)")
MACHINE_LOCAL_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_])/(?:Users|home|private/var|var/folders|Volumes)/[^\s`\"')\]]+"
)
WINDOWS_LOCAL_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:\\[^\s`\"')\]]+")


def read_text_asset(path: Path) -> tuple[str | None, str | None]:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        if path.suffix.casefold() in TEXT_SUFFIXES:
            return None, "non-UTF-8 text asset"
        return None, None
    if "\x00" in text:
        if path.suffix.casefold() in TEXT_SUFFIXES:
            return None, "NUL byte in text asset"
        return None, None
    return text, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill", type=Path)
    args = parser.parse_args()
    root = args.skill.resolve()
    errors: list[str] = []
    trace_findings = 0
    scanned_text_files = 0
    required = set(('LICENSE', 'SKILL.md', 'agents/openai.yaml', 'evals/debate-events-valid.jsonl', 'evals/invalid-completed-no-evidence.json', 'evals/routing-cases.jsonl', 'evals/safety-cases.jsonl', 'evals/valid-handoff.json', 'public-knowledge/USAGE.md', 'public-knowledge/atoms.jsonl', 'public-knowledge/concept-dictionary.md', 'public-knowledge/concepts.jsonl', 'public-knowledge/knowledge-graph.json', 'public-knowledge/knowledge-network.md', 'public-knowledge/manifest.json', 'public-knowledge/methods.jsonl', 'public-knowledge/methods.md', 'public-knowledge/retrieval-cases.jsonl', 'public-knowledge/sources.jsonl', 'references/business-product-playbooks.md', 'references/content-safety.md', 'references/debate-protocol.md', 'references/knowledge-governance.md', 'references/knowledge-learning.md', 'references/knowledge-runtime.md', 'references/memory-governance.md', 'references/output-contract.md', 'references/personal-content-governance-playbooks.md', 'references/runtime-kernel.md', 'references/schemas/case-packet.schema.json', 'references/schemas/handoff.schema.json', 'references/schemas/knowledge-change-set.schema.json', 'references/schemas/memory-proposal.schema.json', 'references/script-operations.md', 'references/source-attribution.md', 'references/task-registry.md', 'references/task-specs.jsonl', 'references/workbench-runtime.md', 'scripts/adaptive_context.py', 'scripts/atom_contract.py', 'scripts/audit_skill.py', 'scripts/build_knowledge_network.py', 'scripts/freeze_contract_bundle.py', 'scripts/knowledge_learning.py', 'scripts/knowledge_runtime.py', 'scripts/render_source_attribution.py', 'scripts/route_task.py', 'scripts/state_store.py', 'scripts/test_adaptive_context.py', 'scripts/test_atom_contract.py', 'scripts/test_audit_skill.py', 'scripts/test_build_knowledge_network.py', 'scripts/test_contracts.py', 'scripts/test_debate.py', 'scripts/test_freeze_contract_bundle.py', 'scripts/test_knowledge_learning.py', 'scripts/test_knowledge_runtime.py', 'scripts/test_render_source_attribution.py', 'scripts/test_route_task.py', 'scripts/test_state_store.py', 'scripts/test_validate_public_knowledge.py', 'scripts/test_workbench_runtime.py', 'scripts/validate_contracts.py', 'scripts/validate_debate.py', 'scripts/validate_public_knowledge.py', 'scripts/validate_public_runtime.py', 'scripts/validate_tasks.py', 'scripts/workbench_runtime.py', 'templates/decision-record.json', 'templates/knowledge-change-set.json', 'templates/knowledge-decisions.json', 'templates/profile-proposal.json', 'templates/project-state.json', 'templates/workbench-config.json'))
    existing = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    for missing in sorted(required - existing):
        errors.append(f"missing required file: {missing}")
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink():
            errors.append(f"symlink is not allowed: {relative}")
            continue
        if any(part in FORBIDDEN_PATH_PARTS for part in relative.parts):
            errors.append(f"private/generated path is not allowed: {relative}")
        if path.is_file() and path.suffix == ".pyc":
            errors.append(f"bytecode is not allowed: {relative}")
        if not path.is_file():
            continue
        text, text_error = read_text_asset(path)
        if text_error is not None:
            errors.append(f"{text_error}: {relative}")
            continue
        if text is None:
            continue
        scanned_text_files += 1
        for forbidden in sorted(FORBIDDEN_TEXT):
            if forbidden.casefold() in text.casefold():
                trace_findings += 1
                errors.append(f"forbidden private trace {forbidden!r}: {relative}")
        for identity in sorted(SOURCE_IDENTITY_TEXT):
            if identity.casefold() in text.casefold() and relative.as_posix() not in SOURCE_IDENTITY_FILES:
                trace_findings += 1
                errors.append(f"source identity outside authorized registry: {relative}")
        for match in MACHINE_LOCAL_PATH_RE.findall(text) + WINDOWS_LOCAL_PATH_RE.findall(text):
            trace_findings += 1
            errors.append(f"machine-local absolute path {match!r}: {relative}")
        if path.suffix == ".md":
            for target in LINK_RE.findall(text):
                clean = target.split("#", 1)[0]
                if clean and not (path.parent / clean).resolve().exists():
                    errors.append(f"broken local link {target!r}: {relative}")
    knowledge_validator = root / "scripts/validate_public_knowledge.py"
    if knowledge_validator.is_file():
        result = subprocess.run(
            [sys.executable, "-B", str(knowledge_validator), str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            errors.append("public knowledge validation failed: " + (result.stdout + result.stderr).strip())
    if errors:
        print(
            f"FAIL scanned_text_files={scanned_text_files} "
            f"private_trace_findings={trace_findings}"
        )
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(
        f"OK open_runtime_files={len(existing)} scanned_text_files={scanned_text_files} "
        f"portable=true private_trace_findings={trace_findings}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
