"""Routes package for the AI Chat application.

Creates Flask blueprints for different functional areas and
registers route handlers from module files.
"""

from flask import Blueprint

# Create blueprints for different areas
main_bp = Blueprint("main", __name__)
chat_bp = Blueprint("chat", __name__)
auth_bp = Blueprint("auth", __name__)


def init_blueprints(app):
    """Initialize and register all blueprints with the Flask app."""
    # Register the blueprints on the app
    app.register_blueprint(main_bp)
    app.register_blueprint(chat_bp, url_prefix="/chat")
    app.register_blueprint(auth_bp, url_prefix="/auth")

    # Import and initialize route handlers
    from . import chat_routes, auth_routes
    chat_routes.init_routes(chat_bp)
    auth_routes.init_routes(auth_bp)