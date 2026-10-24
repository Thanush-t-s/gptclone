"""
Master QA Automation Test Runner
Executes:
1. Backend Authentication API & Logic Tests (pytest)
2. Frontend E2E Browser Interaction Tests (Playwright Chromium/Edge)
Outputs formatted QA Automation Summary Report.
"""

import sys
import os
import time
import subprocess

def run_suite(cmd_args, suite_name):
    print(f"\n>> Running {suite_name}...")
    start_time = time.time()
    result = subprocess.run(
        cmd_args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    duration = time.time() - start_time
    return result, duration

def main():
    print("=" * 80)
    print("AURA HUB - FULL-STACK AUTHENTICATION AUTOMATION TEST SUITE")
    print("=" * 80)

    # 1. Run Backend Suite
    backend_res, backend_dur = run_suite(
        [sys.executable, "-m", "pytest", "tests/test_auth_backend.py", "-v", "--tb=short"],
        "Backend Authentication Test Suite"
    )

    # 2. Run Frontend UI Suite
    ui_res, ui_dur = run_suite(
        [sys.executable, "-m", "pytest", "tests/test_auth_ui.py", "-v", "--tb=short"],
        "Frontend Playwright E2E UI Suite"
    )

    # Parse Results
    print("\n" + "=" * 80)
    print("QA AUTOMATION TEST EXECUTION SUMMARY REPORT")
    print("=" * 80)

    print("\n--- [1] BACKEND AUTHENTICATION TEST SUITE ---")
    print(backend_res.stdout)
    if backend_res.returncode != 0:
        print("[FAILURES DETECTED IN BACKEND SUITE]:")
        print(backend_res.stderr)

    print("\n--- [2] FRONTEND PLAYWRIGHT E2E UI TEST SUITE ---")
    print(ui_res.stdout)
    if ui_res.returncode != 0:
        print("[FAILURES DETECTED IN FRONTEND SUITE]:")
        print(ui_res.stderr)

    print("=" * 80)
    backend_pass = (backend_res.returncode == 0)
    ui_pass = (ui_res.returncode == 0)
    overall_pass = backend_pass and ui_pass

    print(f"Backend Suite Status:  {'PASS' if backend_pass else 'FAIL'} ({backend_dur:.2f}s)")
    print(f"Frontend UI Suite:     {'PASS' if ui_pass else 'FAIL'} ({ui_dur:.2f}s)")
    print(f"Overall Status:        {'ALL TESTS PASSED' if overall_pass else 'SOME TESTS FAILED'}")
    print("=" * 80)

    return 0 if overall_pass else 1

if __name__ == "__main__":
    sys.exit(main())
