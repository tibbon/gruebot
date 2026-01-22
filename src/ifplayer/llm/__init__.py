"""LLM interface backends."""

from ifplayer.llm.anthropic_api import AnthropicAPIBackend
from ifplayer.llm.claude_cli import ClaudeCLIBackend, ClaudeCLIError
from ifplayer.llm.prompts import (
    ParsedResponse,
    format_game_output,
    get_summarization_prompt,
    get_system_prompt,
    parse_response,
)
from ifplayer.llm.protocol import ConversationTurn, LLMInterface, LLMResponse

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
