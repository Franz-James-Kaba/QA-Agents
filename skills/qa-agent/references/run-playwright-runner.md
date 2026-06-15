# Playwright Runner (Universal)

The runner skeleton is universal — same code works for any web app. App-specific selectors and conventions come from the optional **app profile** (see `run-app-profile.md`). Without a profile, the runner uses Playwright's accessibility-first locators and falls back to vision-driven selection.

## The runner script

The runner is a single Python module that the execution subagent writes to `output/results/<RUN_ID>/pw_runner.py` and imports. The full module is below. Copy it verbatim into your run directory.

### Core helpers — universal

```python
"""
Playwright runner for a single execution run.
Universal — no app-specific selectors. App quirks come from the profile, if any.
"""
import os, json, time, re
from playwright.sync_api import sync_playwright, Page

def launch_browser(run_id, base_url, headed=False, group_label="", storage_state=None):
    """
    Launch Chromium and return (playwright, browser, context, page).

    If `storage_state` is a path to a Playwright storage-state JSON (produced by
    an SSO pre-auth step, e.g. scripts/ms_sso_auth.py), it is loaded into the
    context so the session is already authenticated — the runner then skips login
    entirely. See references/run-sso-profile.md.
    """
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=not headed, slow_mo=80)
    ctx_opts = {"viewport": {"width": 1280, "height": 800}}
    if storage_state and os.path.exists(storage_state):
        ctx_opts["storage_state"] = storage_state
        if group_label:
            print(f"[{group_label}] Loaded SSO storage state from {storage_state}")
    context = browser.new_context(**ctx_opts)
    page = context.new_page()

    # Always accept native dialogs — many apps use window.confirm() and they
    # silently fail otherwise.
    page.on("dialog", lambda d: d.accept())

    # Collect JS console errors throughout the run.
    page._console_errors = []
    page.on("console", lambda msg: page._console_errors.append(msg.text)
            if msg.type == "error" else None)

    if group_label:
        print(f"[{group_label}] Browser launched against {base_url}")
    return pw, browser, context, page


def clear_session(page):
    """Wipe localStorage, sessionStorage, and cookies."""
    page.evaluate("""() => {
        try { localStorage.clear(); } catch(e) {}
        try { sessionStorage.clear(); } catch(e) {}
        document.cookie.split(';').forEach(c => {
            const name = c.split('=')[0].trim();
            document.cookie = name + '=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/';
        });
    }""")


def wait_stable(page, timeout_ms=8000):
    """
    SPA-safe wait. Uses domcontentloaded — NOT networkidle.
    Many SPAs poll (notifications, websockets, analytics) and never reach
    networkidle, causing wait_for_load_state('networkidle') to time out.
    """
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        pass  # non-fatal — proceed and let vision assess from the screenshot


def take_screenshot(page, path):
    """Full-page screenshot."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    page.screenshot(path=path, full_page=True)


def capture_dom(page, path):
    """Save the current DOM."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(page.content())
```

### Step execution — verb dispatch

Each step's `action` field starts with a verb. The runner dispatches on the verb and uses Playwright's **accessibility-first** locators (`get_by_role`, `get_by_label`, `get_by_text`) for resolution. This works without app knowledge because most modern apps expose ARIA roles, labels, and visible text.

