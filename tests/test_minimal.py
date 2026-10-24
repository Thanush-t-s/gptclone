"""Minimal tests for the AI Chat application.

Verifies core imports and model structures work correctly.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_app_create():
    """Test that the Flask app creates successfully."""
    from app import app
    assert app is not None
    assert app.config is not None
    print("✓ Flask app created successfully")


def test_config_keys():
    """Test that required config keys exist."""
    from app import app
    assert app.config.get("SECRET_KEY") is not None
    assert app.config.get("SQLALCHEMY_DATABASE_URI") is not None
    print("✓ Required config keys present")


def test_model_imports():
    """Test that all models can be imported."""
    from models import User, Conversation, Message
    assert User is not None
    assert Conversation is not None
    assert Message is not None
    print("✓ All models imported successfully")


def test_model_attributes():
    """Test that models have expected attributes."""
    from models import User, Conversation, Message
    
    # User model
    assert hasattr(User, 'username')
    assert hasattr(User, 'password_hash')
    assert hasattr(User, 'set_password')
    assert hasattr(User, 'check_password')
    
    # Conversation model
    assert hasattr(Conversation, 'title')
    assert hasattr(Conversation, 'created_at')
    assert hasattr(Conversation, 'updated_at')
    
    # Message model
    assert hasattr(Message, 'role')
    assert hasattr(Message, 'content')
    assert hasattr(Message, 'created_at')
    
    print("✓ Model attributes are correct")


def test_service_imports():
    """Test that services can be imported."""
    from services.gemini_service import GeminiService
    assert GeminiService is not None
    print("✓ Gemini service imported successfully")


def test_route_existence():
    """Test that key routes exist on the app."""
    from app import app
    with app.test_client() as client:
        # Test that basic routes are registered
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert any('/login' in rule for rule in rules)
        assert any('/register' in rule for rule in rules)
        assert any('/chat' in rule for rule in rules)
        assert any('/api/' in rule for rule in rules)
    
    print("✓ Routes are registered")


def test_instance_dir():
    """Test that instance directory can be created."""
    basedir = os.path.dirname(os.path.abspath(__file__))
    instance_dir = os.path.join(basedir, 'instance')
    os.makedirs(instance_dir, exist_ok=True)
    assert os.path.isdir(instance_dir)
    print("✓ Instance directory exists")


if __name__ == "__main__":
    print("=" * 60)
    print("AI Chat Application Minimal Tests")
    print("=" * 60)
    
    tests = [
        test_app_create,
        test_config_keys,
        test_model_imports,
        test_model_attributes,
        test_service_imports,
        test_route_existence,
        test_instance_dir,
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