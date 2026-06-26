#!/usr/bin/env python3
"""
failure_injector.py — Process Integrity Skill
Test harness for failure-class injection.

Tests that repair primitives and independent verifiers actually work
by injecting real failure conditions and verifying recovery.

Usage:
  python3 failure_injector.py --workflow daily-brief --step commentary --class forbidden-marker
  python3 failure_injector.py --workflow daily-brief --all
  python3 failure_injector.py --list-classes
"""

import argparse, json, sys, shutil, tempfile
from pathlib import Path
from datetime import datetime, timezone


FAILURE_CLASSES = {
    "missing-artifact": {
        "description": "Required artifact file does not exist",
        "inject": lambda ctx: ctx["artifact_path"].unlink(missing_ok=True),
        "restore": lambda ctx, bak: shutil.copy(bak, ctx["artifact_path"]) if bak else None,
    },
    "empty-artifact": {
        "description": "Required artifact exists but is empty (zero bytes)",
        "inject": lambda ctx: ctx["artifact_path"].write_text(""),
        "restore": lambda ctx, bak: shutil.copy(bak, ctx["artifact_path"]) if bak else None,
    },
    "forbidden-marker": {
        "description": "Artifact contains a forbidden marker word",
        "inject": lambda ctx: ctx["artifact_path"].write_text(
            ctx["artifact_path"].read_text() + "\n\nhandoff: this is a test injection"
            if ctx["artifact_path"].exists() else "handoff: test"
        ),
        "restore": lambda ctx, bak: shutil.copy(bak, ctx["artifact_path"]) if bak else None,
    },
    "import-path": {
        "description": "Python script cannot import a required module",
        "inject": lambda ctx: None,  # Simulate by running from wrong directory
        "restore": lambda ctx, bak: None,
    },
    "missing-attestation": {
        "description": "QC attestation file is missing at send time",
        "inject": lambda ctx: ctx.get("attestation_path", Path("/dev/null")).unlink(missing_ok=True),
        "restore": lambda ctx, bak: shutil.copy(bak, ctx["attestation_path"]) if bak and "attestation_path" in ctx else None,
    },
    "stale-delivery-state": {
        "description": "Delivery state file shows old date, causing false 'already delivered'",
        "inject": lambda ctx: ctx["state_path"].write_text(json.dumps({
            "status": "sent", "receiptProved": True, "sentAt": "2020-01-01T00:00:00+00:00"
        })) if "state_path" in ctx else None,
        "restore": lambda ctx, bak: shutil.copy(bak, ctx["state_path"]) if bak and "state_path" in ctx else None,
    },
    "watch-false-trigger": {
        "description": "Watch file contains no-update wording that falsely triggers actionable review",
        "inject": lambda ctx: ctx["watch_path"].write_text(
            "No named counters produced same-day material news requiring BUY/SELL review today.\n"
            "Markets were generally quiet with no significant counter-specific developments."
        ) if "watch_path" in ctx and ctx["watch_path"].exists() else None,
        "restore": lambda ctx, bak: shutil.copy(bak, ctx["watch_path"]) if bak and "watch_path" in ctx else None,
    },
}


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat()


def backup_artifact(path: Path) -> Path:
    """Create a backup of a file before injection."""
    if not path or not path.exists():
        return None
    bak = Path(tempfile.mktemp(suffix=".bak"))
    shutil.copy(path, bak)
    return bak


