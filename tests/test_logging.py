"""Tests for transcript logging."""

import json
import tempfile
from pathlib import Path

from ifplayer.logging.transcript import (
    TranscriptEntry,
    TranscriptLogger,
    create_transcript_paths,
)


class TestTranscriptEntry:
    """Tests for TranscriptEntry."""

    def test_entry_creation(self) -> None:
        """Test creating a transcript entry."""
        entry = TranscriptEntry(
            timestamp="2024-01-01T12:00:00",
            turn=5,
            entry_type="game_output",
            content="You are in a room.",
        )

        assert entry.timestamp == "2024-01-01T12:00:00"
        assert entry.turn == 5
        assert entry.entry_type == "game_output"
        assert entry.content == "You are in a room."
        assert entry.metadata == {}

    def test_entry_with_metadata(self) -> None:
        """Test entry with metadata."""
        entry = TranscriptEntry(
            timestamp="2024-01-01T12:00:00",
            turn=5,
            entry_type="llm_response",
            content="COMMAND: look",
            metadata={"command": "look", "reasoning": "I want to see the room"},
        )

        assert entry.metadata["command"] == "look"
        assert entry.metadata["reasoning"] == "I want to see the room"


class TestTranscriptLogger:
    """Tests for TranscriptLogger."""

    def test_init_no_files(self) -> None:
        """Test initialization without file output."""
        logger = TranscriptLogger()

        assert logger.json_path is None
        assert logger.markdown_path is None
        assert logger._entries == []
        assert logger._turn == 0

    def test_init_with_files(self) -> None:
        """Test initialization with file output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "test.json"
            md_path = Path(tmpdir) / "test.md"

            logger = TranscriptLogger(
                json_path=json_path,
                markdown_path=md_path,
                game_title="Test Game",
            )

            # Markdown file should be created
            assert md_path.exists()

            logger.finalize()

    def test_log_game_output(self) -> None:
        """Test logging game output."""
        logger = TranscriptLogger()

        logger.log_game_output("You are in a room.", location="Kitchen")

        entries = logger.get_entries()
        assert len(entries) == 1
        assert entries[0].entry_type == "game_output"
        assert entries[0].content == "You are in a room."
        assert entries[0].metadata["location"] == "Kitchen"

    def test_log_llm_response(self) -> None:
        """Test logging LLM response."""
        logger = TranscriptLogger()

        logger.log_llm_response(
            raw_text="Let me look around.\n\nCOMMAND: look",
            command="look",
            reasoning="Let me look around.",
        )

        entries = logger.get_entries()
        assert len(entries) == 1
        assert entries[0].entry_type == "llm_response"
        assert entries[0].metadata["command"] == "look"
        # Turn should increment after LLM response
        assert logger._turn == 1

    def test_log_command(self) -> None:
        """Test logging a command."""
        logger = TranscriptLogger()

        logger.log_command("go north")

        entries = logger.get_entries()
        assert len(entries) == 1
        assert entries[0].entry_type == "command"
        assert entries[0].content == "go north"

    def test_log_summary(self) -> None:
        """Test logging a summary."""
        logger = TranscriptLogger()

        logger.log_summary("Player explored the house and found a key.")

        entries = logger.get_entries()
        assert len(entries) == 1
        assert entries[0].entry_type == "summary"

    def test_log_error(self) -> None:
        """Test logging an error."""
        logger = TranscriptLogger()

        logger.log_error("game_crash", "Interpreter died unexpectedly")

        entries = logger.get_entries()
        assert len(entries) == 1
        assert entries[0].entry_type == "error"
        assert entries[0].metadata["error_type"] == "game_crash"

    def test_log_system_note(self) -> None:
        """Test logging a system note."""
        logger = TranscriptLogger()

        logger.log_system_note("You appear to be stuck.")

        entries = logger.get_entries()
        assert len(entries) == 1
        assert entries[0].entry_type == "system"

    def test_finalize_json(self) -> None:
        """Test finalizing with JSON output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "test.json"

            logger = TranscriptLogger(
                json_path=json_path,
                game_title="Test Game",
            )

            logger.log_game_output("Welcome!")
            logger.log_llm_response("COMMAND: look", command="look")
            logger.finalize()

            # Check JSON file
            assert json_path.exists()
            with open(json_path) as f:
                data = json.load(f)

            assert data["game_title"] == "Test Game"
            assert data["total_turns"] == 1
            assert len(data["entries"]) == 2

    def test_finalize_markdown(self) -> None:
        """Test finalizing with Markdown output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "test.md"

            logger = TranscriptLogger(
                markdown_path=md_path,
                game_title="Test Game",
            )

            logger.log_game_output("Welcome!", location="Start")
            logger.log_llm_response("COMMAND: look", command="look")
            logger.finalize()

            # Check Markdown file
            content = md_path.read_text()
            assert "Test Game" in content
            assert "Welcome!" in content
            assert "`look`" in content
            assert "Completed:" in content

    def test_context_manager(self) -> None:
        """Test using logger as context manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "test.json"

            with TranscriptLogger(json_path=json_path) as logger:
                logger.log_game_output("Test output")

            # File should be finalized
            assert json_path.exists()

    def test_get_entries_returns_copy(self) -> None:
        """Test that get_entries returns a copy."""
        logger = TranscriptLogger()
        logger.log_game_output("Test")

        entries = logger.get_entries()
        entries.append(
            TranscriptEntry(
                timestamp="now",
                turn=0,
                entry_type="test",
                content="extra",
            )
        )

        # Original should be unchanged
        assert len(logger._entries) == 1

    def test_turn_increments_on_llm_response(self) -> None:
        """Test that turn count increments after LLM response."""
        logger = TranscriptLogger()

        assert logger._turn == 0

        logger.log_game_output("Output 1")
        assert logger._turn == 0

        logger.log_llm_response("Response 1", command="cmd1")
        assert logger._turn == 1

        logger.log_game_output("Output 2")
        assert logger._turn == 1

        logger.log_llm_response("Response 2", command="cmd2")
        assert logger._turn == 2


class TestCreateTranscriptPaths:
    """Tests for create_transcript_paths."""

    def test_creates_paths(self) -> None:
        """Test creating transcript paths."""
        base_dir = Path("/transcripts")
        json_path, md_path = create_transcript_paths(
            base_dir,
            "Zork I",
            session_id="test123",
        )

        assert json_path == Path("/transcripts/Zork_I_test123.json")
        assert md_path == Path("/transcripts/Zork_I_test123.md")

    def test_sanitizes_game_name(self) -> None:
        """Test that game names are sanitized."""
        base_dir = Path("/transcripts")
        json_path, _ = create_transcript_paths(
            base_dir,
            "Game: Special Edition!",
            session_id="test",
        )

        # Special characters should be replaced
        assert ":" not in str(json_path)
        assert "!" not in str(json_path)

    def test_auto_generates_session_id(self) -> None:
        """Test auto-generation of session ID."""
        base_dir = Path("/transcripts")
        json_path, _ = create_transcript_paths(base_dir, "Game")

        # Should have a timestamp-like session ID
        filename = json_path.stem
        assert len(filename) > len("Game_")
