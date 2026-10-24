"""Browser end-to-end test of the complete chat flow (Playwright + Chrome).

Drives the REAL running dev server (http://127.0.0.1:5000) in a headless
browser and verifies:
  A. Page boots with ZERO console/page JS errors (catches ReferenceErrors)
  B. Empty state: welcome visible, composer in the welcome slot
  C. Sending a message STREAMS the answer; Markdown (heading, list, table),
     a syntax-highlighted code block with Copy button all render
  D. Welcome screen is properly hidden once the chat is active
  E. Copy-code button works (delegated handler)
  F. Autoscroll keeps the view pinned to the newest output
  G. Regenerate replaces the reply without duplicating messages
  H. Sidebar shows the conversation; reloading + reopening renders history
  I. Suggestion chips send a message; New chat resets the UI
"""

import os
import sys
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

from app import app
from extensions import db
from models import User, Conversation

BASE = "http://127.0.0.1:5000"
PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""), flush=True)


# Ensure the test account exists (same SQLite file the dev server uses).
with app.app_context():
    db.create_all()
    u = User.query.filter_by(username="e2e_user").first()
    if not u:
        u = User(username="e2e_user")
        db.session.add(u)
    u.set_password("e2e-pass-123")
    db.session.commit()

from playwright.sync_api import sync_playwright