def run_injection_test(
    workflow: str,
    step: str,
    failure_class: str,
    context: dict,
    verifier_fn,
    expected_outcome: str = "recovered"
) -> dict:
    """
    Run a single failure injection test.
    
    Args:
        workflow: Workflow name
        step: Step name  
        failure_class: Class from FAILURE_CLASSES
        context: Dict with artifact paths etc
        verifier_fn: Callable that runs the verifier/repair and returns (success, proof)
        expected_outcome: "recovered", "fallback-used", or "failed"
    
    Returns:
        Test result dict
    """
    result = {
        "workflow": workflow,
        "step": step,
        "failureClass": failure_class,
        "testedAt": now_iso(),
        "status": None,
        "proof": None,
        "expectedOutcome": expected_outcome,
        "actualOutcome": None,
    }

    if failure_class not in FAILURE_CLASSES:
        result["status"] = "error"
        result["proof"] = f"Unknown failure class: {failure_class}"
        return result

    cls = FAILURE_CLASSES[failure_class]
    
    # Backup affected artifacts
    backup = backup_artifact(context.get("artifact_path"))

    try:
        print(f"\n[injector] Injecting: {failure_class}")
        print(f"  Description: {cls['description']}")
        
        # Inject the failure
        cls["inject"](context)
        print(f"  Failure injected.")

        # Run the verifier/repair
        print(f"  Running verifier/repair...")
        success, proof = verifier_fn(context, failure_class)

        result["proof"] = proof
        result["actualOutcome"] = "recovered" if success else "failed"
        result["status"] = "PASS" if result["actualOutcome"] == expected_outcome else "FAIL"

        if result["status"] == "PASS":
            print(f"  [PASS] Outcome matches expected: {expected_outcome}")
        else:
            print(f"  [FAIL] Expected: {expected_outcome}, got: {result['actualOutcome']}")
            print(f"  Proof: {proof[:200]}")

    except Exception as e:
        result["status"] = "ERROR"
        result["proof"] = str(e)
        print(f"  [ERROR] {e}")

    finally:
        # Restore backup
        if backup and context.get("artifact_path"):
            cls["restore"](context, backup)
            backup.unlink(missing_ok=True)
            print(f"  Restored backup.")

    return result


def print_summary(results: list):
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] == "ERROR")

    print(f"\n{'='*60}")
    print(f"Failure Injection Test Summary")
    print(f"  Total: {len(results)} | PASS: {passed} | FAIL: {failed} | ERROR: {errors}")
    print(f"{'='*60}")

    if failed or errors:
        print("\nFailed tests:")
        for r in results:
            if r["status"] in ("FAIL", "ERROR"):
                print(f"  [{r['status']}] {r['workflow']}/{r['step']} — {r['failureClass']}")
                print(f"    Expected: {r['expectedOutcome']}, Got: {r['actualOutcome']}")
                if r["proof"]:
                    print(f"    Proof: {r['proof'][:150]}")

    return passed == len(results)


def main():
    p = argparse.ArgumentParser(description="Failure Injector — Process Integrity Skill")
    p.add_argument("--workflow", help="Workflow name")
    p.add_argument("--step", help="Step name")
    p.add_argument("--class", dest="failure_class", help="Failure class to inject")
    p.add_argument("--all", action="store_true", help="Run all registered tests for workflow")
    p.add_argument("--list-classes", action="store_true", help="List all failure classes")
    p.add_argument("--workspace", default=".", help="Agent workspace path")
    args = p.parse_args()

    if args.list_classes:
        print("Available failure classes:")
        for name, cls in FAILURE_CLASSES.items():
            print(f"  {name}: {cls['description']}")
        sys.exit(0)

    if not args.workflow:
        print("ERROR: --workflow required", file=sys.stderr)
        sys.exit(1)

    print(f"[injector] Failure injection test harness")
    print(f"  Workflow: {args.workflow}")
    print(f"  Workspace: {args.workspace}")
    print()
    print("NOTE: This is a template. Implement verifier_fn and context")
    print("      for your specific workflow before running tests.")
    print()
    print("Example usage pattern:")
    print("""
    from failure_injector import run_injection_test, print_summary, FAILURE_CLASSES

    def my_verifier(context, failure_class):
        # Run your repair primitive or independent verifier
        # Return (success: bool, proof: str)
        result = run_my_verifier(slot="morning", date="2026-06-27")
        return result["status"] == "verifier-delivered", result.get("proof", "")

    context = {
        "artifact_path": Path("/path/to/artifact.md"),
        "attestation_path": Path("/path/to/attestation.json"),
        "state_path": Path("/path/to/delivery-state.json"),
    }

    results = []
    for failure_class in ["missing-artifact", "missing-attestation", "forbidden-marker"]:
        result = run_injection_test(
            workflow="my-workflow",
            step="my-step",
            failure_class=failure_class,
            context=context,
            verifier_fn=my_verifier,
            expected_outcome="recovered"
        )
        results.append(result)

    success = print_summary(results)
    sys.exit(0 if success else 1)
    """)


if __name__ == "__main__":
    main()
