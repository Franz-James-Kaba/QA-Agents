# Test scenario — run mode

End-to-end check for `/run` — executes test cases against a running app and files bugs on failures.

## Setup

The tester needs:
- Jira tooling connected
- Xray Cloud tooling connected
- Playwright installed (`pip install playwright && python -m playwright install chromium`)
- A running web app reachable from the test machine
- A Story in Jira with 2–3 linked Test Cases (use the plan-mode test to create these, or use existing ones)
  - At least one TC should pass against the app
  - At least one TC should fail (e.g. asserts an element that doesn't exist) so the bug-filing flow gets exercised
- Environment variables for the credentials the TCs need:
  ```
  PLAYER_USERNAME=<a real test account>
  PLAYER_PASSWORD=<the password>
  ```
  (Add `ADMIN_USERNAME`/`ADMIN_PASSWORD` if any TC has `"user": "admin"`.)

## Invocation

```
/run --from-xray PROJ-100 --url https://staging.example.com --env staging
```

Optionally with an app profile:

```
/run --from-xray PROJ-100 --url https://staging.example.com --env staging --profile ./qa-profile.md
```

## Expected behaviour

### Phase R1 — Resolve test cases

1. **Detect mode** as `run`.
2. **Verify Jira + Xray tooling + Playwright** are all available.
3. Fetch the Story `PROJ-100`. Find linked TCs via the `Test` issue link (Story = outward).
4. For each TC, fetch summary, description, and Xray steps in parallel.
5. Assemble the TestCase JSON array. Write to `output/test-cases/PROJ-100.json`.

### Phase R2 — Verify environment

1. `curl`-style check that `https://staging.example.com` returns < 500.
2. Verify Playwright is importable.
3. Verify credentials are set for each role mentioned in the TCs.
4. Load app profile if `--profile` was given.

### Phase R3–R5 — Run ID, output dirs, banner

Create `output/results/RUN-YYYYMMDD-NNN/` and `output/screenshots/RUN-YYYYMMDD-NNN/`. Print the banner showing the run ID, URL, input path, TC counts by role.

### Phase R6 — Execute test cases

If TCs span multiple roles → spawn one subagent per role in a **single message**. Each subagent:

1. Writes `pw_runner.py` containing the helpers and step-execution function (from `run-playwright-runner.md`).
2. Launches Chromium (headless by default, headed if `--headed`).
3. Authenticates the role.
4. For each TC:
   - Unless `preserveSession: true`, clear session state and re-auth.
   - For each step:
     - Take a before-screenshot.
     - Execute the step via the verb dispatcher (click, fill, navigate, verify, wait).
     - Take an after-screenshot.
     - Read the after-screenshot using the Read tool and assess pass/fail against `expected`.
     - Record the step result with screenshot paths.
   - If a critical step fails (login failed, no state change, essential navigation didn't occur), mark remaining steps in this TC as BLOCKED and end the TC.
5. Writes `output/results/<RUN_ID>/results-<role>.json`.

Main context waits for all role subagents, merges into `output/results/<RUN_ID>/results.json`.

### Phase R7 — File bugs in background

For every failed step in the merged results, spawn a **background** bug-mode subagent (`run_in_background: true`) with:

- The TC key, step number, expected, actual observed
- Screenshot paths and DOM snapshot path
- Parent story key
- The results.json path

The background subagent files the bug per `bug-mode.md` (auto sub-mode shape, but standalone), runs the duplicate guard, and reports back. **The main run does not block waiting for bug filings.**

### Phase R8 — Final report

Print the console summary:

```
=====================================================================
TEST EXECUTION COMPLETE — PROJ-100
Run ID:      RUN-20260520-001
URL:         https://staging.example.com
Env label:   staging
Duration:    Xm Ys
=====================================================================
Results: <P> PASS  |  <F> FAIL  |  <B> BLOCKED  |  <S> SKIPPED

FAILURES:
  PROJ-NNN  Step <N> — <action>
    Expected: <expected>
    Actual:   <actual>
    Bug filed: <bug key or "pending background">
  ...
=====================================================================
```

Also write `results.json`, `run-report.json`, and `run-report.md`.

### Phase R9 — Xray upload in background

Spawn a background subagent to update the Xray Test Execution: map PASS→PASSED, FAIL→FAILED, etc., and update each test result.

## What to verify after the run

- `output/results/RUN-*/results.json` exists and contains entries for every TC.
- Each step has `screenshot_before` and `screenshot_after` paths that point to real files.
- Failed steps have `domSnapshot` and either `bug.jiraTicketKey` or `bug.status: "pending"`.
- A bug was filed in Jira for the failing step. Opening it shows:
  - 6-section ADF description (all h2 level 2).
  - Defect link to the Test Case.
  - Relates link to the Story.
  - Status `In Progress`.
- The Test Execution in Xray now shows updated results (PASSED / FAILED per TC).

## Common ways this can go wrong

- **Runner uses `networkidle` instead of `domcontentloaded`.** Many SPAs poll and never reach networkidle.
- **Screenshots not taken before AND after.** Both are mandatory.
- **`verify`/`check`/`assert` steps interact with the page instead of just observing.** They are vision-only.
- **`preserveSession: true` ignored** — session-scope TCs fail because the runner reset state anyway.
- **Bug filing blocks step execution.** Bug subagents must be background / fire-and-forget.
- **Hardcoded selectors used.** The runner should use accessibility locators first, profile selectors if provided, never hardcoded ones for any specific app.
- **All role TCs run sequentially** instead of in parallel browser groups.

## Cleanup

Created bugs are throwaway. Delete or close them. Delete the `output/RUN-*` folder if you want a clean rerun. The Test Execution in Xray will keep the recorded results — that's expected.
