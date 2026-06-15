# Run Mode

Executes test cases against a running app, captures screenshots, assesses pass/fail with vision, files bugs on failures, and uploads results to Xray.

The runner is universal — it knows nothing about your specific app's selectors, statuses, or API endpoints. To get the most reliable runs, you can optionally provide an **app profile** (see `run-app-profile.md`) that documents your app's conventions.

## Invocation

```
/run --from-xray <STORY_KEY> --url <BASE_URL>
/run --input <PATH_TO_TC_JSON> --url <BASE_URL>
/run --from-xray <STORY_KEY> --url <BASE_URL> --skip-to <TC_KEY>
/run --from-xray <STORY_KEY> --url <BASE_URL> --profile <PATH_TO_APP_PROFILE>
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--from-xray` | One of these | Story key — pull linked Test Cases from Xray automatically |
| `--input` | One of these | Path to a local TestCase JSON file |
| `--url` | Yes | Target base URL |
| `--env` | No | Free-form environment label (`local`, `staging`, etc.) — used in the run report only |
| `--profile` | No | Path to an app-profile markdown file (`run-app-profile.md`) |
| `--skip-to` | No | TC key to resume from |
| `--headed` | No | Launch a visible browser (default is headless) |
| `--sso` | No | Force SSO pre-authentication before execution. Also auto-enabled if the app redirects to a known identity provider. Currently supports Microsoft Entra ID (TOTP/MFA) — see `run-sso-profile.md` |

Credentials are **never** accepted as command-line parameters. They come from environment variables that the QA sets up separately. See "Credentials" below.

## TestCase JSON schema

```json
{
  "id":              "PROJ-1159",
  "name":            "PROJ-1155 — Submit valid registration — positive",
  "type":            "Positive",
  "storyKey":        "PROJ-1155",
  "storySummary":    "Registration",
  "preconditions":   "User is logged out. Email qa@example.com is unused.",
  "steps": [
    {"action": "Navigate to the signup page",   "data": "/signup",         "expected": "Signup form is visible"},
    {"action": "Fill the Email field",          "data": "qa@example.com",  "expected": "Email field shows the value"},
    {"action": "Click the Submit button",       "data": "-",               "expected": "Success page is visible"}
  ],
  "user":            "player",
  "preserveSession": false,
  "manualOnly":      false
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | TC Jira key |
| `name` | Yes | Descriptive name |
| `storyKey` | Yes | Parent story key |
| `steps` | Yes | Array of `{action, data, expected}` |
| `user` | No | Role label (e.g. `"player"`, `"admin"`) — matches an entry in the app profile's `roles` section |
| `preserveSession` | No | `true` = skip the pre-TC state-reset (required for session-scope tests) |
| `manualOnly` | No | `true` = skip execution, count as SKIPPED |

## Credentials

The runner reads credentials from environment variables. The variable names are configurable in the app profile. Default convention:

```
<ROLE>_USERNAME   e.g. PLAYER_USERNAME, ADMIN_USERNAME
<ROLE>_PASSWORD   e.g. PLAYER_PASSWORD, ADMIN_PASSWORD
```

For Xray uploads:
```
JIRA_EMAIL
JIRA_API_TOKEN
```

These last two are only needed if the connected Jira tooling can't itself update Xray Test Execution results (rare — usually the Xray tooling handles auth itself).

If a credential is missing for a role that the TC set uses, mark all TCs for that role as `BLOCKED` with reason `Credentials missing for role: <role>`.

## Workflow

### Phase R1 — Resolve test cases

If `--from-xray <STORY_KEY>`:

1. Run the get-issue operation on the Story with `fields=["issuelinks"]`.
2. Find all TC issues linked via type `Test` (Story = outward → TC keys are inward).
3. For each TC, fetch summary and description via the get-issue operation.
4. For each TC, fetch its Xray steps via the Xray get-test-steps operation. Fire all in parallel.
5. Assemble the TestCase JSON array (one entry per TC), inferring `type`/`user`/`preserveSession` from the TC name/description if not explicit.
6. Write to `output/test-cases/<STORY_KEY>.json` and use as the `--input`.

If `--input <PATH>`: load and validate the JSON. Schema check: array of objects, each with `id`, `name`, `storyKey`, `steps` minimum.

### Phase R2 — Verify environment

1. Reach the `--url` — `urllib.request.urlopen(url, timeout=30)`. If HTTP 5xx or unreachable, stop with `ENVIRONMENT_UNAVAILABLE: <url>`. **Note the final URL after redirects** — if it lands on a known identity provider host (`login.microsoftonline.com`, `okta.com`, `auth0.com`, `accounts.google.com`, `login.live.com`), the app uses SSO; treat as if `--sso` was passed.
2. Verify Playwright is installed (`python -c "from playwright.sync_api import sync_playwright"`).
3. Verify credentials per role (per the app profile or default convention).
4. Optionally load the app profile from `--profile <path>` — see `run-app-profile.md`.

### Phase R2.5 — SSO pre-authentication (only if `--sso` or SSO auto-detected)

Read `references/run-sso-profile.md` and follow it. In short:

1. Confirm the SSO env vars are set (`TEST_EMAIL`, `TEST_PASSWORD`, `TEST_TOTP_SECRET` for Microsoft). If any are missing, stop and tell the user exactly which.
2. Run the SSO auth script once to mint a reusable session:
   ```bash
   python <ABSOLUTE_PATH_TO_SKILL>/scripts/ms_sso_auth.py \
     --url <BASE_URL> --output output/auth/storage_state.json
   ```
3. If it exits non-zero or `output/auth/storage_state.json` is not written, stop run mode with `SSO_AUTH_FAILED` and surface the script's last printed URL/title.
4. Export two env vars so the execution subagents (and mid-run re-auth) can find the session:
   - `SSO_STORAGE_STATE=output/auth/storage_state.json`
   - `SSO_AUTH_SCRIPT=<ABSOLUTE_PATH_TO_SKILL>/scripts/ms_sso_auth.py`
5. Set `STORAGE_STATE_PATH = "output/auth/storage_state.json"` for use in Phase R6. When SSO is **not** active, `STORAGE_STATE_PATH` is `None`.

This runs **once** per execution — every role subagent reuses the same storage state, so the TOTP/MFA flow never repeats per test case.

### Phase R3 — Assign Run ID and create output dirs

```python
import datetime, os
date_str = datetime.date.today().strftime("%Y%m%d")
run_base = "output/results"
os.makedirs(run_base, exist_ok=True)
existing = [d for d in os.listdir(run_base) if d.startswith(f"RUN-{date_str}-")]
nnn = str(len(existing) + 1).zfill(3)
run_id = f"RUN-{date_str}-{nnn}"

