#!/usr/bin/env python3
"""
independent_verifier_template.py — Process Integrity Skill

Template for a same-agent, independent-execution-context verifier.
Copy and customise the CONFIGURATION section for each workflow.

This verifier fires outside the supervised workflow's cron stack.
It must deliver even if the entire main workflow is broken.
It must never depend on the main workflow's scripts or state.

Usage:
  python3 {workflow}_verifier.py --slot morning --date 2026-06-27
  python3 {workflow}_verifier.py --verify
  python3 {workflow}_verifier.py --dry-run --slot morning
"""

import json, sys, shutil, argparse
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Optional

# ================================================================
# CONFIGURATION — customise this section for each workflow
# ================================================================

WORKSPACE         = Path("/path/to/agent/workspace")
DELIVERY_STATE_DIR = WORKSPACE / "state" / "daily-brief-delivery"
FALLBACK_INPUTS   = WORKSPACE / "state" / "last-known-good"
VERIFIER_LOG_DIR  = WORKSPACE / "state" / "verifier-runs"

SEND_DEADLINES = {"morning": "08:00", "evening": "21:00"}

def delivery_state_path(slot: str, d: str) -> Path:
    """Return path to the delivery state file for this slot and date."""
    return DELIVERY_STATE_DIR / f"{d}-{slot}.json"

def is_delivered(state: dict) -> bool:
    """Return True if the deliverable has been confirmed sent and receipt proved."""
    return state.get("status") == "sent" and state.get("receiptProved") is True

# ----------------------------------------------------------------
# REPAIR PRIMITIVES — one per failure class
# Each must be self-contained. Never call main workflow scripts.
# Returns: (success: bool, proof: str)
# ----------------------------------------------------------------

def repair_import_path(detail: dict):
    """Fix Python import path issues."""
    # Implement: add correct sys.path entry, verify import resolves
    return False, "repair_import_path: implement for this workflow"

def repair_missing_artifact(detail: dict):
    """Rebuild a missing required artifact from fallback inputs."""
    artifact_path = Path(detail.get("artifactPath", ""))
    if artifact_path.exists():
        return True, f"Artifact already exists: {artifact_path}"
    
    # Try fallback
    fallback = FALLBACK_INPUTS / artifact_path.name
    if fallback.exists():
        shutil.copy(fallback, artifact_path)
        return True, f"Restored from fallback: {fallback} -> {artifact_path}"
    
    return False, f"Cannot repair missing artifact: {artifact_path} — no fallback available"

def repair_attestation(detail: dict):
    """Generate a verifier attestation when the primary attestation is missing."""
    attest_path = Path(detail.get("attestationPath", ""))
    if attest_path.exists():
        return True, f"Attestation exists: {attest_path}"
    
    attestation = {
        "attestedAt": now_iso(),
        "attestedBy": "independent-verifier",
        "note": "Verifier-generated attestation. Primary QC attestation was unavailable.",
        "status": "verifier-attested"
    }
    attest_path.parent.mkdir(parents=True, exist_ok=True)
    attest_path.write_text(json.dumps(attestation, indent=2))
    return True, f"Generated verifier attestation: {attest_path}"

def repair_send_failure(detail: dict):
    """Retry send with longer timeout or alternative channel."""
    # Implement: retry send_deliverable() with extended timeout
    return False, "repair_send_failure: implement retry logic for this workflow"

# Map failure classes to repair functions
REPAIR_PRIMITIVES = {
    "import-path-failure":    repair_import_path,
    "missing-artifact":       repair_missing_artifact,
    "missing-attestation":    repair_attestation,
    "send-failure":           repair_send_failure,
}

def send_deliverable(slot: str, d: str, artifacts: list, fallback_used: bool) -> tuple:
    """
    Send the deliverable. Implement per workflow.
    Returns (success: bool, proof: str).
    """
    # Implement: Telegram send, email, file write, etc.
    return False, "send_deliverable: implement for this workflow"

def generate_fallback_deliverable(slot: str, d: str) -> tuple:
    """
    Generate a minimal deliverable from last-known-good inputs.
    This must always succeed — it is the final fallback.
    Returns (artifact_paths: list, note: str).
    """
    # Implement: use FALLBACK_INPUTS to produce a minimal valid deliverable
    # Mark it clearly as a fallback
    note = f"FALLBACK: Generated from cached inputs ({d} {slot}). Review before treating as current."
    return [], note

# ================================================================
# CORE VERIFIER LOGIC — generally do not customise below here
# ================================================================

def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat()

def read_delivery_state(slot: str, d: str) -> Optional[dict]:
    path = delivery_state_path(slot, d)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None

def read_failure_records(slot: str, d: str) -> list:
    """Read failure state files. Never re-run the workflow to find what failed."""
    records = []
    runs_dir = WORKSPACE / "state" / "workflow-runs"
    for pattern in [f"{d}-{slot}*.log", f"{d}-{slot}*.json"]:
        for p in runs_dir.glob(pattern) if runs_dir.exists() else []:
            try:
                content = p.read_text()
                try:
                    records.append({"file": str(p), "content": json.loads(content)})
                except Exception:
                    records.append({"file": str(p), "content": content[:1000]})
            except Exception:
                pass
    return records

def identify_failure_class(records: list) -> tuple:
    """Identify failure class from state files. Returns (class, detail_dict)."""
    for r in records:
        s = json.dumps(r.get("content", "")) if isinstance(r.get("content"), dict) else str(r.get("content", ""))
        if "ModuleNotFoundError" in s:
            return "import-path-failure", {"error": s[:200]}
        if "missing" in s.lower() and "artifact" in s.lower():
            return "missing-artifact", {"artifactPath": ""}
        if "attestation" in s.lower():
            return "missing-attestation", {"attestationPath": ""}
        if "send" in s.lower() and ("fail" in s.lower() or "error" in s.lower()):
            return "send-failure", {}
    return "unknown", {"recordCount": len(records)}

