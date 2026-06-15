"""
Microsoft SSO authenticator for the qa-agent run mode.

Handles the full Microsoft Entra ID (Azure AD) login flow including MFA:
  - Email → password → push-notification bypass → TOTP entry → stay-signed-in dialog

Usage:
    python ms_sso_auth.py --url <app_url> --output output/auth/storage_state.json

Required environment variables:
    TEST_EMAIL        Microsoft account email
    TEST_PASSWORD     Microsoft account password
    TEST_TOTP_SECRET  Base32 TOTP secret for the test account (same value as otp.secret in Java config)

Output:
    storage_state.json at --output path — load this in every TC context:
        context = browser.new_context(storage_state="output/auth/storage_state.json")

Flow (translated from LoginPage.java / Selenium implementation):
    1. Navigate to app URL → Microsoft redirects to login.microsoftonline.com
    2. Fill email → Next
    3. Fill password → Sign in
    4. MFA screen — two patterns:
       Pattern A: push-notification screen (OTP field not immediately visible)
                  → click "I can't use Microsoft Authenticator" link
                  → click "Use a verification code" from method list
       Pattern B: direct method-choice screen (no push notification)
                  → click "Use a verification code" directly
    5. Generate TOTP via pyotp → fill OTP field → click Verify
       Retry up to 5 times on rejection (waits for next 30s TOTP window)
    6. Handle "Stay signed in?" dialog → click Yes
    7. Save browser context storage state to --output path
"""

import argparse
import os
import sys
import time

try:
    import pyotp
except ImportError:
    print("ERROR: pyotp not installed. Run: pip install pyotp")
    sys.exit(1)

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright && python -m playwright install chromium")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Selectors (ported from LoginPage.java)
# ---------------------------------------------------------------------------

SEL_EMAIL         = '//input[@type="email" and @name="loginfmt"]'
SEL_NEXT          = '//input[@type="submit" and @data-report-trigger="click"]'
SEL_PASSWORD      = '//input[@name="passwd" and @type="password"]'
SEL_SIGN_IN       = '//input[@type="submit" and @data-report-event="Signin_Submit"]'
SEL_OTP_FIELD     = '#idTxtBx_SAOTCC_OTC'
SEL_CANT_USE      = (
    '//a[contains(normalize-space(),"right now")] | '
    '//a[@id="idA_SAOTCS_SendCode"] | '
    '//a[contains(normalize-space(),"can\'t use")]'
)
SEL_TOTP_OPTION   = (
    '(//div | //a | //li | //button)'
    '[contains(normalize-space(),"verification code") or '
    ' contains(normalize-space(),"Enter a code")]'
    '[string-length(normalize-space()) < 80]'
)
SEL_VERIFY        = (
    '//input[@type="submit" and @data-report-event="Signin_Submit"] | '
    '//input[@type="submit" and contains(@value,"Verify")] | '
    '//button[contains(normalize-space(),"Verify") or contains(normalize-space(),"Sign in")]'
)
SEL_STAY_SIGNED   = '//input[@type="submit" and (@value="Yes" or @value="No")]'

# JS fallback for TOTP option click (mirrors JavascriptExecutor fallback in Java)
JS_CLICK_TOTP = """
var elems = Array.from(document.querySelectorAll('a,button,li,div[role],div[tabindex],span[tabindex]'));
var t = elems.find(function(e) {
    var txt = (e.textContent || '').trim();
    return txt === 'Use a verification code' ||
           (txt.indexOf('verification code') >= 0 && txt.length < 80);
});
if (t) { t.click(); return true; }
return false;
"""


# ---------------------------------------------------------------------------
# Auth flow
# ---------------------------------------------------------------------------

def debug_inputs(page, label):
    print(f"=== {label} ===")
    print(f"  URL: {page.url}")
    print(f"  Title: {page.title()}")
    inputs = page.query_selector_all("input")
    for el in inputs:
        try:
            print(f"  input id='{el.get_attribute('id')}' "
                  f"type='{el.get_attribute('type')}' "
                  f"name='{el.get_attribute('name')}'")
        except Exception:
            pass
    print(f"=== END {label} ===")


def debug_anchors(page):
    print("=== ANCHOR DEBUG ===")
    for el in page.query_selector_all("a, [role='button'], [tabindex='0']"):
        try:
            txt = (el.inner_text() or "").strip()
            if txt:
                print(f"  {el.evaluate('e => e.tagName')} text='{txt}'")
        except Exception:
            pass
    print("=== END ANCHOR DEBUG ===")


