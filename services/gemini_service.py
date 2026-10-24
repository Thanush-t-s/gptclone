"""
Gemini AI Service using LangChain.

Handles:
- Model initialization and configuration
- Conversation context management
- Streaming AI responses
- System instructions
- Error handling
"""

import os
import logging
from typing import Optional, Generator, List, Dict, Any

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, \
    BaseMessage, messages_to_dict
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_google_genai import ChatGoogleGenerativeAI

from extensions import db
from models import Conversation, Message


logger = logging.getLogger(__name__)


class GeminiService:
    """
    Service class for Google Gemini integration via LangChain.
    
    Features:
    - Configurable model name
    - System instruction support
    - Conversation history management
    - Streaming responses
    - Token usage control via history limits
    """

    def __init__(self):
        """Initialize the Gemini service with API key from environment."""
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key or self.api_key == "your_google_api_key_here":
            raise ValueError(
                "GOOGLE_API_KEY environment variable not set. "
                "Please set it in your .env file."
            )

        self.model_name = os.getenv(
            "GEMINI_MODEL_NAME", "gemini-2.5-flash"
        )
        self.temperature = float(
            os.getenv("GEMINI_TEMPERATURE", "0.7")
        )
        self.max_output_tokens = int(
            os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "8192")
        )

        # Initialize the LangChain Gemini chat model
        self._llm = None
        self._init_llm()

    def _init_llm(self):
        """Initialize the LangChain Gemini model."""
        try:
            self._llm = ChatGoogleGenerativeAI(
                model=self.model_name,
                google_api_key=self.api_key,
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
                # streaming=True,  # Handled at request level
            )
            logger.info(
                f"Gemini model initialized: {self.model_name}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Gemini model: {e}")
            raise

    @property
    def llm(self):
        """Get the LangChain LLM instance."""
        return self._llm

    def set_model(self, model_name: str):
        """Change the Gemini model dynamically."""
        self.model_name = model_name
        self._llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=self.api_key,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
        )
        logger.info(f"Model changed to: {model_name}")

    def get_system_prompt(self) -> str:
        """Get the system instruction/prompt for the assistant."""
        # Default system prompt - can be configured
        return os.getenv(
            "GEMINI_SYSTEM_PROMPT",
            """You are a helpful AI assistant. Provide clear, concise, and accurate
            responses. Support markdown formatting for headings, lists, code blocks,
            tables, and links. Be helpful and respectful in your responses."""
        )

    @staticmethod
    def content_to_text(content) -> str:
        """Normalize LangChain message content into a plain string.

        Depending on the model/version, ``AIMessage.content`` may be:
          * a plain ``str``, or
          * a ``list`` of content blocks such as
            ``[{"type": "text", "text": "..."}]`` or block objects.

        Returning the raw value unchanged would make downstream ``.strip()``
        raise ``AttributeError`` (a 500 "response display error") or, worse,
        render unwanted characters like ``{'type': 'text', ...}``. This helper
        always yields a clean string.
        """
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, (list, tuple)):
            parts: List[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                    continue
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                        continue
                    inner = block.get("content")
                    if isinstance(inner, str):
                        parts.append(inner)
                        continue
                    continue
                # Objects exposing a .text attribute (e.g. content-part dataclasses)
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    parts.append(text)
            return "".join(parts)
        # Any other scalar type — stringify defensively
        return str(content)

    def get_response(
        self,
        conversation_id: int,
        user_messages: List[Message],
        model_name: Optional[str] = None,
    ) -> tuple[str, Optional[Conversation]]:
        """
        Get an AI response for the given conversation.

        Args:
            conversation_id: The conversation ID
            user_messages: List of Message objects from the conversation
            model_name: Optional model name override

        Returns:
            Tuple of (response_text, conversation)
        """
        # Use provided model name or default
        target_model = model_name or self.model_name

        # Get the system prompt
        system_prompt = self.get_system_prompt()

        # Build ONLY the conversation turns here. The system prompt is injected
        # once by the ChatPromptTemplate below -- prepending a SystemMessage to
        # this list as well would send the system instruction TWICE, which is a
        # known source of duplicated/garbled model output.
        langchain_messages = []

        # Add conversation messages
        for msg in user_messages:
            if msg.role == "user":
                langchain_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                langchain_messages.append(AIMessage(content=msg.content))

        try:
            # Create a chat prompt template that includes the system prompt
            # and conversation history
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            )

            # Build the chain
            chain = prompt | self._llm

            # Invoke the chain with the conversation messages
            result = chain.invoke({"messages": langchain_messages})

            # Extract the response text (normalize list/str content safely)
            response_text = self.content_to_text(getattr(result, "content", result))

            # Handle empty responses
            if not response_text or not response_text.strip():
                raise ValueError("Received empty response from Gemini API")

            return response_text.strip(), None

        except Exception as e:
            logger.error(
                f"Gemini API error for conversation {conversation_id}: {e}"
            )
            # Re-raise with more context or return a friendly error
            raise RuntimeError(
                f"Failed to get AI response: {str(e)}"
            )

    def get_streaming_response(
        self,
        conversation_id: int,
        user_messages: List[Message],
        model_name: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """
        Get a streaming AI response token by token.

        Args:
            conversation_id: The conversation ID
            user_messages: List of Message objects from the conversation
            model_name: Optional model name override

        Yields:
            Partial response text chunks as they arrive
        """
        # Use provided model name or default
        target_model = model_name or self.model_name

        # Get the system prompt
        system_prompt = self.get_system_prompt()

        # Build ONLY the conversation turns here. The system prompt is injected
        # once by the ChatPromptTemplate below -- prepending a SystemMessage to
        # this list as well would send the system instruction TWICE.
        langchain_messages = []

        for msg in user_messages:
            if msg.role == "user":
                langchain_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                langchain_messages.append(AIMessage(content=msg.content))

        try:
            # Create a chat prompt template
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            )

            # Bind streaming to the LLM
            llm = ChatGoogleGenerativeAI(
                model=target_model,
                google_api_key=self.api_key,
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
                # streaming enabled by default in ChatGoogleGenerativeAI
            )

            # Create the chain
            chain = prompt | llm

            # Stream the response. Chunks are normalized to plain strings --
            # chunk.content may be a list of content blocks with some models,
            # and whitespace-only chunks (newlines between Markdown blocks)
            # MUST be preserved or the streamed output loses its formatting.
            for chunk in chain.stream({"messages": langchain_messages}):
                text = self.content_to_text(getattr(chunk, "content", chunk))
                if text:
                    yield text

        except Exception as e:
            logger.error(
                f"Gemini streaming error for conversation {conversation_id}: {e}"
            )
            # RAISE instead of yielding "Error: ..." -- an error message yielded
            # as a normal chunk would be rendered to the user as Markdown text,
            # looking like a valid (but wrong) model response. The caller
            # converts this into a structured error event.
            raise RuntimeError(f"Failed to stream AI response: {str(e)}") from e