"""Claude CLI backend for LLM interface."""

import asyncio
import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from ifplayer.llm.prompts import (
    get_summarization_prompt,
    get_system_prompt,
    parse_response,
)
from ifplayer.llm.protocol import ConversationTurn, LLMResponse


class ClaudeCLIError(Exception):
    """Error from Claude CLI."""


class ClaudeCLIBackend:
    """LLM backend using the Claude Code CLI.

    This backend shells out to the `claude` CLI tool, providing
    context via stdin or temp files.
    """

    def __init__(
        self,
        claude_path: str | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> None:
        """Initialize the Claude CLI backend.

        Args:
            claude_path: Path to claude executable (auto-detected if None).
            model: Model to use (uses CLI default if None).
            max_tokens: Maximum tokens in response.
        """
        self.claude_path = claude_path or self._find_claude()
        self.model = model
        self.max_tokens = max_tokens

    def _find_claude(self) -> str:
        """Find the claude CLI executable.

        Returns:
            Path to claude executable.

        Raises:
            ClaudeCLIError: If claude is not found.
        """
        path = shutil.which("claude")
        if path is None:
            raise ClaudeCLIError("Claude CLI not found. Install it from https://claude.ai/code")
        return path

    async def send(
        self,
        messages: list[ConversationTurn],
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Send messages and get a response.

        Args:
            messages: Conversation history.
            system_prompt: Optional system prompt override.

        Returns:
            LLMResponse with extracted command.
        """
        if system_prompt is None:
            system_prompt = get_system_prompt()

        # Build the prompt content
        prompt_content = self._build_prompt(messages, system_prompt)

        # Run claude CLI
        raw_text = await self._run_claude(prompt_content)

        # Parse the response
        parsed = parse_response(raw_text)

        return LLMResponse(
            raw_text=parsed.raw_text,
            command=parsed.command,
            reasoning=parsed.reasoning,
            is_meta=parsed.is_meta,
        )

    async def send_streaming(
        self,
        messages: list[ConversationTurn],
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream response text.

        Note: Claude CLI doesn't support true streaming, so this
        returns the full response at once.

        Args:
            messages: Conversation history.
            system_prompt: Optional system prompt override.

        Yields:
            Text (single chunk with full response).
        """
        response = await self.send(messages, system_prompt)
        yield response.raw_text

    async def summarize(
        self,
        history: list[ConversationTurn],
        previous_summary: str | None = None,
        max_tokens: int = 500,  # noqa: ARG002 - CLI doesn't support token limits
    ) -> str:
        """Generate a summary of game history.

        Args:
            history: Conversation turns to summarize.
            previous_summary: Previous summary to incorporate.
            max_tokens: Maximum tokens for summary (not enforced by CLI).

        Returns:
            Summary text.
        """
        system_prompt = get_summarization_prompt(previous_summary)
        history_text = self._format_history_for_summary(history)

        # Note: max_tokens is part of protocol but CLI doesn't support it directly
        prompt = f"{system_prompt}\n\nPlease summarize this game session (keep it concise):\n\n{history_text}"

        return await self._run_claude(prompt)

    def _build_prompt(
        self,
        messages: list[ConversationTurn],
        system_prompt: str,
    ) -> str:
        """Build the full prompt from messages.

        Args:
            messages: Conversation history.
            system_prompt: System prompt.

        Returns:
            Combined prompt string.
        """
        parts = [system_prompt, ""]

        for turn in messages:
            if turn.role == "user":
                parts.append(f"GAME OUTPUT:\n{turn.content}")
            elif turn.role == "assistant":
                parts.append(f"YOUR PREVIOUS RESPONSE:\n{turn.content}")
            elif turn.role == "system":
                parts.append(f"[SYSTEM NOTE: {turn.content}]")
            parts.append("")

        parts.append("Please provide your next command.")

        return "\n".join(parts)

    async def _run_claude(self, prompt: str) -> str:
        """Run the claude CLI with the given prompt.

        Args:
            prompt: The prompt to send.

        Returns:
            Claude's response text.

        Raises:
            ClaudeCLIError: If the CLI fails.
        """
        # Write prompt to temp file (safer for long prompts)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(prompt)
            prompt_file = Path(f.name)

        try:
            # Build command
            cmd = [self.claude_path, "--print"]

            if self.model:
                cmd.extend(["--model", self.model])

            # Use --dangerously-skip-permissions for non-interactive use
            cmd.append("--dangerously-skip-permissions")

            # Read prompt from file
            cmd.extend(["--input-file", str(prompt_file)])

            # Run the command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                raise ClaudeCLIError(f"Claude CLI failed: {error_msg}")

            return stdout.decode("utf-8", errors="replace").strip()

        finally:
            # Clean up temp file
            prompt_file.unlink(missing_ok=True)

    def _format_history_for_summary(self, history: list[ConversationTurn]) -> str:
        """Format conversation history for summarization.

        Args:
            history: Conversation turns.

        Returns:
            Formatted history text.
        """
        lines = []
        for turn in history:
            if turn.role == "user":
                lines.append(f"GAME: {turn.content}")
            elif turn.role == "assistant":
                lines.append(f"PLAYER: {turn.content}")
            else:
                lines.append(f"[{turn.role.upper()}]: {turn.content}")
        return "\n\n".join(lines)
