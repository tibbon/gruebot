"""LLM interface backends."""

from gruebot.llm.anthropic_api import AnthropicAPIBackend
from gruebot.llm.claude_cli import ClaudeCLIBackend, ClaudeCLIError
from gruebot.llm.prompts import (
    ParsedResponse,
    format_game_output,
    get_summarization_prompt,
    get_system_prompt,
    parse_response,
)
from gruebot.llm.protocol import ConversationTurn, LLMInterface, LLMResponse

__all__ = [
    "AnthropicAPIBackend",
    "ClaudeCLIBackend",
    "ClaudeCLIError",
    "ConversationTurn",
    "LLMInterface",
    "LLMResponse",
    "ParsedResponse",
    "format_game_output",
    "get_summarization_prompt",
    "get_system_prompt",
    "parse_response",
]