```python
def execute_step(page, step, tc_id, step_n, screenshot_dir, dom_dir, base_url,
                 app_profile=None):
    """
    Execute one step. Returns the step result dict.
    The runner has no app-specific knowledge — it dispatches on verb and uses
    accessibility locators. If selection fails, the caller falls back to
    vision-driven selection.
    """
    action   = step["action"]
    data     = (step.get("data") or "-").strip()
    expected = step.get("expected", "")
    verb     = action.split()[0].lower() if action.split() else ""

    before_path = os.path.join(screenshot_dir, f"{tc_id}-step{step_n:02d}-before.png")
    after_base  = os.path.join(screenshot_dir, f"{tc_id}-step{step_n:02d}")
    error_msg   = None

    take_screenshot(page, before_path)
    console_before = len(getattr(page, "_console_errors", []))

    try:
        if verb in ("navigate", "open", "go"):
            target = data if data not in ("-", "N/A") else base_url
            if not target.startswith("http"):
                target = base_url.rstrip("/") + "/" + target.lstrip("/")
            page.goto(target)
            wait_stable(page)

        elif verb in ("tap", "click", "press"):
            click_element(page, action, app_profile)
            wait_stable(page)

        elif verb in ("fill", "enter", "type", "input"):
            fill_element(page, action, "" if data in ("-", "N/A") else data, app_profile)

        elif verb == "select":
            m = re.search(r"['\"]([^'\"]+)['\"]", action)
            label = m.group(1) if m else action
            page.get_by_label(label, exact=False).select_option(data)

        elif verb in ("scroll", "swipe"):
            page.evaluate("window.scrollBy(0, 400)")
            wait_stable(page)

        elif verb == "upload":
            m = re.search(r"['\"]([^'\"]+)['\"]", action)
            label = m.group(1) if m else "file"
            page.get_by_label(label, exact=False).set_input_files(data)

        elif verb in ("wait", "pause"):
            dur_match = re.search(r"(\d+(?:\.\d+)?)", data) or re.search(r"(\d+)", action)
            duration_s = min(float(dur_match.group(1)) if dur_match else 2.0, 60.0)
            time.sleep(duration_s)

        elif verb in ("verify", "check", "assert", "confirm", "ensure"):
            # Assertion only — no interaction. Vision assesses from the after-screenshot.
            wait_stable(page, 5000)

        elif verb in ("log", "login", "authenticate", "sign"):
            # Re-auth mid-run. Delegated to app_profile if it has a `login` recipe.
            do_login(page, action, base_url, app_profile)

        else:
            # Unknown verb — best-effort click on whatever the action mentions.
            click_element(page, action, app_profile)
            wait_stable(page)

    except Exception as e:
        error_msg = str(e)

    suffix = "-fail.png" if error_msg else "-pass.png"
    after_path = after_base + suffix
    take_screenshot(page, after_path)

    new_errors = getattr(page, "_console_errors", [])[console_before:]
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

### Click and fill — accessibility-first with profile-aware overrides

```python
def click_element(page, action, app_profile=None):
    """
    Find and click the element described in `action`.
    Priority:
      1. app_profile["selectors"][key] if action matches a profile selector key
      2. data-testid / data-cy if explicitly named in action ("testid:foo")
      3. Quoted text → getByText
      4. get_by_role("button"/"link", name=...)
      5. Longest meaningful word → getByText
    """
    # 1. Profile override
    if app_profile:
        sel = match_profile_selector(action, app_profile, kind="click")
        if sel:
            page.locator(sel).first.click()
            return

    # 2. Explicit testid / data-cy in action
    m = re.search(r"(?:testid|data-testid|data-cy|cy)[:\s=]+['\"]?([a-z0-9_-]+)['\"]?",
                  action, re.I)
    if m:
        attr = "data-testid" if "testid" in action.lower() else "data-cy"
        page.locator(f"[{attr}='{m.group(1)}']").first.click()
        return

    # 3. Quoted text → getByText
    m = re.search(r"['\"]([^'\"]+)['\"]", action)
    if m:
        page.get_by_text(m.group(1), exact=False).first.click()
        return

    # 4. Named button / link → get_by_role
    for role in ("button", "link", "tab", "menuitem"):
        m = re.search(
            rf"(?:tap|click|press)\s+(?:the\s+)?['\"]?([A-Za-z][A-Za-z0-9 ✓←→]{{1,40}}?)['\"]?\s+{role}",
            action, re.I,
        )
        if m:
            page.get_by_role(role,
                             name=re.compile(re.escape(m.group(1).strip()), re.I)).first.click()
            return

    # 5. Fallback: longest meaningful word
    stop = {"click", "tap", "press", "button", "the", "and", "from", "into",
            "on", "at", "link", "item", "with", "for"}
    words = [w for w in re.findall(r"[A-Za-z]{4,}", action) if w.lower() not in stop]
    if words:
        page.get_by_text(words[0], exact=False).first.click()
        return

    raise RuntimeError(f"Cannot resolve click target from action: {action!r}")


