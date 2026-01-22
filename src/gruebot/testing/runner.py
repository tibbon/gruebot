"""Test runner for interactive fiction games."""

from __future__ import annotations

import contextlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

from gruebot.backends.protocol import GameBackend, GameResponse, GameState
from gruebot.testing.assertions import Assertion, AssertionResult, parse_assertion


class ExitCode(IntEnum):
    """Exit codes for test command."""

    SUCCESS = 0
    GAME_START_FAILED = 1
    ASSERTION_FAILED = 2
    GAME_ERROR = 3
    INVALID_INPUT = 4
    WALKTHROUGH_ERROR = 5


@dataclass
class TestState:
    """Current state during test execution."""

    current_location: str | None = None
    last_output: str = ""
    full_transcript: list[str] = field(default_factory=list)
    inventory: list[str] = field(default_factory=list)
    score: int | None = None
    turns: int = 0
    game_over: bool = False
    error: str | None = None


@dataclass
class TestConfig:
    """Configuration for test run."""

    game_path: Path
    walkthrough_path: Path | None = None
    smoke_test: bool = False
    verbose: bool = False
    timeout_per_command: float = 30.0
    final_assertions: list[Assertion] = field(default_factory=list)


@dataclass
class WalkthroughStep:
    """A single step in a walkthrough."""

    line_number: int
    command: str | None = None
    assertion: Assertion | None = None
    comment: str | None = None


@dataclass
class StepResult:
    """Result of executing a single step."""

    step: WalkthroughStep
    output: str | None = None
    assertion_result: AssertionResult | None = None
    error: str | None = None

    @property
    def passed(self) -> bool:
        if self.error:
            return False
        if self.assertion_result:
            return self.assertion_result.passed
        return True


@dataclass
class TestResult:
    """Result of a test run."""

    exit_code: ExitCode
    passed: bool
    steps_executed: int
    steps_passed: int
    steps_failed: int
    assertions_checked: int
    assertions_passed: int
    assertions_failed: int
    failed_assertions: list[AssertionResult] = field(default_factory=list)
    step_results: list[StepResult] = field(default_factory=list)
    final_state: TestState | None = None
    error: str | None = None

    @property
    def summary(self) -> str:
        """Generate a summary of the test results."""
        if self.passed:
            return (
                f"PASSED: {self.steps_executed} steps, "
                f"{self.assertions_passed}/{self.assertions_checked} assertions"
            )
        else:
            return (
                f"FAILED: {self.assertions_failed} assertion(s) failed, "
                f"error: {self.error or 'assertion failure'}"
            )


