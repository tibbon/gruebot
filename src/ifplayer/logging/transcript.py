"""Transcript logging for game sessions."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TextIO


@dataclass
class TranscriptEntry:
    """A single entry in the transcript."""

    timestamp: str
    turn: int
    entry_type: str  # "game_output", "llm_response", "command", "error", "summary"
    content: str
    metadata: dict[str, str | int | None] = field(default_factory=dict)


class TranscriptLogger:
    """Dual-format transcript logger (JSON + Markdown).

    Logs game sessions in both JSON format (for replay/analysis)
    and Markdown format (for human reading).
    """

    def __init__(
        self,
        json_path: Path | None = None,
        markdown_path: Path | None = None,
        game_title: str | None = None,
    ) -> None:
        """Initialize the transcript logger.

        Args:
            json_path: Path for JSON transcript output.
            markdown_path: Path for Markdown transcript output.
            game_title: Title of the game being played.
        """
        self.json_path = json_path
        self.markdown_path = markdown_path
        self.game_title = game_title
        self._entries: list[TranscriptEntry] = []
        self._turn = 0
        self._md_file: TextIO | None = None
        self._start_time = datetime.now()

        # Initialize markdown file if path provided
        # Keep file open for streaming writes during session
        if markdown_path:
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            self._md_file = open(markdown_path, "w")  # noqa: SIM115
            self._write_markdown_header()

    def _write_markdown_header(self) -> None:
        """Write the markdown file header."""
        if self._md_file is None:
            return

        title = self.game_title or "Game Transcript"
        self._md_file.write(f"# {title}\n\n")
        self._md_file.write(f"Started: {self._start_time.isoformat()}\n\n")
        self._md_file.write("---\n\n")
        self._md_file.flush()

    def log_game_output(
        self,
        text: str,
        location: str | None = None,
    ) -> None:
        """Log game output.

        Args:
            text: Game output text.
            location: Current location if known.
        """
        entry = TranscriptEntry(
            timestamp=datetime.now().isoformat(),
            turn=self._turn,
            entry_type="game_output",
            content=text,
            metadata={"location": location} if location else {},
        )
        self._add_entry(entry)

        # Markdown format
        if self._md_file:
            self._md_file.write(f"### Turn {self._turn}\n\n")
            if location:
                self._md_file.write(f"*Location: {location}*\n\n")
            self._md_file.write("**Game:**\n")
            self._md_file.write(f"```\n{text}\n```\n\n")
            self._md_file.flush()

    def log_llm_response(
        self,
        raw_text: str,
        command: str | None = None,
        reasoning: str | None = None,
    ) -> None:
        """Log LLM response and command.

        Args:
            raw_text: Full LLM response text.
            command: Extracted command if any.
            reasoning: LLM's reasoning/thoughts.
        """
        entry = TranscriptEntry(
            timestamp=datetime.now().isoformat(),
            turn=self._turn,
            entry_type="llm_response",
            content=raw_text,
            metadata={
                "command": command,
                "reasoning": reasoning,
            },
        )
        self._add_entry(entry)

        # Markdown format
        if self._md_file:
            if reasoning and reasoning != raw_text:
                self._md_file.write(f"**Claude's reasoning:**\n{reasoning}\n\n")
            if command:
                self._md_file.write(f"**Command:** `{command}`\n\n")
            self._md_file.flush()

        self._turn += 1

    def log_command(self, command: str) -> None:
        """Log a command sent to the game.

        Args:
            command: The command sent.
        """
        entry = TranscriptEntry(
            timestamp=datetime.now().isoformat(),
            turn=self._turn,
            entry_type="command",
            content=command,
        )
        self._add_entry(entry)

    def log_summary(self, summary: str) -> None:
        """Log when summarization occurs.

        Args:
            summary: The generated summary.
        """
        entry = TranscriptEntry(
            timestamp=datetime.now().isoformat(),
            turn=self._turn,
            entry_type="summary",
            content=summary,
        )
        self._add_entry(entry)

        if self._md_file:
            self._md_file.write(f"---\n\n*[Summary generated at turn {self._turn}]*\n\n")
            self._md_file.write(f"> {summary.replace(chr(10), chr(10) + '> ')}\n\n")
            self._md_file.write("---\n\n")
            self._md_file.flush()

    def log_error(self, error_type: str, message: str) -> None:
        """Log an error.

        Args:
            error_type: Type of error.
            message: Error message.
        """
        entry = TranscriptEntry(
            timestamp=datetime.now().isoformat(),
            turn=self._turn,
            entry_type="error",
            content=message,
            metadata={"error_type": error_type},
        )
        self._add_entry(entry)

        if self._md_file:
            self._md_file.write(f"> **Error ({error_type}):** {message}\n\n")
            self._md_file.flush()

    def log_system_note(self, note: str) -> None:
        """Log a system note.

        Args:
            note: System note content.
        """
        entry = TranscriptEntry(
            timestamp=datetime.now().isoformat(),
            turn=self._turn,
            entry_type="system",
            content=note,
        )
        self._add_entry(entry)

        if self._md_file:
            self._md_file.write(f"*[System: {note}]*\n\n")
            self._md_file.flush()

    def _add_entry(self, entry: TranscriptEntry) -> None:
        """Add an entry to the transcript.

        Args:
            entry: Entry to add.
        """
        self._entries.append(entry)

    def get_entries(self) -> list[TranscriptEntry]:
        """Get all transcript entries.

        Returns:
            List of transcript entries.
        """
        return self._entries.copy()

    def finalize(self) -> None:
        """Finalize and close transcript files."""
        end_time = datetime.now()

        # Write JSON transcript
        if self.json_path:
            self.json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.json_path, "w") as f:
                json.dump(
                    {
                        "game_title": self.game_title,
                        "start_time": self._start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "total_turns": self._turn,
                        "entries": [asdict(e) for e in self._entries],
                    },
                    f,
                    indent=2,
                )

        # Close markdown file
        if self._md_file:
            self._md_file.write("\n---\n\n")
            self._md_file.write(f"Completed: {end_time.isoformat()}\n")
            self._md_file.write(f"Total turns: {self._turn}\n")
            self._md_file.close()
            self._md_file = None

    def __enter__(self) -> "TranscriptLogger":
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Context manager exit."""
        self.finalize()


def create_transcript_paths(
    base_dir: Path,
    game_name: str,
    session_id: str | None = None,
) -> tuple[Path, Path]:
    """Create paths for transcript files.

    Args:
        base_dir: Base directory for transcripts.
        game_name: Name of the game.
        session_id: Optional session identifier.

    Returns:
        Tuple of (json_path, markdown_path).
    """
    if session_id is None:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Sanitize game name for filename
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in game_name)

    json_path = base_dir / f"{safe_name}_{session_id}.json"
    markdown_path = base_dir / f"{safe_name}_{session_id}.md"

    return json_path, markdown_path