def fill_element(page, action, data, app_profile=None):
    """Fill a form field described in `action` with `data`."""
    # 1. Profile override
    if app_profile:
        sel = match_profile_selector(action, app_profile, kind="fill")
        if sel:
            page.locator(sel).fill(data)
            return

    # 2. Explicit testid / data-cy
    m = re.search(r"(?:testid|data-testid|data-cy|cy)[:\s=]+['\"]?([a-z0-9_-]+)['\"]?",
                  action, re.I)
    if m:
        attr = "data-testid" if "testid" in action.lower() else "data-cy"
        page.locator(f"[{attr}='{m.group(1)}']").fill(data)
        return

    # 3. Common field names by label
    for field in ("username", "email", "password", "phone", "name", "search"):
        if re.search(rf"\b{field}\b", action, re.I):
            page.get_by_label(re.compile(field, re.I)).fill(data)
            return

    # 4. Named field in action → get_by_label
    m = re.search(
        r"(?:fill|enter|type|input)\s+(?:the\s+)?['\"]?([A-Za-z][A-Za-z ]{1,40}?)['\"]?\s+"
        r"(?:field|input|box|area|textarea)",
        action, re.I,
    )
    if m:
        page.get_by_label(m.group(1), exact=False).fill(data)
        return

    # 5. Placeholder text fallback
    m = re.search(r"['\"]([^'\"]{3,40})['\"]", action)
    if m:
        page.get_by_placeholder(m.group(1), exact=False).fill(data)
        return

    raise RuntimeError(f"Cannot resolve fill target from action: {action!r}")


def match_profile_selector(action, app_profile, kind):
    """
    If the action matches a known profile selector keyword, return the CSS selector.
    The profile's `selectors` section is a list of {keywords, selector, kind}.
    """
    for entry in app_profile.get("selectors", []):
        if entry.get("kind", "any") not in (kind, "any"):
            continue
        for kw in entry["keywords"]:
            if re.search(rf"\b{re.escape(kw)}\b", action, re.I):
                return entry["selector"]
    return None


def sso_session_active(page, base_url):
    """
    True if the context already holds an authenticated SSO session — i.e. visiting
    the app does NOT bounce to an identity provider. Used to skip do_login when a
    storage_state was loaded (see references/run-sso-profile.md).
    """
    try:
        page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
        wait_stable(page)
        idp_hosts = ("login.microsoftonline.com", "login.live.com",
                     "sts.", "okta.com", "auth0.com", "accounts.google.com")
        return not any(h in page.url for h in idp_hosts)
    except Exception:
        return False


def do_login(page, action, base_url, app_profile=None, storage_state=None):
    """
    Re-authenticate mid-run. Uses the profile's `login` recipe if provided;
    otherwise tries common form patterns.

    If `storage_state` is set and the session is already active, this is a no-op
    (the SSO pre-auth step already established the session). If the SSO session
    has expired mid-run, re-run the SSO auth script and reload the page.
    """
    # Mid-run login verbs reach here without the param — fall back to the env var
    # the run-mode SSO phase exports.
    storage_state = storage_state or os.environ.get("SSO_STORAGE_STATE", "")
    if storage_state:
        if sso_session_active(page, base_url):
            return  # already authenticated via the loaded storage_state
        # Session expired — re-run the SSO auth script and reload context state.
        import subprocess, sys
        sso_script = os.environ.get("SSO_AUTH_SCRIPT", "")
        if sso_script and os.path.exists(sso_script):
            subprocess.run([sys.executable, sso_script,
                            "--url", base_url, "--output", storage_state], check=False)
            page.goto(base_url, wait_until="domcontentloaded")
            wait_stable(page)
        return

    is_admin = bool(re.search(r"admin", action, re.I))
    if app_profile and "login" in app_profile:
        role_key = "admin" if is_admin else "default"
        recipe = app_profile["login"].get(role_key) or app_profile["login"].get("default")
        if recipe:
            page.goto(base_url.rstrip("/") + recipe["url"])
            wait_stable(page, 10000)
            for fld in recipe["fields"]:
                page.locator(fld["selector"]).fill(os.environ.get(fld["env"], ""))
            page.locator(recipe["submit"]).click()
            try:
                page.wait_for_url(re.compile(recipe.get("success_pattern", r"(?!.*/login)")),
                                  timeout=15000)
            except Exception:
                pass
            wait_stable(page)
            return

    # Fallback: generic login form
    role_prefix = "ADMIN" if is_admin else "PLAYER"
    user = os.environ.get(f"{role_prefix}_USERNAME", os.environ.get("QA_USERNAME", ""))
    pwd  = os.environ.get(f"{role_prefix}_PASSWORD", os.environ.get("QA_PASSWORD", ""))
    page.goto(base_url.rstrip("/") + "/login")
    wait_stable(page, 10000)
    try:
        page.get_by_label(re.compile(r"username|email", re.I)).fill(user)
        page.get_by_label(re.compile(r"password", re.I)).fill(pwd)
        page.get_by_role("button", name=re.compile(r"login|sign in|submit", re.I)).click()
    except Exception:
        pass
    try:
        page.wait_for_url(re.compile(r"(?!.*/login)"), timeout=15000)
    except Exception:
        pass
    wait_stable(page)