def update_last_known_good(artifacts: list, slot: str, d: str):
    """Update LKG after every successful delivery."""
    FALLBACK_INPUTS.mkdir(parents=True, exist_ok=True)
    saved = []
    for a in artifacts:
        ap = Path(a)
        if ap.exists():
            shutil.copy(ap, FALLBACK_INPUTS / ap.name)
            saved.append(ap.name)
    (FALLBACK_INPUTS / "metadata.json").write_text(json.dumps({
        "updatedAt": now_iso(),
        "slot": slot, "date": d,
        "artifacts": saved
    }))

def write_verifier_log(slot: str, d: str, outcome: dict):
    VERIFIER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = VERIFIER_LOG_DIR / f"{d}-{slot}-verifier.json"
    log.write_text(json.dumps(outcome, indent=2))
    print(f"[verifier] Log: {log}")

def run_verifier(slot: str, d: str, dry_run: bool = False) -> dict:
    print(f"[verifier] Running for {d} {slot}")

    outcome = {
        "runAt": now_iso(), "slot": slot, "date": d,
        "status": None, "action": None,
        "repairUsed": None, "fallbackUsed": False, "proof": None
    }

    # Step 1: Check delivery state — source of truth
    state = read_delivery_state(slot, d)
    if state and is_delivered(state):
        print(f"[verifier] Already delivered. Nothing to do.")
        outcome.update({"status": "already-delivered", "action": "none"})
        write_verifier_log(slot, d, outcome)
        return outcome

    print(f"[verifier] Not delivered. Diagnosing from state files (not re-running workflow)...")

    # Step 2: Identify failure from state files
    records = read_failure_records(slot, d)
    failure_class, failure_detail = identify_failure_class(records)
    print(f"[verifier] Failure class: {failure_class}")
    outcome["failureClass"] = failure_class

    if dry_run:
        print(f"[verifier] DRY RUN — would apply repair: {failure_class}")
        outcome["status"] = "dry-run"
        return outcome

    # Step 3: Apply verifier's own repair primitive
    artifacts = []
    if failure_class in REPAIR_PRIMITIVES:
        print(f"[verifier] Applying repair primitive: {failure_class}")
        repair_fn = REPAIR_PRIMITIVES[failure_class]
        success, proof = repair_fn(failure_detail)
        outcome.update({"repairUsed": failure_class, "repairProof": proof})

        if success:
            print(f"[verifier] Repair succeeded: {proof[:100]}")
        else:
            print(f"[verifier] Repair failed: {proof[:100]}. Using fallback.")
            outcome["fallbackUsed"] = True
            artifacts, note = generate_fallback_deliverable(slot, d)
            print(f"[verifier] Fallback: {note}")
    else:
        print(f"[verifier] No repair primitive for: {failure_class}. Using fallback.")
        outcome["fallbackUsed"] = True
        artifacts, note = generate_fallback_deliverable(slot, d)

    # Step 4: Send (with verifier's own send path)
    print(f"[verifier] Sending deliverable...")
    send_success, send_proof = send_deliverable(slot, d, artifacts, outcome["fallbackUsed"])

    if send_success:
        outcome.update({"status": "verifier-delivered", "proof": send_proof})
        update_last_known_good(artifacts, slot, d)
        print(f"[verifier] Delivered successfully.")
    else:
        outcome.update({"status": "verifier-send-failed", "proof": send_proof})
        print(f"[verifier] WARN: Send failed: {send_proof}")
        # Final fallback: write to known location
        emergency_path = WORKSPACE / "state" / f"emergency-delivery-{d}-{slot}.txt"
        emergency_path.write_text(f"Emergency delivery record\n{now_iso()}\n{send_proof}")
        print(f"[verifier] Emergency record written: {emergency_path}")

    write_verifier_log(slot, d, outcome)
    return outcome


def main():
    p = argparse.ArgumentParser(description="Independent Verifier — Process Integrity Skill")
    p.add_argument("--slot", choices=["morning", "evening"], default="morning")
    p.add_argument("--date", default=str(date.today()))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify", action="store_true")
    args = p.parse_args()

    if args.verify:
        print("[verifier] Verification mode")
        print(f"  Workspace: {WORKSPACE}")
        print(f"  Delivery state dir: {DELIVERY_STATE_DIR}")
        print(f"  Fallback inputs: {FALLBACK_INPUTS}")
        print(f"  Repair primitives: {list(REPAIR_PRIMITIVES.keys())}")

        # Check imports work from this execution context
        try:
            import json, shutil, uuid
            print("  Imports: OK")
        except ImportError as e:
            print(f"  FAIL: Import error: {e}")
            sys.exit(1)

        # Check we can write to workspace
        test = WORKSPACE / "state" / ".verifier-test"
        try:
            test.parent.mkdir(parents=True, exist_ok=True)
            test.write_text("test")
            test.unlink()
            print("  Write access: OK")
        except Exception as e:
            print(f"  FAIL: Cannot write: {e}")
            sys.exit(1)

        print("[verifier] status: ok")
        sys.exit(0)

    outcome = run_verifier(args.slot, args.date, args.dry_run)
    print(f"\n[verifier] Final status: {outcome['status']}")
    sys.exit(0 if outcome["status"] in ("already-delivered", "verifier-delivered", "dry-run") else 1)


if __name__ == "__main__":
    main()
