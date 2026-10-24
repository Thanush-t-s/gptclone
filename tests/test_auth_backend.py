"""
Backend Authentication Flow & API Integration Tests
Tests Flask endpoints, session management, password hashing, and edge cases.
"""

import sys
import types
import pytest

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


@pytest.fixture(scope="module")
def test_client():
    """Create Flask test client and seed test data."""
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()

    with app.app_context():
        # Cleanup any previous QA users
        for email in ["qa_backend_user@example.com", "qa_new_reg@example.com", "qa_google@gmail.com"]:
            existing = User.query.filter_by(email=email).first()
            if existing:
                db.session.delete(existing)
        db.session.commit()

        # Seed primary QA test user
        qa_user = User(
            username="qa_backend_user",
            email="qa_backend_user@example.com",
            full_name="QA Backend Engineer"
        )
        qa_user.set_password("QAPassword2026!")
        db.session.add(qa_user)
        db.session.commit()

    yield client

    with app.app_context():
        # Teardown test data
        for email in ["qa_backend_user@example.com", "qa_new_reg@example.com", "qa_google@gmail.com"]:
            existing = User.query.filter_by(email=email).first()
            if existing:
                db.session.delete(existing)
        db.session.commit()


# -----------------------------------------------------------------------------
# 1. Form & Route Availability
# -----------------------------------------------------------------------------
def test_backend_login_route_accessible(test_client):
    """Verify /login GET returns HTTP 200 with HTML form."""
    res = test_client.get("/login")
    assert res.status_code == 200
    assert b"Aura" in res.data
    assert b"logo-color.svg" in res.data
    assert b"logo-white.svg" in res.data


# -----------------------------------------------------------------------------
# 2. Empty Input Validation
# -----------------------------------------------------------------------------
def test_backend_login_empty_identifier(test_client):
    """Submitting missing or empty email/username returns 400 Bad Request."""
    res = test_client.post("/login", json={"identifier": "", "password": "SomePassword123!"})
    data = res.get_json()
    assert res.status_code == 400
    assert data["success"] is False
    assert data["code"] == "EMPTY_FIELDS"


def test_backend_login_empty_password(test_client):
    """Submitting empty password returns 400 Bad Request."""
    res = test_client.post("/login", json={"identifier": "qa_backend_user@example.com", "password": ""})
    data = res.get_json()
    assert res.status_code == 400
    assert data["success"] is False
    assert data["code"] == "EMPTY_FIELDS"


# -----------------------------------------------------------------------------
# 3. Email Format Validation
# -----------------------------------------------------------------------------
def test_backend_login_malformed_email(test_client):
    """Submitting an identifier with @ that fails RFC regex returns 400."""
    res = test_client.post("/login", json={"identifier": "malformed_email@", "password": "SomePassword123!"})
    data = res.get_json()
    assert res.status_code == 400
    assert data["code"] == "INVALID_EMAIL"


# -----------------------------------------------------------------------------
# 4. Bad Credentials & Negative Testing
# -----------------------------------------------------------------------------
def test_backend_login_nonexistent_user(test_client):
    """Submitting an unregistered user returns 404 with registration suggestion."""
    res = test_client.post("/login", json={"identifier": "nonexistent_qa_user_999@example.com", "password": "AnyPassword123!"})
    data = res.get_json()
    assert res.status_code == 404
    assert data["code"] == "USER_NOT_FOUND"
    assert data["suggestion"] == "register"


def test_backend_login_invalid_password(test_client):
    """Submitting invalid password returns 401 with remaining attempt counter."""
    res = test_client.post("/login", json={"identifier": "qa_backend_user@example.com", "password": "WrongPassword999!"})
    data = res.get_json()
    assert res.status_code == 401
    assert data["code"] == "INVALID_PASSWORD"
    assert data["attempts_left"] < 5


