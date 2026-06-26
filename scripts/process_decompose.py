#!/usr/bin/env python3
"""
process_decompose.py — Process Integrity Skill
Scaffolds a source-to-outcome decomposition document for a workflow.

Usage:
  python3 process_decompose.py \
    --workflow "Daily Brief" \
    --steps "data-fetch,commentary-draft,generation,qc-attestation,send" \
    --output artifacts/decomposition-daily-brief.md
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path


STEP_TEMPLATE = """
### Step {n}: {name}

| Field | Value |
|---|---|
| **Input** | *What does this step receive?* |
| **Action** | *What does this step do?* |
| **Output artifact** | *Exact file path that must exist after this step* |
| **Artifact contract** | *How is the artifact's existence and validity verified?* |
| **Fail-closed verifier** | *Script or check that enforces the contract — "assumed" is NOT acceptable* |
| **Failure classes** | *Which failure modes from `failure-modes.md` can occur here?* |
| **Repair primitive** | *What fixes each failure class directly at this step?* |
| **Fallback** | *What produces valid-enough output if repair fails?* |
| **Owner** | *Which agent/script is responsible for repair at this step?* |
| **Independent verifier** | *Does the independent verifier cover this step? How?* |
| **Failure-injection test** | *Command to inject this step's failure and verify repair works* |

**Audit questions for this step:**
- [ ] What external dependency does this step have?
- [ ] What happens if that dependency is unavailable or returns unexpected data?
- [ ] What happens if the previous step's artifact is missing or invalid?
- [ ] What happens if this step's process fails (import error, exception, timeout)?
- [ ] What happens if this step succeeds but produces output that fails downstream?

"""

DOCUMENT_TEMPLATE = """# Process Decomposition: {workflow}

Generated: {generated}

## Overview

| Field | Value |
|---|---|
| **Workflow** | {workflow} |
| **Owner agent** | *Agent ID* |
| **Deliverable** | *What must be produced* |
| **Hard deadline** | *Time or none* |
| **Outward deliverable** | *Yes/No — does this go to third parties?* |
| **Independent verifier** | *Path to verifier script* |
| **Verifier cron** | *Cron job name and schedule* |

---

## Pre-Decomposition Checklist

Before filling in step details, confirm:
- [ ] The source-to-outcome flow is mapped (not just checkpoint-to-checkpoint)
- [ ] The independent verifier is designed before the workflow goes live
- [ ] Fallback inputs exist for the first run
- [ ] Failure-injection tests are planned for every step

---

## Steps

{steps}

---

## Composite Failure Analysis

List known composite failure patterns (multiple classes occurring in sequence):

| Step A fails with | Which causes | Step B to | Which causes | Final outcome |
|---|---|---|---|---|
| *Class* | → | *downstream step* | *Class* | *What the user sees* |

---

## Gap Registry

Any gaps identified during decomposition must be registered immediately:

```bash
python3 scripts/gap_registry.py write \\
  --gap "description" \\
  --workflow "{workflow_id}" \\
  --class "failure-class" \\
  --ttl 60
```

Open gaps:
*(Populate as gaps are found during decomposition)*

---

## Audit Sign-Off

- [ ] All five audit questions answered for every step
- [ ] Every step has a fail-closed verifier (not "assumed")
- [ ] Every failure class has a repair primitive at the correct layer
- [ ] Every repair primitive is self-contained (does not call back into main workflow)
- [ ] Fallback chain defined and pre-populated for every step
- [ ] Independent verifier designed and independence test planned
- [ ] Failure-injection tests written for every failure class
- [ ] All gaps found during decomposition registered in gap registry

**Decomposition completed by:** *agent-id*
**Decomposition date:** *date*
**Re-decomposition trigger:** *what event would require re-running this decomposition*
"""


def main():
    p = argparse.ArgumentParser(description="Process Decompose — Process Integrity Skill")
    p.add_argument("--workflow", required=True, help="Workflow name")
    p.add_argument("--steps", required=True, help="Comma-separated step names")
    p.add_argument("--output", required=True, help="Output markdown file path")
    args = p.parse_args()

    step_names = [s.strip() for s in args.steps.split(",")]
    steps_content = ""
    for i, name in enumerate(step_names, 1):
        steps_content += STEP_TEMPLATE.format(n=i, name=name)

    content = DOCUMENT_TEMPLATE.format(
        workflow=args.workflow,
        workflow_id=args.workflow.lower().replace(" ", "-"),
        generated=datetime.now(timezone.utc).astimezone().isoformat(),
        steps=steps_content
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)
    print(f"[process-decompose] Scaffolded: {output_path}")
    print(f"  Workflow: {args.workflow}")
    print(f"  Steps: {len(step_names)}")
    print(f"  Fill in all fields before building the workflow.")


if __name__ == "__main__":
    main()
