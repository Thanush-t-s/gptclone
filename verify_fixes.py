"""End-to-end verification for the AI-response output fixes.

Covers, with real assertions (no mocked "success"):
  1. History limit returns the MOST RECENT N messages (chronological order)
  2. System prompt is sent to the model exactly ONCE (was duplicated)
  3. content_to_text normalizes str / list-of-blocks content (no str(list) junk)
  4. Streaming errors RAISE instead of yielding "Error: ..." as chat text
  5. /api/send-message-stream streams NDJSON deltas + done, saves exactly one
     assistant message, and keeps history correct  (real Gemini call)
  6. /api/send-message keeps its exact JSON contract               (real call)
  7. Regenerating does not duplicate the user message in history    (real call)
  8. _persist_user_turn regenerate logic (pure DB, no API)
  9. Conversation-not-found on the stream route -> structured 404 JSON
"""

import json
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app import app
from extensions import db
from models import User, Conversation, Message
from services.gemini_service import GeminiService

PASS, FAIL = [], []


def check(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    (PASS if ok else FAIL).append(name)
    print(f"  [{tag}] {name}" + (f" -- {detail}" if detail else ""))


app.config["TESTING"] = True
app.config["SQLALCHEMY_ECHO"] = False  # keep verification output readable

# --------------------------------------------------------------------------
# Fixture user
# --------------------------------------------------------------------------
with app.app_context():
    db.create_all()
    user = User.query.filter_by(username="verify_bot").first()
    if not user:
        user = User(username="verify_bot")
        user.set_password("x")
        db.session.add(user)
        db.session.commit()
    USER_ID = user.id


def new_conv(title="verify"):
    with app.app_context():
        conv = Conversation(title=title, user_id=USER_ID)
        db.session.add(conv)
        db.session.commit()
        return conv.id


def roles_of(conv_id):
    with app.app_context():
        return [m.role for m in Message.get_conversation_messages(conv_id)]


def cleanup(*conv_ids):
    with app.app_context():
        for cid in conv_ids:
            conv = Conversation.query.get(cid)
            if conv:
                db.session.delete(conv)
        db.session.commit()


# ==========================================================================
print("\n1) History limit keeps the NEWEST messages in chronological order")
# ==========================================================================
conv = new_conv("limit")
with app.app_context():
    for i in range(1, 26):
        db.session.add(Message(role="user", content=f"msg-{i}", conversation_id=conv))
    db.session.commit()
    got = Message.get_conversation_messages(conv, limit=20)
    texts = [m.content for m in got]
    check("returns exactly `limit` rows", len(got) == 20, f"got {len(got)}")
    check("newest message (msg-25) is included", "msg-25" in texts)
    check("oldest message (msg-1) correctly dropped", "msg-1" not in texts)
    check("order is chronological", texts == sorted(texts, key=lambda t: int(t.split("-")[1])))
    check("last returned is the newest", texts[-1] == "msg-25", texts[-1])
cleanup(conv)

# ==========================================================================
print("\n2) System prompt sent to the model EXACTLY once")
# ==========================================================================
svc = GeminiService()
captured = {}


def _fake_llm(msgs):
    captured["msgs"] = msgs
    return AIMessage(content="fake-ok")


svc._llm = RunnableLambda(_fake_llm)
conv = new_conv("sysprompt")
with app.app_context():
    msgs = [
        Message(role="user", content="hi there", conversation_id=conv),
        Message(role="assistant", content="hello", conversation_id=conv),
        Message(role="user", content="and again", conversation_id=conv),
    ]
    text, _ = svc.get_response(conversation_id=conv, user_messages=msgs)
    got = captured["msgs"]
    got_list = list(got.messages) if hasattr(got, "messages") else list(got)
    sys_count = sum(1 for m in got_list if m.type == "system")
    types = [m.type for m in got_list]
    check("exactly one system message", sys_count == 1, f"types={types}")
    check("conversation turns preserved", types == ["system", "human", "ai", "human"], f"types={types}")
    check("response text extracted", text == "fake-ok", repr(text))

    # Streaming builds its own ChatGoogleGenerativeAI, so patch the class in
    # the service module to intercept (and to feed LIST-content chunks, which
    # used to leak "[{'type': 'text', ...}]" or crash .strip()).
    import services.gemini_service as gmod
    captured.clear()
    orig_cls = gmod.ChatGoogleGenerativeAI

    def _fake_stream_llm(msgs_):
        captured["msgs"] = msgs_
        return AIMessage(content=[{"type": "text", "text": "part1 "},
                                  {"type": "text", "text": "part2"}])

    class _FakeLLM:
        def __new__(cls, *a, **k):
            return RunnableLambda(_fake_stream_llm)

    gmod.ChatGoogleGenerativeAI = _FakeLLM
    try:
        chunks = list(svc.get_streaming_response(conv, msgs))
        got = captured.get("msgs", [])
        got_list = list(got.messages) if hasattr(got, "messages") else list(got)
        st = [m.type for m in got_list]
        check("stream: exactly one system message",
              sum(1 for m in got_list if m.type == "system") == 1,
              f"types={st}")
        check("stream: list-content chunks normalized to text",
              chunks == ["part1 part2"], repr(chunks))
    except NotImplementedError as e:
        check("stream: exactly one system message", False,
              f"fake LLM cannot stream: {e}")
    except Exception as e:
        check("stream: exactly one system message", False, f"{type(e).__name__}: {e}")
    finally:
        gmod.ChatGoogleGenerativeAI = orig_cls
cleanup(conv)

# ==========================================================================
print("\n3) content_to_text normalizes content shapes (no str(list) junk)")
# ==========================================================================
check("str passthrough", GeminiService.content_to_text("abc") == "abc")
check("None -> empty", GeminiService.content_to_text(None) == "")
check("list of blocks -> joined text",
      GeminiService.content_to_text([{"type": "text", "text": "Hello "},
                                     {"type": "text", "text": "world"}]) == "Hello world")
check("list of strings -> joined",
      GeminiService.content_to_text(["a", "b"]) == "ab")
check("mixed str/blocks -> joined",
      GeminiService.content_to_text(["a", {"type": "text", "text": "b"}]) == "ab")
check("no dict repr leaked",
      "{" not in GeminiService.content_to_text([{"type": "text", "text": "x"}]))

# ==========================================================================
print("\n4) Streaming errors RAISE (never yielded as chat text)")
# ==========================================================================
# Construct the service BEFORE patching: GeminiService.__init__ also builds
# an LLM, and we want the failure to happen inside the streaming generator.
svc_stream = GeminiService()
import services.gemini_service as gmod2
orig_cls2 = gmod2.ChatGoogleGenerativeAI


class _BoomLLM:
    def __new__(cls, *a, **k):
        raise RuntimeError("simulated Gemini API failure")


gmod2.ChatGoogleGenerativeAI = _BoomLLM
conv = new_conv("streamerr")
raised = None
yielded_text = []
try:
    for piece in svc_stream.get_streaming_response(
            conv, [Message(role="user", content="hi")]):
        yielded_text.append(piece)
    check("error raises RuntimeError", False, "generator completed without raising")
except RuntimeError as e:
    raised = str(e)
finally:
    gmod2.ChatGoogleGenerativeAI = orig_cls2
check("error raises RuntimeError", raised is not None, str(raised))
check("structured failure message",
      raised is not None and raised.startswith("Failed to stream AI response"),
      str(raised))
check("no text yielded before the error", yielded_text == [], repr(yielded_text))
cleanup(conv)

# ==========================================================================
print("\n5) /api/send-message-stream end-to-end (REAL Gemini call)")
# ==========================================================================
client = app.test_client()
with client.session_transaction() as s:
    s["user_id"] = USER_ID
    s["username"] = "verify_bot"

md_prompt = ("Reply with EXACTLY this structure, compact: an '## Overview' heading, "
             "a 3-item bullet list, a ```python fenced code block of 4 lines, "
             "and a 3x3 markdown table.")

resp = client.post("/api/send-message-stream",
                   json={"message": md_prompt, "conversation_id": None})
check("status 200", resp.status_code == 200, str(resp.status_code))
check("content-type ndjson", "ndjson" in (resp.content_type or ""), resp.content_type or "")

raw = resp.get_data(as_text=True)
lines = [l for l in raw.split("\n") if l.strip()]
events = []
bad_json = 0
for l in lines:
    try:
        events.append(json.loads(l))
    except Exception:
        bad_json += 1
check("every line is valid JSON", bad_json == 0, f"{bad_json} bad lines")
types = [e.get("type") for e in events]
check("starts with delta events", types and types[0] == "delta", str(types[:3]))
check("ends with done event", types and types[-1] == "done", str(types[-1]))
check("multiple incremental deltas", types.count("delta") >= 3, f"{types.count('delta')} deltas")
check("no error events", "error" not in types, str(types))

done = next((e for e in events if e.get("type") == "done"), None)
streamed = "".join(e["text"] for e in events if e.get("type") == "delta")
check("done.response == concatenation of deltas",
      done and done["response"].strip() == streamed.strip())
check("response contains a fenced code block", done and "```python" in done["response"])
check("response contains a table row", done and "|" in done["response"])
check("response contains a heading", done and "## " in done["response"])
check("no content-block junk in output", done and "{'type'" not in done["response"])

conv_id = done["conversation_id"] if done else None
if conv_id:
    with app.app_context():
        rows = Message.get_conversation_messages(conv_id)
        r = [m.role for m in rows]
        check("history = [user, assistant] exactly", r == ["user", "assistant"], str(r))
        check("saved assistant text == streamed text",
              rows[-1].content == done["response"])
        check("message_count consistent", done["message_count"] == len(rows),
              f"{done['message_count']} vs {len(rows)}")
        check("conversation auto-created with user message stored",
              rows[0].content == md_prompt)

    # Reload the conversation through the existing API (history preserved)
    r2 = client.get(f"/api/conversation/{conv_id}")
    check("GET /api/conversation works", r2.status_code == 200)
    j2 = r2.get_json()
    check("reload shows both messages", len(j2.get("messages", [])) == 2)

# ==========================================================================
print("\n6) /api/send-message contract unchanged (REAL Gemini call)")
# ==========================================================================
resp = client.post("/api/send-message",
                   json={"message": "Say hello in exactly 5 words.", "conversation_id": None})
j = resp.get_json()
check("status 200", resp.status_code == 200, str(resp.status_code))
check("contract keys present",
      all(k in j for k in ("success", "response", "conversation_id", "message_count")),
      str(sorted(j)))
check("success true + response text", j.get("success") is True and bool(j.get("response")))
nonstream_conv = j.get("conversation_id")

# ==========================================================================
print("\n7) Regenerating does not duplicate messages (REAL Gemini call)")
# ==========================================================================
if nonstream_conv:
    before = roles_of(nonstream_conv)
    r = client.post("/api/send-message",
                    json={"message": "Say hello in exactly 5 words.",
                          "conversation_id": nonstream_conv,
                          "regenerate": True})
    jr = r.get_json()
    after = roles_of(nonstream_conv)
    check("regenerate succeeded", jr.get("success") is True, str(jr.get("error")))
    check(f"roles unchanged {before} -> {after}", before == after)
    check("still exactly 2 messages (no duplicated user turn)", after == ["user", "assistant"],
          str(after))
    with app.app_context():
        rows = Message.get_conversation_messages(nonstream_conv)
        check("prompt stored only once",
              sum(1 for m in rows if m.role == "user" and m.content.startswith("Say hello")) == 1)

    # Regenerate over the STREAMING route too
    r = client.post("/api/send-message-stream",
                    json={"message": "Say hello in exactly 5 words.",
                          "conversation_id": nonstream_conv,
                          "regenerate": True})
    evs = [json.loads(l) for l in r.get_data(as_text=True).split("\n") if l.strip()]
    check("streaming regenerate ends with done", evs and evs[-1].get("type") == "done",
          str([e.get("type") for e in evs]))
    after2 = roles_of(nonstream_conv)
    check("streaming regenerate also keeps 2 messages", after2 == ["user", "assistant"],
          str(after2))

# ==========================================================================
print("\n8) _persist_user_turn regenerate logic (pure DB)")
# ==========================================================================
from app import _persist_user_turn

conv = new_conv("persist")
with app.app_context():
    # normal send appends
    _persist_user_turn(conv, "q1", regenerate=False)
    db.session.add(Message(role="assistant", content="a1", conversation_id=conv))
    db.session.commit()
    check("normal send stores user+assistant", roles_of(conv) == ["user", "assistant"])

    # regenerate removes trailing assistant, keeps prompt (no duplicate)
    _persist_user_turn(conv, "q1", regenerate=True)
    check("regenerate removes assistant, no dup prompt", roles_of(conv) == ["user"],
          str(roles_of(conv)))

    # regenerating a prompt that differs from the stored last one appends it
    # -- the turn must never be silently dropped (defensive edge case)
    _persist_user_turn(conv, "q2", regenerate=True)
    rows = Message.get_conversation_messages(conv)
    check("regenerate with different prompt appends it (never lost)",
          [m.content for m in rows] == ["q1", "q2"],
          str([(m.role, m.content) for m in rows]))

    # consecutive identical prompts are still two distinct turns
    _persist_user_turn(conv, "q2", regenerate=False)
    rows = Message.get_conversation_messages(conv)
    check("identical consecutive prompts stay distinct",
          [m.content for m in rows] == ["q1", "q2", "q2"],
          str([m.content for m in rows]))
cleanup(conv)

# ==========================================================================
print("\n9) Stream route validation errors")
# ==========================================================================
r = client.post("/api/send-message-stream", json={"message": "  "})
check("empty message -> 400", r.status_code == 400, str(r.status_code))
r = client.post("/api/send-message-stream",
                json={"message": "hi", "conversation_id": 99999999})
check("missing conversation -> 404 JSON", r.status_code == 404
      and "json" in (r.content_type or ""), f"{r.status_code} {r.content_type}")

anon = app.test_client()
r = anon.post("/api/send-message-stream", json={"message": "hi"})
check("unauthenticated -> 401", r.status_code == 401, str(r.status_code))

# ==========================================================================
# Cleanup fixture conversations created by the API calls
# ==========================================================================
with app.app_context():
    for c in Conversation.query.filter_by(user_id=USER_ID).all():
        db.session.delete(c)
    db.session.commit()

print("\n" + "=" * 70)
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED CHECKS:")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print("All verification checks passed.")
