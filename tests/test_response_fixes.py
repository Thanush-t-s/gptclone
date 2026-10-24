"""Regression tests for the AI response output fixes.

Each test targets a bug that was reproduced and fixed:
  * history limit returned the OLDEST N messages (stale context)
  * the system prompt was sent to the model TWICE
  * list-typed message content crashed .strip() / leaked "[{'type': ...}]"
  * streaming yielded "Error: ..." as if it were model text
  * regenerating duplicated the user message in the stored history
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app import app, db
from models import User, Conversation, Message
from services.gemini_service import GeminiService


def _user_id():
    with app.app_context():
        db.create_all()
        u = User.query.filter_by(username="fixtester").first()
        if not u:
            u = User(username="fixtester")
            u.set_password("x")
            db.session.add(u)
            db.session.commit()
        return u.id


def _cleanup(conv):
    with app.app_context():
        c = db.session.get(Conversation, conv)
        if c:
            db.session.delete(c)
            db.session.commit()


def test_history_limit_returns_most_recent_messages():
    """limit=20 on 25 messages must keep the NEWEST 20 (incl. the last user turn)."""
    uid = _user_id()
    with app.app_context():
        conv = Conversation(title="limit-test", user_id=uid)
        db.session.add(conv)
        db.session.commit()
        cid = conv.id
        for i in range(1, 26):
            db.session.add(Message(role="user", content=f"msg-{i}", conversation_id=cid))
        db.session.commit()

        got = Message.get_conversation_messages(cid, limit=20)
        texts = [m.content for m in got]

        assert len(got) == 20
        assert "msg-25" in texts, "newest message was dropped"
        assert "msg-1" not in texts, "oldest message should be trimmed"
        assert texts == [f"msg-{i}" for i in range(6, 26)], \
            "returned slice must be the most recent N in chronological order"
    _cleanup(cid)


def test_history_without_limit_is_chronological():
    uid = _user_id()
    with app.app_context():
        conv = Conversation(title="limit-none", user_id=uid)
        db.session.add(conv)
        db.session.commit()
        cid = conv.id
        for i in range(1, 6):
            db.session.add(Message(role="user", content=f"m{i}", conversation_id=cid))
        db.session.commit()
        assert [m.content for m in Message.get_conversation_messages(cid)] == \
            ["m1", "m2", "m3", "m4", "m5"]
    _cleanup(cid)


def test_content_to_text_shapes():
    """AIMessage.content may be str OR a list of blocks -- always end up clean."""
    c2t = GeminiService.content_to_text
    assert c2t("plain") == "plain"
    assert c2t(None) == ""
    assert c2t([{"type": "text", "text": "Hello "}]) == "Hello "
    assert c2t([{"type": "text", "text": "a"},
                {"type": "text", "text": "b"}]) == "ab"
    assert c2t(["a", "b"]) == "ab"
    assert c2t(["a", {"type": "text", "text": "b"}]) == "ab"
    # No dict/list repr may leak into the reply text.
    assert "{" not in c2t([{"type": "text", "text": "x"}])


def test_system_prompt_sent_once():
    """Both response paths inject the system prompt via the template only."""
    svc = GeminiService()
    captured = {}

    def fake(msgs):
        captured["msgs"] = msgs
        return AIMessage(content="ok")

    svc._llm = RunnableLambda(fake)
    with app.app_context():
        msgs = [Message(role="user", content="hi", conversation_id=1),
                Message(role="assistant", content="yo", conversation_id=1)]
        text, _ = svc.get_response(conversation_id=1, user_messages=msgs)

    got = captured["msgs"]
    msgs_list = list(got.messages) if hasattr(got, "messages") else list(got)
    types = [m.type for m in msgs_list]
    assert types.count("system") == 1, f"system prompt duplicated: {types}"
    assert types == ["system", "human", "ai"], types
    assert text == "ok"


def test_streaming_error_raises_instead_of_yielding_text():
    """A streaming failure must surface as an exception, not as chat text."""
    import services.gemini_service as gmod

    svc = GeminiService()  # built BEFORE the patch; __init__ also builds an LLM
    orig = gmod.ChatGoogleGenerativeAI

    class _Boom:
        def __new__(cls, *a, **k):
            raise RuntimeError("boom")

    gmod.ChatGoogleGenerativeAI = _Boom
    yielded = []
    raised = None
    try:
        for piece in svc.get_streaming_response(
                1, [Message(role="user", content="hi")]):
            yielded.append(piece)
    except RuntimeError as e:
        raised = e
    finally:
        gmod.ChatGoogleGenerativeAI = orig

    assert raised is not None, "streaming failure was swallowed"
    assert yielded == [], f"error text leaked as message content: {yielded}"
    assert "Failed to stream AI response" in str(raised)


def test_persist_user_turn_regenerate_no_duplicates():
    """Regenerate replaces the answer and never re-appends the prompt."""
    from app import _persist_user_turn

    uid = _user_id()
    with app.app_context():
        conv = Conversation(title="regen-test", user_id=uid)
        db.session.add(conv)
        db.session.commit()
        cid = conv.id

        _persist_user_turn(cid, "q1", regenerate=False)
        db.session.add(Message(role="assistant", content="a1", conversation_id=cid))
        db.session.commit()
        assert [m.role for m in Message.get_conversation_messages(cid)] == \
            ["user", "assistant"]

        # Regenerating the same prompt: assistant reply dropped, prompt kept.
        _persist_user_turn(cid, "q1", regenerate=True)
        rows = Message.get_conversation_messages(cid)
        assert [m.role for m in rows] == ["user"], "regenerate duplicated the turn"
        assert rows[0].content == "q1"

        # A normal send still appends even for identical text (two turns).
        _persist_user_turn(cid, "q1", regenerate=False)
        assert [m.role for m in Message.get_conversation_messages(cid)] == \
            ["user", "user"]
    _cleanup(cid)
