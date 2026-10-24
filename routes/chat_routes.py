"""Chat routes for the AI Chat application.

Handles message sending, conversation management, and AI integration.
Registered on the 'chat' blueprint.
"""


def init_routes(chat_bp):
    """Initialize chat routes with the given blueprint.
    
    Note: Routes are registered using add_url_rule inside this function
    to avoid decorator evaluation at import time.
    """
    from services.gemini_service import GeminiService
    gemini_service = GeminiService()

    # ---------------------------------------------------------------------------
    # Chat message endpoint
    # ---------------------------------------------------------------------------

    def send_message():
        """Send a message and get a response from Gemini."""
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized"}), 401

        user_id = session["user_id"]
        from flask import request, jsonify
        data = request.get_json()
        if not data or "message" not in data:
            return jsonify({"error": "No message provided"}), 400

        user_message = data["message"].strip()
        if not user_message:
            return jsonify({"error": "Empty message"}), 400

        conversation_id = data.get("conversation_id")
        if conversation_id:
            from models import Conversation
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
            from extensions import db
            db.session.add(conversation)
            db.session.commit()

        # Save user message
        from models import Message
        user_msg = Message(
            role="user",
            content=user_message,
            conversation_id=conversation.id,
        )
        db.session.add(user_msg)
        db.session.commit()

        # Limit conversation history
        messages = Message.get_conversation_messages(
            conversation.id, limit=int(os.getenv("HISTORY_MESSAGE_LIMIT", 20))
        )

        # Get AI response
        try:
            response_text, new_conversation = gemini_service.get_response(
                conversation_id=conversation.id,
                user_messages=messages,
                model_name=os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-flash"),
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
            from extensions import db
            db.session.rollback()
            db.session.commit()
            return jsonify({
                "success": False,
                "error": str(e),
            }), 500

    chat_bp.add_url_rule("/api/send-message", view_func=send_message, methods=["POST"])

    # ---------------------------------------------------------------------------
    # Conversation endpoints
    # ---------------------------------------------------------------------------

    def list_conversations():
        """List all conversations for the user."""
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        user_id = session["user_id"]
        from models import Conversation
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

    chat_bp.add_url_rule("/api/conversations", view_func=list_conversations, methods=["GET"])

    def get_conversation(conv_id):
        """Get a specific conversation with messages."""
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        user_id = session["user_id"]
        from models import Conversation
        conversation = Conversation.query.filter_by(
            id=conv_id, user_id=user_id
        ).first_or_404()

        from models import Message
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

    chat_bp.add_url_rule("/api/conversation/<int:conv_id>", view_func=get_conversation, methods=["GET"])

    def rename_conversation():
        """Rename a conversation."""
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        user_id = session["user_id"]
        data = request.get_json()
        conv_id = data.get("conversation_id")
        new_title = data.get("title", "").strip()

        if not conv_id or not new_title:
            return jsonify({"error": "Missing conversation ID or title"}), 400

        from models import Conversation
        conversation = Conversation.query.filter_by(
            id=conv_id, user_id=user_id
        ).first_or_404()

        conversation.title = new_title
        db.session.commit()

        return jsonify({
            "success": True,
            "title": conversation.title,
        })

    chat_bp.add_url_rule("/api/rename-conversation", view_func=rename_conversation, methods=["POST"])

    def delete_conversation():
        """Delete a conversation."""
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        user_id = session["user_id"]
        data = request.get_json()
        conv_id = data.get("conversation_id")

        if not conv_id:
            return jsonify({"error": "Missing conversation ID"}), 400

        from models import Conversation
        conversation = Conversation.query.filter_by(
            id=conv_id, user_id=user_id
        ).first_or_404()

        db.session.delete(conversation)
        db.session.commit()

        return jsonify({"success": True})

    chat_bp.add_url_rule("/api/delete-conversation", view_func=delete_conversation, methods=["POST"])

    @chat_bp.route("/api/export-markdown/<int:conv_id>")
    def export_markdown(conv_id):
        """Export conversation as Markdown."""
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        user_id = session["user_id"]
        from models import Conversation
        conversation = Conversation.query.filter_by(
            id=conv_id, user_id=user_id
        ).first_or_404()

        from models import Message
        messages = Message.get_conversation_messages(conv_id)

        markdown_lines = []
        for msg in messages:
            role_label = "You" if msg.role == "user" else "Assistant"
            markdown_lines.append(f"**{role_label}** ({msg.created_at.strftime('%Y-%m-%d %H:%M') if msg.created_at else '?'}):**")
            markdown_lines.append(msg.content)
            markdown_lines.append("")  # blank line

        markdown_content = "\n".join(markdown_lines)

        return jsonify({
            "success": True,
            "markdown": markdown_content,
            "title": conversation.title,
        })

    chat_bp.add_url_rule("/api/export-markdown/<int:conv_id>", view_func=export_markdown, methods=["GET"])

    def stats():
        """Get user statistics."""
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        user_id = session["user_id"]
        from models import Conversation
        total_conversations = Conversation.query.filter_by(user_id=user_id).count()
        total_messages = Message.query.filter_by(
            conversation_id__in(
                db.session.query(Conversation.id).filter_by(user_id=user_id)
            )
        ).count()

        return jsonify({
            "total_conversations": total_conversations,
            "total_messages": total_messages,
        })

    chat_bp.add_url_rule("/api/stats", view_func=stats)