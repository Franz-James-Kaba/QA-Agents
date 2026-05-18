---
name: manual-executor
description: >
  Executes test cases step by step using a Playwright-controlled Chromium browser.
  Pulls TCs directly from Xray (--from-xray STORY_KEY) or reads a local JSON file.
  Spawns parallel browser sessions by user role (player vs admin). Captures a
  screenshot before AND after every step, uses Claude vision to assess pass/fail,
  fires background bug-maester sub-agents for failures (non-blocking), and uploads
  results to Xray on completion. Triggered by "execute test cases", "run manual tests",
  "start test execution", "run tests against", or /manual-executor.
allowed-tools: Bash, Read, Write, Agent
model: sonnet
---

## Overview

Provides deterministic, step-level execution of test cases written in the TestCase JSON
format produced by `/test-case-generator`. Every action is executed exactly as written
using Playwright's Python API. A screenshot is captured after every step; Claude reads
each screenshot using the Read tool (image support) to assess pass/fail. Failures
immediately trigger `/bug-maester`.

---

## Prerequisites

Playwright must be installed in the project environment before first use:

```bash
pip install playwright
python -m playwright install chromium
```

---

## Project constants

| Item | Value |
|------|-------|
| Jira project key | `TBL` |
| Jira base URL | `https://amali-tech.atlassian.net` |
| Default target URL | `http://ttl-app-alb-1081216351.eu-west-1.elb.amazonaws.com` |
| Default viewport | 1280 x 800 |
| Browser | Chromium (headed) |
| Screenshot base path | `output/screenshots/{RUN_ID}/` |
| Results base path | `output/results/{RUN_ID}/` |
| Run ID format | `RUN-{YYYYMMDD}-{NNN}` |
| Runner script | `output/results/{RUN_ID}/pw_runner.py` |

Credentials are always read from environment variables — never hardcoded:

| Env var | Used for |
|---------|----------|
| `QA_USERNAME` | Primary player-role test account |
| `QA_PASSWORD` | Primary player-role test account |
| `QA_USERNAME_2` | Secondary player-role test account (for multi-player TCs) |
| `QA_PASSWORD_2` | Secondary player-role test account (for multi-player TCs) |
| `QA_ADMIN_USERNAME` | Admin-role test account |
| `QA_ADMIN_PASSWORD` | Admin-role test account |
| `JIRA_EMAIL` | Jira REST API auth (bug filing) |
| `JIRA_API_TOKEN` | Jira REST API auth (bug filing) |

### Auto-provisioning of test players on staging/UAT

The `reset-db` endpoint is **not exposed** on staging or UAT environments
(returns 404 for security). When running against a remote environment, the
canonical local-only test users (`testplayer1`/`testpass123`,
`testadmin`/`AdminPass123!`) will not authenticate.

Instead, **auto-provision two fresh player accounts via the public signup
endpoint** during Phase 0 setup (Step 0c):

```python
import urllib.request, json, urllib.error, random, string

def provision_test_players(base_url: str) -> dict:
    """
    Create two fresh player accounts via POST /api/auth/signup/.
    Returns {'QA_USERNAME', 'QA_PASSWORD', 'QA_USERNAME_2', 'QA_PASSWORD_2'}.
    Signup form constraints (enforced server-side):
      - username: ≥3 chars, unique
      - email: valid format, unique
      - first_name, last_name: letters only (no digits, hyphens, apostrophes OK)
      - password: ≥8 chars
      - password_confirm: must match password
    """
    suffix = ''.join(random.choices(string.ascii_lowercase, k=8))
    PASSWORD = 'TestPass123!'
    creds = {}
    for n, last in enumerate(['Alpha', 'Beta'], start=1):
        username = f'qaplayer{suffix}{n}'
        payload = {
            'username': username,
            'email': f'{username}@pingmaster.test',
            'first_name': 'QA',
            'last_name': last,
            'password': PASSWORD,
            'password_confirm': PASSWORD,
        }
        req = urllib.request.Request(
            f'{base_url}/api/auth/signup/',
            data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST')
        urllib.request.urlopen(req, timeout=15)
        key_u = 'QA_USERNAME' if n == 1 else 'QA_USERNAME_2'
        key_p = 'QA_PASSWORD' if n == 1 else 'QA_PASSWORD_2'
        creds[key_u] = username
        creds[key_p] = PASSWORD
    return creds
```

Then persist the credentials to `output/.qa-credentials.env` and load them
into `os.environ` for all subsequent Playwright runs. The admin account
(`hugo`/`P@ssw0rd`) is a pre-existing staging admin — do not auto-create
admins.

**When to auto-provision:**
- The `--env` flag is `staging`, `uat`, or `production` (i.e. not `local`)
- OR `QA_USERNAME` env var is unset
- OR `QA_USERNAME` login returns 401

**When NOT to auto-provision:** `--env local` with valid `QA_USERNAME` env
var (use seeded testplayer credentials via `reset-db` instead).

### Multi-player test cases

TCs that require interaction between two players (e.g. one logs a match,
the other receives the notification) reference the secondary credentials
via `QA_USERNAME_2` / `QA_PASSWORD_2`. The `data` field in the step that
introduces the second user MUST use the env-var reference, not a hardcoded
username — substitute at execution time.

Example step rewriting at runtime: if `data` contains the literal string
`testplayer1` and the TC needs a real second player, replace with
`os.environ['QA_USERNAME_2']` before executing the step.

---

## Input / parameter contract

```
# Pull TCs directly from Xray (recommended — no JSON file needed)
/manual-executor --from-xray TBL-1155 --url http://ttl-app-alb-1081216351.eu-west-1.elb.amazonaws.com --env staging

# Use a pre-existing local JSON file
/manual-executor --input output/test-cases/TBL-1155.json --url http://ttl-app-alb-1081216351.eu-west-1.elb.amazonaws.com --env staging

# Resume a run from a specific TC key (skips all earlier TCs)
/manual-executor --from-xray TBL-1155 --url http://ttl-app-alb-1081216351.eu-west-1.elb.amazonaws.com --env staging --skip-to TBL-1165

# Override to local if running against localhost
/manual-executor --from-xray TBL-1155 --url http://localhost:4200 --env local
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--from-xray` | One of these | Jira story key — pull linked TCs from Xray automatically |
| `--input` | One of these | Path to local TestCase JSON file |
| `--url` | Yes | Target base URL |
| `--env` | Yes | Environment name (`local`, `staging`, `uat`, `production`) |
| `--skip-to` | No | TC key to resume from — skips all earlier TCs |

