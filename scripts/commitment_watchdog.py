#!/usr/bin/env python3
"""
commitment_watchdog.py — Process Integrity Skill
Anti-drift watchdog for internal workflows with ETA commitments.

Every ETA commitment must be registered here. The watchdog fires
at committed checkpoints and verifies actual vs committed state.
An unregistered commitment cannot be enforced.

Usage:
  python3 commitment_watchdog.py --workspace /path --add --workflow "X" --milestone "Y" --deadline "ISO"
  python3 commitment_watchdog.py --workspace /path --update --id "uuid" --state "actual state"
  python3 commitment_watchdog.py --workspace /path --close --id "uuid" --proof "what was done"
  python3 commitment_watchdog.py --workspace /path  (run check)
  python3 commitment_watchdog.py --workspace /path --verify
"""

import json, uuid, argparse, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat()


def registry_path(workspace: Path) -> Path:
    return workspace / "state" / "commitment-registry" / "registry.json"


def load(path: Path) -> dict:
    if not path.exists():
        return {"commitments": []}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {"commitments": []}


def save(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def add_commitment(path: Path, workflow: str, milestone: str,
                   deadline: str, checkpoints: list = None) -> dict:
    data = load(path)
    entry = {
        "id": str(uuid.uuid4()),
        "workflow": workflow,
        "milestone": milestone,
        "committedAt": now_iso(),
        "deadline": deadline,
        "checkpoints": checkpoints or [],
        "status": "active",
        "lastCheckedAt": None,
        "actualState": None,
        "closedAt": None,
        "proof": None
    }
    data["commitments"].append(entry)
    save(path, data)
    print(f"[commitment-watchdog] Registered: {entry['id'][:8]}... | {workflow}")
    print(f"  Milestone: {milestone}")
    print(f"  Deadline: {deadline}")
    print(f"  Enforcement begins now. Update actual state at each checkpoint.")
    return entry


def update_state(path: Path, commitment_id: str, state: str) -> dict:
    data = load(path)
    updated = None
    for e in data["commitments"]:
        if e["id"] == commitment_id:
            e["actualState"] = state
            e["lastCheckedAt"] = now_iso()
            updated = e
            break
    if not updated:
        print(f"[commitment-watchdog] ERROR: Not found: {commitment_id}", file=sys.stderr)
        sys.exit(1)
    save(path, data)
    print(f"[commitment-watchdog] State updated: {commitment_id[:8]}...")
    return updated


def close_commitment(path: Path, commitment_id: str, proof: str) -> dict:
    data = load(path)
    closed = None
    for e in data["commitments"]:
        if e["id"] == commitment_id:
            e["status"] = "closed"
            e["closedAt"] = now_iso()
            e["proof"] = proof
            closed = e
            break
    if not closed:
        print(f"[commitment-watchdog] ERROR: Not found: {commitment_id}", file=sys.stderr)
        sys.exit(1)
    save(path, data)
    print(f"[commitment-watchdog] Closed: {commitment_id[:8]}...")
    return closed


def get_overdue(path: Path) -> list:
    data = load(path)
    now = datetime.now(timezone.utc).astimezone()
    overdue = []
    for e in data["commitments"]:
        if e["status"] != "active":
            continue
        deadline = datetime.fromisoformat(e["deadline"])
        if now > deadline:
            age = now - deadline
            e["_overdueMin"] = int(age.total_seconds() / 60)
            overdue.append(e)
    return overdue


def get_due_checkpoints(path: Path) -> list:
    data = load(path)
    now = datetime.now(timezone.utc).astimezone()
    window = timedelta(minutes=30)
    due = []
    for e in data["commitments"]:
        if e["status"] != "active":
            continue
        for cp in e.get("checkpoints", []):
            cp_time = datetime.fromisoformat(cp)
            if abs(now - cp_time) <= window:
                e["_dueCheckpoint"] = cp
                due.append(e)
                break
    return due


def alert_message(commitments: list, reason: str) -> str:
    lines = [
        f"COMMITMENT WATCHDOG — {reason}",
        f"Generated: {now_iso()}",
        f"Commitments requiring attention: {len(commitments)}",
        ""
    ]
    for i, c in enumerate(commitments, 1):
        lines += [
            f"{'='*50}",
            f"COMMITMENT {i}/{len(commitments)} | ID: {c['id']}",
            f"Workflow: {c['workflow']}",
            f"Milestone: {c['milestone']}",
            f"Deadline: {c['deadline']}",
        ]
        if "_overdueMin" in c:
            lines.append(f"OVERDUE BY: {c['_overdueMin']} minutes")
        if "_dueCheckpoint" in c:
            lines.append(f"Checkpoint due: {c['_dueCheckpoint']}")
        if c.get("actualState"):
            lines.append(f"Last known state: {c['actualState']}")
        lines += [
            "",
            "Required:",
            "1. Stop current work. Assess actual state of this workflow now.",
            "2. Compare actual state against committed milestone.",
            "3. If on track: update state and continue.",
            "4. If drifted: re-anchor now. Update realistic ETA. Resume work.",
            f"   python3 scripts/commitment_watchdog.py --workspace {{WORKSPACE}} --update --id {c['id']} --state \"actual state\"",
            "5. If milestone cannot be met: say so with revised ETA.",
            "   Do not stay silent about a missed commitment.",
            ""
        ]
    lines += [
        "="*50,
        "",
        "You cannot acknowledge this alert and continue other work.",
        "Assess actual state first. Update registry. Then continue."
    ]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Commitment Watchdog — Process Integrity Skill")
    p.add_argument("--workspace", required=True)
    p.add_argument("--add", action="store_true")
    p.add_argument("--close", action="store_true")
    p.add_argument("--update", action="store_true")
    p.add_argument("--workflow")
    p.add_argument("--milestone")
    p.add_argument("--deadline")
    p.add_argument("--checkpoints", nargs="*")
    p.add_argument("--id", dest="commitment_id")
    p.add_argument("--proof")
    p.add_argument("--state")
    p.add_argument("--verify", action="store_true")
    args = p.parse_args()

    workspace = Path(args.workspace)
    path = registry_path(workspace)

    if args.verify:
        print("[commitment-watchdog] Verify mode")
        print(f"  Workspace: {workspace}")
        print(f"  Registry: {path} | Exists: {path.exists()}")
        if path.exists():
            data = load(path)
            active = [c for c in data["commitments"] if c["status"] == "active"]
            print(f"  Active commitments: {len(active)}")
        print("[commitment-watchdog] Watchdog correctly installed.")
        sys.exit(0)

    if args.add:
        if not all([args.workflow, args.milestone, args.deadline]):
            print("ERROR: --workflow, --milestone, --deadline required", file=sys.stderr)
            sys.exit(1)
        add_commitment(path, args.workflow, args.milestone, args.deadline, args.checkpoints)
        sys.exit(0)

    if args.close:
        if not all([args.commitment_id, args.proof]):
            print("ERROR: --id and --proof required", file=sys.stderr)
            sys.exit(1)
        close_commitment(path, args.commitment_id, args.proof)
        sys.exit(0)

    if args.update:
        if not all([args.commitment_id, args.state]):
            print("ERROR: --id and --state required", file=sys.stderr)
            sys.exit(1)
        update_state(path, args.commitment_id, args.state)
        sys.exit(0)

    # Default: run the watchdog check
    print(f"[commitment-watchdog] Running check at {now_iso()}")
    overdue = get_overdue(path)
    due = get_due_checkpoints(path)

    if not overdue and not due:
        print("[commitment-watchdog] All commitments on track.")
        sys.exit(0)

    if overdue:
        msg = alert_message(overdue, "overdue commitments")
        inbox = workspace / "state" / "enforcement-inbox.md"
        inbox.parent.mkdir(parents=True, exist_ok=True)
        existing = inbox.read_text() if inbox.exists() else ""
        inbox.write_text(existing + "\n\n" + msg)
        print(msg)

    if due:
        msg = alert_message(due, "checkpoint review required")
        print(msg)

    sys.exit(1)


if __name__ == "__main__":
    main()
