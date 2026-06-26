#!/usr/bin/env python3
"""
install.py — Process Integrity Skill
Self-installs the skill for an OpenClaw agent.

Usage:
  python3 install.py \
    --agent-id qin \
    --workspace /home/terencema/.openclaw/workspace-qin \
    --ttl-minutes 60 \
    --scan-interval-hours 3

  # Verify installation
  python3 install.py --verify --workspace /home/terencema/.openclaw/workspace-qin
"""

import json
import argparse
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone


SKILL_DIR = Path(__file__).parent
CONFIG_FILENAME = "process-integrity-config.json"


def _write_config(workspace: str, agent_id: str, ttl_minutes: int,
                  scan_interval_hours: int) -> dict:
    config = {
        "agentId": agent_id,
        "workspace": workspace,
        "ttlMinutes": ttl_minutes,
        "scanIntervalHours": scan_interval_hours,
        "enforcementCronId": None,
        "enforcementSessionKey": f"agent:{agent_id}:process-integrity-enforcement",
        "scanPaths": [
            f"{workspace}/artifacts",
            f"{workspace}/state",
            f"{workspace}/shared",
            f"{workspace}/memory",
        ],
        "gapPatterns": [
            "not yet built",
            "still needs to be built",
            "not yet implemented",
            "acknowledged but not",
            "uncovered",
            "outstanding",
            "stale",
            "does not yet exist",
            "missing independent",
            "needs to be built",
            "still not built",
            "never implemented",
            "left unpatched",
            "pending implementation",
            "not fully landed",
            "not yet wired",
            "not yet verified",
        ],
        "failureClasses": [
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
        ],
        "installedAt": datetime.now(timezone.utc).isoformat(),
    }

    config_path = Path(workspace) / "state" / CONFIG_FILENAME
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))
    print(f"[install] Config written to {config_path}")
    return config


def _create_registry(workspace: str) -> None:
    registry_path = Path(workspace) / "state" / "gap-registry.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    if not registry_path.exists():
        registry_path.touch()
        print(f"[install] Gap registry created at {registry_path}")
    else:
        print(f"[install] Gap registry already exists at {registry_path}")


def _run_initial_scan(workspace: str) -> int:
    """Run initial scan and return count of gaps found."""
    scanner = SKILL_DIR / "gap_scanner.py"
    result = subprocess.run(
        [sys.executable, str(scanner), "--workspace", workspace, "--report-only"],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"[install] Scanner warning: {result.stderr}")

    # Count findings from output
    lines = result.stdout.splitlines()
    for line in lines:
        if "New findings" in line:
            try:
                count = int(line.split(":")[1].strip().split()[0])
                return count
            except (ValueError, IndexError):
                pass
    return 0


def _verify_installation(workspace: str) -> bool:
    """Verify the installation is complete and working."""
    checks = []

    config_path = Path(workspace) / "state" / CONFIG_FILENAME
    checks.append(("Config file exists", config_path.exists()))

    registry_path = Path(workspace) / "state" / "gap-registry.jsonl"
    checks.append(("Gap registry exists", registry_path.exists()))

    enforcer = SKILL_DIR / "gap_enforcer.py"
    checks.append(("gap_enforcer.py exists", enforcer.exists()))

    scanner = SKILL_DIR / "gap_scanner.py"
    checks.append(("gap_scanner.py exists", scanner.exists()))

    registry_module = SKILL_DIR / "gap_registry.py"
    checks.append(("gap_registry.py exists", registry_module.exists()))

    # Test registry write/read
    try:
        result = subprocess.run(
            [sys.executable, str(registry_module),
             "--workspace", workspace,
             "--gap", "Installation verification test gap",
             "--workflow", "install-test",
             "--failure-class", "other",
             "--ttl", "1"],
            capture_output=True, text=True
        )
        checks.append(("Registry write test", result.returncode == 0))
    except Exception as e:
        checks.append(("Registry write test", False))

    # Test enforcer status
    try:
        result = subprocess.run(
            [sys.executable, str(enforcer),
             "--workspace", workspace,
             "--status"],
            capture_output=True, text=True
        )
        checks.append(("Enforcer status check", result.returncode == 0))
    except Exception as e:
        checks.append(("Enforcer status check", False))

    print("\n[install] Verification results:")
    all_pass = True
    for check_name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {check_name}")
        if not passed:
            all_pass = False

    return all_pass