for d in (f"output/screenshots/{run_id}",
          f"output/results/{run_id}",
          f"output/results/{run_id}/dom"):
    os.makedirs(d, exist_ok=True)
```

### Phase R4 — Apply `--skip-to` (if provided)

```python
if skip_to:
    idx = next((i for i, tc in enumerate(test_cases) if tc["id"] == skip_to), None)
    if idx is None:
        print(f"ERROR: --skip-to key '{skip_to}' not found.")
        sys.exit(1)
    test_cases = test_cases[idx:]
```

### Phase R5 — Print the startup banner

```
=== TEST EXECUTOR ===
Run ID:      RUN-20260513-001
URL:         <url>
Env label:   <env or "n/a">
Profile:     <path or "(none — using defaults)">
Input:       <input path>  (<N> test cases)
Output:      output/results/RUN-20260513-001/
Screenshots: output/screenshots/RUN-20260513-001/
TCs by role: <role-A>: <N>  <role-B>: <M>  ...
=====================
```

### Phase R6 — Execute

> **Delegation (see `orchestrator-protocol.md`).** Execution subagents are **Sonnet workers** (`model: "sonnet"`) — strict delegation, one per role even if there's only one role. They do the browser execution and clear-cut pass/fail vision. When a screenshot is genuinely ambiguous, the worker marks that step `status: "REVIEW"` with `needs_orchestrator_review: true` and a reason; the orchestrator (power model) re-assesses only those screenshots during the merge (R6 → R8) and finalizes PASS/FAIL.

Group TCs by `user` (role). For each role, spawn one Sonnet execution worker **in parallel** (single message). Each worker gets:

- Its role's credentials (from env)
- Its TC subset
- Run ID, output paths
- The app profile (if any)
- `STORAGE_STATE_PATH` from Phase R2.5 (or `None` if SSO is not active) — the subagent passes this to `launch_browser(..., storage_state=STORAGE_STATE_PATH)` and `do_login(..., storage_state=STORAGE_STATE_PATH)` so SSO sessions are reused and never cleared

Read `run-playwright-runner.md` for the full runner skeleton and the subagent template. The runner takes a before/after screenshot for every step, then uses Claude vision to assess pass/fail against the `expected` field.

Each worker writes `output/results/<RUN_ID>/results-<role>.json`. The orchestrator waits for all to finish, then **re-assesses every step marked `REVIEW`** by reading its after-screenshot itself (power-model vision) and finalizing PASS/FAIL, before merging into `output/results/<RUN_ID>/results.json`.

### Phase R7 — File bugs for failures (background)

For each failed step in the merged results, spawn a background bug-mode subagent (`run_in_background: true`) — fire and forget. Each gets:

- The TC key, step number, action, expected, actual observed
- The screenshot paths and DOM snapshot path
- Parent story key
- The current run's results.json path (so the bug subagent can do enrichment per `bug-mode.md`)
- Run ID and env label (for the Environment section)

The bug subagent runs in parallel with the rest of the execution and writes its result back. The Jira bug key gets attached to the step result asynchronously.

### Phase R8 — Final report

Write three files:

- `output/results/<RUN_ID>/results.json` — full step-level results (see "Results schema" below)
- `output/results/<RUN_ID>/run-report.json` — totals, duration, env, bug keys
- `output/results/<RUN_ID>/run-report.md` — human-readable markdown

Then print the console summary:

```
=====================================================================
TEST EXECUTION COMPLETE — <STORY_KEY or input filename>
Run ID:      RUN-20260513-001
URL:         <url>
Env label:   <env>
Duration:    Xm Ys
=====================================================================
Results: <P> PASS  |  <F> FAIL  |  <B> BLOCKED  |  <S> SKIPPED

