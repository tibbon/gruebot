"""Tests for the testing module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gruebot.backends.protocol import GameResponse, GameState
from gruebot.testing import (
    ContainsTextAssertion,
    InventoryAssertion,
    LocationAssertion,
    NotContainsTextAssertion,
    ScoreAssertion,
    TestConfig,
    TestRunner,
    WalkthroughTest,
    parse_assertion,
)
from gruebot.testing.assertions import TurnsAssertion
from gruebot.testing.runner import ExitCode, TestState


class TestAssertions:
    """Tests for assertion classes."""

    def test_location_assertion_substring(self) -> None:
        state = TestState(current_location="The Kitchen")
        assertion = LocationAssertion("Kitchen")
        result = assertion.check(state)
        assert result.passed
        assert "Kitchen" in result.message

    def test_location_assertion_substring_fail(self) -> None:
        state = TestState(current_location="The Kitchen")
        assertion = LocationAssertion("Bedroom")
        result = assertion.check(state)
        assert not result.passed

    def test_location_assertion_exact(self) -> None:
        state = TestState(current_location="Kitchen")
        assertion = LocationAssertion("Kitchen", exact=True)
        result = assertion.check(state)
        assert result.passed

    def test_location_assertion_exact_fail(self) -> None:
        state = TestState(current_location="The Kitchen")
        assertion = LocationAssertion("Kitchen", exact=True)
        result = assertion.check(state)
        assert not result.passed

    def test_contains_text_assertion(self) -> None:
        state = TestState(last_output="You see a brass lantern here.")
        assertion = ContainsTextAssertion("brass lantern")
        result = assertion.check(state)
        assert result.passed

    def test_contains_text_assertion_case_insensitive(self) -> None:
        state = TestState(last_output="You see a BRASS LANTERN here.")
        assertion = ContainsTextAssertion("brass lantern", case_sensitive=False)
        result = assertion.check(state)
        assert result.passed

    def test_contains_text_assertion_fail(self) -> None:
        state = TestState(last_output="You see nothing special.")
        assertion = ContainsTextAssertion("brass lantern")
        result = assertion.check(state)
        assert not result.passed

    def test_not_contains_text_assertion(self) -> None:
        state = TestState(last_output="You are in a well-lit room.")
        assertion = NotContainsTextAssertion("grue")
        result = assertion.check(state)
        assert result.passed

    def test_not_contains_text_assertion_fail(self) -> None:
        state = TestState(last_output="A grue eats you.")
        assertion = NotContainsTextAssertion("grue")
        result = assertion.check(state)
        assert not result.passed

    def test_inventory_assertion(self) -> None:
        state = TestState(inventory=["brass lantern", "sword"])
        assertion = InventoryAssertion("lantern")
        result = assertion.check(state)
        assert result.passed

    def test_inventory_assertion_fail(self) -> None:
        state = TestState(inventory=["sword"])
        assertion = InventoryAssertion("lantern")
        result = assertion.check(state)
        assert not result.passed

    def test_score_assertion_eq(self) -> None:
        state = TestState(score=50)
        assertion = ScoreAssertion(50, "eq")
        result = assertion.check(state)
        assert result.passed

    def test_score_assertion_gte(self) -> None:
        state = TestState(score=50)
        assertion = ScoreAssertion(40, "gte")
        result = assertion.check(state)
        assert result.passed

    def test_score_assertion_no_score(self) -> None:
        state = TestState(score=None)
        assertion = ScoreAssertion(50, "eq")
        result = assertion.check(state)
        assert not result.passed

    def test_turns_assertion(self) -> None:
        state = TestState(turns=10)
        assertion = TurnsAssertion(15, "lte")
        result = assertion.check(state)
        assert result.passed

    def test_turns_assertion_fail(self) -> None:
        state = TestState(turns=20)
        assertion = TurnsAssertion(15, "lte")
        result = assertion.check(state)
        assert not result.passed


class TestParseAssertion:
    """Tests for parsing assertions from walkthrough files."""

    def test_parse_location(self) -> None:
        assertion = parse_assertion('@expect-location "Kitchen"')
        assert isinstance(assertion, LocationAssertion)
        assert assertion.expected == "Kitchen"
        assert not assertion.exact

    def test_parse_location_exact(self) -> None:
        assertion = parse_assertion('@expect-location-exact "The Kitchen"')
        assert isinstance(assertion, LocationAssertion)
        assert assertion.expected == "The Kitchen"
        assert assertion.exact

    def test_parse_contains(self) -> None:
        assertion = parse_assertion('@expect-contains "brass lantern"')
        assert isinstance(assertion, ContainsTextAssertion)
        assert assertion.expected == "brass lantern"

    def test_parse_not_contains(self) -> None:
        assertion = parse_assertion('@expect-not-contains "grue"')
        assert isinstance(assertion, NotContainsTextAssertion)
        assert assertion.forbidden == "grue"

    def test_parse_inventory(self) -> None:
        assertion = parse_assertion('@expect-inventory "sword"')
        assert isinstance(assertion, InventoryAssertion)
        assert assertion.item == "sword"

    def test_parse_score(self) -> None:
        assertion = parse_assertion("@expect-score 50")
        assert isinstance(assertion, ScoreAssertion)
        assert assertion.expected == 50
        assert assertion.comparison == "eq"

    def test_parse_score_gte(self) -> None:
        assertion = parse_assertion("@expect-score-gte 40")
        assert isinstance(assertion, ScoreAssertion)
        assert assertion.expected == 40
        assert assertion.comparison == "gte"

    def test_parse_turns_lte(self) -> None:
        assertion = parse_assertion("@expect-turns-lte 100")
        assert isinstance(assertion, TurnsAssertion)
        assert assertion.expected == 100
        assert assertion.comparison == "lte"

    def test_parse_non_assertion(self) -> None:
        assert parse_assertion("look") is None
        assert parse_assertion("# comment") is None
        assert parse_assertion("") is None


class TestWalkthroughTest:
    """Tests for walkthrough file parsing."""

    def test_parse_simple_walkthrough(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# Test walkthrough\n")
            f.write("look\n")
            f.write("north\n")
            f.write('@expect-location "Kitchen"\n')
            f.write("take lamp\n")
            f.flush()

            walkthrough = WalkthroughTest(Path(f.name))
            assert len(walkthrough.commands) == 3
            assert walkthrough.commands == ["look", "north", "take lamp"]
            assert len(walkthrough.assertions) == 1

    def test_parse_with_inline_comments(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("look  # look around\n")
            f.write("north\n")
            f.flush()

            walkthrough = WalkthroughTest(Path(f.name))
            assert walkthrough.commands == ["look", "north"]

    def test_parse_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            WalkthroughTest(Path("/nonexistent/walkthrough.txt"))

    def test_parse_invalid_assertion(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("@invalid-assertion\n")
            f.flush()

            with pytest.raises(ValueError, match="Invalid assertion"):
                WalkthroughTest(Path(f.name))


class TestTestRunner:
    """Tests for the test runner."""

    def test_smoke_test_success(self) -> None:
        # Create mock backend
        backend = MagicMock()
        backend.start.return_value = GameResponse(
            text="Welcome to the game!",
            location="Start",
            state=GameState.WAITING_INPUT,
        )
        backend.send_command.return_value = GameResponse(
            text="You are in a room.",
            location="Room",
            state=GameState.WAITING_INPUT,
        )

        config = TestConfig(
            game_path=Path("test.z5"),
            smoke_test=True,
        )
        runner = TestRunner(backend, config)
        result = runner.run()

        assert result.passed
        assert result.exit_code == ExitCode.SUCCESS
        backend.start.assert_called_once()
        backend.send_command.assert_called_once_with("look")

    def test_smoke_test_game_start_fails(self) -> None:
        backend = MagicMock()
        backend.start.side_effect = Exception("Game not found")

        config = TestConfig(
            game_path=Path("test.z5"),
            smoke_test=True,
        )
        runner = TestRunner(backend, config)
        result = runner.run()

        assert not result.passed
        assert result.exit_code == ExitCode.GAME_START_FAILED

    def test_walkthrough_success(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("look\n")
            f.write("north\n")
            f.write('@expect-location "Kitchen"\n')
            f.flush()

            backend = MagicMock()
            backend.start.return_value = GameResponse(
                text="Welcome!",
                location="Start",
                state=GameState.WAITING_INPUT,
            )
            backend.send_command.side_effect = [
                GameResponse(text="You see a door.", state=GameState.WAITING_INPUT),
                GameResponse(
                    text="You enter the kitchen.",
                    location="Kitchen",
                    state=GameState.WAITING_INPUT,
                ),
            ]

            config = TestConfig(
                game_path=Path("test.z5"),
                walkthrough_path=Path(f.name),
            )
            runner = TestRunner(backend, config)
            result = runner.run()

            assert result.passed
            assert result.exit_code == ExitCode.SUCCESS
            assert result.assertions_passed == 1

    def test_walkthrough_assertion_fails(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("look\n")
            f.write('@expect-location "Kitchen"\n')
            f.flush()

            backend = MagicMock()
            backend.start.return_value = GameResponse(
                text="Welcome!",
                location="Start",
                state=GameState.WAITING_INPUT,
            )
            backend.send_command.return_value = GameResponse(
                text="You are in the bedroom.",
                location="Bedroom",
                state=GameState.WAITING_INPUT,
            )

            config = TestConfig(
                game_path=Path("test.z5"),
                walkthrough_path=Path(f.name),
            )
            runner = TestRunner(backend, config)
            result = runner.run()

            assert not result.passed
            assert result.exit_code == ExitCode.ASSERTION_FAILED
            assert result.assertions_failed == 1

    def test_final_assertions(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("look\n")
            f.flush()

            backend = MagicMock()
            backend.start.return_value = GameResponse(
                text="Welcome!",
                location="Start",
                state=GameState.WAITING_INPUT,
            )
            backend.send_command.return_value = GameResponse(
                text="You see gold in the Treasure Room!",
                location="Treasure Room",
                state=GameState.WAITING_INPUT,
            )

            config = TestConfig(
                game_path=Path("test.z5"),
                walkthrough_path=Path(f.name),
                final_assertions=[
                    LocationAssertion("Treasure"),
                    ContainsTextAssertion("gold"),
                ],
            )
            runner = TestRunner(backend, config)
            result = runner.run()

            # Walkthrough runs, then final assertions are checked
            assert result.assertions_checked == 2
            assert result.assertions_passed == 2

    def test_game_error_during_walkthrough(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("look\n")
            f.write("crash\n")
            f.flush()

            backend = MagicMock()
            backend.start.return_value = GameResponse(
                text="Welcome!",
                state=GameState.WAITING_INPUT,
            )
            backend.send_command.side_effect = [
                GameResponse(text="You look around.", state=GameState.WAITING_INPUT),
                GameResponse(text="Error!", state=GameState.ERROR),
            ]

            config = TestConfig(
                game_path=Path("test.z5"),
                walkthrough_path=Path(f.name),
            )
            runner = TestRunner(backend, config)
            result = runner.run()

            assert not result.passed
            assert result.exit_code == ExitCode.GAME_ERROR
