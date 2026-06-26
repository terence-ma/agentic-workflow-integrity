#!/usr/bin/env python3
"""
gap_registry.py — Process Integrity Skill
Read, write, and close entries in the agent gap registry.

Usage:
  # Register a gap
  python3 gap_registry.py --workspace /path/to/workspace \
    --gap "Description of gap" \
    --workflow "workflow-name" \
    --failure-class "weak-supervision" \
    --ttl 60

  # Close a gap
  python3 gap_registry.py --workspace /path/to/workspace \
    --close <gap-id> \
    --proof "verification output" \
    --execution-context "ran from production path"

  # List open gaps
  python3 gap_registry.py --workspace /path/to/workspace --list-open

  # List overdue gaps
  python3 gap_registry.py --workspace /path/to/workspace --list-overdue
"""

import json
import uuid
import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


REGISTRY_FILENAME = "gap-registry.jsonl"

VALID_FAILURE_CLASSES = [
    "surface-fix",
    "insufficient-decomposition",
    "blocking-gate",
    "weak-supervision",
    "acknowledged-not-implemented",
    "half-done-workflow",
    "false-tool-unavailability",
    "premature-escalation",
    "weak-followup",
    "source-of-truth-not-used",
    "other",
]


def _registry_path(workspace: str) -> Path:
    p = Path(workspace) / "state" / REGISTRY_FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _load_registry(workspace: str) -> list[dict]:
    path = _registry_path(workspace)
    if not path.exists():
        return []
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def _save_registry(workspace: str, entries: list[dict]) -> None:
    path = _registry_path(workspace)
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def register_gap(
    workspace: str,
    gap: str,
    workflow: str,
    failure_class: str = "other",
    ttl_minutes: int = 60,
    source: str = "manual",
    artifact_path: str = None,
) -> dict:
    """Register a new gap. Returns the created entry."""
    if failure_class not in VALID_FAILURE_CLASSES:
        failure_class = "other"

    entry = {
        "gapId": str(uuid.uuid4()),
        "identifiedAt": _now_iso(),
        "gap": gap,
        "workflow": workflow,
        "failureClass": failure_class,
        "ttlMinutes": ttl_minutes,
        "status": "open",
        "source": source,
        "artifactPath": artifact_path,
        "closedAt": None,
        "proof": None,
        "executionContext": None,
    }

    entries = _load_registry(workspace)
    entries.append(entry)
    _save_registry(workspace, entries)

    print(f"[gap-registry] Registered gap {entry['gapId']}: {gap}")
    return entry


def close_gap(
    workspace: str,
    gap_id: str,
    proof: str,
    execution_context: str,
) -> dict:
    """
    Close a gap. Requires production proof and execution context.
    A gap closed without proof is rejected.
    """
    if not proof or not proof.strip():
        print("[gap-registry] ERROR: Cannot close gap without proof. Provide verification output.")
        sys.exit(1)

    if not execution_context or not execution_context.strip():
        print("[gap-registry] ERROR: Cannot close gap without execution context. Specify where the fix was verified.")
        sys.exit(1)

    entries = _load_registry(workspace)
    found = False
    for entry in entries:
        if entry["gapId"] == gap_id:
            if entry["status"] == "closed":
                print(f"[gap-registry] Gap {gap_id} is already closed.")
                return entry
            entry["status"] = "closed"
            entry["closedAt"] = _now_iso()
            entry["proof"] = proof.strip()
            entry["executionContext"] = execution_context.strip()
            found = True
            print(f"[gap-registry] Closed gap {gap_id}: {entry['gap']}")
            break

    if not found:
        print(f"[gap-registry] ERROR: Gap {gap_id} not found in registry.")
        sys.exit(1)

    _save_registry(workspace, entries)
    return entry


def list_open_gaps(workspace: str) -> list[dict]:
    """Return all open gaps."""
    return [e for e in _load_registry(workspace) if e["status"] == "open"]


