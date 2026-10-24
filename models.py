"""
Database models for the AI Chat application.
Uses SQLAlchemy ORM with SQLite.
"""

from datetime import datetime, timezone, timedelta
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from extensions import db


class User(db.Model):
    """User model with authentication credentials and security features."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False, index=True)
    email = db.Column(db.String(150), unique=True, nullable=True, index=True)
    full_name = db.Column(db.String(150), nullable=True)
    password_hash = db.Column(db.String(256), nullable=True)
    avatar_url = db.Column(db.String(500), nullable=True)
    auth_provider = db.Column(db.String(50), default="local")  # 'local', 'google', 'github'
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships - use back_populates instead of backref to avoid conflicts
    conversations = db.relationship(
        "Conversation", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )

    def set_password(self, password):
        """Hash and store the password using secure Werkzeug hashing."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify password against stored hash, supporting both Werkzeug and legacy SHA-256."""
        if not self.password_hash or not password:
            return False
        # Check if Werkzeug format (starts with scrypt:, pbkdf2:, etc.)
        if ":" in self.password_hash or "$" in self.password_hash:
            try:
                return check_password_hash(self.password_hash, password)
            except Exception:
                pass
        # Fallback to legacy SHA-256
        legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
        if legacy_hash == self.password_hash:
            # Upgrade hash automatically to Werkzeug
            self.set_password(password)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            return True
        return False

    def is_locked(self):
        """Check if account is temporarily locked due to failed login attempts."""
        if not self.locked_until:
            return False
        # Normalize timezone-naive or aware datetime
        now = datetime.now(timezone.utc)
        locked_time = self.locked_until
        if locked_time.tzinfo is None:
            locked_time = locked_time.replace(tzinfo=timezone.utc)
        return now < locked_time

    def seconds_remaining_locked(self):
        """Return integer seconds remaining until lock expires."""
        if not self.is_locked():
            return 0
        now = datetime.now(timezone.utc)
        locked_time = self.locked_until
        if locked_time.tzinfo is None:
            locked_time = locked_time.replace(tzinfo=timezone.utc)
        diff = (locked_time - now).total_seconds()
        return max(1, int(diff))

    def record_failed_attempt(self):
        """Increment failed attempts and lock out for 60 seconds if threshold reached."""
        self.failed_login_attempts = (self.failed_login_attempts or 0) + 1
        if self.failed_login_attempts >= 5:
            self.locked_until = datetime.now(timezone.utc) + timedelta(seconds=60)

    def reset_failed_attempts(self):
        """Clear failed attempts and unlock account."""
        self.failed_login_attempts = 0
        self.locked_until = None

    def get_reset_token(self, secret_key, salt="password-reset-salt"):
        """Generate a secure, time-limited token for password reset."""
        s = URLSafeTimedSerializer(secret_key)
        return s.dumps({"user_id": self.id, "email": self.email or self.username}, salt=salt)

    @staticmethod
    def verify_reset_token(token, secret_key, max_age_seconds=900, salt="password-reset-salt"):
        """Verify password reset token (valid for 15 minutes by default)."""
        s = URLSafeTimedSerializer(secret_key)
        try:
            data = s.loads(token, salt=salt, max_age=max_age_seconds)
            user_id = data.get("user_id")
            if not user_id:
                return None
            return db.session.get(User, user_id)
        except (SignatureExpired, BadSignature, Exception):
            return None

    def __repr__(self):
        return f"<User {self.username}>"



class Conversation(db.Model):
    """Conversation model representing a chat thread."""
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), default="New Conversation", nullable=False)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships - use back_populates instead of backref
    user = db.relationship("User", back_populates="conversations")
    messages = db.relationship(
        "Message", back_populates="conversation", lazy="dynamic", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Conversation {self.title}>"

    @staticmethod
    def get_title_from_initial_message(messages):
        """Generate a title from the first user message if no title set."""
        if not messages:
            return "New Conversation"

        # Get the first user message content
        first_user_msg = None
        for msg in messages:
            if msg.role == "user":
                first_user_msg = msg.content
                break

        if not first_user_msg:
            return "New Conversation"

        # Truncate to a reasonable title length
        title_text = first_user_msg.strip()
        if len(title_text) > 80:
            title_text = title_text[:77] + "..."

        return title_text or "New Conversation"


class Message(db.Model):
    """Individual message within a conversation."""
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(
        db.String(20), nullable=False
    )  # "user" or "assistant"
    content = db.Column(db.Text, nullable=False)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("conversations.id"), nullable=False, index=True
    )
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships - use back_populates
    conversation = db.relationship("Conversation", back_populates="messages", lazy="joined")

    @staticmethod
    def get_conversation_messages(conversation_id, limit=None):
        """Get messages for a conversation, ordered by creation time.

        When ``limit`` is given, the MOST RECENT ``limit`` messages are
        returned (still in chronological order). The previous implementation
        applied ``.asc().limit()``, which silently kept the OLDEST N and
        dropped the newest messages -- including the user message that was
        about to be answered -- so the model responded from stale context.
        ``id`` is used as a tiebreaker so messages written in the same
        microsecond still have a deterministic order.
        """
        if limit:
            recent = (
                Message.query.filter_by(conversation_id=conversation_id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(limit)
                .all()
            )
            recent.reverse()
            return recent

        return (
            Message.query.filter_by(conversation_id=conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .all()
        )

    @staticmethod
    def get_recent_messages(user_id, limit=20):
        """Get recent messages across user's conversations."""
        from models import Conversation

        conv_ids = db.session.query(Conversation.id).filter_by(user_id=user_id).all()
        if not conv_ids:
            return []

        # Get messages from all user's conversations
        query = Message.query.filter(
            Message.conversation_id.in_(conv_ids)
        ).order_by(Message.created_at.desc())

        if limit:
            query = query.limit(limit)

        return query.all()

    def __repr__(self):
        return f"<Message {self.role}: {self.content[:50]}...>"