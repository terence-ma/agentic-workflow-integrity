#!/usr/bin/env python3
"""
gap_enforcer.py — Process Integrity Skill
The enforcement session script. This runs as a separate OpenClaw cron,
waking an independent session of the same agent whose sole job is to
close overdue gaps.

This script produces the enforcement session prompt that OpenClaw injects
at session start. The agent wakes, reads the prompt, and must close all
overdue gaps before doing anything else.

Usage (typically called by OpenClaw cron, not directly):
  python3 gap_enforcer.py --workspace /path/to/workspace

  # Check what would be enforced without waking the session
  python3 gap_enforcer.py --workspace /path/to/workspace --dry-run

  # Generate the enforcement prompt for a specific session
  python3 gap_enforcer.py --workspace /path/to/workspace --generate-prompt
"""

import json
import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


def _load_overdue_gaps(workspace: str) -> list[dict]:
    """Load all overdue open gaps from the registry."""
    registry_path = Path(workspace) / "state" / "gap-registry.jsonl"
    if not registry_path.exists():
        return []

    now = datetime.now(timezone.utc)
    overdue = []

    with open(registry_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("status") != "open":
                continue

            identified = datetime.fromisoformat(entry["identifiedAt"])
            ttl = timedelta(minutes=entry.get("ttlMinutes", 60))

            if now - identified > ttl:
                age_minutes = int((now - identified).total_seconds() / 60)
                entry["_ageMinutes"] = age_minutes
                overdue.append(entry)

    # Sort by age descending — oldest gaps first
    overdue.sort(key=lambda x: x["_ageMinutes"], reverse=True)
    return overdue


def generate_enforcement_prompt(workspace: str) -> str:
    """
    Generate the enforcement session prompt. This is injected at the
    start of the enforcement session by OpenClaw.
    """
    overdue = _load_overdue_gaps(workspace)

    if not overdue:
        return (
            "PROCESS INTEGRITY ENFORCEMENT — SCAN COMPLETE\n\n"
            "No overdue gaps found. Gap registry is current.\n"
            "You may proceed with normal work.\n"
        )

    gap_list = ""
    for i, gap in enumerate(overdue, 1):
        gap_list += (
            f"\n{i}. [{gap['gapId'][:8]}] {gap['gap']}\n"
            f"   Workflow: {gap['workflow']}\n"
            f"   Failure class: {gap['failureClass']}\n"
            f"   Age: {gap['_ageMinutes']} minutes overdue\n"
            f"   Source: {gap['source']}\n"
        )
        if gap.get("artifactPath"):
            gap_list += f"   Found in: {gap['artifactPath']}\n"

    prompt = f"""PROCESS INTEGRITY ENFORCEMENT — READ FIRST — MANDATORY

You have been woken by the process integrity enforcement cron.
This is not a normal session. Your only job this session is to close overdue gaps.

OVERDUE GAPS ({len(overdue)} total):
{gap_list}

MANDATORY RULES FOR THIS SESSION:

1. Do not start any other work until every gap above is closed.

2. For each gap:
   a. Implement the fix — not plan it, not describe it, implement it now
   b. Verify from the PRODUCTION execution context — not a test harness,
      not workspace/, from the actual runtime path the workflow uses
   c. Paste the verification output verbatim
   d. Close the gap in the registry:
      python3 {workspace}/../../skills/process-integrity/gap_registry.py \\
        --workspace {workspace} \\
        --close <gap-id> \\
        --proof "<paste verification output here>" \\
        --execution-context "<where exactly you ran the verification>"

3. Do not write "I will fix" — fix it in this session.

4. Do not mark a gap closed without the proof field populated.

5. If you genuinely cannot fix a gap in this session, write:
   - The exact blocker (not a general caveat)
   - What specific capability is missing
   - What you will do in the next session to unblock it
   Then update the gap TTL and move to the next gap.

6. After all gaps are addressed, run the scanner to check for new gaps:
   python3 {workspace}/../../skills/process-integrity/gap_scanner.py \\
     --workspace {workspace}

7. This session is complete only when:
   - All overdue gaps are either closed with proof or have explicit
     documented blockers
   - The gap registry reflects current state
   - The scanner has run and new findings are registered

GAP REGISTRY LOCATION: {workspace}/state/gap-registry.jsonl

Begin with gap 1. Do not stop until all gaps are addressed.
"""
    return prompt


def run_enforcement_check(workspace: str) -> dict:
    """
    Check enforcement state. Returns dict with overdue count and status.
    Used by install.py and monitoring scripts.
    """
    overdue = _load_overdue_gaps(workspace)
    registry_path = Path(workspace) / "state" / "gap-registry.jsonl"

    all_gaps = []
    if registry_path.exists():
        with open(registry_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        all_gaps.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    open_gaps = [g for g in all_gaps if g.get("status") == "open"]
    closed_gaps = [g for g in all_gaps if g.get("status") == "closed"]

    return {
        "status": "enforcement_needed" if overdue else "ok",
        "overdueCount": len(overdue),
        "openCount": len(open_gaps),
        "closedCount": len(closed_gaps),
        "totalCount": len(all_gaps),
        "overdueGaps": [
            {
                "gapId": g["gapId"],
                "gap": g["gap"],
                "workflow": g["workflow"],
                "failureClass": g["failureClass"],
                "ageMinutes": g["_ageMinutes"],
            }
            for g in overdue
        ],
        "checkedAt": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="Process Integrity Gap Enforcer")
    parser.add_argument("--workspace", required=True,
                        help="Absolute path to agent workspace")
    parser.add_argument("--dry-run", action="store_true",
                        help="Check what would be enforced without taking action")
    parser.add_argument("--generate-prompt", action="store_true",
                        help="Generate and print the enforcement session prompt")
    parser.add_argument("--status", action="store_true",
                        help="Print enforcement status as JSON")

    args = parser.parse_args()

    if args.generate_prompt:
        prompt = generate_enforcement_prompt(args.workspace)
        print(prompt)
        return

    if args.status:
        result = run_enforcement_check(args.workspace)
        print(json.dumps(result, indent=2))
        return

    result = run_enforcement_check(args.workspace)

    if args.dry_run:
        print(f"[gap-enforcer] Dry run — enforcement status: {result['status']}")
        print(f"[gap-enforcer] Overdue gaps: {result['overdueCount']}")
        for g in result["overdueGaps"]:
            print(f"  [{g['gapId'][:8]}] {g['gap']} — {g['ageMinutes']}min overdue")
        return

    if result["overdueCount"] == 0:
        print("[gap-enforcer] No overdue gaps. Registry is current.")
        return

    print(f"[gap-enforcer] {result['overdueCount']} overdue gaps found.")
    print("[gap-enforcer] Generating enforcement prompt for session injection...")

    prompt = generate_enforcement_prompt(args.workspace)
    print("\n" + "=" * 60)
    print(prompt)
    print("=" * 60)
    print(f"\n[gap-enforcer] Enforcement prompt generated. "
          f"Inject into enforcement session via OpenClaw cron payload.")


if __name__ == "__main__":
    main()
