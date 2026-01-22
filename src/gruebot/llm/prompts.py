"""System prompts and response parsing for LLM interfaces."""

import re
from dataclasses import dataclass


@dataclass
class ParsedResponse:
    """Parsed LLM response with extracted command and reasoning."""

    raw_text: str
    command: str | None
    reasoning: str | None
    is_meta: bool = False


# System prompt for playing interactive fiction
SYSTEM_PROMPT = """\
You are playing an interactive fiction (text adventure) game. Your goal is to \
explore the game world, solve puzzles, and progress through the story.

## How to Play

You will receive the game's text output, and you must respond with a single \
command to send to the game. Interactive fiction games understand simple \
English commands like:

**Movement:** north, south, east, west, up, down, n, s, e, w, u, d
**Actions:** look, examine [object], take [object], drop [object], open [door], \
read [book], use [item], talk to [person]
**Inventory:** inventory, i
**Meta:** save, restore, quit

## Response Format

Think through what you observe and what you should do, then provide your command.
Put your final command on its own line, prefixed with "COMMAND:".

Example response:
```
I see a brass lantern on the ground. This might be useful for exploring dark areas.
Let me pick it up.

COMMAND: take lantern
```

## Tips

- Examine objects carefully - they often contain clues
- Map the environment mentally as you explore
- Try different approaches if you get stuck
- Pay attention to descriptions - important details are often hidden in the text

## Current Game
"""


def get_system_prompt(
    game_title: str | None = None,
    turn_count: int = 0,
    additional_context: str | None = None,
) -> str:
    """Generate the system prompt for the LLM.

    Args:
        game_title: Title of the game being played.
        turn_count: Current turn number.
        additional_context: Additional context to include.

    Returns:
        Complete system prompt.
    """
    prompt = SYSTEM_PROMPT

    if game_title:
        prompt += f"\nGame: {game_title}"

    if turn_count > 0:
        prompt += f"\nTurn: {turn_count}"

    if additional_context:
        prompt += f"\n\n{additional_context}"

    return prompt


def get_summarization_prompt(
    previous_summary: str | None = None,
) -> str:
    """Generate the prompt for summarizing game history.

    Args:
        previous_summary: Previous summary to incorporate.

    Returns:
        Summarization system prompt.
    """
    prompt = """\
You are summarizing an interactive fiction game session. Your summary should help \
the player continue from where they left off.

Include in your summary:
- Key locations visited and their notable features
- Important items found or used
- Puzzles encountered and their solutions (if solved)
- Current objectives or goals the player seems to be pursuing
- Any important NPCs or conversations
- Current state/situation in the game

Keep the summary concise but preserve all critical information needed to continue \
playing effectively.
"""

    if previous_summary:
        prompt += f"\n\nPrevious summary to incorporate:\n{previous_summary}"

    return prompt


# Pattern to extract the command from LLM response
# Matches "COMMAND: something" or "COMMAND:something" (case insensitive)
COMMAND_PATTERN = re.compile(
    r"^COMMAND:\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)

# Patterns for meta commands (save, restore, quit)
META_COMMANDS = frozenset({"save", "restore", "quit", "restart"})


def parse_response(text: str) -> ParsedResponse:
    """Parse an LLM response to extract the command.

    Args:
        text: Raw LLM response text.

    Returns:
        ParsedResponse with extracted command and reasoning.
    """
    # Look for explicit COMMAND: prefix
    match = COMMAND_PATTERN.search(text)

    if match:
        command = match.group(1).strip()
        # Everything before the command is reasoning
        reasoning = text[: match.start()].strip() or None

        # Check if it's a meta command
        is_meta = command.lower().split()[0] in META_COMMANDS if command else False

        return ParsedResponse(
            raw_text=text,
            command=command,
            reasoning=reasoning,
            is_meta=is_meta,
        )

    # Fallback: try to extract command from the last line
    lines = text.strip().split("\n")
    if lines:
        last_line = lines[-1].strip()
        # If last line looks like a command (short, no punctuation except for objects)
        if last_line and len(last_line) < 50 and not last_line.endswith((".", "?", "!")):
            command = last_line
            reasoning = "\n".join(lines[:-1]).strip() or None

            is_meta = command.lower().split()[0] in META_COMMANDS if command else False

            return ParsedResponse(
                raw_text=text,
                command=command,
                reasoning=reasoning,
                is_meta=is_meta,
            )

    # No command found
    return ParsedResponse(
        raw_text=text,
        command=None,
        reasoning=text.strip() or None,
        is_meta=False,
    )


def format_game_output(
    output: str,
    location: str | None = None,
    turn_number: int | None = None,
) -> str:
    """Format game output for the LLM.

    Args:
        output: Raw game output text.
        location: Current location name.
        turn_number: Current turn number.

    Returns:
        Formatted output string.
    """
    parts = []

    if turn_number is not None:
        parts.append(f"[Turn {turn_number}]")

    if location:
        parts.append(f"[Location: {location}]")

    parts.append(output)

    return "\n".join(parts)
