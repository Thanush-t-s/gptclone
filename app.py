"""
ChatGPT-Style AI Chat Application
Flask backend with Google Gemini API integration via LangChain.
"""

import os
import sys
import types
import json
import logging
import re
from datetime import timedelta

# Windows Application Control / WDAC compatibility shim for xxhash
if "xxhash" not in sys.modules:
    try:
        import xxhash
    except (ImportError, OSError):
        xxhash_mock = types.ModuleType("xxhash")
        xxhash_mock._xxhash = types.ModuleType("xxhash._xxhash")
        sys.modules["xxhash"] = xxhash_mock
        sys.modules["xxhash._xxhash"] = xxhash_mock._xxhash

from flask import Flask, render_template, redirect, url_for, request, \
    session, flash, jsonify, Response
from flask_migrate import Migrate
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = False  # Set to True in production with HTTPS
app.permanent_session_lifetime = timedelta(days=30)

# Configure SQLAlchemy
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = (
    os.getenv("DATABASE_URL",
              f"sqlite:///{os.path.join(basedir, 'instance', 'chat.db')}")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ECHO"] = os.getenv("FLASK_ENV", "development") == "development"

# Initialize extensions
from extensions import db, init_app
init_app(app)
migrate = Migrate(app, db)

# Import models after db initialization
from models import User, Conversation, Message

# Initialize Gemini service safely
gemini_service = None
try:
    from services.gemini_service import GeminiService
    gemini_service = GeminiService()
except Exception as e:
    logging.warning(f"GeminiService deferred initialization: {e}")



# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Home page - redirect to login or chat."""
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("chat"))


EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")


@app.route("/login", methods=["GET", "POST"])
def login():
    """User login page with email/username support, rate limiting, and edge cases."""
    if "user_id" in session and request.method == "GET":
        return redirect(url_for("chat"))

    if request.method == "POST":
        is_ajax = request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        data = request.get_json() if request.is_json else request.form

        identifier = (data.get("identifier") or data.get("email") or data.get("username") or "").strip()
        password = data.get("password", "")
        remember_me = bool(data.get("remember_me") or data.get("remember"))

        # Edge case: Empty fields
        if not identifier or not password:
            msg = "Please enter both email/username and password."
            if is_ajax:
                return jsonify({"success": False, "error": msg, "code": "EMPTY_FIELDS"}), 400
            flash(msg, "error")
            return render_template("login.html", mode="login", identifier=identifier)

        # Edge case: Invalid email format if user entered an email containing '@'
        if "@" in identifier and not EMAIL_REGEX.match(identifier):
            msg = "Please enter a valid email address format (e.g., name@example.com)."
            if is_ajax:
                return jsonify({"success": False, "error": msg, "code": "INVALID_EMAIL"}), 400
            flash(msg, "error")
            return render_template("login.html", mode="login", identifier=identifier)

        # Lookup user by case-insensitive email or username
        user = User.query.filter(
            (db.func.lower(User.email) == identifier.lower()) |
            (db.func.lower(User.username) == identifier.lower())
        ).first()

        # Edge case: User does not exist
        if not user:
            msg = "No account found with this email or username."
            if is_ajax:
                return jsonify({
                    "success": False,
                    "error": msg,
                    "code": "USER_NOT_FOUND",
                    "suggestion": "register",
                    "email": identifier if "@" in identifier else ""
                }), 404
            flash(msg, "error")
            return render_template("login.html", mode="login", identifier=identifier)

        # Edge case: Account locked due to failed attempts (Brute force protection)
        if user.is_locked():
            remaining_seconds = user.seconds_remaining_locked()
            msg = f"Account temporarily locked due to multiple failed login attempts. Please wait {remaining_seconds} seconds before trying again."
            if is_ajax:
                return jsonify({
                    "success": False,
                    "error": msg,
                    "code": "ACCOUNT_LOCKED",
                    "retry_after": remaining_seconds
                }), 429
            flash(msg, "error")
            return render_template("login.html", mode="login", identifier=identifier, locked_seconds=remaining_seconds)

        # Check password
        if user.check_password(password):
            user.reset_failed_attempts()
            db.session.commit()

            session.permanent = remember_me
            session["user_id"] = user.id
            session["username"] = user.username
            session["email"] = user.email
            session["avatar_url"] = user.avatar_url
            session["full_name"] = user.full_name or user.username
            flash(f"Welcome back, {user.full_name or user.username}!", "success")

            next_url = request.args.get("next") or url_for("chat")
            if is_ajax:
                return jsonify({
                    "success": True,
                    "redirect": next_url,
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "name": user.full_name or user.username
                    }
                })
            return redirect(next_url)
        else:
            # Bad password: increment failed attempts
            user.record_failed_attempt()
            db.session.commit()

            if user.is_locked():
                remaining_seconds = user.seconds_remaining_locked()
                msg = f"Too many failed login attempts. Account temporarily locked for {remaining_seconds} seconds."
                code = "ACCOUNT_LOCKED"
                status_code = 429
            else:
                attempts_left = max(0, 5 - (user.failed_login_attempts or 0))
                msg = f"Incorrect password. {attempts_left} attempt{'s' if attempts_left != 1 else ''} remaining before temporary lock."
                code = "INVALID_PASSWORD"
                status_code = 401

            if is_ajax:
                return jsonify({
                    "success": False,
                    "error": msg,
                    "code": code,
                    "attempts_left": max(0, 5 - (user.failed_login_attempts or 0)),
                    "retry_after": user.seconds_remaining_locked() if user.is_locked() else 0
                }), status_code
            flash(msg, "error")
            return render_template("login.html", mode="login", identifier=identifier)

    mode = request.args.get("mode", "login")
    return render_template("login.html", mode=mode)