def _print_cron_instructions(agent_id: str, workspace: str,
                              scan_interval_hours: int) -> None:
    """Print instructions for registering the enforcement cron in OpenClaw."""
    enforcer_path = SKILL_DIR / "gap_enforcer.py"

    print(f"""
[install] CRON REGISTRATION REQUIRED

The enforcement cron must be registered in OpenClaw manually.
Add the following cron to your OpenClaw configuration:

Agent: {agent_id}
Session key: agent:{agent_id}:process-integrity-enforcement
Interval: every {scan_interval_hours} hours
Command to run before session: 
  python3 {enforcer_path} --workspace {workspace} --generate-prompt

The output of --generate-prompt should be injected as the first message
in the enforcement session. This tells the agent what gaps to close.

In openclaw.json, add to agent {agent_id} crons:
{{
  "id": "process-integrity-enforcement",
  "sessionKey": "agent:{agent_id}:process-integrity-enforcement",
  "schedule": "0 */{scan_interval_hours} * * *",
  "message": "$(python3 {enforcer_path} --workspace {workspace} --generate-prompt)"
}}

Or register via openclaw CLI:
  openclaw cron add \\
    --agent {agent_id} \\
    --session-key "agent:{agent_id}:process-integrity-enforcement" \\
    --schedule "0 */{scan_interval_hours} * * *" \\
    --message-from-command "python3 {enforcer_path} --workspace {workspace} --generate-prompt"
""")


def main():
    parser = argparse.ArgumentParser(description="Process Integrity Skill Installer")
    parser.add_argument("--agent-id", help="OpenClaw agent ID (e.g. qin, warren)")
    parser.add_argument("--workspace", required=True,
                        help="Absolute path to agent workspace")
    parser.add_argument("--ttl-minutes", type=int, default=60,
                        help="Default gap TTL in minutes (default: 60)")
    parser.add_argument("--scan-interval-hours", type=int, default=3,
                        help="Enforcement cron interval in hours (default: 3)")
    parser.add_argument("--verify", action="store_true",
                        help="Verify existing installation")
    parser.add_argument("--no-scan", action="store_true",
                        help="Skip initial workspace scan")

    args = parser.parse_args()

    if args.verify:
        ok = _verify_installation(args.workspace)
        sys.exit(0 if ok else 1)

    if not args.agent_id:
        print("[install] ERROR: --agent-id required for installation")
        sys.exit(1)

    print(f"[install] Installing process-integrity skill for agent: {args.agent_id}")
    print(f"[install] Workspace: {args.workspace}")

    # 1. Write config
    config = _write_config(
        workspace=args.workspace,
        agent_id=args.agent_id,
        ttl_minutes=args.ttl_minutes,
        scan_interval_hours=args.scan_interval_hours,
    )

    # 2. Create registry
    _create_registry(args.workspace)

    # 3. Initial scan
    if not args.no_scan:
        print("\n[install] Running initial workspace scan...")
        gap_count = _run_initial_scan(args.workspace)
        if gap_count > 0:
            print(f"[install] Found {gap_count} existing gaps. "
                  f"Run without --report-only to register them.")

    # 4. Verify
    print("\n[install] Verifying installation...")
    ok = _verify_installation(args.workspace)

    # 5. Print cron instructions
    if ok:
        _print_cron_instructions(
            agent_id=args.agent_id,
            workspace=args.workspace,
            scan_interval_hours=args.scan_interval_hours,
        )
        print("\n[install] Installation complete.")
    else:
        print("\n[install] Installation has issues — check verification output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