```

## Pass/fail assessment — vision

After each step, the execution subagent:

1. Reads the after-screenshot using the `Read` tool (image support).
2. Compares the visible UI against `step["expected"]`.
3. Marks the step PASS if the expected outcome is observable; FAIL if not.

This is **how the runner is universal** — no need to hardcode mappings like `"COMPLETED" → green badge`. Claude looks at the screenshot and judges.

For **negative assertions** ("does NOT appear", "should be absent"): PASS = the element is absent in the after-screenshot; FAIL = it's present.

If the screenshot is ambiguous, the subagent can also call `page.inner_text("body")[:2000]` to get supplementary text context, or read the DOM snapshot for failed steps.

## Subagent — execution per role

When run-mode Phase R6 spawns one subagent per role, each subagent uses this template:

```
You are executing one role's test cases for a manual-test run.
All data is provided below. Do NOT ask any questions. Execute every TC and write the result file.

## Required reading (do this first)
Read these files for the runner skeleton and (if provided) the app profile:
- <ABSOLUTE_PATH_TO_SKILL>/references/run-playwright-runner.md
- <APP_PROFILE_PATH or "none">

## Access
- Playwright is installed.
- Your role: <ROLE>
- Username env var: <ROLE_USERNAME_ENV>
- Password env var: <ROLE_PASSWORD_ENV>
- Base URL: <BASE_URL>
- Run ID: <RUN_ID>
- SSO storage state: <STORAGE_STATE_PATH or "none">   ← if set, the session is pre-authenticated
- Output paths:
    screenshots: output/screenshots/<RUN_ID>/
    results:     output/results/<RUN_ID>/results-<ROLE>.json
    dom dumps:   output/results/<RUN_ID>/dom/

## Test cases to execute
<JSON ARRAY of TestCase objects for this role>

## Procedure
1. Write the runner module to output/results/<RUN_ID>/pw_runner.py using the code in
   run-playwright-runner.md (the Core helpers + Step execution sections, verbatim).
2. Import it: pw, browser, ctx, page = launch_browser(<RUN_ID>, <BASE_URL>, headed=<HEADED>, group_label="<ROLE>", storage_state=<STORAGE_STATE_PATH or None>)
3. Authenticate via do_login(page, "login as <ROLE>", <BASE_URL>, app_profile, storage_state=<STORAGE_STATE_PATH or None>).
   - If SSO storage state is set, do_login is a no-op (session already established) — DO NOT clear cookies before the first TC.
4. For each TC:
   a. Unless preserveSession=True OR SSO storage state is set, clear_session(page) and re-auth.
      With SSO storage state, NEVER clear_session — it would destroy the SSO cookies. Re-auth is handled
      automatically by do_login only if the session expired.
   b. Apply preconditions (navigate to a start page if specified).
   c. For each step: call execute_step(...). Use the Read tool on the after-screenshot
      to assess pass/fail against step["expected"]. Capture body text and DOM on FAIL.
      If the screenshot is genuinely ambiguous (you cannot confidently call PASS or FAIL),
      set the step status to "REVIEW" and add "needs_orchestrator_review": true with a
      short "review_reason" — do NOT guess. The orchestrator re-assesses these on a power model.
   d. If a critical step fails (login failed, no state change after the action, essential
      navigation didn't occur), mark remaining steps in this TC as BLOCKED and end the TC.
   e. Record the step result.
5. After all TCs: close the browser; write results-<ROLE>.json.

## Return format
ROLE: <role>
EXECUTED: <N>
PASSED: <N>
FAILED: <N>
BLOCKED: <N>
SKIPPED: <N>
RESULTS_FILE: output/results/<RUN_ID>/results-<ROLE>.json
ERROR: none
```

## Why this is universal

The original team-specific runner had ~200 lines of regex matching app-specific selectors (`.btn-accept`, `.contest-textarea`, `.notif-overlay`) and ~150 lines of app-specific helpers (`cleanup_all_pending`, `verify_match_status_via_api`, `provision_test_players`). Those didn't generalize.

This version replaces them with:

- **Accessibility-first locators** — `get_by_role`, `get_by_label`, `get_by_text` work for any app that has decent ARIA labels (which is nearly all modern web apps).
- **An optional profile** for apps that need specific selectors — see `run-app-profile.md`.
- **Vision assessment** for pass/fail — Claude reads the screenshot and decides, without needing a hardcoded "status badge means COMPLETED" table.

If your team needs the old behaviour, port your selectors into a profile and pass `--profile`. The runner stays generic.