@app.route("/register", methods=["GET", "POST"])
def register():
    """User registration page with edge case validation."""
    if "user_id" in session and request.method == "GET":
        return redirect(url_for("chat"))

    if request.method == "POST":
        is_ajax = request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        data = request.get_json() if request.is_json else request.form

        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        confirm = data.get("confirm", "")
        full_name = data.get("full_name", "").strip()
        username = data.get("username", "").strip()

        # Edge case: Empty fields
        if not email or not password:
            msg = "Please enter all required fields."
            if is_ajax:
                return jsonify({"success": False, "error": msg, "code": "EMPTY_FIELDS"}), 400
            flash(msg, "error")
            return render_template("login.html", mode="signup", email=email, full_name=full_name)

        # Edge case: Invalid email format
        if not EMAIL_REGEX.match(email):
            msg = "Please enter a valid email address."
            if is_ajax:
                return jsonify({"success": False, "error": msg, "code": "INVALID_EMAIL"}), 400
            flash(msg, "error")
            return render_template("login.html", mode="signup", email=email, full_name=full_name)

        # Edge case: Password mismatch
        if confirm and password != confirm:
            msg = "Passwords do not match."
            if is_ajax:
                return jsonify({"success": False, "error": msg, "code": "PASSWORD_MISMATCH"}), 400
            flash(msg, "error")
            return render_template("login.html", mode="signup", email=email, full_name=full_name)

        # Edge case: Weak password length
        if len(password) < 8:
            msg = "Password must be at least 8 characters long."
            if is_ajax:
                return jsonify({"success": False, "error": msg, "code": "WEAK_PASSWORD"}), 400
            flash(msg, "error")
            return render_template("login.html", mode="signup", email=email, full_name=full_name)

        # Edge case: Email already exists
        if User.query.filter(db.func.lower(User.email) == email).first():
            msg = "An account with this email already exists. Please sign in instead."
            if is_ajax:
                return jsonify({"success": False, "error": msg, "code": "EMAIL_EXISTS"}), 409
            flash(msg, "error")
            return render_template("login.html", mode="login", identifier=email)

        # Derive username if omitted
        if not username:
            base_username = email.split("@")[0]
            clean_username = re.sub(r"[^\w]", "", base_username) or "user"
            candidate_username = clean_username
            counter = 1
            while User.query.filter(db.func.lower(User.username) == candidate_username.lower()).first():
                candidate_username = f"{clean_username}{counter}"
                counter += 1
            username = candidate_username
        else:
            if User.query.filter(db.func.lower(User.username) == username.lower()).first():
                msg = "Username already exists. Please choose another."
                if is_ajax:
                    return jsonify({"success": False, "error": msg, "code": "USERNAME_EXISTS"}), 409
                flash(msg, "error")
                return render_template("login.html", mode="signup", email=email, full_name=full_name)

        try:
            new_user = User(
                username=username,
                email=email,
                full_name=full_name or username,
                auth_provider="local"
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()

            session.permanent = True
            session["user_id"] = new_user.id
            session["username"] = new_user.username
            session["email"] = new_user.email
            session["avatar_url"] = new_user.avatar_url
            session["full_name"] = new_user.full_name or new_user.username
            flash(f"Account created successfully! Welcome to your personal hub.", "success")

            if is_ajax:
                return jsonify({"success": True, "redirect": url_for("chat")})
            return redirect(url_for("chat"))
        except Exception as e:
            db.session.rollback()
            msg = f"Error during registration: {str(e)}"
            if is_ajax:
                return jsonify({"success": False, "error": msg}), 500
            flash(msg, "error")
            return render_template("login.html", mode="signup", email=email, full_name=full_name)

    return render_template("login.html", mode="signup")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Forgot password request handler."""
    if request.method == "POST":
        is_ajax = request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        data = request.get_json() if request.is_json else request.form

        email = data.get("email", "").strip().lower()
        if not email:
            msg = "Please enter your email address."
            if is_ajax:
                return jsonify({"success": False, "error": msg, "code": "EMPTY_EMAIL"}), 400
            flash(msg, "error")
            return render_template("login.html", mode="forgot")

        if not EMAIL_REGEX.match(email):
            msg = "Please enter a valid email address format."
            if is_ajax:
                return jsonify({"success": False, "error": msg, "code": "INVALID_EMAIL"}), 400
            flash(msg, "error")
            return render_template("login.html", mode="forgot", email=email)

        user = User.query.filter(db.func.lower(User.email) == email).first()
        if not user:
            # Edge case: User does not exist
            msg = "If an account exists with this email, recovery instructions have been prepared."
            if is_ajax:
                return jsonify({
                    "success": True,
                    "message": msg,
                    "user_exists": False,
                    "info": "No registered account found with this email. You can create a new account or try another email."
                })
            flash(msg, "info")
            return render_template("login.html", mode="forgot")

        # Generate secure reset token
        token = user.get_reset_token(app.config["SECRET_KEY"])
        reset_url = url_for("reset_password", token=token, _external=True)

        session["last_reset_url"] = reset_url
        session["last_reset_email"] = user.email

        msg = f"Password recovery link generated for {user.email}."
        if is_ajax:
            return jsonify({
                "success": True,
                "message": msg,
                "user_exists": True,
                "reset_url": reset_url,
                "token": token,
                "expires_in_minutes": 15
            })
        flash(msg, "success")
        return render_template("login.html", mode="forgot", reset_url=reset_url)

    return render_template("login.html", mode="forgot")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Password reset page with token verification."""
    user = User.verify_reset_token(token, app.config["SECRET_KEY"])
    if not user:
        flash("The password reset link is invalid or has expired (links expire after 15 minutes). Please request a new link.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        is_ajax = request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        data = request.get_json() if request.is_json else request.form

        password = data.get("password", "")
        confirm = data.get("confirm", "")

        if not password:
            msg = "Please enter your new password."
            if is_ajax:
                return jsonify({"success": False, "error": msg}), 400
            flash(msg, "error")
            return render_template("login.html", mode="reset", token=token, email=user.email)

        if len(password) < 8:
            msg = "Password must be at least 8 characters long."
            if is_ajax:
                return jsonify({"success": False, "error": msg}), 400
            flash(msg, "error")
            return render_template("login.html", mode="reset", token=token, email=user.email)

        if confirm and password != confirm:
            msg = "Passwords do not match."
            if is_ajax:
                return jsonify({"success": False, "error": msg}), 400
            flash(msg, "error")
            return render_template("login.html", mode="reset", token=token, email=user.email)

        try:
            user.set_password(password)
            user.reset_failed_attempts()
            db.session.commit()

            session.permanent = True
            session["user_id"] = user.id
            session["username"] = user.username
            session["email"] = user.email
            session["avatar_url"] = user.avatar_url
            session["full_name"] = user.full_name or user.username
            flash("Your password has been reset successfully! Welcome back.", "success")

            if is_ajax:
                return jsonify({"success": True, "redirect": url_for("chat")})
            return redirect(url_for("chat"))
        except Exception as e:
            db.session.rollback()
            msg = f"Failed to reset password: {str(e)}"
            if is_ajax:
                return jsonify({"success": False, "error": msg}), 500
            flash(msg, "error")
            return render_template("login.html", mode="reset", token=token, email=user.email)

    return render_template("login.html", mode="reset", token=token, email=user.email)


@app.route("/auth/google", methods=["POST"])
def google_auth():
    """Google sign-in authentication endpoint (handles simulated or live Google credential)."""
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    google_id = str(data.get("google_id") or data.get("sub") or "").strip()
    name = data.get("name", "").strip() or "Google User"
    avatar_url = data.get("picture", "").strip() or f"https://api.dicebear.com/7.x/identicon/svg?seed={email}"

    if not email or not EMAIL_REGEX.match(email):
        return jsonify({"success": False, "error": "Invalid or missing Google email account."}), 400

    if not google_id:
        import hashlib
        google_id = "g_" + hashlib.sha256(email.encode("utf-8")).hexdigest()[:16]

    # Edge case 1: Lookup by google_id
    user = User.query.filter_by(google_id=google_id).first()

    # Edge case 2: Lookup by email if not yet linked to google_id
    if not user:
        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user:
            user.google_id = google_id
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
            user.reset_failed_attempts()
            db.session.commit()

    # Edge case 3: Create new user if not registered
    if not user:
        base_username = email.split("@")[0]
        clean_username = re.sub(r"[^\w]", "", base_username) or "user"
        candidate_username = clean_username
        counter = 1
        while User.query.filter(db.func.lower(User.username) == candidate_username.lower()).first():
            candidate_username = f"{clean_username}{counter}"
            counter += 1

        import secrets
        user = User(
            username=candidate_username,
            email=email,
            full_name=name,
            avatar_url=avatar_url,
            auth_provider="google",
            google_id=google_id
        )
        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)
        db.session.commit()

    # Authenticate session
    session.permanent = True
    session["user_id"] = user.id
    session["username"] = user.username
    session["email"] = user.email
    session["avatar_url"] = user.avatar_url
    session["full_name"] = user.full_name or user.username
    flash(f"Signed in with Google as {user.full_name or user.username}!", "success")

    return jsonify({
        "success": True,
        "redirect": url_for("chat"),
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "name": user.full_name or user.username,
            "avatar_url": user.avatar_url
        }
    })


