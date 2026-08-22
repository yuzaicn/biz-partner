#!/usr/bin/env python3
"""Validate the machine-readable TaskSpec registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED = {
    "id",
    "version",
    "aliases",
    "domain",
    "required_slots",
    "outputs",
    "allowed_tools",
    "risk",
    "can_write",
    "next_signals",
}
TOOLS = {"read_local", "write_local", "network_read", "external_write", "destructive", "sensitive"}
RISKS = {"low", "medium", "high"}


def load(path: Path) -> list[dict]:
    rows: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"line {number}: TaskSpec must be object")
        rows.append(row)
    return rows


def errors_for(rows: list[dict]) -> list[str]:
    errors: list[str] = []
    ids: set[str] = set()
    aliases: dict[str, str] = {}
    for row in rows:
        task_id = row.get("id", "<missing>")
        missing = REQUIRED - set(row)
        if missing:
            errors.append(f"{task_id}: missing {sorted(missing)}")
        if task_id in ids:
            errors.append(f"duplicate task id: {task_id}")
        ids.add(task_id)
        for field in ("aliases", "domain", "required_slots", "outputs", "allowed_tools", "next_signals"):
            if not isinstance(row.get(field), list):
                errors.append(f"{task_id}: {field} must be list")
        for alias in row.get("aliases", []):
            if alias in aliases:
                errors.append(f"duplicate alias {alias}: {aliases[alias]} and {task_id}")
            aliases[alias] = task_id
        unknown_tools = set(row.get("allowed_tools", [])) - TOOLS
        if unknown_tools:
            errors.append(f"{task_id}: unknown tools {sorted(unknown_tools)}")
        if row.get("risk") not in RISKS:
            errors.append(f"{task_id}: invalid risk {row.get('risk')}")
        if not isinstance(row.get("can_write"), bool):
            errors.append(f"{task_id}: can_write must be boolean")
        if row.get("can_write") and "write_local" not in row.get("allowed_tools", []):
            errors.append(f"{task_id}: can_write requires write_local")
        if not row.get("can_write") and any(tool in {"external_write", "destructive"} for tool in row.get("allowed_tools", [])):
            errors.append(f"{task_id}: side-effect tool requires can_write")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("registry", type=Path)
    args = parser.parse_args()
    try:
        rows = load(args.registry)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    errors = errors_for(rows)
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK tasks={len(rows)} aliases={sum(len(row['aliases']) for row in rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
