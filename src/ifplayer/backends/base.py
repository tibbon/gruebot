"""Base utilities for subprocess-based game backends."""

import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from typing import IO


class InterpreterError(Exception):
    """Base exception for interpreter errors."""


class InterpreterStartError(InterpreterError):
    """Failed to start the interpreter."""


class InterpreterCommunicationError(InterpreterError):
    """Failed to communicate with the interpreter."""


@dataclass
class InterpreterProcess:
    """Wrapper around a subprocess for game interpreters.

    Provides utilities for starting, communicating with, and stopping
    an interpreter process.
    """

    process: subprocess.Popen[str]
    _stdin: IO[str]
    _stdout: IO[str]

    @classmethod
    def start(
        cls,
        cmd: list[str],
        encoding: str = "utf-8",
        cwd: str | None = None,
    ) -> "InterpreterProcess":
        """Start an interpreter subprocess.

        Args:
            cmd: Command and arguments to run.
            encoding: Text encoding for I/O.
            cwd: Working directory for the process.

        Returns:
            InterpreterProcess wrapper.

        Raises:
            InterpreterStartError: If the process fails to start.
        """
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding=encoding,
                bufsize=1,  # Line buffered
                cwd=cwd,
            )
        except FileNotFoundError as e:
            raise InterpreterStartError(f"Interpreter not found: {cmd[0]}") from e
        except OSError as e:
            raise InterpreterStartError(f"Failed to start interpreter: {e}") from e

        if process.stdin is None or process.stdout is None:
            process.kill()
            raise InterpreterStartError("Failed to open stdin/stdout pipes")

        return cls(process=process, _stdin=process.stdin, _stdout=process.stdout)

    def write(self, text: str) -> None:
        """Write text to the interpreter's stdin.

        Args:
            text: Text to write.

        Raises:
            InterpreterCommunicationError: If write fails.
        """
        try:
            self._stdin.write(text)
            self._stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise InterpreterCommunicationError(f"Failed to write to interpreter: {e}") from e

    def write_line(self, text: str) -> None:
        """Write a line to the interpreter's stdin.

        Args:
            text: Text to write (newline added automatically).
        """
        self.write(text + "\n")

    def readline(self) -> str:
        """Read a line from the interpreter's stdout.

        Returns:
            The line read (including newline).

        Raises:
            InterpreterCommunicationError: If read fails.
        """
        try:
            return self._stdout.readline()
        except OSError as e:
            raise InterpreterCommunicationError(f"Failed to read from interpreter: {e}") from e

    def read_lines(self) -> Iterator[str]:
        """Read lines from stdout until empty line or EOF.

        Yields:
            Lines from the interpreter.
        """
        while True:
            line = self.readline()
            if not line:
                break
            yield line

    def read_until_prompt(
        self,
        prompt_char: str = ">",
        timeout_lines: int = 1000,
    ) -> str:
        """Read output until a prompt character is encountered.

        This is useful for interpreters like dfrotz that use '>' as
        an input prompt.

        Args:
            prompt_char: Character that indicates prompt.
            timeout_lines: Maximum lines to read before giving up.

        Returns:
            All output up to and including the prompt line.
        """
        lines = []
        for _ in range(timeout_lines):
            line = self.readline()
            if not line:
                break
            lines.append(line)
            # Check if line ends with prompt (allowing for whitespace)
            stripped = line.rstrip()
            if stripped.endswith(prompt_char):
                break
        return "".join(lines)

    @property
    def is_alive(self) -> bool:
        """Check if the process is still running."""
        return self.process.poll() is None

    def terminate(self, timeout: float = 5.0) -> None:
        """Terminate the interpreter process.

        Args:
            timeout: Seconds to wait for graceful termination.
        """
        if not self.is_alive:
            return

        self.process.terminate()
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

    def kill(self) -> None:
        """Forcefully kill the interpreter process."""
        if self.is_alive:
            self.process.kill()
            self.process.wait()
