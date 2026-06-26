# Failure Modes Taxonomy

## Overview

Every failure an agent encounters in a workflow belongs to one of these classes.
Identifying the correct class is the first step to applying the correct repair.

The most important question before applying any repair:
**"Is this the earliest point where this failure can manifest?"**
If the answer is no, go upstream until you reach the earliest point.

---

## Process Failure Classes

### Class 1: surface-fix
**Pattern:** Symptom fixed, underlying cause untouched. Same failure recurs.
**Detection:** Fixed once, recurs within 1-3 cycles in a slightly different form.
**Example:** Fixed the generator crash without fixing the import path that caused it.
**Repair:** Identify the failure class of the underlying cause. Apply that fix.
**Layer:** Always upstream of where the symptom appeared.

---

### Class 2: finding-not-action
**Pattern:** Gap identified, named accurately, not implemented.
**Detection:** Gap appears in artifacts, diagnoses, or session outputs but no corresponding fix exists on disk.
**Example:** "Weekly ECM supervisor not built" appears in three session artifacts. No supervisor script exists.
**Repair:** Gap registry entry → immediate implementation in same session → closure with proof.
**Prevention:** Gap registration is mandatory and atomic. See `gap_registry.py`.

---

### Class 3: wrong-layer
**Pattern:** Fix applied at checkpoint or observation layer when failure originates upstream.
**Detection:** The checkpoint correctly detects the failure but cannot repair it because the source is before the checkpoint's scope.
**Example:** Owner fallback fires and detects missing commentary draft but cannot fix it because the build step is upstream.
**Repair:** Source-to-outcome trace. Find the earliest failure point. Apply fix there.
**Key question:** "If I apply this fix, could the same failure class occur upstream of my fix?" If yes, go higher.

---

### Class 4: observational-gate
**Pattern:** Process stops on failure instead of repairing and continuing.
**Detection:** Exit codes, gate scripts, or status flags that return FAIL and halt the process with no repair path wired.
**Example:** `render_gate.py` returns exit code 5 → wrapper suppresses all downstream phases → deliverable never sent.
**Repair:** Every gate must have a repair primitive. Gate fails → rectification request → repair primitive → gate re-evaluated.
**Rule:** No stop-only gates. Every gate must also be able to say REPAIR-AND-RETRY.

---

### Class 5: false-completion
**Pattern:** Marked done without production-context verification.
**Detection:** Task has a completion marker but the fix fails in production while passing in tests.
**Example:** Step 3 declared done after test harness passes. Generator import fails when run from production directory.
**Repair:** Run from production execution context. If it fails, reopen and fix.
**Rule:** "It should work logically" is not verification. Run it.

---

### Class 6: acknowledgement-drift
**Pattern:** Committed to fix, never executed.
**Detection:** Session output contains "I will implement X" without a corresponding artifact on disk.
**Example:** "I will add the closing standard gate enforcement" — gate script exists without the new enforcement field.
**Repair:** Gap registry entry with TTL. Enforcer kicks session with unimplemented commitment.
**Prevention:** Implementation must happen in the same session as the commitment, with proof.

---

### Class 7: execution-context-mismatch
**Pattern:** Fix verified in test harness or wrong working directory, fails in production.
**Detection:** Tests pass. Production fails with import errors, path errors, or missing dependencies.
**Example:** `scripts.daily_brief_rectification` resolves from `workspace/` tests but not from `workspace-warren/` production.
**Repair:** Always run verification from the production execution directory.
**Test:** `cd {production_dir} && python3 {script} --verify`

---

### Class 8: independent-path-dependency
**Pattern:** "Independent" verifier depends on the broken process it supervises.
**Detection:** If you disable the main process, the verifier also fails.
**Example:** Owner fallback calls `converge_daily_brief_delivery.py` which depends on the broken generator.
**Repair:** Build verifier-specific repair primitives. Verifier must never call main process scripts directly.
**Independence test:** Disable all main process crons. Inject failure. Verifier must still deliver.

---

### Class 9: stale-state-accumulation
**Pattern:** Old session memory causes agent to believe it lacks tools or access it actually has.
**Detection:** Agent reports "I cannot access X" without attempting access. Reports tool unavailability without a failed tool call.
**Example:** Agent says "I cannot write to this path" based on a prior session, without trying in the current session.
**Repair:** Always attempt before reporting. Paste the actual error, not the assumed error.
**Prevention:** Session compaction at 75% context threshold. Tool pre-flight at session start.

---

