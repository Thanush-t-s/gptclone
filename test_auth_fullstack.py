"""
Comprehensive test script for full-stack authentication system:
- Standard login (email & username)
- Edge case: Non-existent user
- Edge case: Bad password & failed attempt counter
- Edge case: Rate limiting lockout (5 attempts)
- Registration with validation & duplicate email checks
- Forgot password token generation & reset password verification
- Google OAuth simulation & auto-provisioning
"""
import sys
import types

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
import json

def run_tests():
    print("=" * 60)
    print("Testing Full-Stack Auth System & Edge Cases")
    print("=" * 60)

    client = app.test_client()

    with app.app_context():
        # Clean up any test users from previous runs
        test_emails = ["test_auth_user@example.com", "test_new_user@example.com", "google_test_user@gmail.com"]
        for email in test_emails:
            existing = User.query.filter_by(email=email).first()
            if existing:
                db.session.delete(existing)
        db.session.commit()

        # 1. Create a seed test user
        user = User(username="test_auth_user", email="test_auth_user@example.com", full_name="Test User")
        user.set_password("SecurePass123!")
        db.session.add(user)
        db.session.commit()
        print("[OK] Created seed test user: test_auth_user / test_auth_user@example.com")

        # 2. Test GET /login
        res = client.get("/login")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        assert b"Create an account" in res.data or b"Welcome back" in res.data, "Login page missing brand headers"
        assert b"logo-white.svg" in res.data, "White logo missing"
        assert b"logo-color.svg" in res.data, "Color logo missing"
        print("[OK] GET /login rendered successfully with custom brand logos")

        # 3. Test POST /login with invalid password
        res = client.post("/login", json={"identifier": "test_auth_user@example.com", "password": "WrongPassword"})
        data = res.get_json()
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"
        assert data["code"] == "INVALID_PASSWORD"
        assert "attempts_left" in data
        print(f"[OK] Bad password handled cleanly: {data['error']} (attempts left: {data['attempts_left']})")

        # 4. Test Lockout Edge Case (5 failed attempts)
        for i in range(4):
            client.post("/login", json={"identifier": "test_auth_user@example.com", "password": "WrongPassword"})
        
        # 5th attempt should trigger lock
        res = client.post("/login", json={"identifier": "test_auth_user@example.com", "password": "WrongPassword"})
        data = res.get_json()
        assert res.status_code == 429, f"Expected 429, got {res.status_code}"
        assert data["code"] == "ACCOUNT_LOCKED"
        assert data["retry_after"] > 0
        print(f"[OK] Lockout edge case verified: {data['error']} (retry after: {data['retry_after']}s)")

        # Unlock user for next tests
        user.reset_failed_attempts()
        db.session.commit()

        # 5. Test Login with valid credentials via Email
        res = client.post("/login", json={"identifier": "test_auth_user@example.com", "password": "SecurePass123!"})
        data = res.get_json()
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        assert data["success"] is True
        print("[OK] Login via Email succeeded")

        # 6. Test Login with valid credentials via Username
        res = client.post("/login", json={"identifier": "test_auth_user", "password": "SecurePass123!"})
        data = res.get_json()
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        assert data["success"] is True
        print("[OK] Login via Username succeeded")

        # 7. Test Non-existent user
        res = client.post("/login", json={"identifier": "nonexistent_9999@example.com", "password": "AnyPassword123!"})
        data = res.get_json()
        assert res.status_code == 404, f"Expected 404, got {res.status_code}"
        assert data["code"] == "USER_NOT_FOUND"
        print("[OK] Non-existent user edge case handled cleanly")

        # 8. Test Registration of new user
        reg_payload = {
            "email": "test_new_user@example.com",
            "password": "SuperSecretPass99#",
            "confirm": "SuperSecretPass99#",
            "full_name": "New Tester"
        }
        res = client.post("/register", json=reg_payload)
        data = res.get_json()
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        assert data["success"] is True
        print("[OK] New user registration succeeded")

        # 9. Test Registration duplicate email prevention
        res = client.post("/register", json=reg_payload)
        data = res.get_json()
        assert res.status_code == 409, f"Expected 409, got {res.status_code}"
        assert data["code"] == "EMAIL_EXISTS"
        print("[OK] Duplicate email prevention edge case verified")

        # 10. Test Forgot Password
        res = client.post("/forgot-password", json={"email": "test_auth_user@example.com"})
        data = res.get_json()
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        assert data["success"] is True
        assert "token" in data
        assert "reset_url" in data
        reset_token = data["token"]
        print(f"[OK] Forgot password token generated successfully: {reset_token[:15]}...")

        # 11. Test Reset Password with Token
        res = client.post(f"/reset-password/{reset_token}", json={
            "password": "BrandNewPassword2026!",
            "confirm": "BrandNewPassword2026!"
        })
        data = res.get_json()
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        assert data["success"] is True
        print("[OK] Password reset verified and updated successfully")

        # Verify new password works
        res = client.post("/login", json={"identifier": "test_auth_user@example.com", "password": "BrandNewPassword2026!"})
        data = res.get_json()
        assert res.status_code == 200 and data["success"] is True
        print("[OK] Login with newly updated password succeeded")

        # 12. Test Google Auth Endpoint
        google_payload = {
            "email": "google_test_user@gmail.com",
            "name": "Google Test User",
            "picture": "https://api.dicebear.com/7.x/identicon/svg?seed=google_test",
            "google_id": "google_sub_123456789"
        }
        res = client.post("/auth/google", json=google_payload)
        data = res.get_json()
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        assert data["success"] is True
        assert data["user"]["email"] == "google_test_user@gmail.com"
        print("[OK] Google Authentication & automatic account provisioning succeeded")

        # Clean up test users
        for email in test_emails:
            u = User.query.filter_by(email=email).first()
            if u:
                db.session.delete(u)
        db.session.commit()
        print("[OK] Test cleanup completed")

    print("=" * 60)
    print("ALL 12 AUTHENTICATION & EDGE CASE TESTS PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
