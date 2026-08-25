#!/usr/bin/env python3
"""Read-only heuristic audit for a local Skill package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".woff", ".woff2", ".ttf", ".pyc"}
MACHINE_HOME_PATTERN = (
    r"(?:/" + "Users/" + r"[^\s`]+|/" + "home/" + r"[^\s`]+)"
)
RULES = (
    ("destructive_command", "critical", re.compile(r"\b(?:rm\s+-rf|git\s+reset\s+--hard|drop\s+database|TRUNCATE\s+TABLE)\b", re.I), "destructive command or database operation"),
    ("external_write", "high", re.compile(r"(?:curl\b[^\n]*\s(?:-X\s*)?(?:POST|PUT|PATCH|DELETE)|requests\.(?:post|put|patch|delete)\s*\(|fetch\s*\([^\n]*method\s*:\s*['\"](?:POST|PUT|PATCH|DELETE))", re.I), "possible external write"),
    ("process_execution", "high", re.compile(r"\b(?:subprocess\.(?:run|Popen|call|check_call|check_output)|os\.(?:system|popen)|child_process\.(?:exec|spawn))\s*\(", re.I), "process or shell execution"),
    ("dynamic_execution", "high", re.compile(r"(?<![.\w])(?:eval|exec|compile)\s*\(", re.I), "dynamic code execution"),
    ("command_network_access", "high", re.compile(r"(?:subprocess\.[^(]+\([^\n]*(?:curl|wget)\b|\b(?:curl|wget)\b[^\n]*(?:--data|-d\s|--upload-file|-T\s|@[^\s]+))", re.I), "command-line network access or possible data transfer"),
    ("credential_or_pii_access", "high", re.compile(r"(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|AWS_SECRET|PRIVATE_KEY|keychain|password|cookie|\.env|access[_-]?token)", re.I), "credential, token, or sensitive data access"),
    ("prompt_injection", "high", re.compile(r"(?:ignore\s+(?:all\s+)?previous\s+instructions|system\s+message|reveal\s+(?:the\s+)?prompt|do\s+not\s+tell\s+the\s+user)", re.I), "prompt-like authority manipulation"),
    ("hidden_promotion", "medium", re.compile(r"(?:affiliate|referral|邀请码|返佣|推广链接|use\s+my\s+link|sponsor(?:ed)?\s+by)", re.I), "possible advertising, affiliate, or referral behavior"),
    ("broad_file_access", "medium", re.compile(r"(?:" + MACHINE_HOME_PATTERN + r"|glob\s*\(\s*['\"]\*|read\s+all\s+files|扫描所有文件)", re.I), "broad or sensitive file access claim"),
)

CODE_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".jsx", ".sh", ".bash", ".zsh", ".rb", ".go", ".rs"}


def finding_context(relative: str, line: str) -> tuple[str, str]:
    """Classify where a signal was found without hiding the raw finding."""

    path = Path(relative)
    if path.name.startswith("test_") or "tests" in path.parts or "evals" in path.parts:
        return "test_fixture", "low"
    if "re.compile(" in line or (path.name == "audit_skill.py" and line.lstrip().startswith("RULES")):
        return "detector_definition", "low"
    if path.suffix.lower() in {".md", ".mdx", ".txt", ".rst"}:
        return "documentation", "low"
    if path.suffix.lower() in CODE_SUFFIXES:
        return "executable_code", "high"
    return "data_or_configuration", "medium"


def iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file() or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            if path.stat().st_size <= MAX_BYTES:
                path.read_bytes()
                files.append(path)
        except OSError:
            continue
    return files


def audit(root: Path) -> dict:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"skill path must be an existing directory: {root}")
    findings: list[dict] = []
    inventory: list[dict] = []
    for path in sorted(root.rglob("*")):
        if not path.is_symlink():
            continue
        relative = str(path.relative_to(root))
        try:
            target = path.resolve(strict=True)
            target.relative_to(root)
            escaped = False
        except (OSError, ValueError):
            target = None
            escaped = True
        inventory.append({
            "path": relative,
            "bytes": 0,
            "sha256": None,
            "text_scanned": False,
            "symlink": True,
        })
        findings.append({
            "finding_id": f"symlink_{'escape' if escaped else 'present'}:{relative}:0",
            "rule": "symlink_escape" if escaped else "symlink_present",
            "severity": "high" if escaped else "medium",
            "path": relative,
            "line": 0,
            "signal": str(target) if target is not None else "unresolved-or-outside-root",
            "reason": "symlink target is outside the approved Skill root" if escaped else "symlink requires explicit human review",
            "context": "filesystem_link",
            "confidence": "high" if escaped else "medium",
            "read_only_audit": True,
            "requires_human_review": escaped,
        })
    for path in iter_files(root):
        relative = str(path.relative_to(root))
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            inventory.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "text_scanned": False})
            continue
        inventory.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "text_scanned": True})
        for line_number, line in enumerate(text.splitlines(), 1):
            for rule_id, severity, pattern, reason in RULES:
                match = pattern.search(line)
                if match:
                    context, confidence = finding_context(relative, line)
                    findings.append({
                        "finding_id": f"{rule_id}:{relative}:{line_number}",
                        "rule": rule_id,
                        "severity": severity,
                        "path": relative,
                        "line": line_number,
                        "signal": match.group(0)[:160],
                        "reason": reason,
                        "context": context,
                        "confidence": confidence,
                        "read_only_audit": True,
                        "requires_human_review": severity in {"critical", "high"} and context == "executable_code",
                    })
    return {"skill_path": str(root), "files": inventory, "findings": findings, "side_effects": [], "status": "audit_only"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill_path")
    args = parser.parse_args()
    try:
        result = audit(Path(args.skill_path))
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