def handle_mfa(page, totp_secret):
    """Handle MFA — Pattern A (push bypass) or Pattern B (direct choice)."""

    # Check if OTP field is already visible (rare but possible)
    otp_visible = False
    try:
        page.wait_for_selector(SEL_OTP_FIELD, timeout=12_000)
        otp_visible = True
        print("OTP field visible directly.")
    except PWTimeout:
        print(f"OTP field not immediately visible — URL: {page.url}")
        debug_inputs(page, "MFA PAGE DEBUG")

    if not otp_visible:
        time.sleep(3)

        # Pattern A: push-notification screen — click "I can't use..." link first
        try:
            cant_use = page.wait_for_selector(SEL_CANT_USE, timeout=20_000)
            print(f"Clicking 'I can't use...' link: '{cant_use.inner_text().strip()}'")
            cant_use.click()
            time.sleep(2)
            page.wait_for_load_state("domcontentloaded")
        except PWTimeout:
            print("'I can't use...' link not found — trying direct TOTP option (Pattern B)...")

        # Pattern A + B: click "Use a verification code" from method list
        totp_clicked = False

        try:
            totp_option = page.wait_for_selector(SEL_TOTP_OPTION, timeout=15_000)
            txt = totp_option.inner_text().strip()
            print(f"Clicking TOTP method option: '{txt}'")
            try:
                totp_option.click()
            except Exception:
                page.evaluate("el => el.click()", totp_option)
            totp_clicked = True
            time.sleep(2)
            page.wait_for_load_state("domcontentloaded")
        except PWTimeout:
            print("XPath TOTP locator timed out — trying JS fallback...")
            debug_anchors(page)

        if not totp_clicked:
            clicked = page.evaluate(JS_CLICK_TOTP)
            if clicked:
                print("Clicked TOTP option via JS fallback.")
                totp_clicked = True
                time.sleep(2)
                page.wait_for_load_state("domcontentloaded")

        if not totp_clicked:
            print(f"WARNING: TOTP method option not found by any strategy. URL: {page.url}")
            handle_stay_signed_in(page)
            return

        try:
            page.wait_for_selector(SEL_OTP_FIELD, timeout=30_000)
            otp_visible = True
            print("OTP field visible after method selection.")
        except PWTimeout:
            print(f"WARNING: OTP field not visible after method selection. URL: {page.url}")
            handle_stay_signed_in(page)
            return

    # Enter TOTP — retry up to 5 times on rejection
    submitted = False
    retries = 0
    while not submitted and retries < 5:
        try:
            code = pyotp.TOTP(totp_secret).now()
            print(f"Entering OTP code (attempt {retries + 1}): {code}")

            otp_input = page.wait_for_selector(SEL_OTP_FIELD, timeout=10_000)
            otp_input.fill("")
            otp_input.fill(str(code))

            verify_btn = page.wait_for_selector(SEL_VERIFY, timeout=10_000)
            verify_btn.click()

            # OTP accepted when the field disappears
            try:
                page.wait_for_selector(SEL_OTP_FIELD, state="hidden", timeout=6_000)
                submitted = True
                print("OTP accepted.")
            except PWTimeout:
                retries += 1
                print(f"OTP rejected — attempt {retries}. Waiting for next TOTP window...")
                time.sleep(2)
        except Exception as ex:
            retries += 1
            print(f"OTP attempt {retries} failed: {ex}")
            time.sleep(1)

    if not submitted:
        raise RuntimeError(f"OTP validation failed after {retries} attempts")

    print("OTP submitted successfully.")
    handle_stay_signed_in(page)


def handle_stay_signed_in(page):
    """Dismiss 'Stay signed in?' dialog if it appears."""
    try:
        btn = page.wait_for_selector(SEL_STAY_SIGNED, timeout=8_000)
        print("'Stay signed in?' dialog detected — clicking Yes")
        btn.click()
        time.sleep(2)
    except PWTimeout:
        print("No 'Stay signed in?' dialog — continuing.")


def authenticate(app_url, output_path, headless=True):
    email    = os.environ.get("TEST_EMAIL")
    password = os.environ.get("TEST_PASSWORD")
    secret   = os.environ.get("TEST_TOTP_SECRET")

    missing = [k for k, v in [
        ("TEST_EMAIL", email), ("TEST_PASSWORD", password), ("TEST_TOTP_SECRET", secret)
    ] if not v]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        # 1. Navigate → triggers Microsoft redirect
        print(f"Navigating to {app_url} ...")
        page.goto(app_url, wait_until="domcontentloaded")

        # 2. Email
        print("Filling email...")
        page.wait_for_selector(SEL_EMAIL, timeout=25_000)
        page.fill(SEL_EMAIL, email)
        page.click(SEL_NEXT)

        # 3. Password
        print("Filling password...")
        page.wait_for_selector(SEL_PASSWORD, timeout=30_000)
        page.fill(SEL_PASSWORD, password)
        page.click(SEL_SIGN_IN)

        # 4–6. MFA
        print("Handling MFA...")
        handle_mfa(page, secret)
        print("MFA complete — waiting for dashboard...")

        # 7. Confirm we landed on the app
        try:
            page.wait_for_function(
                """() => {
                    const urlOk = window.location.href.includes('/dashboard');
                    const greetingOk = !!document.querySelector('header h1');
                    return urlOk || greetingOk;
                }""",
                timeout=70_000,
            )
            print(f"Login successful. URL: {page.url}")
        except PWTimeout:
            print(f"WARNING: Dashboard not detected — URL: {page.url} | Title: {page.title()}")

        # 8. Save storage state
        context.storage_state(path=output_path)
        print(f"Storage state saved to: {output_path}")

        browser.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Microsoft SSO authenticator for qa-agent run mode")
    parser.add_argument("--url",      required=True,  help="App URL (triggers Microsoft redirect)")
    parser.add_argument("--output",   required=True,  help="Path for storage_state.json output")
    parser.add_argument("--headless", action="store_true", default=True,
                        help="Run browser headlessly (default: True)")
    parser.add_argument("--headed",   action="store_true",
                        help="Run browser in headed mode (useful for debugging)")
    args = parser.parse_args()

    headless = not args.headed
    authenticate(args.url, args.output, headless=headless)