@app.route("/api/auth/validate-email", methods=["POST"])
def validate_email():
    """Real-time validation for email status."""
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    if not email:
        return jsonify({"valid": False, "error": "Email is required"}), 400
    if not EMAIL_REGEX.match(email):
        return jsonify({"valid": False, "error": "Invalid email format"}), 400
    user = User.query.filter(db.func.lower(User.email) == email).first()
    return jsonify({
        "valid": True,
        "exists": user is not None,
        "auth_provider": user.auth_provider if user else None,
        "has_password": bool(user and user.password_hash) if user else False
    })



@app.route("/chat")
def chat():
    """Main chat interface."""
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    # Get recent conversations for the sidebar
    conversations = (
        Conversation.query.filter_by(user_id=user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(20)
        .all()
    )

    # Format conversations for the template
    conv_data = []
    for conv in conversations:
        last_msg = (
            conv.messages.order_by(Message.created_at.desc()).first()
        )
        conv_data.append({
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
            "last_message": last_msg.content if last_msg else None,
        })

    return render_template(
        "chat.html",
        conversations=conv_data,
        username=session.get("username", "User"),
        avatar_url=session.get("avatar_url"),
    )


@app.route("/api/new-conversation", methods=["POST"])
def new_conversation():
    """Create a new conversation."""
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session["user_id"]
    conversation = Conversation(
        title="New Conversation",
        user_id=user_id,
    )
    db.session.add(conversation)
    db.session.commit()

    return jsonify({
        "id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    })


def _persist_user_turn(conversation_id, user_message, regenerate=False):
    """Store the incoming user turn for a conversation.

    Normal sends always append a new user message (sending the same text
    twice in a row stays two distinct turns).

    With ``regenerate=True`` the previous assistant reply is removed and the
    prompt that is already stored is reused instead of being appended again.
    Without this, every "Regenerate" duplicated the user message in the saved
    history, which showed up as repeated text when the chat was reloaded and
    skewed the context sent to the model.
    """

    def last():
        return (
            Message.query.filter_by(conversation_id=conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .first()
        )

    if not regenerate:
        db.session.add(Message(
            role="user",
            content=user_message,
            conversation_id=conversation_id,
        ))
        db.session.commit()
        return

    last_msg = last()
    if last_msg is not None and last_msg.role == "assistant":
        db.session.delete(last_msg)
        db.session.commit()
        last_msg = last()

    prompt_is_stored = (
        last_msg is not None
        and last_msg.role == "user"
        and last_msg.content == user_message
    )
    if not prompt_is_stored:
        db.session.add(Message(
            role="user",
            content=user_message,
            conversation_id=conversation_id,
        ))
        db.session.commit()


@app.route("/api/send-message", methods=["POST"])
def send_message():
    """Send a message and get a response from Gemini."""
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session["user_id"]
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "No message provided"}), 400

    user_message = data["message"].strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    conversation_id = data.get("conversation_id")
    if conversation_id:
        # Verify ownership
        conversation = Conversation.query.filter_by(
            id=conversation_id, user_id=user_id
        ).first()
        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404
    else:
        # Create new conversation
        conversation = Conversation(
            title="New Conversation",
            user_id=user_id,
        )
        db.session.add(conversation)
        db.session.commit()

    # Save user message (or swap the turn when regenerating)
    _persist_user_turn(
        conversation.id, user_message, bool(data.get("regenerate"))
    )

    # Limit conversation history
    messages = Message.get_conversation_messages(
        conversation.id, limit=int(os.getenv("HISTORY_MESSAGE_LIMIT", 20))
    )

    # Get AI response
    try:
        response_text, new_conversation = gemini_service.get_response(
            conversation_id=conversation.id,
            user_messages=messages,
            model_name=os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash"),
        )

        # Save assistant response
        assistant_msg = Message(
            role="assistant",
            content=response_text,
            conversation_id=conversation.id,
        )
        db.session.add(assistant_msg)
        db.session.commit()

        return jsonify({
            "success": True,
            "response": response_text,
            "conversation_id": conversation.id,
            "message_count": Message.query.filter_by(
                conversation_id=conversation.id
            ).count(),
        })

    except Exception as e:
        db.session.rollback()
        # Still save the user message but mark error
        db.session.commit()
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@app.route("/api/send-message-stream", methods=["POST"])
def send_message_stream():
    """Stream an AI response as newline-delimited JSON (NDJSON).

    One JSON event per line:
      {"type": "delta", "text": "..."}            incremental Markdown text
      {"type": "done", "response": "...",
       "conversation_id": N, "message_count": N}  final result (already saved)
      {"type": "error", "error": "..."}           failure; stream stops

    This is additive: /api/send-message keeps its exact existing contract.
    """
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session["user_id"]
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "No message provided"}), 400

    user_message = data["message"].strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    conversation_id = data.get("conversation_id")
    if conversation_id:
        conversation = Conversation.query.filter_by(
            id=conversation_id, user_id=user_id
        ).first()
        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404
    else:
        conversation = Conversation(
            title="New Conversation",
            user_id=user_id,
        )
        db.session.add(conversation)
        db.session.commit()

    # Save user message (same persistence behaviour as /api/send-message)
    _persist_user_turn(
        conversation.id, user_message, bool(data.get("regenerate"))
    )

    conv_id = conversation.id
    model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

    # Snapshot history as plain data BEFORE streaming. The generator below
    # runs after Flask has torn down the request context (and the SQLAlchemy
    # session bound to it), so ORM instances must not be used inside it.
    messages = Message.get_conversation_messages(
        conv_id, limit=int(os.getenv("HISTORY_MESSAGE_LIMIT", 20))
    )
    history = [Message(role=m.role, content=m.content) for m in messages]

    def ndjson(payload):
        return json.dumps(payload, ensure_ascii=False) + "\n"

    def generate():
        chunks = []
        try:
            for chunk in gemini_service.get_streaming_response(
                conversation_id=conv_id,
                user_messages=history,
                model_name=model_name,
            ):
                chunks.append(chunk)
                yield ndjson({"type": "delta", "text": chunk})
        except Exception as e:
            app.logger.error(
                "Gemini streaming failed for conversation %s: %s", conv_id, e
            )
            yield ndjson({"type": "error", "error": str(e)})
            return

        full_text = "".join(chunks).strip()
        if not full_text:
            yield ndjson({
                "type": "error",
                "error": "Received empty response from Gemini API",
            })
            return

        # Persist the assistant message in its own application context.
        try:
            with app.app_context():
                assistant_msg = Message(
                    role="assistant",
                    content=full_text,
                    conversation_id=conv_id,
                )
                db.session.add(assistant_msg)
                db.session.commit()
                message_count = Message.query.filter_by(
                    conversation_id=conv_id
                ).count()
            yield ndjson({
                "type": "done",
                "response": full_text,
                "conversation_id": conv_id,
                "message_count": message_count,
            })
        except Exception as e:
            app.logger.error(
                "Failed to save streamed response for conversation %s: %s",
                conv_id, e,
            )
            try:
                with app.app_context():
                    db.session.rollback()
            except Exception:  # pragma: no cover - best effort cleanup
                pass
            # The answer was already streamed to the client, so include it;
            # the UI keeps the rendered text and reports the save failure.
            yield ndjson({
                "type": "error",
                "error": str(e),
                "response": full_text,
            })

    return Response(
        generate(),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/api/conversations", methods=["GET"])
def list_conversations():
    """List all conversations for the user."""
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session["user_id"]
    conversations = Conversation.query.filter_by(user_id=user_id)\
        .order_by(Conversation.updated_at.desc())\
        .all()

    return jsonify({
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat(),
            }
            for c in conversations
        ]
    })