Credentials are always read from env vars — never accepted as parameters.

---

## TestCase JSON schema (input contract)

```json
{
  "id":              "TBL-1159",
  "name":            "TBL-1155 — Player B sees confirmation dialog within 15s — positive",
  "type":            "Positive",
  "storyKey":        "TBL-1155",
  "storySummary":    "Match Result Confirmation Workflow",
  "preconditions":   "User testplayer2 is logged in. PENDING_CONFIRMATION match exists.",
  "steps": [
    {
      "action":   "Navigate to the player dashboard",
      "data":     "/dashboard",
      "expected": "Player dashboard is visible"
    }
  ],
  "user":            "player",
  "preserveSession": false,
  "manualOnly":      false
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | TC Jira key |
| `name` | Yes | Full descriptive name |
| `storyKey` | Yes | Parent story key |
| `steps` | Yes | Array of `{action, data, expected}` |
| `user` | No | `"player"` (default) or `"admin"` — which credential pair to use |
| `preserveSession` | No | `true` = skip pre-TC state clear (required for session-scope tests) |
| `manualOnly` | No | `true` = skip execution, count as SKIPPED |

`manualOnly: true` test cases are skipped — counted in the report but not executed.

---

## Sub-Agent Architecture

Five sub-agents parallelise and decouple the work:

```
Phase -0.5: [SA-1 Explore]     fetch all TC steps from Xray in parallel → assembled JSON
Phase  0:   [Main + SA-5]      validate inputs AND seed/check backend simultaneously
Phase  2:   [SA-2a Player] ──+
                               ├── run simultaneously → merge results
            [SA-2b Admin]  ──+
Phase  3:   [SA-3 Background x N]   fire-and-forget bug reports per failure step
Phase  5:   [SA-4 Background]       Xray result upload while main prints report
```

---

## Phase -0.5 — Xray Pull (only when `--from-xray` is used)

**Sub-agent type: Explore**

Spawn a single Explore sub-agent with this intent:

1. Call `GET /rest/api/3/issue/{STORY_KEY}?fields=issuelinks` (Basic auth from
   env vars `JIRA_EMAIL` and `JIRA_API_TOKEN`) to find all issues linked via
   type `"is tested by"`. Collect each inward issue's key and numeric id.

2. For each TC numeric id, call `mcp__xray__get_test_steps` — fire all in parallel,
   not sequentially.

3. For each TC key, call `GET /rest/api/3/issue/{TC_KEY}?fields=summary,description`
   to get names and preconditions.

4. Assemble a JSON array in the TestCase schema:
   - `id`: TC Jira key
   - `name`: TC summary from Jira
   - `type`: `"Positive"` if name contains "positive", else `"Negative"`
   - `storyKey`: the story key passed in
   - `preconditions`: first paragraph of TC description
   - `steps`: from Xray — map `action`→`action`, `data`→`data`, `result`→`expected`
   - `user`: `"admin"` if TC name/preconditions mention "admin", else `"player"`
   - `preserveSession`: `true` if TC name contains "session", "reappear", or "dismissed"
   - `manualOnly`: `false`

5. Return the JSON array.

Wait for SA-1. Write the result to `output/test-cases/{STORY_KEY}.json`.
Set `--input` to this file and continue to Phase 0.

---

## Phase 0 — Validate inputs and environment

### Step 0a — Validate input file

```python
import json, sys, os

input_path = "<RESOLVED_INPUT_PATH>"
if not os.path.exists(input_path):
    print(f"ERROR: Input file not found: {input_path}")
    sys.exit(1)

with open(input_path, encoding="utf-8") as f:
    test_cases = json.load(f)

if not isinstance(test_cases, list) or len(test_cases) == 0:
    print("ERROR: Input must be a non-empty JSON array of TestCase objects.")
    sys.exit(1)

required = {"id", "name", "storyKey", "steps"}
for tc in test_cases:
    missing = required - tc.keys()
    if missing:
        print(f"ERROR: TestCase {tc.get('id','?')} missing fields: {missing}")
        sys.exit(1)
```

### Step 0b — Validate target URL is reachable

```python
import urllib.request

url = "<RESOLVED_URL>"
try:
    with urllib.request.urlopen(url, timeout=30) as r:
        status = r.status
        if status >= 500:
            print(f"ENVIRONMENT_UNAVAILABLE: {url} returned HTTP {status}")
            sys.exit(1)
        print(f"Environment check: {url}  HTTP {status}  ✓")
except Exception as e:
    print(f"ENVIRONMENT_UNAVAILABLE: {url} — {e}")
    sys.exit(1)
```

**Spawn SA-5 (background general-purpose sub-agent) at the same time as Steps 0a–0e.**

SA-5 checks:
1. Backend health — `GET {BASE_URL_API}/api/`
2. Pending match data — `GET /api/matches/?status=PENDING_CONFIRMATION` (warns if 0)
3. Player credentials — `POST /api/auth/login/` with `QA_USERNAME`/`QA_PASSWORD`
4. Admin credentials — same endpoint with `QA_ADMIN_USERNAME`/`QA_ADMIN_PASSWORD`

Reports OK/FAIL for each. Main context waits for SA-5 after Step 0e.
If SA-5 reports backend unavailable or credentials invalid for a role, mark all
TCs for that role as BLOCKED before Phase 2.

### Step 0c — Verify or auto-provision credentials

For local environments, verify env vars are set:

```python
env_flag = "<RESOLVED_ENV>"
url      = "<RESOLVED_URL>"

def login_ok(base, u, p):
    """Returns True if /api/auth/login/ accepts the credentials."""
    import urllib.request, urllib.error, json
    try:
        body = json.dumps({'username': u, 'password': p}).encode()
        req  = urllib.request.Request(f'{base}/api/auth/login/', data=body,
                 headers={'Content-Type':'application/json'}, method='POST')
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception:
        return False

# Player credentials — auto-provision if missing or invalid on remote envs
need_provision = (
    env_flag != "local" or
    not os.environ.get("QA_USERNAME") or
    not login_ok(url, os.environ.get("QA_USERNAME",""), os.environ.get("QA_PASSWORD",""))
)