def test_backend_brute_force_lockout(test_client):
    """5 consecutive bad attempts trigger account lockout and HTTP 429."""
    with app.app_context():
        u = User.query.filter_by(email="qa_backend_user@example.com").first()
        u.reset_failed_attempts()
        db.session.commit()

    # Trigger 5 consecutive failed attempts
    for _ in range(4):
        test_client.post("/login", json={"identifier": "qa_backend_user@example.com", "password": "WrongPassword!"})

    res = test_client.post("/login", json={"identifier": "qa_backend_user@example.com", "password": "WrongPassword!"})
    data = res.get_json()
    assert res.status_code == 429
    assert data["code"] == "ACCOUNT_LOCKED"
    assert data["retry_after"] > 0

    # Reset lockout for following tests
    with app.app_context():
        u = User.query.filter_by(email="qa_backend_user@example.com").first()
        u.reset_failed_attempts()
        db.session.commit()


# -----------------------------------------------------------------------------
# 5. Happy Path Login
# -----------------------------------------------------------------------------
def test_backend_login_success_via_email(test_client):
    """Logging in with valid email + password succeeds and sets session."""
    res = test_client.post("/login", json={
        "identifier": "qa_backend_user@example.com",
        "password": "QAPassword2026!",
        "remember_me": True
    })
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["redirect"] == "/chat"
    assert data["user"]["email"] == "qa_backend_user@example.com"

    # Verify session cookie set
    with test_client.session_transaction() as sess:
        assert sess.get("user_id") is not None
        assert sess.get("username") == "qa_backend_user"


def test_backend_login_success_via_username(test_client):
    """Logging in with valid username succeeds."""
    res = test_client.post("/login", json={
        "identifier": "qa_backend_user",
        "password": "QAPassword2026!"
    })
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True


# -----------------------------------------------------------------------------
# 6. User Registration & Duplicate Email Prevention
# -----------------------------------------------------------------------------
def test_backend_registration_and_duplicate_prevention(test_client):
    """Verify registration creates user in DB, and prevents duplicates."""
    reg_payload = {
        "email": "qa_new_reg@example.com",
        "password": "StrongPassword2026#",
        "confirm": "StrongPassword2026#",
        "full_name": "New QA Tester"
    }
    # Success registration
    res = test_client.post("/register", json=reg_payload)
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True

    # Duplicate registration should return 409
    res_dup = test_client.post("/register", json=reg_payload)
    data_dup = res_dup.get_json()
    assert res_dup.status_code == 409
    assert data_dup["code"] == "EMAIL_EXISTS"


# -----------------------------------------------------------------------------
# 7. Forgot Password & Reset Token Verification
# -----------------------------------------------------------------------------
def test_backend_forgot_password_and_token_reset(test_client):
    """Verify forgot password generates timed token, and reset updates password."""
    # Request token
    res = test_client.post("/forgot-password", json={"email": "qa_backend_user@example.com"})
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    token = data["token"]
    assert token is not None

    # Reset password with token
    res_reset = test_client.post(f"/reset-password/{token}", json={
        "password": "BrandNewResetPass2026!",
        "confirm": "BrandNewResetPass2026!"
    })
    data_reset = res_reset.get_json()
    assert res_reset.status_code == 200
    assert data_reset["success"] is True

    # Verify new password logs in successfully
    res_login = test_client.post("/login", json={
        "identifier": "qa_backend_user@example.com",
        "password": "BrandNewResetPass2026!"
    })
    assert res_login.status_code == 200


# -----------------------------------------------------------------------------
# 8. Google OAuth & Auto Provisioning Flow
# -----------------------------------------------------------------------------
def test_backend_google_auth(test_client):
    """Verify Google sign-in auto-provisions user and establishes session."""
    google_data = {
        "email": "qa_google@gmail.com",
        "name": "QA Google User",
        "picture": "https://api.dicebear.com/7.x/identicon/svg?seed=qa_google",
        "google_id": "google_uid_987654321"
    }
    res = test_client.post("/auth/google", json=google_data)
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["user"]["email"] == "qa_google@gmail.com"

    # Verify session active
    with test_client.session_transaction() as sess:
        assert sess.get("email") == "qa_google@gmail.com"
