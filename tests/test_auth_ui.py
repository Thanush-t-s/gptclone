"""
Frontend UI End-to-End Automation Test Suite (Playwright)
Validates visual rendering, form interactions, client validation,
password toggles, modal dialogs, and end-to-end login flows.
"""

import sys
import types
import pytest
from playwright.sync_api import sync_playwright

# Windows xxhash shim if needed
if "xxhash" not in sys.modules:
    try:
        import xxhash
    except (ImportError, OSError):
        xxhash_mock = types.ModuleType("xxhash")
        xxhash_mock._xxhash = types.ModuleType("xxhash._xxhash")
        sys.modules["xxhash"] = xxhash_mock
        sys.modules["xxhash._xxhash"] = xxhash_mock._xxhash

from app import app
from extensions import db
from models import User

BASE_URL = "http://127.0.0.1:5000"


def get_browser(p):
    """Launch available Chromium channel (Chrome, Edge, or default)."""
    for ch in ["chrome", "msedge", None]:
        try:
            if ch:
                return p.chromium.launch(channel=ch, headless=True)
            return p.chromium.launch(headless=True)
        except Exception:
            continue
    raise RuntimeError("No compatible Chromium/Edge/Chrome browser found.")


@pytest.fixture(scope="module")
def setup_ui_test_user():
    """Seed test user for E2E tests."""
    with app.app_context():
        # Clean previous
        existing = User.query.filter_by(email="qa_ui_tester@example.com").first()
        if existing:
            db.session.delete(existing)
        db.session.commit()

        user = User(
            username="qa_ui_tester",
            email="qa_ui_tester@example.com",
            full_name="QA UI Automation"
        )
        user.set_password("CorrectPassword2026!")
        db.session.add(user)
        db.session.commit()

    yield "qa_ui_tester@example.com", "CorrectPassword2026!"

    with app.app_context():
        existing = User.query.filter_by(email="qa_ui_tester@example.com").first()
        if existing:
            db.session.delete(existing)
        db.session.commit()


# -----------------------------------------------------------------------------
# 1. UI Form Rendering & Element Accessibility
# -----------------------------------------------------------------------------
def test_ui_form_rendering():
    """Verify all visual components, inputs, buttons, and logos render properly."""
    with sync_playwright() as p:
        browser = get_browser(p)
        page = browser.new_page()
        page.goto(f"{BASE_URL}/login")

        # Verify page title
        assert "Aura Hub" in page.title()

        # Verify left hero branding and text
        assert page.locator('img[src="/static/images/logo-white.svg"]').is_visible()
        hero_heading = page.locator("text=Get access your personal hub for clarity and productivity")
        assert hero_heading.is_visible()

        # Verify right panel branding and controls
        assert page.locator('img[src="/static/images/logo-color.svg"]').is_visible()
        assert page.locator("#emailInput").is_visible()
        assert page.locator("#emailInput").get_attribute("placeholder") == "farazhaidet786@gmail.com"
        assert page.locator("#passwordInput").is_visible()
        assert page.locator("#passwordInput").get_attribute("placeholder") == "••••••••••••"
        assert page.locator("#submitBtn").is_visible()
        assert page.locator("#rememberMeInput").is_visible()
        assert page.locator("#forgotPasswordLink").is_visible()

        # Verify 3 social buttons
        assert page.locator("#googleLoginBtn").is_visible()
        assert page.locator('button[title*="Behance"]').is_visible()
        assert page.locator('button[title*="Facebook"]').is_visible()

        browser.close()


# -----------------------------------------------------------------------------
# 2. Password Visibility Toggle
# -----------------------------------------------------------------------------
def test_ui_password_toggle():
    """Verify clicking eye icon toggles password visibility between password and text."""
    with sync_playwright() as p:
        browser = get_browser(p)
        page = browser.new_page()
        page.goto(f"{BASE_URL}/login")

        pwd_input = page.locator("#passwordInput")
        toggle_btn = page.locator("#togglePasswordBtn")

        # Initially type='password'
        assert pwd_input.get_attribute("type") == "password"
        pwd_input.fill("SuperSecret999!")

        # Toggle to visible
        toggle_btn.click()
        assert pwd_input.get_attribute("type") == "text"

        # Toggle back to hidden
        toggle_btn.click()
        assert pwd_input.get_attribute("type") == "password"

        browser.close()


# -----------------------------------------------------------------------------
# 3. Client Validation on Blank / Empty Input
# -----------------------------------------------------------------------------
def test_ui_validation_empty_inputs():
    """Submitting empty fields triggers client alert without crashing or redirecting."""
    with sync_playwright() as p:
        browser = get_browser(p)
        page = browser.new_page()
        page.goto(f"{BASE_URL}/login")

        # Clear inputs and submit
        page.locator("#emailInput").fill("")
        page.locator("#passwordInput").fill("")
        page.locator("#submitBtn").click()

        # Verify client error alert appears
        alert = page.locator("#dynamicAlert")
        page.wait_for_selector("#dynamicAlert:not(.hidden)", timeout=3000)
        assert "Please enter your email or username" in alert.text_content()

        # Fill email only and submit
        page.locator("#emailInput").fill("qa_tester@example.com")
        page.locator("#passwordInput").fill("")
        page.locator("#submitBtn").click()

        page.wait_for_selector("#dynamicAlert:not(.hidden)", timeout=3000)
        assert "Please enter your password" in alert.text_content()

        # Ensure page stayed on /login
        assert "/login" in page.url

        browser.close()