if need_provision:
    print(f"Auto-provisioning fresh player accounts via /api/auth/signup/ ...")
    creds = provision_test_players(url)
    for k, v in creds.items():
        os.environ[k] = v
    os.makedirs("output", exist_ok=True)
    with open("output/.qa-credentials.env", "w") as f:
        for k, v in creds.items():
            f.write(f"{k}={v}\n")
        f.write(f"QA_ADMIN_USERNAME={os.environ.get('QA_ADMIN_USERNAME','hugo')}\n")
        f.write(f"QA_ADMIN_PASSWORD={os.environ.get('QA_ADMIN_PASSWORD','P@ssw0rd')}\n")
    print(f"Provisioned: {creds['QA_USERNAME']} and {creds['QA_USERNAME_2']}")

# Admin credentials — never auto-create admins
admin_tcs_present = any(tc.get("user") == "admin" for tc in test_cases)
if admin_tcs_present:
    for var in ("QA_ADMIN_USERNAME", "QA_ADMIN_PASSWORD"):
        if not os.environ.get(var):
            print(f"WARNING: {var} not set — admin TCs will be BLOCKED.")
```

### Step 0d — Verify Playwright is installed

```bash
python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
```

If this fails, print:
```
ERROR: Playwright is not installed. Run:
  pip install playwright
  python -m playwright install chromium
```
and stop.

### Step 0e — Assign Run ID and create output directories

```python
import datetime

date_str = datetime.date.today().strftime("%Y%m%d")
run_base = "output/results"
os.makedirs(run_base, exist_ok=True)
existing = [d for d in os.listdir(run_base) if d.startswith(f"RUN-{date_str}-")]
nnn = str(len(existing) + 1).zfill(3)
run_id = f"RUN-{date_str}-{nnn}"

screenshot_dir = f"output/screenshots/{run_id}"
results_dir    = f"output/results/{run_id}"
dom_dir        = f"output/results/{run_id}/dom"
os.makedirs(screenshot_dir, exist_ok=True)
os.makedirs(results_dir, exist_ok=True)
os.makedirs(dom_dir, exist_ok=True)

print(f"Run ID: {run_id}")
```

### Step 0f — Apply `--skip-to` filter (if provided)

```python
skip_to = "<RESOLVED_SKIP_TO_OR_NONE>"
if skip_to:
    idx = next((i for i, tc in enumerate(test_cases) if tc["id"] == skip_to), None)
    if idx is None:
        print(f"ERROR: --skip-to key '{skip_to}' not found.")
        sys.exit(1)
    print(f"Skipping {idx} TCs, resuming from {skip_to}")
    test_cases = test_cases[idx:]
```

Wait for SA-5. If backend unavailable, stop. Then print the startup banner:

```
=== MANUAL TEST EXECUTOR ===
Run ID:      RUN-20260513-001
Environment: staging
URL:         http://ttl-app-alb-1081216351.eu-west-1.elb.amazonaws.com
Input:       output/test-cases/TBL-1155.json  (11 test cases)
Output:      output/results/RUN-20260513-001/
Screenshots: output/screenshots/RUN-20260513-001/
Player TCs:  7  (TBL-1159, 1160, 1161, 1162, 1166, 1167, 1169)
Admin TCs:   4  (TBL-1163, 1164, 1165, 1168)
============================
```

---

## Phase 1 — Browser initialisation and authentication

### Step 1a — Write and launch the Playwright runner

Write `output/results/{RUN_ID}/pw_runner.py` with the following content, substituting
`{RUN_ID}`, `{BASE_URL}`, and `{SCREENSHOT_DIR}`:

```python
"""
Playwright browser session for manual-executor run {RUN_ID}.
Called once to launch the browser; the page object is reused across all steps
by writing/reading a CDP endpoint file.
"""
import os, json, sys, time
from playwright.sync_api import sync_playwright, Page, expect

RUN_ID        = "{RUN_ID}"
BASE_URL      = "{BASE_URL}"
SCREENSHOT_DIR = "{SCREENSHOT_DIR}"
RESULTS_DIR   = "output/results/{RUN_ID}"
DOM_DIR       = os.path.join(RESULTS_DIR, "dom")

def launch_browser(group_label: str = ""):
    """Launch a headed Chromium browser and return (playwright, browser, context, page)."""
    pw      = sync_playwright().start()
    browser = pw.chromium.launch(headless=False, slow_mo=80)
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page    = context.new_page()

    # Accept all native browser dialogs (required: admin Void uses window.confirm)
    page.on("dialog", lambda d: d.accept())

    # Collect JS console errors throughout the run
    page._console_errors = []
    page.on("console", lambda msg: page._console_errors.append(msg.text)
            if msg.type == "error" else None)

    if group_label:
        print(f"[{group_label}] Browser launched")
    return pw, browser, context, page

def clear_session(page: Page):
    """Clear cookies, localStorage, and sessionStorage."""
    page.evaluate("""() => {
        localStorage.clear();
        sessionStorage.clear();
        document.cookie.split(';').forEach(c => {
            const name = c.split('=')[0].trim();
            document.cookie = name + '=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/';
        });
    }""")

def wait_stable(page: Page, timeout_ms: int = 8000):
    """
    SPA-safe stable-state wait. Uses domcontentloaded — NOT networkidle.
    Angular SPAs with polling intervals (like MatchNotificationService) never
    reach networkidle; using it causes every wait to time out at 10s.
    """
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        pass  # non-fatal — proceed and assess from screenshot


def wait_for_element(page: Page, selector: str, timeout_ms: int = 12000) -> bool:
    """
    Wait for a CSS selector to appear. Returns True if found, False on timeout.
    Use instead of time.sleep() for async-appearing elements (e.g. polling dialog).
    """
    try:
        page.wait_for_selector(selector, timeout=timeout_ms)
        return True
    except Exception:
        return False

def spa_navigate(page: Page, link_text: str):
    """
    SPA-aware in-app navigation. Clicks a sidebar nav link instead of page.goto().
    CRITICAL: Use this for ALL in-app navigation during a TC that has preserveSession=True.
    page.goto() triggers a full Angular app reload which RESETS in-memory state
    (e.g. MatchNotificationService seenIds Set) — causing session-scope TCs to fail.
    Only use page.goto() for the initial page load or when preserveSession=False.
    """
    page.locator("nav").get_by_text(link_text, exact=True).first.click()
    time.sleep(2)

