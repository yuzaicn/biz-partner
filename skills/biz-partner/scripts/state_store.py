#!/usr/bin/env python3
"""Consent-gated local state store for biz-partner projects."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATE_DIR = ".biz-partner"
DATABASE_FILE = "state.sqlite3"
NAMESPACES = {
    "user_profile",
    "project_state",
    "decision_log",
    "asset_index",
    "playbook_feedback",
}
OPERATIONS = {"add", "supersede", "retire", "suppress"}


class StateError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def resolve_root(raw: str) -> Path:
    root = Path(raw).expanduser().resolve()
    if not root.is_absolute() or not root.is_dir():
        raise StateError(f"project root must be an existing directory: {root}")
    return root


def paths_for(root: Path) -> dict[str, Path]:
    project_root = root.expanduser().resolve()
    state_dir = project_root / STATE_DIR
    if state_dir.is_symlink():
        raise StateError(f"state directory must not be a symbolic link: {state_dir}")
    database = state_dir / DATABASE_FILE
    if database.is_symlink():
        raise StateError(f"state database must not be a symbolic link: {database}")
    for label, path in (("state directory", state_dir), ("state database", database)):
        try:
            path.resolve().relative_to(project_root)
        except ValueError as exc:
            raise StateError(f"{label} must resolve within project root: {path}") from exc
    return {
        "dir": state_dir,
        "database": database,
    }


def init_action(root: Path) -> dict[str, Any]:
    paths = paths_for(root)
    return {"action": "init", "root": str(root), "target": str(paths["dir"])}


def initial_state(root: Path) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project_id": root.name,
        "state_version": 1,
        "user_profile": {},
        "project_state": {},
        "decision_log": [],
        "asset_index": [],
        "playbook_feedback": [],
        "suppressions": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StateError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StateError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StateError(f"JSON root must be an object: {path}")
    return value


def connect_store(root: Path) -> sqlite3.Connection:
    database = paths_for(root)["database"]
    if not database.is_file():
        raise StateError(f"missing state database: {database}")
    connection = sqlite3.connect(database, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE project_state ("
        "singleton INTEGER PRIMARY KEY CHECK (singleton = 1), "
        "state_version INTEGER NOT NULL, state_json TEXT NOT NULL, state_hash TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE events ("
        "sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, "
        "state_version INTEGER NOT NULL, event_json TEXT NOT NULL)"
    )


def insert_event(connection: sqlite3.Connection, event: dict[str, Any]) -> None:
    connection.execute(
        "INSERT INTO events(event_type, state_version, event_json) VALUES (?, ?, ?)",
        (event["event"], event["state_version"], canonical_bytes(event).decode("utf-8")),
    )


def decode_state_row(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        raise StateError("state database has no project state")
    try:
        value = json.loads(row["state_json"])
    except json.JSONDecodeError as exc:
        raise StateError("stored project state is invalid JSON") from exc
    if not isinstance(value, dict):
        raise StateError("stored project state is not an object")
    if digest(value) != row["state_hash"]:
        raise StateError("stored project state hash mismatch")
    if value.get("state_version") != row["state_version"]:
        raise StateError("stored project state version mismatch")
    return value


def replay_event_rows(
    rows: list[sqlite3.Row],
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    if not rows:
        raise StateError("state database has no events")
    expected_version = 0
    replayed: dict[str, Any] | None = None
    historical: dict[str, Any] | None = None
    future_reached = False
    for row in rows:
        try:
            event = json.loads(row["event_json"])
        except json.JSONDecodeError as exc:
            raise StateError(f"invalid event JSON at sequence {row['sequence']}") from exc
        if not isinstance(event, dict):
            raise StateError(f"event is not an object at sequence {row['sequence']}")
        if event.get("event") != row["event_type"]:
            raise StateError(f"event type mismatch at sequence {row['sequence']}")
        version = event.get("state_version")
        if version != row["state_version"]:
            raise StateError(f"event column version mismatch at sequence {row['sequence']}")
        if version != expected_version + 1:
            raise StateError(f"event version gap: expected {expected_version + 1}, got {version}")
        state_after = event.get("state_after")
        if not isinstance(state_after, dict) or digest(state_after) != event.get("state_hash"):
            raise StateError(f"event state hash mismatch at version {version}")
        replayed = state_after
        if as_of is not None and version == 1:
            initialized_at = parse_datetime(event.get("timestamp"))
            if as_of < initialized_at:
                raise StateError("as_of precedes state initialization")
            historical = state_after
        elif as_of is not None and not future_reached:
            effective_at = parse_datetime(event.get("confirmed_at", event.get("timestamp")))
            if effective_at <= as_of:
                historical = state_after
            else:
                future_reached = True
        expected_version = version
    assert replayed is not None
    if as_of is not None:
        assert historical is not None
        return historical
    return replayed


def load_consistent_state(connection: sqlite3.Connection) -> dict[str, Any]:
    row = connection.execute(
        "SELECT state_version, state_json, state_hash FROM project_state WHERE singleton = 1"
    ).fetchone()
    state = decode_state_row(row)
    event_rows = connection.execute(
        "SELECT sequence, event_type, state_version, event_json FROM events ORDER BY sequence"
    ).fetchall()
    replayed = replay_event_rows(event_rows)
    if replayed != state:
        raise StateError("materialized state does not match event replay")
    return state


def load_state(root: Path) -> dict[str, Any]:
    with closing(connect_store(root)) as connection:
        connection.execute("BEGIN")
        return load_consistent_state(connection)


def load_events(root: Path) -> list[dict[str, Any]]:
    with closing(connect_store(root)) as connection:
        rows = connection.execute("SELECT event_json FROM events ORDER BY sequence").fetchall()
    try:
        return [json.loads(row["event_json"]) for row in rows]
    except json.JSONDecodeError as exc:
        raise StateError("invalid event JSON") from exc


def replay_state(root: Path) -> dict[str, Any]:
    with closing(connect_store(root)) as connection:
        rows = connection.execute(
            "SELECT sequence, event_type, state_version, event_json FROM events ORDER BY sequence"
        ).fetchall()
    return replay_event_rows(rows)


def replay_state_as_of(root: Path, *, as_of: str | datetime) -> dict[str, Any]:
    instant = resolve_as_of(as_of)
    with closing(connect_store(root)) as connection:
        connection.execute("BEGIN")
        load_consistent_state(connection)
        rows = connection.execute(
            "SELECT sequence, event_type, state_version, event_json FROM events ORDER BY sequence"
        ).fetchall()
        return replay_event_rows(rows, as_of=instant)


def parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise StateError(f"invalid ISO 8601 date-time with timezone: {value}") from exc
    if parsed.tzinfo is None:
        raise StateError(f"date-time must include timezone: {value}")
    return parsed


def valid_datetime(value: Any, *, nullable: bool = False) -> bool:
    if value is None:
        return nullable
    if not isinstance(value, str) or not value:
        return False
    try:
        parse_datetime(value)
    except StateError:
        return False
    return True


def resolve_as_of(value: str | datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        return parse_datetime(value)
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value
    raise StateError("as_of must be an ISO 8601 date-time with timezone")


def suppression_keys(state: dict[str, Any]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    suppressions = state.get("suppressions", [])
    if not isinstance(suppressions, list):
        raise StateError("stored suppressions must be a list")
    for tombstone in suppressions:
        if not isinstance(tombstone, dict):
            raise StateError("stored suppression tombstone must be an object")
        namespace = tombstone.get("namespace")
        subject = tombstone.get("subject")
        if namespace not in NAMESPACES or not isinstance(subject, str) or not subject:
            raise StateError("stored suppression tombstone has an invalid namespace or subject")
        keys.add((namespace, subject))
    return keys


def record_is_visible(
    record: Any,
    *,
    namespace: str,
    suppressed: set[tuple[str, str]],
    as_of: datetime,
) -> bool:
    if not isinstance(record, dict):
        raise StateError(f"stored {namespace} record must be an object")
    subject = record.get("subject")
    if not isinstance(subject, str) or not subject:
        raise StateError(f"stored {namespace} record has an invalid subject")
    if (namespace, subject) in suppressed:
        return False
    expires_at = record.get("expires_at")
    if expires_at is None:
        return True
    return parse_datetime(expires_at) > as_of


def visible_state(state: dict[str, Any], *, as_of: str | datetime | None = None) -> dict[str, Any]:
    """Return the user-visible state after suppression and expiry filtering."""

    instant = resolve_as_of(as_of)
    projected = deepcopy(state)
    suppressed = suppression_keys(projected)
    for namespace in NAMESPACES:
        collection = projected.get(namespace)
        if namespace in {"user_profile", "project_state"}:
            if not isinstance(collection, dict):
                raise StateError(f"stored {namespace} must be an object")
            projected[namespace] = {
                subject: record
                for subject, record in collection.items()
                if record_is_visible(
                    record,
                    namespace=namespace,
                    suppressed=suppressed,
                    as_of=instant,
                )
            }
        else:
            if not isinstance(collection, list):
                raise StateError(f"stored {namespace} must be a list")
            projected[namespace] = [
                record
                for record in collection
                if record_is_visible(
                    record,
                    namespace=namespace,
                    suppressed=suppressed,
                    as_of=instant,
                )
            ]
    return projected


def load_visible_state(root: Path, *, as_of: str | datetime | None = None) -> dict[str, Any]:
    instant = resolve_as_of(as_of)
    state = replay_state_as_of(root, as_of=instant)
    return visible_state(state, as_of=instant)


def validate_proposal(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["proposal root must be an object"]
    required = {
        "proposal_id",
        "namespace",
        "operation",
        "subject",
        "value",
        "source_refs",
        "confidence",
        "scope",
        "created_at",
        "expires_at",
        "deletion_key",
        "requires_confirmation",
    }
    optional = {"last_validated_at", "user_confirmation"}
    for key in sorted(required - set(value)):
        errors.append(f"missing {key}")
    for key in sorted(set(value) - required - optional):
        errors.append(f"unexpected field: {key}")
    if value.get("namespace") not in NAMESPACES:
        errors.append(f"invalid namespace: {value.get('namespace')}")
    if value.get("operation") not in OPERATIONS:
        errors.append(f"invalid operation: {value.get('operation')}")
    if value.get("requires_confirmation") is not True:
        errors.append("requires_confirmation must be true")
    if not isinstance(value.get("source_refs"), list) or not value.get("source_refs"):
        errors.append("source_refs must be a non-empty list")
    elif not all(isinstance(ref, str) and ref for ref in value["source_refs"]):
        errors.append("source_refs must contain non-empty strings")
    confidence = value.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
        errors.append("confidence must be between 0 and 1")
    for key in ("proposal_id", "subject", "scope", "deletion_key"):
        if not isinstance(value.get(key), str) or not value.get(key):
            errors.append(f"{key} must be a non-empty string")
    if not valid_datetime(value.get("created_at")):
        errors.append("created_at must be an ISO 8601 date-time with timezone")
    if not valid_datetime(value.get("expires_at"), nullable=True):
        errors.append("expires_at must be null or an ISO 8601 date-time with timezone")
    if "last_validated_at" in value and not valid_datetime(value.get("last_validated_at"), nullable=True):
        errors.append("last_validated_at must be null or an ISO 8601 date-time with timezone")
    if "user_confirmation" in value and value["user_confirmation"] is not None and not isinstance(value["user_confirmation"], dict):
        errors.append("user_confirmation must be an object or null")
    return errors


def commit_action(root: Path, proposal_hash: str, expected_version: int) -> dict[str, Any]:
    return {
        "action": "commit_memory_proposal",
        "root": str(root),
        "proposal_hash": proposal_hash,
        "expected_version": expected_version,
    }


def apply_proposal(state: dict[str, Any], proposal: dict[str, Any]) -> None:
    namespace = proposal["namespace"]
    operation = proposal["operation"]
    subject = proposal["subject"]
    value = proposal["value"]

    if operation in {"retire", "suppress"}:
        if namespace in {"user_profile", "project_state"}:
            state[namespace].pop(subject, None)
        else:
            state[namespace] = [
                record for record in state[namespace] if record.get("subject") != subject
            ]
        state["suppressions"].append(
            {
                "namespace": namespace,
                "subject": subject,
                "deletion_key": proposal["deletion_key"],
                "operation": operation,
                "created_at": proposal["created_at"],
            }
        )
        return

    record = {
        "subject": subject,
        "value": value,
        "source_refs": proposal["source_refs"],
        "confidence": proposal["confidence"],
        "scope": proposal["scope"],
        "proposal_id": proposal["proposal_id"],
        "created_at": proposal["created_at"],
        "expires_at": proposal["expires_at"],
        "deletion_key": proposal["deletion_key"],
    }
    suppression_keys(state)
    state["suppressions"] = [
        tombstone
        for tombstone in state["suppressions"]
        if not (
            tombstone["namespace"] == namespace
            and tombstone["subject"] == subject
        )
    ]
    if namespace in {"user_profile", "project_state"}:
        state[namespace][subject] = record
    else:
        if operation == "supersede":
            state[namespace] = [
                current for current in state[namespace] if current.get("subject") != subject
            ]
        state[namespace].append(record)


def cmd_plan_init(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    action = init_action(root)
    print(json.dumps({"preview": action, "confirmation_hash": digest(action)}, ensure_ascii=False, indent=2))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    action = init_action(root)
    expected = digest(action)
    if args.confirmation_hash != expected:
        raise StateError("confirmation hash does not match the exact init action")
    paths = paths_for(root)
    if paths["dir"].exists():
        raise StateError(f"state directory already exists: {paths['dir']}")
    paths["dir"].mkdir(mode=0o700, parents=False, exist_ok=False)
    state = initial_state(root)
    database = paths["database"]
    connection = sqlite3.connect(database, timeout=10)
    try:
        connection.execute("BEGIN IMMEDIATE")
        create_schema(connection)
        connection.execute(
            "INSERT INTO project_state(singleton, state_version, state_json, state_hash) VALUES (1, ?, ?, ?)",
            (1, canonical_bytes(state).decode("utf-8"), digest(state)),
        )
        insert_event(
            connection,
            {
                "event": "StateInitialized",
                "state_version": 1,
                "action_hash": expected,
                "timestamp": state["updated_at"],
                "state_hash": digest(state),
                "state_after": state,
            },
        )
        connection.commit()
    except Exception as exc:
        connection.rollback()
        connection.close()
        database.unlink(missing_ok=True)
        paths["dir"].rmdir()
        raise StateError(f"state initialization failed: {exc}") from exc
    finally:
        if connection:
            connection.close()
    os.chmod(database, 0o600)
    print(json.dumps({"created": str(database), "state_version": 1}, ensure_ascii=False))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    state = load_visible_state(root, as_of=getattr(args, "as_of", None))
    print(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    return cmd_show(args)


def cmd_validate_proposal(args: argparse.Namespace) -> int:
    proposal = load_json(Path(args.proposal).expanduser().resolve())
    errors = validate_proposal(proposal)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(json.dumps({"proposal_hash": digest(proposal)}, ensure_ascii=False))
    return 0


def cmd_plan_commit(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    proposal = load_json(Path(args.proposal).expanduser().resolve())
    errors = validate_proposal(proposal)
    if errors:
        raise StateError("; ".join(errors))
    state = load_state(root)
    proposal_hash = digest(proposal)
    action = commit_action(root, proposal_hash, state["state_version"])
    print(
        json.dumps(
            {
                "preview": proposal,
                "proposal_hash": proposal_hash,
                "expected_version": state["state_version"],
                "confirmation_hash": digest(action),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    proposal = load_json(Path(args.proposal).expanduser().resolve())
    errors = validate_proposal(proposal)
    if errors:
        raise StateError("; ".join(errors))
    proposal_hash = digest(proposal)
    action = commit_action(root, proposal_hash, args.expected_version)
    if args.confirmation_hash != digest(action):
        raise StateError("confirmation hash does not match proposal, root, and state version")
    if not valid_datetime(args.confirmed_at):
        raise StateError("confirmed_at must be an ISO 8601 date-time with timezone")
    confirmed_at = parse_datetime(args.confirmed_at)
    proposal_created_at = parse_datetime(proposal["created_at"])
    if confirmed_at < proposal_created_at:
        raise StateError("confirmed_at must be at or after proposal created_at")
    connection = connect_store(root)
    try:
        connection.execute("BEGIN IMMEDIATE")
        state = load_consistent_state(connection)
        if state["state_version"] != args.expected_version:
            raise StateError(
                f"state version conflict: expected {args.expected_version}, current {state['state_version']}"
            )
        if confirmed_at < parse_datetime(state.get("updated_at")):
            raise StateError("confirmed_at must be at or after current state updated_at")
        apply_proposal(state, proposal)
        state["state_version"] += 1
        state["updated_at"] = args.confirmed_at
        event = {
            "event": "MemoryProposalCommitted",
            "proposal_id": proposal["proposal_id"],
            "proposal_hash": proposal_hash,
            "confirmation_hash": args.confirmation_hash,
            "confirmed_at": args.confirmed_at,
            "state_version": state["state_version"],
            "state_hash": digest(state),
            "state_after": state,
            "proposal": proposal,
        }
        connection.execute(
            "UPDATE project_state SET state_version = ?, state_json = ?, state_hash = ? "
            "WHERE singleton = 1 AND state_version = ?",
            (
                state["state_version"],
                canonical_bytes(state).decode("utf-8"),
                digest(state),
                args.expected_version,
            ),
        )
        if connection.total_changes != 1:
            raise StateError("state version conflict during commit")
        insert_event(connection, event)
        connection.commit()
    except Exception as exc:
        connection.rollback()
        if isinstance(exc, StateError):
            raise
        raise StateError(f"state transaction failed: {exc}") from exc
    finally:
        connection.close()
    print(json.dumps({"committed": proposal["proposal_id"], "state_version": state["state_version"]}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    plan_init = sub.add_parser("plan-init")
    plan_init.add_argument("root")
    plan_init.set_defaults(func=cmd_plan_init)

    init = sub.add_parser("init")
    init.add_argument("root")
    init.add_argument("--confirmation-hash", required=True)
    init.set_defaults(func=cmd_init)

    show = sub.add_parser("show")
    show.add_argument("root")
    show.add_argument("--as-of")
    show.set_defaults(func=cmd_show)

    export = sub.add_parser("export")
    export.add_argument("root")
    export.add_argument("--as-of")
    export.set_defaults(func=cmd_export)

    validate = sub.add_parser("validate-proposal")
    validate.add_argument("proposal")
    validate.set_defaults(func=cmd_validate_proposal)

    plan_commit = sub.add_parser("plan-commit")
    plan_commit.add_argument("root")
    plan_commit.add_argument("proposal")
    plan_commit.set_defaults(func=cmd_plan_commit)

    commit = sub.add_parser("commit")
    commit.add_argument("root")
    commit.add_argument("proposal")
    commit.add_argument("--expected-version", required=True, type=int)
    commit.add_argument("--confirmation-hash", required=True)
    commit.add_argument("--confirmed-at", required=True)
    commit.set_defaults(func=cmd_commit)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except StateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