# -----------------------------------------------------------------------------
# 4. Bad Credentials (Negative Test)
# -----------------------------------------------------------------------------
def test_ui_bad_credentials(setup_ui_test_user):
    """Submitting wrong password shows error message, shake animation, and remains on login."""
    email, _ = setup_ui_test_user
    with sync_playwright() as p:
        browser = get_browser(p)
        page = browser.new_page()
        page.goto(f"{BASE_URL}/login")

        page.locator("#emailInput").fill(email)
        page.locator("#passwordInput").fill("CompletelyWrongPassword999!")
        page.locator("#submitBtn").click()

        # Wait for error alert
        page.wait_for_selector("#dynamicAlert:not(.hidden)", timeout=4000)
        alert_text = page.locator("#dynamicAlert").text_content()
        assert "Incorrect password" in alert_text or "remaining before temporary lock" in alert_text

        # Verify page URL remained on /login
        assert "/login" in page.url

        browser.close()


# -----------------------------------------------------------------------------
# 5. Mode Switching & Password Strength Meter
# -----------------------------------------------------------------------------
def test_ui_mode_switch_and_strength_meter():
    """Switching between Sign In and Sign Up dynamically reveals fields & strength meter."""
    with sync_playwright() as p:
        browser = get_browser(p)
        page = browser.new_page()
        page.goto(f"{BASE_URL}/login")

        # Click Sign Up tab
        page.locator("#tabSignupBtn").click()

        # Check title updated
        assert page.locator("#formTitle").text_content() == "Create an account"
        assert page.locator("#submitBtnText").text_content() == "Get Started"
        assert page.locator("#fullNameGroup").is_visible()
        assert page.locator("#confirmPasswordGroup").is_visible()
        assert page.locator("#strengthContainer").is_visible()

        # Type password and verify strength meter
        page.locator("#passwordInput").fill("abc")
        assert page.locator("#strengthLabel").text_content() in ["Weak", "Too short"]

        page.locator("#passwordInput").fill("ComplexPass2026!#")
        page.wait_for_function("document.getElementById('strengthLabel').textContent === 'Strong'")
        assert page.locator("#strengthLabel").text_content() == "Strong"

        # Switch back to Sign In
        page.locator("#tabLoginBtn").click()
        assert page.locator("#formTitle").text_content() == "Welcome back"
        assert page.locator("#submitBtnText").text_content() == "Sign In"
        assert not page.locator("#fullNameGroup").is_visible()

        browser.close()


# -----------------------------------------------------------------------------
# 6. Google Identity Modal Interaction
# -----------------------------------------------------------------------------
def test_ui_google_modal_interaction():
    """Clicking Google button opens Google Identity dialog; close button dismisses it."""
    with sync_playwright() as p:
        browser = get_browser(p)
        page = browser.new_page()
        page.goto(f"{BASE_URL}/login")

        # Open Google modal
        page.locator("#googleLoginBtn").click()
        modal = page.locator("#googleModal")
        page.wait_for_selector("#googleModal:not(.hidden)", timeout=2000)
        assert modal.is_visible()
        assert "Sign in with Google" in modal.text_content()

        # Close via Escape key
        page.keyboard.press("Escape")
        page.wait_for_selector("#googleModal", state="hidden", timeout=2000)
        assert not modal.is_visible()

        browser.close()


# -----------------------------------------------------------------------------
# 7. Successful Login (Happy Path)
# -----------------------------------------------------------------------------
def test_ui_successful_login_happy_path(setup_ui_test_user):
    """Submitting valid credentials authenticates user and redirects away from /login to /chat."""
    email, password = setup_ui_test_user
    with sync_playwright() as p:
        browser = get_browser(p)
        context = browser.new_context()
        page = context.new_page()
        page.goto(f"{BASE_URL}/login")

        page.locator("#emailInput").fill(email)
        page.locator("#passwordInput").fill(password)
        page.locator("#submitBtn").click()

        # Wait for redirect to /chat
        page.wait_for_url("**/chat", timeout=6000)
        assert "/chat" in page.url

        # Verify session cookies exist in context
        cookies = context.cookies()
        cookie_names = [c["name"] for c in cookies]
        assert "session" in cookie_names

        browser.close()


# -----------------------------------------------------------------------------
# 8. Google One-Click Login (Happy Path)
# -----------------------------------------------------------------------------
def test_ui_google_login_happy_path():
    """One-click Google sign-in from modal logs in and redirects to /chat."""
    with sync_playwright() as p:
        browser = get_browser(p)
        context = browser.new_context()
        page = context.new_page()
        page.goto(f"{BASE_URL}/login")

        # Open Google modal
        page.locator("#googleLoginBtn").click()
        page.wait_for_selector("#googleModal:not(.hidden)", timeout=2000)

        # Select first detected account (Thanush)
        account_btn = page.locator('#googleModal button:has-text("Thanush")')
        account_btn.click()

        # Wait for redirect to /chat
        page.wait_for_url("**/chat", timeout=6000)
        assert "/chat" in page.url

        browser.close()