def wait_loading_done(page: Page, timeout_ms: int = 12000):
    """
    Wait for admin page data-fetch spinners to disappear before interacting with tabs.
    Admin pages (e.g. /admin/match-confirmations) show a "Loading confirmations..."
    spinner while fetching data. Clicking tabs/buttons before it disappears silently
    fails — the click registers but the DOM hasn't rendered the content yet.
    Also handles generic loading/spinner classes as fallback.
    """
    # Try exact "Loading confirmations..." text first (admin match-confirmations)
    try:
        page.wait_for_selector("text=Loading confirmations...", state="hidden",
                               timeout=timeout_ms)
    except Exception:
        pass
    # Fallback: any generic loading/spinner element
    try:
        page.wait_for_selector("[class*='loading'], [class*='spinner']", state="hidden",
                               timeout=3000)
    except Exception:
        pass
    time.sleep(0.5)

def poll_for_elements(page: Page, selector: str, max_seconds: int = 15) -> bool:
    """
    DOM polling loop for post-action re-renders.
    Angular re-renders the match list ~2s after dialog dismissal (Decide Later).
    Fixed sleeps miss this window; a poll loop catches the render reliably.
    Use when `expected` mentions "inline buttons visible" after a dialog was dismissed.
    Returns True if elements appeared within max_seconds, False otherwise.
    """
    for _ in range(max_seconds):
        time.sleep(1)
        if page.locator(selector).count() > 0:
            return True
    return False

def take_screenshot(page: Page, path: str):
    """Capture a full-page screenshot to path."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    page.screenshot(path=path, full_page=True)

def capture_dom(page: Page, path: str):
    """Save the current DOM to path."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(page.content())

def resolve_selector(action: str) -> str | None:
    """
    Infer a CSS/attribute selector from action text. Priority:
      1. data-testid  — "testid:login-btn" syntax
      2. data-cy      — "data-cy:login-btn" (Cypress attrs used on login form)
      3. CSS class    — "click .btn-accept" (dialog/admin buttons have only CSS classes)
    Returns None when no explicit selector found — caller uses get_by_* fluent API.
    """
    import re
    # data-testid
    m = re.search(r"(?:testid|data-testid)[:\s=]+['\"]?([a-z0-9_-]+)['\"]?", action, re.I)
    if m:
        return f"[data-testid='{m.group(1)}']"
    # data-cy (Cypress convention — present on TBL login form inputs and submit button)
    m = re.search(r"(?:data-cy|cy)[:\s=]+['\"]?([a-z0-9_-]+)['\"]?", action, re.I)
    if m:
        return f"[data-cy='{m.group(1)}']"
    # CSS class explicitly in action — e.g. "Click .btn-accept" or "Click .btn-force-confirm"
    m = re.search(r"\.([a-z][a-z0-9_-]{2,})", action)
    if m:
        return f".{m.group(1)}"
    return None  # caller uses page.get_by_* fluent API instead

def click_element(page: Page, action: str):
    """Click the element described in action text."""
    import re
    # 1. Explicit selector (data-testid, data-cy, CSS class)
    sel = resolve_selector(action)
    if sel:
        page.locator(sel).first.click()
        return
    # 2. Quoted text → getByText
    m = re.search(r"['\"]([^'\"]+)['\"]", action)
    if m:
        page.get_by_text(m.group(1), exact=False).first.click()
        return
    # 3. Named button (handles Accept, Contest, Decide Later, Force Confirm, Void, etc.)
    m = re.search(
        r"(?:tap|click|press)\s+(?:the\s+)?['\"]?([A-Za-z][A-Za-z0-9 ✓←]{1,40}?)['\"]?\s+button",
        action, re.I)
    if m:
        page.get_by_role("button",
                         name=re.compile(re.escape(m.group(1).strip()), re.I)).first.click()
        return
    # 4. Named link
    m = re.search(
        r"(?:tap|click|press)\s+(?:the\s+)?['\"]?([A-Za-z][A-Za-z0-9 ]{1,40}?)['\"]?\s+link",
        action, re.I)
    if m:
        page.get_by_role("link",
                         name=re.compile(re.escape(m.group(1).strip()), re.I)).first.click()
        return
    # 5. Fallback: longest meaningful word → getByText
    stop = {"click","tap","press","button","the","and","from","into","on","at","link","item"}
    words = [w for w in re.findall(r"[A-Za-z]{4,}", action) if w.lower() not in stop]
    if words:
        page.get_by_text(words[0], exact=False).first.click()
        return
    raise RuntimeError(f"Cannot resolve click target from action: {action!r}")

def fill_element(page: Page, action: str, data: str):
    """Fill a form field described in action text with data."""
    import re
    # 1. Explicit selector (data-cy preferred for login form)
    sel = resolve_selector(action)
    if sel:
        page.locator(sel).fill(data)
        return
    # 2. Username field — label "Username" on the Angular login form
    if re.search(r"\busername\b", action, re.I):
        page.get_by_label(re.compile(r"username", re.I)).fill(data)
        return
    # 3. Email field
    if re.search(r"\bemail\b", action, re.I):
        page.get_by_label(re.compile(r"email", re.I)).fill(data)
        return
    # 4. Password field
    if re.search(r"password", action, re.I):
        page.get_by_label(re.compile(r"password", re.I)).fill(data)
        return
    # 5. Contest/dispute reason textarea (TBL-1155 dialog specific)
    if re.search(r"contest|reason|dispute", action, re.I):
        page.locator(".contest-textarea").fill(data)
        return
    # 6. Named label in action
    m = re.search(
        r"(?:fill|enter|type|input)\s+(?:the\s+)?['\"]?([A-Za-z][A-Za-z ]{1,40}?)['\"]?\s+"
        r"(?:field|input|box|area|textarea)", action, re.I)
    if m:
        page.get_by_label(m.group(1), exact=False).fill(data)
        return
    # 7. Placeholder text as fallback
    m = re.search(r"['\"]([^'\"]{3,40})['\"]", action)
    if m:
        page.get_by_placeholder(m.group(1), exact=False).fill(data)
        return
    raise RuntimeError(f"Cannot resolve fill target from action: {action!r}")

