#!/usr/bin/env python3
"""
gap_registry.py — Process Integrity Skill
Atomic gap registration and closure.

Gap identification and enforcement are the same atomic action.
Writing a gap to this registry begins enforcement automatically.

Usage:
  python3 gap_registry.py write --gap "desc" --workflow "name" --class "failure-class" --ttl 60
  python3 gap_registry.py close --id "uuid" --proof "verbatim production output"
  python3 gap_registry.py list [--status open|closed]
  python3 gap_registry.py enforce --workspace /path/to/workspace
  python3 gap_registry.py verify
"""

import json, uuid, argparse, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat()


def get_registry_path(workspace: Path = None) -> Path:
    if workspace:
        return workspace / "state" / "gap-registry" / "registry.jsonl"
    return Path("state/gap-registry/registry.jsonl")


def load(path: Path) -> list:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def save(path: Path, entries: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def write_gap(path: Path, gap: str, workflow: str, failure_class: str, ttl: int = 60) -> dict:
    entry = {
        "id": str(uuid.uuid4()),
        "identifiedAt": now_iso(),
        "gap": gap,
        "workflow": workflow,
        "failureClass": failure_class,
        "ttlMinutes": ttl,
        "status": "open",
        "closedAt": None,
        "proof": None
    }
    entries = load(path)
    entries.append(entry)
    save(path, entries)
    print(f"[gap-registry] Registered: {entry['id'][:8]}... | {workflow} | {failure_class}")
    print(f"  Gap: {gap}")
    print(f"  TTL: {ttl} minutes. Enforcement begins now.")
    return entry


def close_gap(path: Path, gap_id: str, proof: str) -> dict:
    entries = load(path)
    closed = None
    for e in entries:
        if e["id"] == gap_id:
            if e["status"] == "closed":
                print(f"[gap-registry] Already closed: {gap_id[:8]}...")
                return e
            e["status"] = "closed"
            e["closedAt"] = now_iso()
            e["proof"] = proof
            closed = e
            break
    if not closed:
        print(f"[gap-registry] ERROR: Not found: {gap_id}", file=sys.stderr)
        sys.exit(1)
    save(path, entries)
    print(f"[gap-registry] Closed: {gap_id[:8]}...")
    return closed


def get_overdue(path: Path) -> list:
    entries = load(path)
    now = datetime.now(timezone.utc).astimezone()
    overdue = []
    for e in entries:
        if e["status"] != "open":
            continue
        identified_at = datetime.fromisoformat(e["identifiedAt"])
        age = now - identified_at
        ttl = timedelta(minutes=e["ttlMinutes"])
        if age > ttl:
            e["_ageMin"] = int(age.total_seconds() / 60)
            e["_overdueMin"] = int((age - ttl).total_seconds() / 60)
            overdue.append(e)
    return overdue


def enforcement_message(gaps: list) -> str:
    lines = [
        "PROCESS INTEGRITY ALERT — mandatory first actions",
        f"Generated: {now_iso()}",
        f"Overdue gaps requiring immediate resolution: {len(gaps)}",
        "",
        "Resolve ALL of the following before any other work:",
        ""
    ]
    for i, g in enumerate(gaps, 1):
        lines += [
            f"{'='*50}",
            f"GAP {i}/{len(gaps)} | ID: {g['id']}",
            f"Workflow: {g['workflow']} | Class: {g['failureClass']}",
            f"Gap: {g['gap']}",
            f"Open: {g['_ageMin']}min | Overdue: {g['_overdueMin']}min",
            "",
            "Required:",
            "1. Fix the gap now",
            "2. Verify from production execution context (not test harness)",
            f"3. Close: python3 scripts/gap_registry.py close --id {g['id']} --proof \"output\"",
            ""
        ]
    lines += [
        "="*50,
        "",
        "Closing standard:",
        "- Fix exists on disk at specified path",
        "- Verified from production execution context",
        "- Verification output recorded as proof",
        "- Failure-injection test exists for this class",
        "",
        "Do not proceed to other work until all gaps above are closed."
    ]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Gap Registry — Process Integrity Skill")
    p.add_argument("command", choices=["write", "close", "list", "enforce", "verify"])
    p.add_argument("--workspace", default=None)
    p.add_argument("--gap")
    p.add_argument("--workflow")
    p.add_argument("--class", dest="failure_class")
    p.add_argument("--ttl", type=int, default=60)
    p.add_argument("--id", dest="gap_id")
    p.add_argument("--proof")
    p.add_argument("--status", default=None)
    args = p.parse_args()

    workspace = Path(args.workspace) if args.workspace else None
    path = get_registry_path(workspace)

    if args.command == "write":
        if not all([args.gap, args.workflow, args.failure_class]):
            print("ERROR: --gap, --workflow, --class required", file=sys.stderr)
            sys.exit(1)
        write_gap(path, args.gap, args.workflow, args.failure_class, args.ttl)

    elif args.command == "close":
        if not all([args.gap_id, args.proof]):
            print("ERROR: --id and --proof required", file=sys.stderr)
            sys.exit(1)
        close_gap(path, args.gap_id, args.proof)

    elif args.command == "list":
        entries = load(path)
        if args.status:
            entries = [e for e in entries if e["status"] == args.status]
        if not entries:
            print(f"[gap-registry] No entries (filter: {args.status or 'all'})")
            return
        for e in entries:
            age = ""
            if e["status"] == "open":
                identified_at = datetime.fromisoformat(e["identifiedAt"])
                mins = int((datetime.now(timezone.utc).astimezone() - identified_at).total_seconds() / 60)
                age = f" ({mins}m old)"
            print(f"  [{e['status'].upper()}] {e['id'][:8]}... {e['workflow']}: {e['gap'][:60]}{age}")

    elif args.command == "enforce":
        if not workspace:
            print("ERROR: --workspace required for enforce", file=sys.stderr)
            sys.exit(1)
        overdue = get_overdue(path)
        if not overdue:
            print("[gap-registry] No overdue gaps. All clear.")
            sys.exit(0)
        msg = enforcement_message(overdue)
        inbox = workspace / "state" / "enforcement-inbox.md"
        inbox.parent.mkdir(parents=True, exist_ok=True)
        inbox.write_text(f"# Enforcement Inbox\nGenerated: {now_iso()}\n\n{msg}")
        print(f"[gap-registry] {len(overdue)} overdue gap(s). Enforcement inbox written.")
        print(msg)
        sys.exit(1)

    elif args.command == "verify":
        print("[gap-registry] Verify mode")
        entries = load(path)
        open_gaps = [e for e in entries if e["status"] == "open"]
        closed_gaps = [e for e in entries if e["status"] == "closed"]
        overdue = get_overdue(path)
        print(f"  Registry: {path}")
        print(f"  Total: {len(entries)} | Open: {len(open_gaps)} | Closed: {len(closed_gaps)} | Overdue: {len(overdue)}")
        print("[gap-registry] Registry readable and well-formed.")


if __name__ == "__main__":
    main()