### Class 10: source-truth-write-not-read
**Pattern:** Agent writes to source-of-truth documents but doesn't use them in subsequent sessions.
**Detection:** Source-of-truth document contains correct guidance. Agent repeats the error the guidance was meant to prevent.
**Example:** Source-of-truth says "supervisor must be independent of lane." Next session builds a dependent supervisor.
**Repair:** Source-of-truth documents are reference material, not enforcement. Build enforcement into code, registry, and crons.
**Prevention:** Never rely on a document to enforce a behaviour. Make the enforcement executable.

---

### Class 11: artifact-contract-undefined
**Pattern:** A step is considered complete when "it ran" rather than when it produced a valid artifact.
**Detection:** No fail-closed verifier exists for the step's output. Downstream steps fail because they assume the artifact is valid.
**Example:** Commentary generation "completes" but leaves a zero-byte file. Generator imports it and crashes.
**Repair:** Define exact artifact path and validity criteria. Write a fail-closed verifier script. Wire it at the step.
**Prevention:** Decomposition template requires artifact contract and verifier for every step.

---

### Class 12: fallback-not-populated
**Pattern:** Fallback path exists in code but the fallback data has never been written.
**Detection:** Fallback fires and finds empty or non-existent `last-known-good` directory.
**Example:** Supervisor falls back to `last-known-good/commentary.md` which has never been created because no successful run has populated it.
**Repair:** Populate fallback data manually from most recent successful artifacts. Add fallback update step after every successful delivery.
**Prevention:** Fallback update is a mandatory step in the delivery confirmation path.

---

### Class 13: repair-primitive-calls-broken-path
**Pattern:** Repair primitive calls back into the same broken process component it's supposed to fix.
**Detection:** Repair fires, appears to do something, but the failure recurs because the repair re-entered the broken path.
**Example:** Commentary repair primitive calls `generate_daily_brief.py` which still has the broken import path.
**Repair:** Repair primitives must be self-contained. They cannot call scripts that are part of the failing workflow.
**Test:** Disable the failing component. Run the repair primitive. It must succeed without the component.

---

### Class 14: safety-net-not-instantiated
**Pattern:** The independent verifier exists in code and spec but is not registered as a live cron in the runtime.
**Detection:** Parity check shows expected supervisor job IDs have no run records.
**Example:** brief_independent_supervisor cron id c1a7f6b5 exists in spec but not in live cron registry.
**Repair:** Parity check must verify live registry matches spec before treating any safeguard as active.
**Rule:** A safety net that is not live is not a safety net. Spec existence ≠ runtime existence.
**Prevention:** Independent verifier startup must self-verify its own cron is registered. If not, register it and alert.

---

## Repair Primitive Selection Matrix

| Failure Class | Primary Repair | Layer |
|---|---|---|
| surface-fix | Find underlying class; apply that fix | Source |
| finding-not-action | Gap registry + enforcer TTL | Meta |
| wrong-layer | Source-to-outcome trace; fix at earliest point | Source |
| observational-gate | Rectification request + repair primitive per gate | Gate |
| false-completion | Production-context verification | Verification |
| acknowledgement-drift | Gap registry TTL + enforcer wake | Meta |
| execution-context-mismatch | Run from production dir | Verification |
| independent-path-dependency | Verifier-specific repair primitives | Verifier |
| stale-state-accumulation | 75% compaction + tool pre-flight | Session |
| source-truth-write-not-read | Move enforcement to code/registry/cron | Architecture |
| artifact-contract-undefined | Define contract + write fail-closed verifier | Step |
| fallback-not-populated | Populate from recent success + update on delivery | Fallback |
| repair-primitive-calls-broken-path | Self-contained repair primitive | Repair |

---

## Composite Failures

Real incidents usually involve multiple failure classes in sequence. The pattern is:

1. **Class 11** (artifact-contract-undefined) at step N allows an invalid artifact
2. **Class 3** (wrong-layer) means the repair is wired at step N+2, not step N
3. **Class 4** (observational-gate) means the intervention observes but does not fix
4. **Class 8** (independent-path-dependency) means the "independent" verifier re-enters the broken path
5. Result: process fails, verifier fails, deliverable not sent

The fix sequence must be:
1. Wire artifact contract at step N (class 11)
2. Move repair to step N (class 3)
3. Convert gate to repair-and-retry (class 4)
4. Build verifier-specific repair primitive (class 8)

Always fix in source-to-outcome order. Fixing at step N+2 before fixing step N
means the fix at N+2 will never be reached.
