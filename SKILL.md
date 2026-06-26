---
name: agentic-workflow-integrity
description: >
  Process integrity harness for AI agents. Use this skill whenever an agent needs
  to: build a new workflow that must be resilient; audit an existing workflow for
  failure points; wire proper fallbacks so processes never stop on failure; set up
  an independent same-agent verification layer that fires outside the supervised
  process; enforce that identified gaps are implemented and not left as findings;
  or systematically decompose a process from source to outcome to find and plug
  gaps before they cause incidents. Trigger this skill when building any workflow
  with a deliverable, a deadline, or a quality gate. Also trigger when a workflow
  has silently failed, when an agent reports gaps as findings without actioning
  them, when processes stop on failure instead of repairing and continuing, or
  when an agent has acknowledged something but not implemented it. This skill
  covers the full process integrity stack: resilience wiring, independent
  verification, and gap enforcement. It is not just a gap finder — it is a
  complete harness for making agent-owned processes production-grade.
---

# Process Integrity Skill

This skill gives an agent a complete harness for making any workflow it owns
production-grade. It covers three interlocking layers:

**Layer 1 — Process Resilience**
Systematically decompose any workflow from source to outcome. Identify every
failure point. Wire proper fallbacks at each. No failure class should result
in a stopped process — every failure has a repair path and a continuation.

**Layer 2 — Independent Verification**
Same agent, separate execution context (isolated cron). Fires outside the
supervised process. Has its own repair primitives. Verifies the process ran
correctly and intervenes directly if not. Does not depend on the process it
supervises — if the entire main workflow is broken, the verifier still fires,
diagnoses, repairs, and delivers.

**Layer 3 — Gap Enforcement**
Ensures gaps identified during layers 1 and 2 are implemented, not left as
findings. Gap identification and enforcement are the same atomic action.
No gap stays a finding — it becomes tracked, time-bounded, enforced work.

---

## The Central Failure Modes This Skill Addresses

Read `references/failure-modes.md` for the full taxonomy. The most common:

- **Finding-not-action:** Gap identified, named, not implemented
- **Wrong-layer fix:** Fix at checkpoint level when failure is upstream
- **Observational gate:** Process stops on failure instead of repairing
- **False completion:** Marked done without production-context verification
- **Independent-path dependency:** "Independent" verifier depends on the broken process
- **Acknowledgement drift:** Committed to fix, never executed
- **Execution context mismatch:** Tested in harness, fails in production

---

## How to Use This Skill

### When building a new workflow

1. Read `references/process-decomposition.md`
2. Run the source-to-outcome decomposition before writing any code
3. For each step, define: artifact contract, failure class, repair primitive, fallback
4. Wire the independent verifier before the workflow goes live
5. Write failure-injection tests for every failure class

### When auditing an existing workflow

1. Read `references/process-decomposition.md`
2. Ask the five audit questions (see below)
3. For each gap found, register it immediately (see Layer 3)
4. Fix from source downward — never patch the symptom without finding the class

### When a workflow has failed

1. Read delivery/output state files first — never re-run the broken process to find out what failed
2. Identify failure class from state files
3. Apply the repair primitive for that class
4. Verify the repair from production execution context
5. Re-enter the process only after the repair is confirmed
6. Update fallback inputs after successful completion

---

## The Five Audit Questions

Ask these for every workflow, in this order. Do not skip to question 5.

**Q1: What is the first point in this workflow where it can fail?**
Start at the data source or build step. Not at the checkpoints.

**Q2: For each step from source downward — what artifact must exist at the end of this step? Is that contract enforced with a fail-closed verifier, or only assumed?**

**Q3: For each classifier or parser — what is the full range of inputs it will receive? Is there a synthetic test for edge cases, specifically inputs that look like one thing but mean another?**

**Q4: For each failure mode — does the failure route to a repair path or a terminal state? Who owns the repair? Can they actually perform it, or only observe it?**

**Q5: For each intervention path — have you tested it by injecting the actual failure, not by checking that the job exists?**

The question "are the checkpoints wired correctly?" is question 5, not question 1.
Starting at question 5 is why gaps are invisible.

---

## The Closing Standard

A task is not done when the symptom is resolved. A task is done when:

1. The specific failure is fixed and tested
2. The failure class is identified
3. All other instances of the same failure class in the same workflow are found and fixed
4. A failure-injection test exists that would have caught this before production
5. The fix is verified from the actual production execution context — not a test harness
6. The gap registry entry has `status: closed` with `proof` field populated
7. The fix would have prevented the original incident if it had existed before it

If the answer to item 7 is no, you have fixed the symptom, not the problem.

---

## Components

Read `references/components.md` for full implementation details.

### Scripts (in `scripts/`)
- `process_decompose.py` — source-to-outcome decomposition tool
- `gap_registry.py` — atomic gap registration and closure
- `gap_enforcer.py` — independent enforcement cron
- `independent_verifier_template.py` — template for same-agent independent verifier
- `commitment_watchdog.py` — anti-drift watchdog for ETA commitments
- `failure_injector.py` — test harness for failure-class injection

### References (in `references/`)
- `process-decomposition.md` — how to decompose any workflow
- `failure-modes.md` — full failure class taxonomy with repair primitives
- `components.md` — component documentation
- `resilience-patterns.md` — fallback patterns for common failure classes
- `independent-verifier-design.md` — how to build a truly independent verifier

### Templates (in `templates/`)
- `workflow-spec-template.md` — template for specifying a resilient workflow
- `verifier-config-template.json` — configuration template for verifiers

---

## Installation

Read `references/components.md` Step-by-step installation guide.

Quick summary:
```bash
# Copy scripts to agent workspace
cp scripts/*.py {AGENT_WORKSPACE}/scripts/

# Initialise state directories
mkdir -p {AGENT_WORKSPACE}/state/gap-registry
mkdir -p {AGENT_WORKSPACE}/state/verifier-runs
mkdir -p {AGENT_WORKSPACE}/state/last-known-good

# Add gap enforcement header to AGENTS.md (top, above session startup)
# See references/components.md for the exact text

# Register gap enforcer as isolated cron
# Register independent verifier crons per workflow
# See references/components.md for cron registration
```

---

## Compatibility

**Runtime:** OpenClaw (primary). Core scripts (gap registry, decomposition, failure injection)
are runtime-agnostic Python. The cron wake mechanism is OpenClaw-specific — for
Paperclip-native agents, replace cron kicks with Paperclip todo issue assignment
(same pattern, different transport).

**sessions_spawn:** Not used. All independent verification uses isolated crons,
which fire as separate execution contexts without spawning child sessions.
Works correctly with `sessions_spawn` in the deny list.
