"""Tests for the AI Chat application.

Simple tests that verify the core functionality works.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db


def test_app_imports():
    """Test that the Flask app imports correctly."""
    assert app is not None
    print("✓ App imported successfully")


def test_models_imports():
    """Test that models can be imported."""
    from models import User, Conversation, Message
    assert User is not None
    assert Conversation is not None
    assert Message is not None
    print("✓ Models imported successfully")


def test_user_creation():
    """Test User model can be created and password hashing works."""
    from models import User
    with app.app_context():
        user = User(username="testuser123")
        user.set_password("mypassword123")
        
        assert user.check_password("mypassword123") is True
        assert user.check_password("wrongpassword") is False
        assert user.username == "testuser123"
    
    print("✓ User creation and password hashing works")


def test_database_tables_exist():
    """Test that database tables are created."""
    with app.app_context():
        # Create all tables if they don't exist
        db.create_all()
        
        from sqlalchemy import inspect
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        
        assert 'users' in tables, f"users table not found in {tables}"
        assert 'conversations' in tables, f"conversations table not found in {tables}"
        assert 'messages' in tables, f"messages table not found in {tables}"
    
    print("✓ Database tables exist")


def test_database_columns():
    """Test that database tables have expected columns."""
    with app.app_context():
        db.create_all()
        from sqlalchemy import inspect
        inspector = db.inspect(db.engine)
        
        # Check users table columns
        user_cols = [col['name'] for col in inspector.get_columns('users')]
        assert 'id' in user_cols
        assert 'username' in user_cols
        assert 'password_hash' in user_cols
        assert 'created_at' in user_cols
        
        # Check conversations table columns
        conv_cols = [col['name'] for col in inspector.get_columns('conversations')]
        assert 'id' in conv_cols
        assert 'title' in conv_cols
        assert 'user_id' in conv_cols
        assert 'created_at' in conv_cols
        assert 'updated_at' in conv_cols
        
        # Check messages table columns
        msg_cols = [col['name'] for col in inspector.get_columns('messages')]
        assert 'id' in msg_cols
        assert 'role' in msg_cols
        assert 'content' in msg_cols
        assert 'conversation_id' in msg_cols
        assert 'created_at' in msg_cols
    
    print("✓ Database columns are correct")


def test_gemini_service_class():
    """Test Gemini service class is accessible."""
    from services.gemini_service import GeminiService
    assert GeminiService is not None
    assert hasattr(GeminiService, 'get_response')
    assert hasattr(GeminiService, 'get_streaming_response')
    assert hasattr(GeminiService, 'set_model')
    
    print("✓ Gemini service class is accessible")


def test_conversation_title_generation():
    """Test conversation title generation from messages."""
    from models import Conversation
    
    # Test with no messages
    title = Conversation.get_title_from_initial_message([])
    assert title == "New Conversation"
    
    # Test with a user message
    from models import Message
    msg = Message(role="user", content="How do I learn Python?")
    title = Conversation.get_title_from_initial_message([msg])
    assert "Python" in title or "learn" in title.lower()
    
    # Test truncation with long message
    long_msg = Message(role="user", content="A" * 200)
    title = Conversation.get_title_from_initial_message([long_msg])
    assert len(title) <= 80
    
    print("✓ Conversation title generation works")


def test_message_retrieval():
    """Test that messages can be retrieved from conversation."""
    from models import User, Conversation, Message
    
    with app.app_context():
        db.create_all()
        
        # Clean up any leftover state from a previous run (idempotent test)
        User.query.filter_by(username="retriever").delete()
        db.session.commit()
        
        # Create user and conversation
        user = User(username="retriever")
        user.set_password("pass123")
        db.session.add(user)
        db.session.commit()
        
        conv = Conversation(title="Retrieval Test", user_id=user.id)
        db.session.add(conv)
        db.session.commit()
        
        # Add messages
        msg1 = Message(role="user", content="Hello", conversation_id=conv.id)
        msg2 = Message(role="assistant", content="Hi there!", conversation_id=conv.id)
        db.session.add_all([msg1, msg2])
        db.session.commit()
        
        # Retrieve messages
        messages = Message.get_conversation_messages(conv.id)
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
    
    print("✓ Message retrieval works")


if __name__ == "__main__":
    print("=" * 60)
    print("Running AI Chat Application Tests")
    print("=" * 60)
    
    tests = [
        test_app_imports,
        test_models_imports,
        test_user_creation,
        test_database_tables_exist,
        test_database_columns,
        test_gemini_service_class,
        test_conversation_title_generation,
        test_message_retrieval,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)