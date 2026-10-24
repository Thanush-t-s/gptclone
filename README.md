# AI Chatbot - ChatGPT-Style Web Application

A fully functional, ChatGPT-inspired AI chatbot web application powered by Google's Gemini API via LangChain.

## Table of Contents

1. [Project Overview](#project-overview)
2. [Technology Stack](#technology-stack)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
5. [Environment Setup](#environment-setup)
6. [Database Initialization](#database-initialization)
7. [Running the Application](#running-the-application)
8. [API Key Configuration](#api-key-configuration)
9. [Project Structure](#project-structure)
10. [Features](#features)
11. [Development](#development)

## Project Overview

This project is a ChatGPT-style AI chatbot web application that provides:

- **Modern UI** - ChatGPT-inspired interface with responsive design
- **Authentication** - User registration, login, and session management
- **Persistent Conversations** - SQLite-backed chat history that persists across sessions
- **Gemini AI Integration** - Google's Gemini API via LangChain
- **Streaming Responses** - AI responses displayed token by token
- **Conversation Management** - Create, rename, delete, and export conversations
- **Markdown Rendering** - Formatted AI responses with code highlighting
- **Theme Support** - Light and dark modes with user preference saving

## Technology Stack

### Backend
- **Flask** - Web framework
- **Flask-SQLAlchemy** - SQLAlchemy integration for Flask
- **Flask-Migrate** - Database migration support
- **LangChain** - LLM framework for model integration
- **google-genai** - Google Gemini API client

### AI Integration
- **Google Gemini** - Large language model via Google AI Studio
- **LangChain** - Model integration, prompt management, message history
- **Streaming** - Token-by-token response delivery

### Frontend
- **HTML5** - Markup structure
- **CSS3** - Styling with Tailwind CDN and custom styles
- **JavaScript** - Frontend interaction logic
- **Font Awesome** - Icons
- **Google Fonts** - Inter font family

### Development
- **Python 3.14** - Runtime environment
- **pytest** - Testing framework

## Prerequisites

- Python 3.14 or higher
- Google AI Studio API key (get free at [ai.google.dev](https://ai.google.dev))
- pip (Python package installer)

## Installation

1. **Clone the repository** (or download the project files):
   ```bash
   git clone https://github.com/your-username/ai-chatbot.git
   cd ai-chpt-style-chatbot
   ```

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install the application package** (if applicable):
   ```bash
   pip install -e .
   ```

## Environment Setup

1. **Copy the example environment file**:
   ```bash
   cp .env.example .env
   ```

2. **Edit the `.env` file** and add your Google API key:
   ```
   GOOGLE_API_KEY=your_google_api_key_here
   GEMINI_MODEL_NAME=gemini-1.5-flash
   ```

3. **Required environment variables**:
   - `GOOGLE_API_KEY` - Your Google AI Studio API key (REQUIRED)
   - `GEMINI_MODEL_NAME` - Gemini model to use (default: `gemini-1.5-flash`)
   - `SECRET_KEY` - Flask session secret (generated automatically if not set)
   - `FLASK_ENV` - Environment mode (`development` or `production`)
   - `FLASK_DEBUG` - Debug mode (`True` or `False`)
   - `HOST` - Server host (default: `127.0.0.1`)
   - `PORT` - Server port (default: `5000`)
   - `DATABASE_URL` - Database URL (optional, defaults to SQLite)
   - `GEMINI_TEMPERATURE` - Model temperature (default: `0.7`)
   - `GEMINI_MAX_OUTPUT_TOKENS` - Max output tokens (default: `8192`)

## Database Initialization

The application uses SQLite database by default. To initialize:

```bash
# Create the instance directory and database
python -c "from app import app, db; app.app_context(); db.create_all()"

# Or run the app once (it creates the database on startup)
python app.py
```

The database file `instance/chat.db` will be created automatically on first run.

## Running the Application

```bash
# Start the development server
python app.py
```

The application will be available at `http://127.0.0.1:5000` by default.

### Development Mode
```bash
FLASK_ENV=development FLASK_DEBUG=true python app.py
```

### Production Mode
```bash
FLASK_ENV=production python app.py
```

### Custom Port and Host
```bash
python app.py --port 3000 --host 0.0.0.0
```

## API Key Configuration

To use the Gemini AI functionality, you need an API key from [Google AI Studio](https://ai.google.dev):

1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Sign in with your Google account
3. Click "Get API key" 
4. Create a new API key or use an existing one
5. Copy the key and add it to your `.env` file:
   ```
   GOOGLE_API_KEY=your_actual_api_key_here
   ```

The application supports configurable model names. By default, it uses `gemini-1.5-flash`, but you can change it via the `GEMINI_MODEL_NAME` environment variable or in the settings panel.

## Project Structure

```
ai-chatbot/
├── app.py                  # Application entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Example environment configuration
├── .env                   # Environment variables (create from .env.example)
├── instance/              # SQLite database directory
├── README.md              # This file
│
├── routes/                # Route handlers
│   ├── __init__.py        # Package initialization
│   ├── auth_routes.py     # Authentication routes (register, login, logout)
│   └── chat_routes.py     # Chat routes (messages, conversations, AI integration)
│
├── services/              # Business logic services
│   └── gemini_service.py  # Gemini API integration via LangChain
│
├── models/                # Database models
│   └── models.py          # SQLAlchemy models (User, Conversation, Message)
│
├── static/                # Static assets
│   ├── css/               # Stylesheets
│   │   └── style.css      # Custom Tailwind overrides
│   └── js/                # JavaScript files
│       └── app.js         # Frontend interaction logic
│
├── templates/             # HTML templates
│   ├── base.html          # Base layout template
│   ├── chat.html          # Main chat interface
│   ├── login.html         # Login page
│   ├── register.html      # Registration page
│   ├── 404.html           # Error page - 404 Not Found
│   └── 500.html           # Error page - 500 Internal Server Error
│
└── tests/                 # Test suite
    ├── test_minimal.py    # Minimal import/functionality tests
    └── test_models.py     # Database model tests
```

## Features

### Authentication
- User registration with password hashing
- User login/logout with session management
- Secure password handling with SHA-256 hashing
- Session protection with HTTP-only cookies

### Chat Interface
- ChatGPT-inspired layout and interaction patterns
- Centered welcome screen with suggested prompts
- User messages and AI responses visually distinct
- Automatic scroll to latest message
- Multiline input that expands as you type
- Shift+Enter for new line, Enter-to-send
- Loading animation/typing indicator during AI generation
- Auto-focus input after sending message
- Responsive layout with appropriate spacing

### Conversation Management
- New chat creation
- Conversation history grouped by date
- Click to reopen previous conversations
- Rename conversations
- Delete conversations
- Search through conversation titles
- Export conversation as Markdown

### AI Features
- Google Gemini API integration via LangChain
- Configurable system instruction/behavior
- Conversation context retention
- Streaming responses (token-by-token display)
- Configurable history limit for token usage control
- Error handling for API failures, rate limits, network issues

### User Experience
- Light and dark mode support with preference saving
- Smooth theme transitions
- Suggested starter prompts
- Copy response to clipboard
- Regenerate response
- Message timestamps
- Keyboard accessible interface

### Responsive Design
- Collapsible sidebar for mobile/desktop
- Mobile-friendly conversation list
- Touch-friendly buttons and inputs
- Adaptive layout at different screen sizes

### Error Handling
- Graceful API error handling
- User-friendly error messages
- Retry capability for failed requests
- Preservation of messages on request failure
- Proper 404 and 500 error pages

### Security
- API key never exposed to frontend
- Input validation and sanitization
- XSS prevention for markdown rendering
- Password hashing
- CSRF protection consideration
- Parameterized database queries

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run specific test files
pytest tests/test_minimal.py
pytest tests/test_models.py
```

### Adding New Features

1. **Backend**: Add routes in `routes/chat_routes.py` or `app.py`, update services in `services/gemini_service.py`
2. **Frontend**: Add/modify templates in `templates/`, update styles in `static/css/style.css`, update logic in `static/js/app.js`
3. **Database**: Modify `models.py` for new data structures, create migrations with `flask db migrate`

### Code Style

- Follow Python PEP 8 style guidelines
- Use type hints where appropriate
- Document functions with docstrings
- Keep frontend and backend logic separated
- Use environment variables for configuration

## License

This project is for educational purposes. Please obtain your own Google AI Studio API key for production use.

## Acknowledgments

- Google Gemini API for language model capabilities
- LangChain for LLM framework and integration
- Tailwind CSS for responsive UI styling
- Font Awesome for icons
- Flask community for web framework