FAILURES:
  <TC>  Step <N> — <action>
    Expected: <expected>
    Actual:   <actual>
    Bug filed: <bug key or "pending background">
  ...
=====================================================================
```

### Phase R9 — Upload to Xray (background)

Spawn a background subagent (`run_in_background: true`) to update the Xray Test Execution. The subagent needs:

- Path to results.json
- The Test Execution key (either passed explicitly via `--exec-key`, or inferred from the parent Test Plan, or asked from the user)
- Status mapping: `PASS → PASSED`, `FAIL → FAILED`, `BLOCKED → BLOCKED`, `SKIPPED → TODO`

The subagent uses the connected Xray tooling to update each test status in the execution. Main session is complete once the console summary prints.

## Results schema

```json
[
  {
    "tcId":      "PROJ-1159",
    "name":      "...",
    "storyKey":  "PROJ-1155",
    "user":      "player",
    "type":      "Positive",
    "status":    "PASS",
    "duration":  "00:00:47",
    "steps": [
      {
        "stepNumber":        1,
        "action":            "...",
        "data":              "...",
        "expected":          "...",
        "actual":            "...",
        "status":            "PASS",
        "screenshot_before": "...",
        "screenshot_after":  "...",
        "consoleErrors":     []
      }
    ],
    "bugs":            [],
    "consoleWarnings": []
  }
]
```

For FAIL steps the entry also has `domSnapshot` and `bug: { status, jiraTicketKey }`.

## Early abort rule

After every test case, check the failure rate:

```python
executed = [tc for tc in results if tc["status"] in ("PASS", "FAIL", "BLOCKED")]
if len(executed) >= 10:
    failed = len([tc for tc in executed if tc["status"] in ("FAIL", "BLOCKED")])
    if failed / len(executed) > 0.50:
        print("Run aborted — >50% failure rate in first 10 test cases.")
        print("Likely environment-wide failure. Check the app and env health.")
        write_run_report(status="EARLY_ABORT")
        sys.exit(0)
```

Always write `results.json` and `run-report.json` even on early abort, with `"status": "EARLY_ABORT"`.

## Run-mode rules

- **Never accept credentials as parameters** — always env vars.
- **Never skip the screenshot** — before AND after every step, no exceptions.
- **Never paraphrase a step's action** — execute the `action` field as written.
- **Never bundle steps** — one Playwright action per `execute_step`.
- **`verify`/`check`/`assert`/`ensure` steps are assertion-only** — no interaction; vision assesses the after-screenshot.
- **`wait`/`pause` parses duration from the `data` field**, capped at 60s.
- **`preserveSession: true` skips pre-TC state reset entirely** — required for session-scope tests.
- **Bug filing is fire-and-forget** — never block step execution waiting for a bug to be filed.
- **Xray upload is fire-and-forget** — runs after the summary prints.
- **Use `domcontentloaded`, not `networkidle`** — many SPAs with polling never reach networkidle.
- **With SSO active, never `clear_session()`** — clearing cookies destroys the SSO session. The pre-auth storage state is authenticated once and reused for every TC; re-auth happens automatically only if the session expires mid-run.
- **SSO pre-auth runs exactly once** (Phase R2.5) — never per test case. Credentials come from env vars (`TEST_EMAIL`/`TEST_PASSWORD`/`TEST_TOTP_SECRET`), never from CLI params.
