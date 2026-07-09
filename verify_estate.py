#!/usr/bin/env python3
"""
verify_estate.py — Generalised OpenClaw agent estate parity verifier
Checks that what is implemented matches what is specified.
Configured via estate-config.json in the same directory.

Usage:
    python3 verify_estate.py                    # uses estate-config.json in same dir
    python3 verify_estate.py --config path.json # custom config path
    python3 verify_estate.py --quiet            # PASS/FAIL only, no detail
    python3 verify_estate.py --log path.log     # append results to log file

Exit codes:
    0 = PASS (no gaps found)
    1 = FAIL (gaps found)
    2 = ERROR (could not run checks)

GitHub: https://github.com/terence-ma/agentic-workflow-integrity
"""

import json
import sqlite3
import subprocess
import sys
import os
import argparse
from datetime import datetime
from pathlib import Path

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="OpenClaw estate parity verifier")
parser.add_argument("--config", default=None, help="Path to estate-config.json")
parser.add_argument("--quiet",  action="store_true", help="PASS/FAIL only")
parser.add_argument("--log",    default=None, help="Append results to log file")
args = parser.parse_args()

# ── Load config ───────────────────────────────────────────────────────────────
script_dir  = Path(__file__).parent
config_path = Path(args.config) if args.config else script_dir / "estate-config.json"

if not config_path.exists():
    print(f"ERROR: config not found at {config_path}")
    print(f"Copy estate-config.example.json to estate-config.json and edit it.")
    sys.exit(2)

try:
    config = json.loads(config_path.read_text())
except Exception as e:
    print(f"ERROR: could not parse config — {e}")
    sys.exit(2)

# ── Results ───────────────────────────────────────────────────────────────────
gaps   = []
passes = []

def fail(msg):
    gaps.append(msg)

def ok(msg):
    passes.append(msg)

def log(msg):
    if not args.quiet:
        print(msg)

# ── Check 1: Anti-patterns grep ───────────────────────────────────────────────
def check_anti_patterns():
    log("\n[1] Anti-pattern scan")
    anti_patterns = config.get("anti_patterns", [])
    search_roots  = [Path(p) for p in config.get("search_roots", [])]
    extensions    = config.get("search_extensions", ["*.py", "*.json", "*.md", "*.sh"])

    for item in anti_patterns:
        pattern     = item["pattern"]
        description = item["description"]
        exclude     = item.get("exclude_if_in", [])

        found_files = []
        for root in search_roots:
            if not root.exists():
                continue
            try:
                grep_args = ["grep", "-rl"] + [f"--include={e}" for e in extensions] + [pattern, str(root)]
                result = subprocess.run(grep_args, capture_output=True, text=True, timeout=15)
                if result.stdout.strip():
                    for f in result.stdout.strip().splitlines():
                        # Apply exclusion filter
                        if exclude and any(x in f for x in exclude):
                            continue
                        found_files.append(f)
            except Exception:
                pass

        if found_files:
            fail(f"ANTI-PATTERN [{description}]: found in {[os.path.basename(f) for f in found_files[:5]]}")
        else:
            ok(f"Anti-pattern clean: {pattern}")

# ── Check 2: System crontab ───────────────────────────────────────────────────
def check_crontab():
    log("\n[2] System crontab")
    expected = config.get("expected_crontab", [])
    if not expected:
        ok("Crontab check: skipped (none configured)")
        return

    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
        crontab_text = result.stdout
    except Exception as e:
        fail(f"CRONTAB: could not read — {e}")
        return

    for item in expected:
        expr  = item["expr"]
        label = item["label"]
        must_contain = item.get("must_contain", "")
        line_matches = [l for l in crontab_text.splitlines() if expr in l]
        if line_matches and (not must_contain or any(must_contain in l for l in line_matches)):
            ok(f"Crontab present: {label}")
        else:
            fail(f"CRONTAB MISSING: {label} (expr: {expr})")

