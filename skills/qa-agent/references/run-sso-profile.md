# run-sso-profile — Microsoft SSO Bypass

Loaded by run mode when SSO is detected on the target app. Handles Microsoft Entra ID
(Azure AD) login with MFA/TOTP so individual test cases never touch the auth flow.

---

## When to load this file

Load this reference when any of the following are true:
- The user passes `--sso` or `--sso-type microsoft` to the run command
- Navigating to the app URL redirects to `login.microsoftonline.com`
- The app profile captured during `run-app-profile.md` records `sso: microsoft`

Do NOT load this for apps with a standard username/password form on their own domain.

---

## How it works

Instead of repeating the full MFA flow for every test case, the script authenticates
**once**, saves the browser session to `output/auth/storage_state.json`, and every
subsequent TC context loads that file — zero auth overhead per TC.

```
run mode start
    │
    ├─ SSO detected?
    │       │
    │       └─ YES → run ms_sso_auth.py → output/auth/storage_state.json
    │                                             │
    │                                    all TCs load storage_state
    │
    └─ NO → standard login via app profile selectors
```

---

## Step 1 — Check environment variables

Before running, confirm these three env vars are set. If any are missing, stop and
tell the user exactly which ones are needed:

| Variable | Value |
|----------|-------|
| `TEST_EMAIL` | Microsoft account email for the test account |
| `TEST_PASSWORD` | Microsoft account password |
| `TEST_TOTP_SECRET` | Base32 TOTP secret (same as `otp.secret` in the Java config) |

---

## Step 2 — Run the SSO auth script

```bash
python skills/qa-agent/scripts/ms_sso_auth.py \
  --url <app_url> \
  --output output/auth/storage_state.json
```

- `--url` is the same URL passed to run mode via `--url`
- For debugging a failing auth flow, add `--headed` to watch the browser
- The script handles both MFA patterns automatically:
  - **Pattern A**: push-notification screen → "I can't use Microsoft Authenticator" → "Use a verification code"
  - **Pattern B**: direct method-choice screen → "Use a verification code"
- Retries TOTP entry up to 5 times (covers TOTP window boundary edge cases)
- Saves `output/auth/storage_state.json` on success

If the script exits with a non-zero code or raises `RuntimeError`, stop run mode and
report the auth failure to the user with the last printed URL and title.

---

## Step 3 — Wire storage state into every TC context

In `pw_runner.py`, replace bare `browser.new_context()` with:

```python
STORAGE_STATE = "output/auth/storage_state.json"

context = browser.new_context(
    storage_state=STORAGE_STATE if os.path.exists(STORAGE_STATE) else None
)
```

This applies to every test case in the session — the TOTP challenge never appears
during TC execution.

---

## Step 4 — Handle session expiry mid-run

Microsoft tokens typically survive 1–8 hours. For long runs (>100 TCs), check after
every 50 TCs whether the current page has drifted back to `login.microsoftonline.com`.
If it has, re-run the auth script before continuing:

```python
if "login.microsoftonline.com" in page.url:
    subprocess.run([
        "python", "skills/qa-agent/scripts/ms_sso_auth.py",
        "--url", APP_URL,
        "--output", STORAGE_STATE,
    ], check=True)
    context = browser.new_context(storage_state=STORAGE_STATE)
    page = context.new_page()
    page.goto(current_tc_url)
```

---

## Required dependencies

Both must be installed for the auth script to run:

```bash
pip install pyotp playwright
python -m playwright install chromium
```

`pyotp` is the Python equivalent of `com.warrenstrange:googleauth` used in the
Java/Selenium implementation — same RFC 6238 algorithm, same TOTP secret format.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Script times out at email field | App didn't redirect to Microsoft login | Confirm `--url` is the right app URL |
| OTP rejected 5 times | Wrong TOTP secret or clock drift | Verify `TEST_TOTP_SECRET` matches `otp.secret`; check system clock is NTP-synced |
| "TOTP method option not found" | Microsoft tenant uses different MFA method text | Run with `--headed`, observe the method-choice screen, add the text to `SEL_TOTP_OPTION` in the script |
| Session expires mid-run | Token TTL shorter than run duration | Reduce TC batch size or implement the mid-run re-auth check in Step 4 |
| `storage_state.json` not accepted | Context created before file was written | Ensure auth script completes before the first `new_context()` call |
