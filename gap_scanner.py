#!/usr/bin/env python3
"""
gap_scanner.py — Process Integrity Skill
Scans agent artifact and state files for gap language and auto-registers
findings in the gap registry.

Usage:
  # Scan and register gaps (production mode)
  python3 gap_scanner.py --workspace /path/to/workspace

  # Scan and report only — no registry writes
  python3 gap_scanner.py --workspace /path/to/workspace --report-only

  # Scan a specific directory
  python3 gap_scanner.py --workspace /path/to/workspace --scan-path /path/to/dir
"""

import json
import re
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone


# Default patterns that indicate an open gap
GAP_PATTERNS = [
    (r"not yet built", "weak-supervision"),
    (r"still needs to be built", "weak-supervision"),
    (r"not yet implemented", "acknowledged-not-implemented"),
    (r"acknowledged but not", "acknowledged-not-implemented"),
    (r"\buncovered\b", "weak-supervision"),
    (r"\boutstanding\b", "acknowledged-not-implemented"),
    (r"\bstale\b(?! data| pricing| cache)", "weak-followup"),
    (r"does not yet exist", "weak-supervision"),
    (r"missing independent", "weak-supervision"),
    (r"needs to be built", "weak-supervision"),
    (r"needs an independent supervisor", "weak-supervision"),
    (r"still not built", "acknowledged-not-implemented"),
    (r"never implemented", "acknowledged-not-implemented"),
    (r"left unpatched", "acknowledged-not-implemented"),
    (r"pending implementation", "acknowledged-not-implemented"),
    (r"not fully landed", "acknowledged-not-implemented"),
    (r"not yet wired", "weak-supervision"),
    (r"not yet verified", "acknowledged-not-implemented"),
    (r"hit the same.*blocker", "weak-followup"),
    (r"repair path.*not independent", "weak-supervision"),
    (r"relied on.*broken route", "weak-supervision"),
    (r"coverage gap", "weak-supervision"),
]

# File extensions to scan
SCAN_EXTENSIONS = {".md", ".json", ".jsonl", ".txt", ".log"}

# Paths to skip even if they match scan directories
SKIP_PATTERNS = [
    "gap-registry.jsonl",       # Don't scan the registry itself
    ".git/",
    "node_modules/",
    "__pycache__/",
    ".venv/",
    "venv/",
    "venv-brief/",
]

# Maximum file size to scan (bytes) — skip very large files
MAX_FILE_SIZE = 500_000


def _should_skip(path: Path) -> bool:
    path_str = str(path)
    for pattern in SKIP_PATTERNS:
        if pattern in path_str:
            return True
    if path.stat().st_size > MAX_FILE_SIZE:
        return True
    return False


def _scan_file(path: Path) -> list[dict]:
    """Scan a single file for gap language. Returns list of findings."""
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    lines = text.splitlines()
    for i, line in enumerate(lines):
        for pattern, failure_class in GAP_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                # Extract context: the line itself plus surrounding lines
                start = max(0, i - 1)
                end = min(len(lines), i + 2)
                context = " | ".join(lines[start:end]).strip()
                findings.append({
                    "file": str(path),
                    "line": i + 1,
                    "pattern": pattern,
                    "failureClass": failure_class,
                    "context": context[:300],
                })
                break  # One finding per line maximum

    return findings


def scan_workspace(workspace: str, scan_paths: list[str] = None) -> list[dict]:
    """
    Scan the workspace for gap language. Returns all findings.
    If scan_paths provided, only scan those directories.
    """
    workspace_path = Path(workspace)

    if scan_paths:
        dirs_to_scan = [Path(p) for p in scan_paths]
    else:
        # Default: scan artifacts and state directories
        dirs_to_scan = [
            workspace_path / "artifacts",
            workspace_path / "state",
            workspace_path / "shared",
            workspace_path / "memory",
        ]

    all_findings = []

    for scan_dir in dirs_to_scan:
        if not scan_dir.exists():
            continue
        for path in scan_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in SCAN_EXTENSIONS:
                continue
            if _should_skip(path):
                continue
            findings = _scan_file(path)
            all_findings.extend(findings)

    return all_findings


def deduplicate_against_registry(
    findings: list[dict],
    workspace: str,
) -> list[dict]:
    """
    Filter out findings that are already registered in the gap registry
    (open or closed within the last 7 days).
    """
    registry_path = Path(workspace) / "state" / "gap-registry.jsonl"
    if not registry_path.exists():
        return findings

    registered_contexts = set()
    with open(registry_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                # Use first 80 chars of gap description as dedup key
                registered_contexts.add(entry.get("gap", "")[:80].lower())
            except json.JSONDecodeError:
                continue

    new_findings = []
    for finding in findings:
        context_key = finding["context"][:80].lower()
        if context_key not in registered_contexts:
            new_findings.append(finding)

    return new_findings


def register_findings(findings: list[dict], workspace: str) -> int:
    """
    Register new findings in the gap registry.
    Returns count of newly registered gaps.
    """
    if not findings:
        return 0

    # Import here to avoid circular dependency
    sys.path.insert(0, str(Path(__file__).parent))
    from gap_registry import register_gap

    count = 0
    for finding in findings:
        gap_description = f"Gap found in {Path(finding['file']).name} line {finding['line']}: {finding['context'][:150]}"
        register_gap(
            workspace=workspace,
            gap=gap_description,
            workflow=_infer_workflow(finding["file"]),
            failure_class=finding["failureClass"],
            ttl_minutes=60,
            source="scanner",
            artifact_path=finding["file"],
        )
        count += 1

    return count


def _infer_workflow(file_path: str) -> str:
    """Infer workflow name from file path."""
    path = Path(file_path)
    name = path.stem.lower()

    workflow_hints = {
        "brief": "daily-brief",
        "ecm": "weekly-ecm-brief",
        "homebuild": "homebuild",
        "daemon": "daemon-calibration",
        "portfolio": "portfolio-calibration",
        "polymarket": "polymarkets",
        "commitment": "commitment-watchdog",
        "supervisor": "supervisor",
    }

    for hint, workflow in workflow_hints.items():
        if hint in name:
            return workflow

    return "unknown"


def main():
    parser = argparse.ArgumentParser(description="Process Integrity Gap Scanner")
    parser.add_argument("--workspace", required=True, help="Absolute path to agent workspace")
    parser.add_argument("--report-only", action="store_true",
                        help="Report findings without writing to registry")
    parser.add_argument("--scan-path", action="append", dest="scan_paths",
                        help="Specific path(s) to scan (can be repeated)")
    parser.add_argument("--json", action="store_true", help="Output findings as JSON")

    args = parser.parse_args()

    print(f"[gap-scanner] Scanning workspace: {args.workspace}")

    findings = scan_workspace(args.workspace, args.scan_paths)
    print(f"[gap-scanner] Raw findings: {len(findings)}")

    new_findings = deduplicate_against_registry(findings, args.workspace)
    print(f"[gap-scanner] New findings (not yet registered): {len(new_findings)}")

    if args.json:
        print(json.dumps(new_findings, indent=2))
        return

    if not new_findings:
        print("[gap-scanner] No new gaps found.")
        return

    for f in new_findings:
        print(f"  [{f['failureClass']}] {Path(f['file']).name}:{f['line']} — {f['context'][:100]}")

    if args.report_only:
        print(f"\n[gap-scanner] Report only mode — {len(new_findings)} gaps not registered.")
        return

    count = register_findings(new_findings, args.workspace)
    print(f"\n[gap-scanner] Registered {count} new gaps in registry.")


if __name__ == "__main__":
    main()
