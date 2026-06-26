#!/usr/bin/env python3
"""
gap_enforcer.py — Process Integrity Skill
Independent enforcement cron for the gap registry.

Runs on its own schedule outside the supervised workflows.
Reads the gap registry, fires enforcement messages for overdue gaps.

Register as an isolated OpenClaw cron with a distinct session key:
  session key: agent:{id}:gap-enforcer
  schedule: every 2 hours
  isolated: true

Usage:
  python3 gap_enforcer.py --workspace /path/to/workspace
  python3 gap_enforcer.py --workspace /path --verify
  python3 gap_enforcer.py --workspace /path --dry-run
"""

import json, argparse, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat()


def registry_path(workspace: Path) -> Path:
    return workspace / "state" / "gap-registry" / "registry.jsonl"


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
        f"Overdue gaps: {len(gaps)}",
        "",
        "Resolve ALL of the following before any other work:",
        ""
    ]
    for i, g in enumerate(gaps, 1):
        lines += [
            f"{'='*50}",
            f"GAP {i}/{len(gaps)} | {g['id']}",
            f"Workflow: {g['workflow']} | Class: {g['failureClass']}",
            f"Gap: {g['gap']}",
            f"Open: {g['_ageMin']}min | Overdue: {g['_overdueMin']}min",
            "",
            "Steps:",
            "1. Fix the gap",
            "2. Verify from production execution context",
            f"3. Close: python3 scripts/gap_registry.py close --id {g['id']} --proof \"output\"",
            ""
        ]
    lines += [
        "="*50,
        "",
        "Closing standard — a gap is closed only when:",
        "- Fix exists on disk at specified path",
        "- Verified from production execution context (not test harness)",
        "- Verification output recorded as proof",
        "- Failure-injection test exists for this class",
        "",
        "Do not proceed to other work until all gaps are closed."
    ]
    return "\n".join(lines)


def write_to_inbox(workspace: Path, message: str):
    inbox = workspace / "state" / "enforcement-inbox.md"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    existing = inbox.read_text() if inbox.exists() else ""
    inbox.write_text(f"# Enforcement Inbox\nGenerated: {now_iso()}\n\n{message}\n\n{existing}")
    print(f"[gap-enforcer] Enforcement inbox written: {inbox}")


def log_run(workspace: Path, overdue: list, action: str):
    log = workspace / "state" / "gap-enforcer-log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a") as f:
        f.write(json.dumps({
            "runAt": now_iso(),
            "overdueCount": len(overdue),
            "gapIds": [g["id"] for g in overdue],
            "action": action
        }) + "\n")


def main():
    p = argparse.ArgumentParser(description="Gap Enforcer — Process Integrity Skill")
    p.add_argument("--workspace", required=True)
    p.add_argument("--verify", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    workspace = Path(args.workspace)
    path = registry_path(workspace)

    if args.verify:
        print("[gap-enforcer] Verify mode")
        print(f"  Workspace: {workspace}")
        print(f"  Registry: {path} | Exists: {path.exists()}")
        if path.exists():
            entries = load(path)
            open_gaps = [e for e in entries if e["status"] == "open"]
            overdue = get_overdue(path)
            print(f"  Total: {len(entries)} | Open: {len(open_gaps)} | Overdue: {len(overdue)}")
        print("[gap-enforcer] Enforcer correctly installed.")
        sys.exit(0)

    print(f"[gap-enforcer] Running at {now_iso()}")

    if not path.exists():
        print("[gap-enforcer] No registry. Nothing to enforce.")
        log_run(workspace, [], "no-registry")
        sys.exit(0)

    overdue = get_overdue(path)

    if not overdue:
        print("[gap-enforcer] No overdue gaps. All clear.")
        log_run(workspace, [], "all-clear")
        sys.exit(0)

    print(f"[gap-enforcer] {len(overdue)} overdue gap(s):")
    for g in overdue:
        print(f"  [{g['failureClass']}] {g['workflow']}: {g['gap'][:60]} ({g['_overdueMin']}m overdue)")

    msg = enforcement_message(overdue)

    if args.dry_run:
        print("\n[gap-enforcer] DRY RUN:")
        print(msg)
        sys.exit(0)

    write_to_inbox(workspace, msg)
    log_run(workspace, overdue, "enforcement-fired")
    print(f"[gap-enforcer] Enforcement complete.")
    sys.exit(1)  # Non-zero signals cron to escalate


if __name__ == "__main__":
    main()