def list_overdue_gaps(workspace: str) -> list[dict]:
    """Return all open gaps that have exceeded their TTL."""
    now = datetime.now(timezone.utc)
    overdue = []
    for entry in _load_registry(workspace):
        if entry["status"] != "open":
            continue
        identified = datetime.fromisoformat(entry["identifiedAt"])
        ttl = timedelta(minutes=entry.get("ttlMinutes", 60))
        if now - identified > ttl:
            age_minutes = int((now - identified).total_seconds() / 60)
            entry["_ageMinutes"] = age_minutes
            overdue.append(entry)
    return overdue


def gap_report(workspace: str, period_days: int = 14) -> dict:
    """Produce a closure rate report for the given period."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=period_days)
    entries = [
        e for e in _load_registry(workspace)
        if datetime.fromisoformat(e["identifiedAt"]) >= cutoff
    ]

    total = len(entries)
    closed = [e for e in entries if e["status"] == "closed"]
    open_gaps = [e for e in entries if e["status"] == "open"]

    by_class = {}
    for e in entries:
        fc = e.get("failureClass", "other")
        if fc not in by_class:
            by_class[fc] = {"total": 0, "closed": 0}
        by_class[fc]["total"] += 1
        if e["status"] == "closed":
            by_class[fc]["closed"] += 1

    avg_close_minutes = None
    if closed:
        times = []
        for e in closed:
            if e.get("closedAt"):
                identified = datetime.fromisoformat(e["identifiedAt"])
                closed_at = datetime.fromisoformat(e["closedAt"])
                times.append((closed_at - identified).total_seconds() / 60)
        if times:
            avg_close_minutes = int(sum(times) / len(times))

    return {
        "periodDays": period_days,
        "totalIdentified": total,
        "totalClosed": len(closed),
        "closureRate": f"{int(len(closed)/total*100)}%" if total else "n/a",
        "avgCloseMinutes": avg_close_minutes,
        "openGaps": len(open_gaps),
        "byFailureClass": by_class,
    }


def main():
    parser = argparse.ArgumentParser(description="Process Integrity Gap Registry")
    parser.add_argument("--workspace", required=True, help="Absolute path to agent workspace")
    parser.add_argument("--gap", help="Gap description (for registration)")
    parser.add_argument("--workflow", help="Workflow name (for registration)")
    parser.add_argument("--failure-class", default="other", help="Failure class")
    parser.add_argument("--ttl", type=int, default=60, help="TTL in minutes")
    parser.add_argument("--source", default="manual", help="Source: manual or scanner")
    parser.add_argument("--artifact-path", help="Path to artifact where gap was found")
    parser.add_argument("--close", metavar="GAP_ID", help="Close a gap by ID")
    parser.add_argument("--proof", help="Production proof (required for close)")
    parser.add_argument("--execution-context", help="Where fix was verified (required for close)")
    parser.add_argument("--list-open", action="store_true", help="List all open gaps")
    parser.add_argument("--list-overdue", action="store_true", help="List overdue gaps")
    parser.add_argument("--report", action="store_true", help="Print gap closure report")
    parser.add_argument("--period", type=int, default=14, help="Report period in days")

    args = parser.parse_args()

    if args.close:
        close_gap(
            workspace=args.workspace,
            gap_id=args.close,
            proof=args.proof or "",
            execution_context=args.execution_context or "",
        )

    elif args.gap:
        register_gap(
            workspace=args.workspace,
            gap=args.gap,
            workflow=args.workflow or "unknown",
            failure_class=args.failure_class,
            ttl_minutes=args.ttl,
            source=args.source,
            artifact_path=args.artifact_path,
        )

    elif args.list_open:
        gaps = list_open_gaps(args.workspace)
        if not gaps:
            print("[gap-registry] No open gaps.")
        for g in gaps:
            print(f"  [{g['gapId'][:8]}] {g['gap']} ({g['failureClass']}) — identified {g['identifiedAt']}")

    elif args.list_overdue:
        gaps = list_overdue_gaps(args.workspace)
        if not gaps:
            print("[gap-registry] No overdue gaps.")
        for g in gaps:
            print(f"  [{g['gapId'][:8]}] {g['gap']} — {g['_ageMinutes']}min overdue ({g['failureClass']})")

    elif args.report:
        report = gap_report(args.workspace, args.period)
        print(json.dumps(report, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