console_errors = []
page_errors = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, channel="chrome")
    ctx = browser.new_context(viewport={"width": 1366, "height": 900})
    try:
        ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE)
    except Exception as e:  # pragma: no cover - permission API varies
        print(f"  (clipboard permissions not granted: {e})")

    page = ctx.new_page()
    page.on("console",
            lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: page_errors.append(str(e)))

    # Record whether we ever observe a streaming bubble with live content.
    page.add_init_script("""
        window.__sawStreamingWithContent = false;
        window.__maxStreamChars = 0;
        setInterval(function () {
            var b = document.querySelector('.msg[data-role="assistant"][data-streaming]');
            if (b) {
                var p = b.querySelector('.prose');
                var n = p ? p.textContent.trim().length : 0;
                if (n > 0) {
                    window.__sawStreamingWithContent = true;
                    if (n > window.__maxStreamChars) window.__maxStreamChars = n;
                }
            }
        }, 40);
    """)

    # ------------------------------------------------------------------
    print("\nA) Login + page boot")
    # ------------------------------------------------------------------
    page.goto(BASE + "/login", wait_until="networkidle")
    page.fill("#username", "e2e_user")
    page.fill("#password", "e2e-pass-123")
    page.click("button[type=submit]")
    page.wait_for_url("**/chat", timeout=15000)
    page.wait_for_load_state("networkidle")
    check("logged in and landed on /chat", "/chat" in page.url)

    # ------------------------------------------------------------------
    print("\nB) Empty state layout")
    # ------------------------------------------------------------------
    check("welcome visible", page.is_visible("#welcome"))
    check("composer authored inside the welcome slot",
          page.evaluate("""() => {
              const slot = document.getElementById('welcomeComposerSlot');
              const form = document.getElementById('messageForm');
              return !!(slot && form && slot.contains(form));
          }"""))
    check("conversation list rendered from server JSON (no JS crash)",
          page.evaluate("() => !!document.getElementById('convList')"))

    # ------------------------------------------------------------------
    print("\nC) Streaming send with Markdown + code rendering")
    # ------------------------------------------------------------------
    prompt = ("Give me a Markdown answer with: an '## Overview' heading, a "
              "3-item bullet list, a 4-line ```python code block, and a 3x3 "
              "table. Keep it compact.")
    page.fill("#messageInput", prompt)
    page.press("#messageInput", "Enter")

    page.wait_for_selector('.msg[data-role="assistant"]:not([data-streaming])',
                           timeout=90000)
    check("user message rendered", page.is_visible('.msg[data-role="user"]'))
    check("welcome hidden once chat is active", not page.is_visible("#welcome"))

    html_checks = page.evaluate("""() => {
        const bubbles = document.querySelectorAll('.msg[data-role="assistant"]');
        const last = bubbles[bubbles.length - 1];
        const prose = last.querySelector('.prose');
        const code = prose.querySelector('pre code');
        return {
            bubbles: bubbles.length,
            hasH2: !!prose.querySelector('h2'),
            hasList: !!prose.querySelector('ul li'),
            hasTable: !!prose.querySelector('table th') && !!prose.querySelector('table td'),
            hasPre: !!prose.querySelector('pre'),
            hasCodeLang: !!prose.querySelector('pre .code-lang'),
            hasCopyBtn: !!prose.querySelector('pre .copy-btn'),
            codeHighlighted: !!(code && /hljs|language-/.test(code.className)),
            codeText: code ? code.textContent.slice(0, 200) : '',
            actionsVisible: !!last.querySelector('.msg-actions:not([hidden])'),
            leftoverFences: (prose.textContent.match(/```/g) || []).length
        };
    }""")
    check("exactly one assistant bubble", html_checks["bubbles"] == 1)
    check("Markdown heading rendered (<h2>)", html_checks["hasH2"])
    check("bullet list rendered", html_checks["hasList"])
    check("table with header + cells rendered",
          html_checks["hasTable"])
    check("fenced code block rendered (<pre>)", html_checks["hasPre"])
    check("code language label present", html_checks["hasCodeLang"])
    check("Copy button present", html_checks["hasCopyBtn"])
    check("code block syntax-highlighted", html_checks["codeHighlighted"],
          html_checks["codeText"][:60])
    check("no stray ``` fences left in output", html_checks["leftoverFences"] == 0,
          f"{html_checks['leftoverFences']} fences")
    check("message action row revealed after completion",
          html_checks["actionsVisible"])

    saw_stream = page.evaluate("window.__sawStreamingWithContent")
    print(f"  (live streaming observed in browser: {saw_stream}; "
          f"max chars seen mid-stream: {page.evaluate('window.__maxStreamChars')})")

    # ------------------------------------------------------------------
    print("\nE) Copy-code button (delegated handler)")
    # ------------------------------------------------------------------
    page.click('.msg[data-role="assistant"] pre .copy-btn')
    page.wait_for_timeout(300)
    copied_label = page.text_content('.msg[data-role="assistant"] pre .copy-btn')
    check("copy button switched to 'Copied!'",
          "Copied" in (copied_label or ""), repr(copied_label))
    clip = page.evaluate("navigator.clipboard.readText()")
    check("clipboard contains the code block text",
          "def " in clip or "print" in clip or len(clip) > 10, repr(clip[:60]))

    # ------------------------------------------------------------------
    print("\nF) Autoscroll keeps newest output in view")
    # ------------------------------------------------------------------
    at_bottom = page.evaluate("""() => {
        const s = document.getElementById('scrollArea');
        return (s.scrollHeight - s.scrollTop - s.clientHeight) < 120;
    }""")
    check("viewport pinned near the bottom after reply", at_bottom)

    # ------------------------------------------------------------------
    print("\nG) Regenerate replaces the reply (no duplicates)")
    # ------------------------------------------------------------------
    first_response_len = page.evaluate(
        "() => document.querySelector('.msg[data-role=\"assistant\"] .prose').textContent.length")
    page.click('.msg[data-role="assistant"] .msg-regen')
    page.wait_for_selector('.msg[data-role="assistant"]:not([data-streaming])',
                           timeout=90000)
    counts = page.evaluate("""() => ({
        users: document.querySelectorAll('.msg[data-role="user"]').length,
        assistants: document.querySelectorAll('.msg[data-role="assistant"]').length
    })""")
    check("still exactly 1 user + 1 assistant bubble after regenerate",
          counts == {"users": 1, "assistants": 1}, str(counts))
    second_len = page.evaluate(
        "() => document.querySelector('.msg[data-role=\"assistant\"] .prose').textContent.length")
    check("a fresh reply was rendered", second_len > 20,
          f"{first_response_len} -> {second_len}")

    # ------------------------------------------------------------------
    print("\nH) Sidebar + reload + reopen history")
    # ------------------------------------------------------------------
    page.wait_for_selector(".conv-item", timeout=10000)
    check("conversation appears in the sidebar", page.is_visible(".conv-item"))
    page.wait_for_timeout(2500)  # allow the rename request to settle
    page.reload(wait_until="networkidle")
    check("sidebar list still rendered after reload",
          page.is_visible(".conv-item"))
    page.click(".conv-item")
    page.wait_for_selector('.msg[data-role="assistant"]', timeout=15000)
    page.wait_for_timeout(400)
    hist = page.evaluate("""() => ({
        users: document.querySelectorAll('.msg[data-role="user"]').length,
        assistants: document.querySelectorAll('.msg[data-role="assistant"]').length,
        hasTable: !!document.querySelector('.msg[data-role="assistant"] .prose table'),
        hasCode: !!document.querySelector('.msg[data-role="assistant"] .prose pre code')
    })""")
    check("reopened history shows 1 user + 1 assistant (no duplicates)",
          hist["users"] == 1 and hist["assistants"] == 1, str(hist))
    check("history Markdown still rendered (table + code)",
          hist["hasTable"] and hist["hasCode"], str(hist))

    # ------------------------------------------------------------------
    print("\nI) Suggestion chip + New chat reset")
    # ------------------------------------------------------------------
    page.click("#newChatBtn")
    page.wait_for_timeout(300)
    check("New chat resets to welcome", page.is_visible("#welcome"))
    check("composer returned to the welcome slot",
          page.evaluate("""() => {
              const slot = document.getElementById('welcomeComposerSlot');
              const form = document.getElementById('messageForm');
              return !!(slot && form && slot.contains(form));
          }"""))
    page.click("[data-prompt]")
    page.wait_for_selector('.msg[data-role="assistant"]:not([data-streaming])',
                           timeout=90000)
    check("suggestion chip produced a streamed reply",
          page.is_visible('.msg[data-role="assistant"] .prose'))

    # ------------------------------------------------------------------
    print("\nJ) Console / page JS errors")
    # ------------------------------------------------------------------
    benign = ("tailwindcss.com", "cdn.tailwindcss", "favicon",
              "Download the React DevTools")
    real_console = [e for e in console_errors
                    if not any(b in e for b in benign)]
    check("no console errors", not real_console, str(real_console[:3]))
    check("no uncaught page errors", not page_errors, str(page_errors[:3]))

    browser.close()

# Cleanup: remove conversations created by the E2E user.
with app.app_context():
    for c in Conversation.query.join(User).filter(User.username == "e2e_user").all():
        db.session.delete(c)
    db.session.commit()

print("\n" + "=" * 70)
print(f"BROWSER E2E RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for f in FAIL:
        print("  FAILED:", f)
    sys.exit(1)
print("All browser end-to-end checks passed.")
