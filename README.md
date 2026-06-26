# agentic-workflow-integrity

**A complete process integrity harness for AI agents.**

This skill gives AI agents (OpenClaw-based) a production-grade harness for making
any workflow resilient, independently verified, and gap-enforced.

Built from operational experience running a multi-agent AI organisation where the
same failure classes recurred across different agents, different workflows, and
different failure surfaces. The common thread: agents were solving visible break
points instead of the full recurrence path.

---

## The Three Layers

### Layer 1 — Process Resilience
Systematically decompose any workflow from source to outcome. Identify every
failure point. Wire proper fallbacks at each. No failure class should result in
a stopped process — every failure has a repair path and a continuation.

### Layer 2 — Independent Verification
Same agent, separate execution context (isolated cron). Fires outside the
supervised process. Has its own repair primitives. Verifies the process ran
correctly and intervenes directly if not. If the entire main workflow is broken,
the verifier still fires, diagnoses, repairs, and delivers.

### Layer 3 — Gap Enforcement
Ensures gaps identified during layers 1 and 2 are implemented, not left as
findings. Gap identification and enforcement are the same atomic action.
No gap stays a finding.

---

## The Problem This Solves

AI agents running complex workflows have recurring failure patterns:

- **Finding-not-action:** Gaps identified, named accurately, never implemented
- **Wrong-layer fix:** Fix applied at checkpoint level when failure is upstream
- **Observational gate:** Process stops on failure instead of repairing and continuing
- **False completion:** Marked done without production-context verification
- **Independent-path dependency:** "Independent" verifier depends on the broken process
- **Acknowledgement drift:** Committed to fix, never executed

This skill provides tooling, patterns, and enforced process to break these patterns.

---

## What's Included

```
agentic-workflow-integrity/
├── SKILL.md                               # OpenClaw skill definition
├── README.md                              # This file
├── scripts/
│   ├── gap_registry.py                    # Atomic gap registration and closure
│   ├── gap_enforcer.py                    # Independent enforcement cron
│   ├── independent_verifier_template.py   # Template for workflow verifiers
│   ├── commitment_watchdog.py             # Anti-drift watchdog for ETA commitments
│   ├── process_decompose.py               # Scaffolds decomposition documents
│   └── failure_injector.py               # Test harness for failure injection
├── references/
│   ├── process-decomposition.md          # How to decompose any workflow
│   ├── failure-modes.md                  # 13 failure class taxonomy
│   ├── independent-verifier-design.md    # How to build a true independent verifier
│   ├── resilience-patterns.md            # 7 resilience patterns with code
│   └── components.md                     # Installation guide
└── templates/
    ├── workflow-spec-template.md          # Workflow specification template
    └── verifier-config-template.json     # Verifier configuration template
```

---

## The Five Audit Questions

Ask these for every workflow, in this order:

1. **What is the first point where this workflow can fail?** (Start at source, not checkpoints)
2. **For each step — what artifact must exist? Is that contract enforced with a fail-closed verifier, or only assumed?**
3. **For each classifier/parser — is there a synthetic test for edge cases?**
4. **For each failure mode — does failure route to repair or terminal stop? Who owns the repair?**
5. **For each intervention path — have you tested it by injecting the actual failure?**

Question 5 ("are the checkpoints wired?") is the last question, not the first. Starting at question 5 is why gaps are invisible.

---

## The Closing Standard

A task is done ONLY when ALL of these are true:

1. The specific failure is fixed and tested
2. The failure class is identified
3. All other instances of the same failure class are found and fixed
4. A failure-injection test exists that would have caught this before production
5. The fix is verified from the actual production execution context — not a test harness
6. The gap registry entry has `status: closed` with proof field populated
7. The fix would have prevented the original incident if it had existed before it

If the answer to #7 is no, you have fixed the symptom, not the problem.

---

## Quick Start

```bash
# 1. Copy scripts to your agent workspace
cp scripts/*.py {WORKSPACE}/scripts/

# 2. Initialise state directories
mkdir -p {WORKSPACE}/state/{gap-registry,verifier-runs,last-known-good,enforcement-inbox}

# 3. Verify installation
python3 {WORKSPACE}/scripts/gap_registry.py verify
python3 {WORKSPACE}/scripts/gap_enforcer.py --workspace {WORKSPACE} --verify

# 4. Scaffold a workflow decomposition
python3 {WORKSPACE}/scripts/process_decompose.py \
  --workflow "My Workflow" \
  --steps "step1,step2,step3" \
  --output {WORKSPACE}/artifacts/decomposition-my-workflow.md

# 5. For each workflow with a deliverable, customise the verifier template
cp scripts/independent_verifier_template.py {WORKSPACE}/scripts/my_workflow_verifier.py
# Edit CONFIGURATION section

# 6. Register gap enforcer as isolated cron (outside main workflow stack)
# 7. Register verifier crons (outside main workflow stack)
# 8. Add gap enforcement header to AGENTS.md
```

See `references/components.md` for detailed installation steps.

---

## Compatibility

**Runtime:** OpenClaw (primary). Scripts are runtime-agnostic Python.
The cron wake mechanism is OpenClaw-specific. For Paperclip-native agents,
replace cron kicks with Paperclip todo issue assignment.

**sessions_spawn:** Not required. All independent verification uses isolated
crons. Works with `sessions_spawn` in the deny list.

---

## Design Principles

1. **Gap identification and enforcement are the same atomic action.** You cannot name a gap without enforcement beginning.

2. **The independent verifier must not depend on the workflow it supervises.** If the main lane is broken, the verifier still delivers.

3. **Every gate must have a repair primitive.** No stop-only gates. Every failure must have a path forward.

4. **Production-context verification is the only valid verification.** Test harness passes are not evidence.

5. **A fallback deliverable is always better than no deliverable.** If the canonical route cannot be repaired, use last-known-good inputs. Mark it as fallback. Send it.

6. **Fix at the source layer, not the symptom layer.** The most common error is applying fixes at checkpoints when the failure originates upstream.

---

## License

MIT. Share freely.