# ── Check 3: OpenClaw cron SQLite ─────────────────────────────────────────────
def check_openclaw_crons():
    log("\n[3] OpenClaw cron estate (SQLite)")
    db_path = config.get("openclaw_sqlite")
    if not db_path:
        ok("OpenClaw SQLite check: skipped (not configured)")
        return

    db = Path(db_path)
    if not db.exists():
        fail(f"SQLITE: not found at {db}")
        return

    must_be_disabled = config.get("cron_must_be_disabled", [])
    must_be_enabled  = config.get("cron_must_be_enabled",  [])

    try:
        conn = sqlite3.connect(str(db))
        cur  = conn.cursor()

        for job in must_be_disabled:
            name    = job if isinstance(job, str) else job["name"]
            cur.execute("SELECT enabled FROM cron_jobs WHERE name = ? LIMIT 1", (name,))
            row = cur.fetchone()
            if row is None:
                ok(f"Job not found (removed/renamed): {name}")
            elif row[0] == 0:
                ok(f"Correctly disabled: {name}")
            else:
                fail(f"SHOULD BE DISABLED but ENABLED: {name}")

        for job in must_be_enabled:
            name    = job if isinstance(job, str) else job["name"]
            pattern = job.get("name_contains", name) if isinstance(job, dict) else name
            cur.execute("SELECT enabled FROM cron_jobs WHERE name LIKE ? LIMIT 1", (f"%{pattern}%",))
            row = cur.fetchone()
            if row is None:
                fail(f"EXPECTED JOB NOT FOUND: {pattern}")
            elif row[0] == 1:
                ok(f"Correctly enabled: {pattern}")
            else:
                fail(f"SHOULD BE ENABLED but DISABLED: {pattern}")

        conn.close()
    except Exception as e:
        fail(f"SQLITE ERROR: {e}")

# ── Check 4: Required files exist ─────────────────────────────────────────────
def check_required_files():
    log("\n[4] Required files")
    required = config.get("required_files", [])
    for item in required:
        path  = Path(item["path"])
        label = item.get("label", str(path))
        if path.exists():
            ok(f"File present: {label}")
        else:
            fail(f"FILE MISSING: {label} ({path})")

# ── Check 5: Source-of-truth content checks ───────────────────────────────────
def check_source_of_truth():
    log("\n[5] Source-of-truth content")
    sot_checks = config.get("source_of_truth_checks", [])

    for item in sot_checks:
        path    = Path(item["path"])
        label   = item.get("label", str(path))
        must    = item.get("must_contain",     [])
        must_not = item.get("must_not_contain", [])

        if not path.exists():
            fail(f"SOT FILE MISSING: {label}")
            continue

        content = path.read_text()

        for term in must:
            if term in content:
                ok(f"SOT [{label}]: contains '{term}'")
            else:
                fail(f"SOT [{label}]: MISSING required term '{term}'")

        for term in must_not:
            if term in content:
                fail(f"SOT [{label}]: still contains forbidden term '{term}'")
            else:
                ok(f"SOT [{label}]: clean of '{term}'")

# ── Check 6: Custom shell checks ──────────────────────────────────────────────
def check_custom_commands():
    log("\n[6] Custom verification commands")
    custom = config.get("custom_checks", [])

    for item in custom:
        label   = item["label"]
        cmd     = item["command"]
        expect  = item.get("expect_exit_code", 0)
        expect_output = item.get("expect_output_contains", None)

        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30
            )
            if result.returncode != expect:
                fail(f"CUSTOM CHECK [{label}]: exit code {result.returncode} (expected {expect})")
            elif expect_output and expect_output not in (result.stdout + result.stderr):
                fail(f"CUSTOM CHECK [{label}]: output did not contain '{expect_output}'")
            else:
                ok(f"Custom check passed: {label}")
        except Exception as e:
            fail(f"CUSTOM CHECK [{label}]: error — {e}")

# ── Run all checks ─────────────────────────────────────────────────────────────
def main():
    now     = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    name    = config.get("name", "Estate")
    version = config.get("version", "1.0")

    if not args.quiet:
        print(f"\n{'='*60}")
        print(f"{name} Parity Verification v{version}")
        print(f"Run at: {now}")
        print(f"Config: {config_path}")
        print(f"{'='*60}")

    check_anti_patterns()
    check_crontab()
    check_openclaw_crons()
    check_required_files()
    check_source_of_truth()
    check_custom_commands()

    # ── Summary ───────────────────────────────────────────────────────────────
    total   = len(passes) + len(gaps)
    verdict = "PASS" if not gaps else "FAIL"

    print(f"\n{'─'*60}")
    print(f"RESULT: {verdict}  ({len(passes)}/{total} checks passed, {len(gaps)} gaps)")
    print(f"{'─'*60}")

    if gaps and not args.quiet:
        print(f"\n❌ GAPS ({len(gaps)}):")
        for g in gaps:
            print(f"  • {g}")

    if passes and not args.quiet:
        print(f"\n✅ PASSED ({len(passes)}):")
        for p in passes:
            print(f"  • {p}")

    # ── Log ───────────────────────────────────────────────────────────────────
    log_path = args.log or config.get("log_file")
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as lf:
            lf.write(f"\n{'='*60}\n")
            lf.write(f"{name} Parity — {now}\n")
            lf.write(f"Result: {verdict}  ({len(passes)}/{total} passed)\n")
            if gaps:
                lf.write("Gaps:\n")
                for g in gaps:
                    lf.write(f"  • {g}\n")
            lf.write(f"{'='*60}\n")
        log(f"\nLog appended to: {log_path}")

    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