def cleanup_all_pending(base_url: str, admin_token: str):
    """
    Pre-TC state reset: force-confirm all PENDING_CONFIRMATION matches and void all
    DISPUTED matches via API before creating a new match for the TC.
    Call this before any TC that creates a fresh match (user=="player" TCs that
    interact with match confirmation workflow). Without this, leftover matches from
    prior TCs can trigger unexpected dialogs, polluting the test environment.
    """
    import urllib.request, json
    for status, action in [("PENDING_CONFIRMATION", "force-confirm"), ("DISPUTED", "void")]:
        try:
            req = urllib.request.Request(
                f"{base_url}/api/matches/?status={status}&limit=100",
                headers={"Authorization": f"Bearer {admin_token}", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode())
            matches = data.get("results", data) if isinstance(data, dict) else data
            for m in matches:
                try:
                    act = urllib.request.Request(
                        f"{base_url}/api/matches/{m['id']}/{action}/", data=b"{}",
                        headers={"Content-Type": "application/json",
                                 "Authorization": f"Bearer {admin_token}"},
                        method="POST")
                    urllib.request.urlopen(act, timeout=10)
                except Exception:
                    pass
        except Exception:
            pass

def verify_match_status_via_api(base_url: str, admin_token: str, match_id: int) -> str:
    """
    API-based outcome verification. Use after UI actions that change match status
    (Accept, Contest, Force Confirm, Void). DOM may lag; API is the authoritative source.
    Returns the match status string (e.g. 'COMPLETED', 'DISPUTED', 'CANCELLED').
    """
    import urllib.request, json
    req = urllib.request.Request(f"{base_url}/api/matches/{match_id}/",
        headers={"Authorization": f"Bearer {admin_token}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode()).get("status", "UNKNOWN")

def execute_step(page: Page, step: dict, tc_id: str, step_n: int,
                 screenshot_dir: str, dom_dir: str) -> dict:
    """
    Execute one test step. Takes a screenshot BEFORE and AFTER the action.
    Returns:
      {
        "screenshot_before": str,
        "screenshot_after":  str,
        "dom":               str | None,
        "error":             str | None,
        "consoleErrors":     [str]
      }
    """
    action   = step["action"]
    data     = step.get("data", "-") or "-"
    expected = step.get("expected", "")
    import re

    before_path = os.path.join(screenshot_dir, f"{tc_id}-step{step_n:02d}-before.png")
    after_base  = os.path.join(screenshot_dir, f"{tc_id}-step{step_n:02d}")
    error_msg   = None

    # Capture BEFORE screenshot (shows initial state before the action)
    take_screenshot(page, before_path)
    console_before = len(getattr(page, "_console_errors", []))

    try:
        verb = action.split()[0].lower() if action.split() else ""

        # Navigate
        # SPA note: for preserveSession=True TCs, in-app navigation must NOT use
        # page.goto() — that triggers a full reload and resets Angular in-memory state.
        # Instead, detect sidebar nav keywords and call spa_navigate().
        # Only use page.goto() for the initial load or preserveSession=False TCs.
        if verb in ("navigate", "open", "go"):
            # Detect explicit "navigate to /path" with a URL path → page.goto()
            target = data if data not in ("N/A", "-") else BASE_URL
            # Check if action describes a sidebar navigation (no URL path given)
            sidebar_keywords = re.search(
                r"\b(tournaments|dashboard|standings|challenge.hub|league)\b",
                action, re.I)
            if sidebar_keywords and (data in ("N/A", "-") or not data.startswith("/")):
                # SPA navigation via sidebar link click
                spa_navigate(page, sidebar_keywords.group(1).replace("-", " ").title())
            else:
                if not target.startswith("http"):
                    target = BASE_URL.rstrip("/") + ("" if target.startswith("/") else "/") + target.lstrip("/")
                page.goto(target)
                wait_stable(page)
                # If navigating to an admin page, wait for loading spinner to clear
                if "/admin/" in target:
                    wait_loading_done(page)

        # Click
        elif verb in ("tap", "click", "press"):
            click_element(page, action)
            wait_stable(page)

        # Fill
        elif verb in ("fill", "enter", "type", "input"):
            fill_element(page, action, "" if data in ("N/A", "-") else data)

        # Select
        elif verb == "select":
            m = re.search(r"['\"]([^'\"]+)['\"]", action)
            label = m.group(1) if m else action
            page.get_by_label(label, exact=False).select_option(data)

        # Scroll
        elif verb in ("scroll", "swipe"):
            page.evaluate("window.scrollBy(0, 400)")
            wait_stable(page)

        # Upload
        elif verb == "upload":
            m = re.search(r"['\"]([^'\"]+)['\"]", action)
            label = m.group(1) if m else "file"
            page.get_by_label(label, exact=False).set_input_files(data)

        # Wait / Pause — parse numeric duration from data field; use selector wait for dialogs
        elif verb in ("wait", "pause"):
            duration_match = re.search(r"(\d+(?:\.\d+)?)", data) or re.search(r"(\d+)", action)
            duration_s = float(duration_match.group(1)) if duration_match else 2.0
            duration_s = min(duration_s, 60.0)  # cap at 60s

            if re.search(r"dialog|overlay|popup|confirmation|notif", expected, re.I):
                # Use selector wait instead of sleep — more reliable for polling-triggered UI
                found = wait_for_element(page, ".notif-overlay",
                                         timeout_ms=int(duration_s * 1000) + 2000)
                if not found:
                    raise RuntimeError(
                        f".notif-overlay did not appear within {duration_s}s"
                    )
            else:
                time.sleep(duration_s)

        # Verify / Check / Assert / Ensure — pure assertion, NO Playwright interaction
        # Claude vision assesses the after-screenshot against `expected`
        elif verb in ("verify", "check", "assert", "confirm", "ensure"):
            wait_stable(page, 5000)
            sel = resolve_selector(action)
            if sel:
                wait_for_element(page, sel, timeout_ms=8000)
            # No interaction — screenshot will be read and assessed

        # Log in / Authenticate (re-auth mid-run using role-appropriate credentials)
        elif verb in ("log", "login", "authenticate", "sign"):
            if re.search(r"admin", action, re.I):
                u = os.environ.get("QA_ADMIN_USERNAME", "")
                p = os.environ.get("QA_ADMIN_PASSWORD", "")
            else:
                u = os.environ.get("QA_USERNAME", "")
                p = os.environ.get("QA_PASSWORD", "")
            # Inline auth — navigate to /login and submit
            page.goto(BASE_URL.rstrip("/") + "/login")
            wait_stable(page, 10000)
            try:
                page.locator('[data-cy="login-username-input"]').fill(u)
                page.locator('[data-cy="login-password-input"]').fill(p)
                page.locator('[data-cy="login-submit-btn"]').click()
            except Exception:
                page.get_by_label(re.compile(r"username|email", re.I)).fill(u)
                page.get_by_label(re.compile(r"password", re.I)).fill(p)
                page.get_by_role("button", name=re.compile(r"login|sign in", re.I)).click()
            try:
                page.wait_for_url(re.compile(r"(?!.*/login)"), timeout=15000)
            except Exception:
                pass
            wait_stable(page)

        # Fallback: attempt click
        else:
            click_element(page, action)
            wait_stable(page)

    except Exception as e:
        error_msg = str(e)

    # Capture AFTER screenshot
    suffix = "-fail.png" if error_msg else "-pass.png"
    after_path = after_base + suffix
    take_screenshot(page, after_path)

    # Collect new console errors since before-snapshot
    all_errors = getattr(page, "_console_errors", [])
    new_errors = all_errors[console_before:]

    result = {
        "screenshot_before": before_path,
        "screenshot_after":  after_path,
        "dom":               None,
        "error":             error_msg,
        "consoleErrors":     new_errors,
    }

    if error_msg:
        dom_path = os.path.join(dom_dir, f"{tc_id}-step{step_n:02d}.html")
        capture_dom(page, dom_path)
        result["dom"] = dom_path

    return result
```

Then execute:

```bash
python -c "from output.results.{RUN_ID}.pw_runner import launch_browser; pw, browser, ctx, page = launch_browser(); print('Browser launched')"
```

Adapt the import path to the actual run ID. If the launch fails, print the error and stop.

### Step 1b — Authenticate (per browser group)

Each browser session (SA-2a player, SA-2b admin) authenticates with its own
credential pair. Use the `data-cy` selectors present on the Angular login form
as the primary mechanism, with label-based fallback:

```python
# Determine credentials from the group's user type
is_admin_group = (group_label == "admin-group")
username = os.environ.get("QA_ADMIN_USERNAME" if is_admin_group else "QA_USERNAME", "")
password = os.environ.get("QA_ADMIN_PASSWORD" if is_admin_group else "QA_PASSWORD", "")

page.goto(BASE_URL.rstrip("/") + "/login")
wait_stable(page, 10000)

try:
    # Primary: data-cy selectors on Angular login form
    page.locator('[data-cy="login-username-input"]').fill(username)
    page.locator('[data-cy="login-password-input"]').fill(password)
    page.locator('[data-cy="login-submit-btn"]').click()
except Exception:
    # Fallback: label-based
    page.get_by_label(re.compile(r"username|email", re.I)).fill(username)
    page.get_by_label(re.compile(r"password", re.I)).fill(password)
    page.get_by_role("button", name=re.compile(r"login|sign in|submit", re.I)).click()

try:
    page.wait_for_url(re.compile(r"(?!.*/login)"), timeout=15000)
except Exception:
    pass

shot = f"output/screenshots/{RUN_ID}/session-login-{group_label}.png"
page.screenshot(path=shot)
print(f"Post-login URL: {page.url}")
```

Use the Read tool to view the screenshot and verify the dashboard is visible.

If still on `/login` after 15s:
- Save screenshot `session-login-failed.png`
- Mark all TCs in this group BLOCKED with reason "Login failed"
- Write partial results file and stop this sub-agent

### Step 1c — Session re-authentication during the run

If a screenshot mid-run shows a login form when a dashboard is expected:
1. Re-run the login steps from 1b using the existing page object
2. Log: `Session re-authenticated at TC {TC_ID} step {STEP_N}`
3. Resume from the current step

---

## Phase 2 — Execute test cases (parallel browser sessions)

### Group TCs by user field

```python
player_tcs = [tc for tc in test_cases if tc.get("user", "player") == "player"
              and not tc.get("manualOnly")]
admin_tcs  = [tc for tc in test_cases if tc.get("user") == "admin"
              and not tc.get("manualOnly")]
manual_tcs = [tc for tc in test_cases if tc.get("manualOnly")]
```

### Spawn SA-2a and SA-2b in a single message (they run simultaneously)

Give each sub-agent:
- Its credential pair (`QA_USERNAME`/`QA_PASSWORD` or `QA_ADMIN_USERNAME`/`QA_ADMIN_PASSWORD`)
- Its subset of TCs (the JSON array for that group)
- The shared `output/` paths and `run_id`
- The pw_runner module path to import from

Each sub-agent authenticates, then executes its TCs and writes its results file:
- SA-2a writes `output/results/{RUN_ID}/results-player.json`
- SA-2b writes `output/results/{RUN_ID}/results-admin.json`

Main context waits for both to finish, then merges:

```python
import json, os
player_r = json.load(open(f"{results_dir}/results-player.json")) \
           if os.path.exists(f"{results_dir}/results-player.json") else []
admin_r  = json.load(open(f"{results_dir}/results-admin.json")) \
           if os.path.exists(f"{results_dir}/results-admin.json")  else []
manual_r = [{"tcId": tc["id"], "name": tc["name"], "status": "SKIPPED", "steps": []}
            for tc in manual_tcs]
all_results = player_r + admin_r + manual_r
json.dump(all_results, open(f"{results_dir}/results.json", "w"), indent=2)
```

### Pre-test setup (before each TC, inside each sub-agent)

Unless `tc["preserveSession"] == True`:
1. `clear_session(page)` — wipes localStorage, sessionStorage, cookies
2. `page.goto(BASE_URL)` + `wait_stable(page)` — reloads app, resets all Angular
   in-memory services including `MatchNotificationService.seenIds`
3. Re-authenticate — sessionStorage clear removes the Angular JWT token, so
   auth must be re-done before each TC

When `preserveSession == True` (e.g. TC-009 "dismissed dialog does not reappear"):
- **Skip all three steps entirely** — the in-memory `seenIds` Set must survive
  between steps; a page reload would reset it and make the test unexecutable

If `preconditions` specify a start page (e.g. "User is on /admin/match-confirmations"),
navigate there directly after re-auth: `page.goto(BASE_URL + "/admin/match-confirmations")`.

If SA-5 reported backend data missing (no `PENDING_CONFIRMATION` match) and the TC
needs one, mark it BLOCKED with reason "Precondition: no PENDING_CONFIRMATION match".

### Step execution loop

For each step in the test case, repeat this sequence:

**1. Call `execute_step()`** from pw_runner — handles verb dispatch, takes before+after screenshots.

Action verb → Playwright mapping (handled inside `execute_step`):

| Verb | Playwright action | Notes |
|------|-----------------|-------|
| Tap / Click | `page.locator(sel).click()` or `get_by_role/text` | CSS class sel preferred for dialog/admin btns |
| Fill / Enter / Type | `page.locator(sel).fill()` or `get_by_label()` | data-cy preferred for login form |
| Navigate / Open / Go | `page.goto(url)` | Relative paths resolved against BASE_URL |
| Select | `page.get_by_label().select_option()` | |
| Scroll / Swipe | `page.evaluate("window.scrollBy(0, 400)")` | |
| Wait / Pause | `wait_for_selector(".notif-overlay")` or `time.sleep(N)` | Parses N from data field |
| **Verify / Check / Assert** | **No interaction** | Vision-only assessment from screenshot |
| Log in / Sign in | `data-cy` fill + click | Re-auths with env-var credentials |

Selector priority (most to least preferred):
1. `[data-cy="…"]` — login form
2. `[data-testid="…"]` — if present
3. CSS class `.btn-accept`, `.btn-force-confirm` etc. — dialog and admin page
4. `get_by_role("button", name="…")` — named buttons
5. `get_by_label("…")` — form fields
6. `get_by_text("…")` — visible text
7. Never use positional XPath

**2. Read the AFTER screenshot** using the Read tool:
```
Read tool: output/screenshots/{RUN_ID}/{TC_ID}-step{N:02d}-pass.png (or -fail.png)
```

**3. Assess pass/fail** by comparing visible UI against `step["expected"]`:

| Expected phrase | What to look for |
|----------------|-----------------|
| "dialog appears" / "overlay" | `.notif-overlay` card visible on page |
| "COMPLETED" / "DISPUTED" / "CANCELLED" | Status text/badge on match row |
| "success toast" | Toast notification with correct message |
| "dialog dismissed" | `.notif-overlay` no longer present |
| "does NOT appear" | **Absence** of `.notif-overlay` |
| "empty state" | Zero-count badge, "No results" text |
| "button is disabled" | Greyed button, `disabled` attribute |
| "contest textarea" | `.contest-textarea` visible and editable |

For **negative assertions** ("does NOT appear", "should be absent"): PASS = absent, FAIL = present.

**4. Check page text** for supplementary failure context:
```python
body_text = page.inner_text("body")[:2000]
```

Log the actual observed state precisely: `"Actual: 'Server error' toast shown; match still in table"`

**5. Console errors** are already collected automatically via the `page.on("console", ...)` listener
   set up in `launch_browser()`. They are attached to each step result as `consoleErrors`.

---

## Phase 3 — Failure handling and escalation

### On step failure

1. **Rename screenshot** to `{TC_ID}-step{N:02d}-fail.png`.

2. **Capture DOM snapshot:**
   ```python
   dom_path = f"output/results/{RUN_ID}/dom/{TC_ID}-step{N:02d}.html"
   with open(dom_path, "w", encoding="utf-8") as f:
       f.write(page.content())
   ```

3. **Log the failure:**
   ```
   FAIL  TC: {TC_ID}  Step {N}: {action}
         Expected: {expected}
         Actual:   {actual_observed}
         Screenshot: {screenshot_path}
   ```

4. **Determine criticality:**
   - **Critical**: login failed, required form did not submit, page is still on the same
     step after action (no state change), essential navigation did not occur.
   - **Non-critical**: a label has wrong text, a secondary toast has wrong wording,
     minor visual mismatch that does not block the next step.

   If **critical**: mark all remaining steps in this TC as `BLOCKED` and end the TC.
   If **non-critical**: mark this step `FAIL`, continue to the next step.

5. **Spawn a background sub-agent (SA-3) for every FAIL step — fire and DO NOT wait:**

   Use `run_in_background: true`. The run immediately continues to the next step.

   Give the background sub-agent:
   - TC id, step number, expected, actual observed, screenshot path, DOM path
   - Story key, environment, run ID
   - Instruction to use `JIRA_EMAIL` and `JIRA_API_TOKEN` env vars for Jira REST auth
   - Check for existing open TBL Bug with same TC/step prefix before creating a new one
   - File under `TBL` project (not AMOB)

   Expected return: `{ "status": "filed"|"duplicate-updated"|"unfiled", "key": "TBL-XXX" }`

   Collect all SA-3 agent keys in Phase 4 when background work completes.
   Attach the returned Jira key to the step result in `results.json`.

### Early abort rule

After every test case, check:

```python
executed_so_far = [tc for tc in results if tc["status"] in ("PASS", "FAIL", "BLOCKED")]
if len(executed_so_far) >= 10:
    fail_count = len([tc for tc in executed_so_far if tc["status"] in ("FAIL", "BLOCKED")])
    if fail_count / len(executed_so_far) > 0.50:
        print("Run aborted — >50% failure rate in first 10 test cases.")
        print("Possible environment or build-wide failure. Check environment health.")
        write_run_report(status="EARLY_ABORT")
        sys.exit(0)
```

---

## Phase 4 — Post-test and final report

### Step 4a — Close browser

```python
context.close()
browser.close()
pw.stop()
```

### Step 4b — Write results JSON

**Output:** `output/results/{RUN_ID}/results.json`

```json
[
  {
    "tcId":       "TBL-1159",
    "name":       "TBL-1155 — Player B sees dialog within 15s — positive",
    "storyKey":   "TBL-1155",
    "user":       "player",
    "type":       "Positive",
    "status":     "PASS",
    "duration":   "00:00:47",
    "steps": [
      {
        "stepNumber":        1,
        "action":            "Navigate to the player dashboard",
        "data":              "/dashboard",
        "expected":          "Player dashboard is visible",
        "actual":            "Dashboard heading and Recent Matches section visible",
        "status":            "PASS",
        "screenshot_before": "output/screenshots/RUN-20260512-001/TBL-1159-step01-before.png",
        "screenshot_after":  "output/screenshots/RUN-20260512-001/TBL-1159-step01-pass.png",
        "consoleErrors":     []
      }
    ],
    "bugs":            [],
    "consoleWarnings": []
  },
  {
    "tcId":   "TBL-1161",
    "status": "FAIL",
    "steps": [
      {
        "stepNumber":        3,
        "status":            "FAIL",
        "actual":            "Server error toast; match status stayed PENDING_CONFIRMATION",
        "screenshot_before": "output/screenshots/RUN-20260512-001/TBL-1161-step03-before.png",
        "screenshot_after":  "output/screenshots/RUN-20260512-001/TBL-1161-step03-fail.png",
        "domSnapshot":       "output/results/RUN-20260512-001/dom/TBL-1161-step03.html",
        "bug": {
          "status":        "filed",
          "jiraTicketKey": "TBL-1180"
        }
      }
    ]
  }
]
```

### Step 4c — Write run report

**Output:** `output/results/{RUN_ID}/run-report.json`

```json
{
  "runId":              "RUN-20260512-001",
  "storyKey":           "TBL-1155",
  "environment":        "local",
  "url":                "http://ttl-app-alb-1081216351.eu-west-1.elb.amazonaws.com",
  "startTime":          "2026-05-12T10:00:00Z",
  "endTime":            "2026-05-12T10:08:41Z",
  "duration":           "00:08:41",
  "status":             "COMPLETE",
  "totals": {
    "total":     11,
    "pass":       8,
    "fail":       2,
    "blocked":    1,
    "skipped":    0,
    "manualOnly": 0
  },
  "bugs":               ["TBL-1180", "TBL-1181"],
  "warnings":           2,
  "xrayExecutionKey":   "TBL-1171"
}
```

**Output:** `output/results/{RUN_ID}/run-report.md` (human-readable markdown table)

### Step 4d — Print final console summary

```
===================================================================
MANUAL TEST EXECUTION COMPLETE — TBL-1155
Run ID:      RUN-20260513-001
Environment: staging  |  URL: http://ttl-app-alb-1081216351.eu-west-1.elb.amazonaws.com
Duration:    8m 41s  (player group: 6m 12s / admin group: 5m 04s)
===================================================================
Results:  8 PASS  |  2 FAIL  |  1 BLOCKED  |  0 SKIPPED

FAILURES:
  TBL-1161  Step 3 — Verify match status changes to DISPUTED
    Expected: DISPUTED status badge visible
    Actual:   Server error toast; status remained PENDING_CONFIRMATION
    Bug filed: TBL-1180

  TBL-1163  Step 2 — Click .btn-force-confirm
    Expected: Match row disappears, success toast shown
    Actual:   Match still visible in table after Force Confirm click
    Bug filed: TBL-1181

WARNINGS (console errors on passing tests): 2

Report:      output/results/RUN-20260512-001/run-report.json
Results:     output/results/RUN-20260512-001/results.json
Screenshots: output/screenshots/RUN-20260512-001/
===================================================================
Uploading results to Xray TBL-1171... (background)
```

---

## Phase 5 — Xray result upload (background sub-agent SA-4)

After printing the summary, spawn a background general-purpose sub-agent (`run_in_background: true`):

Give it `output/results/{RUN_ID}/results.json` and these instructions:
- Map each TC status: PASS → "PASSED", FAIL → "FAILED", BLOCKED → "BLOCKED", SKIPPED → "TODO"
- Use `mcp__xray__authenticate` to get a Bearer token
- For each TC, call the Xray GraphQL API to update the test run status in Test Execution TBL-1171
- The numeric Xray issue IDs for TBL-1155 TCs are in the assembled TestCase JSON
  (field `xrayIssueId` if added by SA-1, or fall back to the `id` field mapping)
- Print: "Xray TBL-1171 updated: X PASSED / Y FAILED / Z BLOCKED"

The main session is complete once the console summary prints — SA-4 completes in the background.

---

## Hard rules

- **Never accept or hardcode credentials** — always `os.environ["QA_USERNAME"]` etc.
- **Never skip the screenshot** — before AND after every step, no exceptions; use the Read tool to view after-screenshot
- **Never interpret or paraphrase step actions** — execute the `action` field word for word
- **Never combine steps** — one Playwright action per `execute_step()` call
- **`verify`/`check`/`assert`/`ensure` steps are assertion-only** — no Playwright interaction; vision assesses after-screenshot against `expected`
- **`wait`/`pause` must parse duration from `data` field** — never default to 2s when a number is specified; cap at 60s; use `wait_for_selector` when dialog appearance is expected
- **`page.on("dialog", ...)` must be set at browser launch** — the admin Void action uses `window.confirm()` and will silently fail without this handler
- **`preserveSession: true` TCs must never clear state** — the in-memory `MatchNotificationService.seenIds` Set must survive; a page reload resets it
- **Spawn SA-2a and SA-2b in a single message** — simultaneous execution is required
- **SA-3 bug reporters are fire-and-forget** — never block step execution; always `run_in_background: true`
- **Spawn SA-4 Xray upload after printing the summary** — also `run_in_background: true`
- **DOM snapshot is mandatory on every FAIL step**
- **Write `results.json` and `run-report.json` even on early abort** — set `"status": "EARLY_ABORT"`
- **Use `data-cy` selectors for the login form** — `[data-cy="login-username-input"]`, `[data-cy="login-password-input"]`, `[data-cy="login-submit-btn"]`
- **Use CSS class selectors for dialog buttons** — `.btn-accept`, `.btn-contest`, `.btn-decide-later`, `.btn-submit-contest`, `.btn-force-confirm`, `.btn-void` — these elements have no ARIA roles or data-testid
- **Never use positional XPath**
- **Use `domcontentloaded` — not `networkidle`** — Angular SPAs with polling intervals never reach networkidle
- **All bug reports go to `TBL` project** — not AMOB
