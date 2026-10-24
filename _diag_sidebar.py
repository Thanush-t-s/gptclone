import os
import sys
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"
console_errors = []
net = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, channel="chrome")
    page = browser.new_context().new_page()
    page.on("console", lambda m: console_errors.append((m.type, m.text))
            if m.type in ("error", "warning") else None)
    page.on("response", lambda r: net.append((r.status, r.url))
            if "/api/" in r.url else None)

    page.goto(BASE + "/login", wait_until="networkidle")
    page.fill("#username", "e2e_user")
    page.fill("#password", "e2e-pass-123")
    page.click("button[type=submit]")
    page.wait_for_url("**/chat", timeout=15000)

    page.fill("#messageInput", "Reply with just the word: pong")
    page.press("#messageInput", "Enter")
    page.wait_for_selector('.msg[data-role="assistant"]:not([data-streaming])',
                           timeout=90000)
    # give autoTitle's rename fetch time to complete
    page.wait_for_timeout(4000)

    state = page.evaluate("""() => ({
        convItems: document.querySelectorAll('.conv-item').length,
        title: document.getElementById('chatTitle').textContent,
        convListHTML: document.getElementById('convList').innerHTML.length
    })""")
    print("state:", state)
    print("api calls:")
    for s, u in net:
        print("  ", s, u)
    print("console:", console_errors[:10])
    browser.close()
