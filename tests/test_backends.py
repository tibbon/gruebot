"""Tests for game backends."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ifplayer.backends.base import (
    InterpreterProcess,
    InterpreterStartError,
)
from ifplayer.backends.protocol import GameState
from ifplayer.backends.zmachine import ZMachineBackend


class TestInterpreterProcess:
    """Tests for InterpreterProcess."""

    def test_start_not_found(self) -> None:
        """Test starting non-existent interpreter."""
        with pytest.raises(InterpreterStartError, match="Interpreter not found"):
            InterpreterProcess.start(["nonexistent_interpreter_12345"])

    @patch("subprocess.Popen")
    def test_start_success(self, mock_popen: MagicMock) -> None:
        """Test successful interpreter start."""
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_popen.return_value = mock_process

        proc = InterpreterProcess.start(["echo", "hello"])

        assert proc.process is mock_process
        mock_popen.assert_called_once()

    @patch("subprocess.Popen")
    def test_write_line(self, mock_popen: MagicMock) -> None:
        """Test writing a line to interpreter."""
        mock_stdin = MagicMock()
        mock_process = MagicMock()
        mock_process.stdin = mock_stdin
        mock_process.stdout = MagicMock()
        mock_popen.return_value = mock_process

        proc = InterpreterProcess.start(["test"])
        proc.write_line("hello world")

        mock_stdin.write.assert_called_with("hello world\n")
        mock_stdin.flush.assert_called()

    @patch("subprocess.Popen")
    def test_readline(self, mock_popen: MagicMock) -> None:
        """Test reading a line from interpreter."""
        mock_stdout = MagicMock()
        mock_stdout.readline.return_value = "response line\n"
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = mock_stdout
        mock_popen.return_value = mock_process

        proc = InterpreterProcess.start(["test"])
        line = proc.readline()

        assert line == "response line\n"

    @patch("subprocess.Popen")
    def test_is_alive(self, mock_popen: MagicMock) -> None:
        """Test checking if process is alive."""
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.poll.return_value = None  # Still running
        mock_popen.return_value = mock_process

        proc = InterpreterProcess.start(["test"])
        assert proc.is_alive is True

        mock_process.poll.return_value = 0  # Exited
        assert proc.is_alive is False

    @patch("subprocess.Popen")
    def test_read_until_prompt(self, mock_popen: MagicMock) -> None:
        """Test reading until prompt character."""
        mock_stdout = MagicMock()
        # Simulate multi-line output ending with prompt
        mock_stdout.readline.side_effect = [
            "Welcome to the game!\n",
            "You are in a room.\n",
            ">",
        ]
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = mock_stdout
        mock_popen.return_value = mock_process

        proc = InterpreterProcess.start(["test"])
        output = proc.read_until_prompt(">")

        assert "Welcome to the game!" in output
        assert "You are in a room." in output


class TestZMachineBackend:
    """Tests for ZMachineBackend."""

    def test_init_default_values(self) -> None:
        """Test backend initializes with default values."""
        backend = ZMachineBackend()

        assert backend.dfrotz_path == "dfrotz"
        assert backend.save_directory == Path("./saves")
        assert backend.is_running is False
        assert backend.game_info is None

    def test_init_custom_values(self) -> None:
        """Test backend with custom values."""
        backend = ZMachineBackend(
            dfrotz_path="/custom/dfrotz",
            save_directory=Path("/custom/saves"),
        )

        assert backend.dfrotz_path == "/custom/dfrotz"
        assert backend.save_directory == Path("/custom/saves")

    def test_start_game_not_found(self) -> None:
        """Test starting with non-existent game file."""
        backend = ZMachineBackend()

        with pytest.raises(FileNotFoundError):
            backend.start("/nonexistent/game.z5")

    @patch.object(InterpreterProcess, "start")
    def test_start_success(self, mock_start: MagicMock) -> None:
        """Test successful game start."""
        # Create a fake game file
        with tempfile.NamedTemporaryFile(suffix=".z5", delete=False) as f:
            game_path = f.name

        try:
            # Mock the interpreter process
            mock_proc = MagicMock()
            mock_proc.is_alive = True
            mock_proc.read_until_prompt.return_value = (
                "ZORK I: The Great Underground Empire\n"
                "Copyright (c) 1981, 1982, 1983 Infocom, Inc.\n"
                "\n"
                "West of House\n"
                "You are standing in an open field west of a white house.\n"
                ">"
            )
            mock_start.return_value = mock_proc

            backend = ZMachineBackend()
            response = backend.start(game_path)

            assert backend.is_running is True
            assert backend.game_info is not None
            assert backend.game_info.format == "zmachine"
            assert "ZORK" in response.text or "West of House" in response.text
            assert response.state == GameState.WAITING_INPUT
        finally:
            Path(game_path).unlink()

    @patch.object(InterpreterProcess, "start")
    def test_send_command(self, mock_start: MagicMock) -> None:
        """Test sending a command."""
        with tempfile.NamedTemporaryFile(suffix=".z5", delete=False) as f:
            game_path = f.name

        try:
            mock_proc = MagicMock()
            mock_proc.is_alive = True
            mock_proc.read_until_prompt.side_effect = [
                "Welcome!\n>",  # Intro
                "You go north.\n\nNorth Room\nYou are in a northern room.\n>",  # After command
            ]
            mock_start.return_value = mock_proc

            backend = ZMachineBackend()
            backend.start(game_path)

            response = backend.send_command("go north")

            assert "north" in response.text.lower()
            mock_proc.write_line.assert_called_with("go north")
        finally:
            Path(game_path).unlink()

    def test_send_command_not_running(self) -> None:
        """Test sending command when no game running."""
        backend = ZMachineBackend()

        with pytest.raises(RuntimeError, match="No game is currently running"):
            backend.send_command("look")

    @patch.object(InterpreterProcess, "start")
    def test_detect_game_over(self, mock_start: MagicMock) -> None:
        """Test detection of game over state."""
        with tempfile.NamedTemporaryFile(suffix=".z5", delete=False) as f:
            game_path = f.name

        try:
            mock_proc = MagicMock()
            mock_proc.is_alive = True
            mock_proc.read_until_prompt.side_effect = [
                "Welcome!\n>",  # Intro
                "*** You have died ***\n\nDo you want to RESTART, RESTORE, or QUIT?\n>",
            ]
            mock_start.return_value = mock_proc

            backend = ZMachineBackend()
            backend.start(game_path)

            response = backend.send_command("jump off cliff")

            assert response.state == GameState.GAME_OVER
        finally:
            Path(game_path).unlink()

    @patch.object(InterpreterProcess, "start")
    def test_quit(self, mock_start: MagicMock) -> None:
        """Test quitting the game."""
        with tempfile.NamedTemporaryFile(suffix=".z5", delete=False) as f:
            game_path = f.name

        try:
            mock_proc = MagicMock()
            mock_proc.is_alive = True
            mock_proc.read_until_prompt.return_value = "Welcome!\n>"
            mock_start.return_value = mock_proc

            backend = ZMachineBackend()
            backend.start(game_path)

            assert backend.is_running is True

            # Make is_alive return False after quit
            mock_proc.is_alive = False
            backend.quit()

            mock_proc.terminate.assert_called_once()
        finally:
            Path(game_path).unlink()


class TestZMachineBackendTextExtraction:
    """Tests for text extraction methods."""

    def test_extract_location_simple(self) -> None:
        """Test extracting simple location."""
        backend = ZMachineBackend()

        text = "West of House\nYou are standing in an open field."
        location = backend._extract_location(text)

        assert location == "West of House"

    def test_extract_location_skip_description(self) -> None:
        """Test that descriptions are not extracted as locations."""
        backend = ZMachineBackend()

        text = "This is a very long line that describes something, with commas.\nActual Location\nMore text."
        location = backend._extract_location(text)

        assert location == "Actual Location"

    def test_extract_title(self) -> None:
        """Test extracting game title."""
        backend = ZMachineBackend()

        intro = "ZORK I: The Great Underground Empire\nCopyright (c) 1981 Infocom"
        title = backend._extract_title(intro)

        assert title == "ZORK I: The Great Underground Empire"

    def test_extract_author(self) -> None:
        """Test extracting author."""
        backend = ZMachineBackend()

        intro = "Adventure Game\nby John Smith\nRelease 1"
        author = backend._extract_author(intro)

        assert author == "John Smith"

    def test_extract_author_copyright(self) -> None:
        """Test extracting author from copyright notice."""
        backend = ZMachineBackend()

        intro = "Game Title\nCopyright 1984 by Jane Doe"
        author = backend._extract_author(intro)

        assert "Jane Doe" in author

    def test_clean_output(self) -> None:
        """Test output cleaning."""
        backend = ZMachineBackend()

        raw = "Line 1\n\n\nLine 2\n\nLine 3\n  >"
        cleaned = backend._clean_output(raw)

        assert cleaned == "Line 1\n\nLine 2\n\nLine 3"
        assert ">" not in cleaned