@app.route("/api/conversation/<int:conv_id>", methods=["GET"])
def get_conversation(conv_id):
    """Get a specific conversation with messages."""
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    conversation = Conversation.query.filter_by(
        id=conv_id, user_id=session["user_id"]
    ).first_or_404()

    messages = Message.get_conversation_messages(conversation.id)

    return jsonify({
        "conversation": {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat(),
        },
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ]
    })


@app.route("/api/rename-conversation", methods=["POST"])
def rename_conversation():
    """Rename a conversation."""
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    conv_id = data.get("conversation_id")
    new_title = data.get("title", "").strip()

    if not conv_id or not new_title:
        return jsonify({"error": "Missing conversation ID or title"}), 400

    conversation = Conversation.query.filter_by(
        id=conv_id, user_id=session["user_id"]
    ).first_or_404()

    conversation.title = new_title
    db.session.commit()

    return jsonify({
        "success": True,
        "title": conversation.title,
    })


@app.route("/api/delete-conversation", methods=["POST"])
def delete_conversation():
    """Delete a conversation."""
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    conv_id = data.get("conversation_id")

    if not conv_id:
        return jsonify({"error": "Missing conversation ID"}), 400

    conversation = Conversation.query.filter_by(
        id=conv_id, user_id=session["user_id"]
    ).first_or_404()

    db.session.delete(conversation)
    db.session.commit()

    return jsonify({"success": True})