class WalkthroughTest:
    """Parser and container for walkthrough test files."""

    def __init__(self, path: Path) -> None:
        """Load a walkthrough from file.

        Args:
            path: Path to walkthrough file.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If file is invalid.
        """
        self.path = path
        self.steps: list[WalkthroughStep] = []
        self._parse()

    def _parse(self) -> None:
        """Parse the walkthrough file."""
        if not self.path.exists():
            raise FileNotFoundError(f"Walkthrough file not found: {self.path}")

        with open(self.path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.rstrip("\n\r")

                # Skip empty lines
                if not line.strip():
                    continue

                # Comments
                if line.strip().startswith("#"):
                    self.steps.append(
                        WalkthroughStep(
                            line_number=line_num,
                            comment=line.strip()[1:].strip(),
                        )
                    )
                    continue

                # Assertions
                if line.strip().startswith("@"):
                    assertion = parse_assertion(line)
                    if assertion:
                        self.steps.append(
                            WalkthroughStep(
                                line_number=line_num,
                                assertion=assertion,
                            )
                        )
                    else:
                        raise ValueError(f"Invalid assertion at line {line_num}: {line}")
                    continue

                # Commands - strip inline comments
                command = line.split("#")[0].strip()
                if command:
                    self.steps.append(
                        WalkthroughStep(
                            line_number=line_num,
                            command=command,
                        )
                    )

    @property
    def commands(self) -> list[str]:
        """Get just the commands from the walkthrough."""
        return [s.command for s in self.steps if s.command]

    @property
    def assertions(self) -> list[Assertion]:
        """Get just the assertions from the walkthrough."""
        return [s.assertion for s in self.steps if s.assertion]


class TestRunner:
    """Runs tests against an IF game."""

    def __init__(
        self,
        backend: GameBackend,
        config: TestConfig,
        on_step: Callable[[StepResult], None] | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> None:
        """Initialize the test runner.

        Args:
            backend: Game backend to use.
            config: Test configuration.
            on_step: Callback for each step result.
            on_output: Callback for game output.
        """
        self.backend = backend
        self.config = config
        self.on_step = on_step
        self.on_output = on_output
        self.state = TestState()

    def run(self) -> TestResult:
        """Run the test.

        Returns:
            TestResult with pass/fail status and details.
        """
        step_results: list[StepResult] = []
        assertions_checked = 0
        assertions_passed = 0
        failed_assertions: list[AssertionResult] = []

        # Start the game
        try:
            response = self.backend.start(str(self.config.game_path))
            self._update_state(response)
            if self.on_output:
                self.on_output(response.text)
        except Exception as e:
            return TestResult(
                exit_code=ExitCode.GAME_START_FAILED,
                passed=False,
                steps_executed=0,
                steps_passed=0,
                steps_failed=1,
                assertions_checked=0,
                assertions_passed=0,
                assertions_failed=0,
                final_state=self.state,
                error=f"Failed to start game: {e}",
            )

        # Smoke test: just verify game started
        if self.config.smoke_test:
            # Send a basic command to verify game responds
            try:
                response = self.backend.send_command("look")
                self._update_state(response)
                if self.on_output:
                    self.on_output(response.text)

                # Check game is still running
                if response.state == GameState.ERROR:
                    return TestResult(
                        exit_code=ExitCode.GAME_ERROR,
                        passed=False,
                        steps_executed=1,
                        steps_passed=0,
                        steps_failed=1,
                        assertions_checked=0,
                        assertions_passed=0,
                        assertions_failed=0,
                        final_state=self.state,
                        error="Game returned error state",
                    )

                return TestResult(
                    exit_code=ExitCode.SUCCESS,
                    passed=True,
                    steps_executed=1,
                    steps_passed=1,
                    steps_failed=0,
                    assertions_checked=0,
                    assertions_passed=0,
                    assertions_failed=0,
                    final_state=self.state,
                )
            except Exception as e:
                return TestResult(
                    exit_code=ExitCode.GAME_ERROR,
                    passed=False,
                    steps_executed=1,
                    steps_passed=0,
                    steps_failed=1,
                    assertions_checked=0,
                    assertions_passed=0,
                    assertions_failed=0,
                    final_state=self.state,
                    error=f"Smoke test failed: {e}",
                )

        # Walkthrough test
        if self.config.walkthrough_path:
            try:
                walkthrough = WalkthroughTest(self.config.walkthrough_path)
            except (FileNotFoundError, ValueError) as e:
                return TestResult(
                    exit_code=ExitCode.INVALID_INPUT,
                    passed=False,
                    steps_executed=0,
                    steps_passed=0,
                    steps_failed=0,
                    assertions_checked=0,
                    assertions_passed=0,
                    assertions_failed=0,
                    final_state=self.state,
                    error=str(e),
                )

            for step in walkthrough.steps:
                # Skip comments
                if step.comment is not None:
                    continue

                # Execute command
                if step.command:
                    try:
                        response = self.backend.send_command(step.command)
                        self._update_state(response)
                        if self.on_output:
                            self.on_output(f"> {step.command}")
                            self.on_output(response.text)

                        result = StepResult(step=step, output=response.text)
                        step_results.append(result)
                        if self.on_step:
                            self.on_step(result)

                        # Check for game error/crash
                        if response.state == GameState.ERROR:
                            return TestResult(
                                exit_code=ExitCode.GAME_ERROR,
                                passed=False,
                                steps_executed=len(step_results),
                                steps_passed=len([r for r in step_results if r.passed]),
                                steps_failed=len([r for r in step_results if not r.passed]),
                                assertions_checked=assertions_checked,
                                assertions_passed=assertions_passed,
                                assertions_failed=len(failed_assertions),
                                failed_assertions=failed_assertions,
                                step_results=step_results,
                                final_state=self.state,
                                error=f"Game error at step {step.line_number}",
                            )

                        # Check for game over
                        if response.state == GameState.GAME_OVER:
                            self.state.game_over = True

                    except Exception as e:
                        result = StepResult(step=step, error=str(e))
                        step_results.append(result)
                        if self.on_step:
                            self.on_step(result)
                        return TestResult(
                            exit_code=ExitCode.WALKTHROUGH_ERROR,
                            passed=False,
                            steps_executed=len(step_results),
                            steps_passed=len([r for r in step_results if r.passed]),
                            steps_failed=len([r for r in step_results if not r.passed]),
                            assertions_checked=assertions_checked,
                            assertions_passed=assertions_passed,
                            assertions_failed=len(failed_assertions),
                            failed_assertions=failed_assertions,
                            step_results=step_results,
                            final_state=self.state,
                            error=f"Error at line {step.line_number}: {e}",
                        )

                # Check assertion
                if step.assertion:
                    assertions_checked += 1
                    assertion_result = step.assertion.check(self.state)

                    result = StepResult(step=step, assertion_result=assertion_result)
                    step_results.append(result)
                    if self.on_step:
                        self.on_step(result)

                    if assertion_result.passed:
                        assertions_passed += 1
                    else:
                        failed_assertions.append(assertion_result)

        # Check final assertions from config
        for assertion in self.config.final_assertions:
            assertions_checked += 1
            assertion_result = assertion.check(self.state)

            step = WalkthroughStep(line_number=0, assertion=assertion)
            result = StepResult(step=step, assertion_result=assertion_result)
            step_results.append(result)
            if self.on_step:
                self.on_step(result)

            if assertion_result.passed:
                assertions_passed += 1
            else:
                failed_assertions.append(assertion_result)

        # Clean up
        with contextlib.suppress(Exception):
            self.backend.quit()

        # Determine final result
        passed = len(failed_assertions) == 0
        exit_code = ExitCode.SUCCESS if passed else ExitCode.ASSERTION_FAILED

        return TestResult(
            exit_code=exit_code,
            passed=passed,
            steps_executed=len([r for r in step_results if r.step.command]),
            steps_passed=len([r for r in step_results if r.step.command and r.passed]),
            steps_failed=len([r for r in step_results if r.step.command and not r.passed]),
            assertions_checked=assertions_checked,
            assertions_passed=assertions_passed,
            assertions_failed=len(failed_assertions),
            failed_assertions=failed_assertions,
            step_results=step_results,
            final_state=self.state,
        )

    def _update_state(self, response: GameResponse) -> None:
        """Update test state from game response."""
        self.state.last_output = response.text
        self.state.full_transcript.append(response.text)

        if response.location:
            self.state.current_location = response.location

        if response.state == GameState.GAME_OVER:
            self.state.game_over = True

        # Try to extract score from output
        score_match = re.search(r"(?:score[:\s]+|scored?\s+)(\d+)", response.text, re.IGNORECASE)
        if score_match:
            self.state.score = int(score_match.group(1))

        self.state.turns += 1

        # Update inventory if this looks like inventory output
        if "carrying" in response.text.lower() or "inventory" in response.text.lower():
            # Simple extraction - lines that start with spaces or bullets
            lines = response.text.split("\n")
            items = []
            for line in lines:
                line = line.strip()
                if line and not line.lower().startswith(("you", "carrying", "inventory")):
                    # Clean up common prefixes
                    line = re.sub(r"^[-*•]\s*", "", line)
                    line = re.sub(r"^a\s+", "", line, flags=re.IGNORECASE)
                    line = re.sub(r"^an\s+", "", line, flags=re.IGNORECASE)
                    line = re.sub(r"^the\s+", "", line, flags=re.IGNORECASE)
                    if line:
                        items.append(line)
            if items:
                self.state.inventory = items
