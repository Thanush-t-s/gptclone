"""Authentication routes for the AI Chat application.

Handles user registration, login, and logout.
Registered on the 'auth' blueprint.
"""


def init_routes(auth_bp):
    """Initialize auth routes with the given blueprint.
    
    Note: Routes are registered using add_url_rule inside this function
    to avoid decorator evaluation at import time.
    """

    # ---------------------------------------------------------------------------
    # Register route
    # ---------------------------------------------------------------------------

    def register():
        """User registration page."""
        from flask import request, redirect, url_for, flash
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm", "")

            if not username or not password:
                flash("Please enter all required fields.", "error")
                return redirect(url_for("auth.register"))

            if password != confirm:
                flash("Passwords do not match.", "error")
                return redirect(url_for("auth.register"))

            from models import User
            if User.query.filter_by(username=username).first():
                flash("Username already exists. Please choose another.", "error")
                return redirect(url_for("auth.register"))

            try:
                user = User(username=username)
                user.set_password(password)
                from extensions import db
                db.session.add(user)
                db.session.commit()
                flash("Registration successful! Please log in.", "success")
                return redirect(url_for("auth.login"))
            except Exception as e:
                from extensions import db
                db.session.rollback()
                flash(f"Error during registration: {str(e)}", "error")

        return redirect(url_for("auth.login"))

    auth_bp.add_url_rule("/register", view_func=register, methods=["GET", "POST"])

    # ---------------------------------------------------------------------------
    # Login route
    # ---------------------------------------------------------------------------

    def login():
        """User login page."""
        from flask import request, redirect, url_for, flash
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            if not username or not password:
                flash("Please enter both username and password.", "error")
                return redirect(url_for("auth.login"))

            from models import User
            user = User.query.filter_by(username=username).first()
            from werkzeug.security import check_password_hash
            if user and check_password_hash(user.password_hash, password):
                session["user_id"] = user.id
                session["username"] = user.username
                flash(f"Welcome back, {username}!", "success")
                return redirect(url_for("main.chat"))
            else:
                flash("Invalid username or password.", "error")

        return redirect(url_for("auth.login"))

    auth_bp.add_url_rule("/login", view_func=login, methods=["GET", "POST"])

    # ---------------------------------------------------------------------------
    # Logout route
    # ---------------------------------------------------------------------------

    def logout():
        """User logout."""
        session.clear()
        from flask import flash, redirect, url_for
        flash("You have been logged out.", "success")
        return redirect(url_for("auth.login"))

    auth_bp.add_url_rule("/logout", view_func=logout)