@app.route("/api/copy-response", methods=["POST"])
def copy_response():
    """Mark a response for copying (client-side)."""
    data = request.get_json()
    response_text = data.get("response", "")
    # Just return the text for the client to copy
    return jsonify({"success": True, "response": response_text})


@app.route("/api/export-markdown/<int:conv_id>")
def export_markdown(conv_id):
    """Export conversation as Markdown."""
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    conversation = Conversation.query.filter_by(
        id=conv_id, user_id=session["user_id"]
    ).first_or_404()

    messages = Message.get_conversation_messages(conv_id)

    markdown_lines = []
    for msg in messages:
        role_label = "You" if msg.role == "user" else "Assistant"
        markdown_lines.append(f"**{role_label}** ({msg.created_at.strftime('%Y-%m-%d %H:%M') if msg.created_at else '?'}):")
        markdown_lines.append(msg.content)
        markdown_lines.append("")  # blank line

    markdown_content = "\n".join(markdown_lines)

    return jsonify({
        "success": True,
        "markdown": markdown_content,
        "title": conversation.title,
    })


@app.route("/api/stats")
def stats():
    """Get user statistics."""
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session["user_id"]
    total_conversations = Conversation.query.filter_by(user_id=user_id).count()
    total_messages = Message.query.filter(
        Message.conversation_id.in_(
            db.session.query(Conversation.id).filter_by(user_id=user_id)
        )
    ).count()

    return jsonify({
        "total_conversations": total_conversations,
        "total_messages": total_messages,
    })


@app.route("/logout")
def logout():
    """User logout."""
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# Error handlers
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(e):
    return render_template("500.html"), 500


if __name__ == "__main__":
    # Create instance directory if needed
    os.makedirs(os.path.join(basedir, "instance"), exist_ok=True)
    with app.app_context():
        db.create_all()
    app.run(host=os.getenv("HOST", "127.0.0.1"),
            port=int(os.getenv("PORT", 5000)),
            debug=os.getenv("FLASK_DEBUG", "False").lower() == "true")