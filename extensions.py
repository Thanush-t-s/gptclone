"""Extension initialization for the Flask application.

Provides helper functions for database operations.
"""

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def init_app(app):
    """Initialize the database with the Flask app."""
    db.init_app(app)


def create_all():
    """Create all database tables.
    
    Note: Caller must provide an app context if needed.
    """
    db.create_all()


def drop_all():
    """Drop all database tables."""
    db.drop_all()