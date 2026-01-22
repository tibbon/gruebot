"""Assertion classes for testing IF games."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from gruebot.testing.types import TestState


@dataclass
class AssertionResult:
    """Result of an assertion check."""

    passed: bool
    assertion: Assertion
    message: str
    actual_value: str | None = None


class Assertion(ABC):
    """Base class for test assertions."""

    @abstractmethod
    def check(self, state: TestState) -> AssertionResult:
        """Check if the assertion passes.

        Args:
            state: Current test state.

        Returns:
            AssertionResult with pass/fail and details.
        """
        pass

    @abstractmethod
    def describe(self) -> str:
        """Return a human-readable description of the assertion."""
        pass


class LocationAssertion(Assertion):
    """Assert the player is at a specific location."""

    def __init__(self, expected: str, exact: bool = False) -> None:
        """Initialize location assertion.

        Args:
            expected: Expected location name (or substring).
            exact: If True, require exact match; otherwise substring match.
        """
        self.expected = expected
        self.exact = exact

    def check(self, state: TestState) -> AssertionResult:
        actual = state.current_location or ""
        if self.exact:
            passed = actual.lower() == self.expected.lower()
        else:
            passed = self.expected.lower() in actual.lower()

        return AssertionResult(
            passed=passed,
            assertion=self,
            message=f"Expected location '{self.expected}', got '{actual}'"
            if not passed
            else f"Location is '{actual}'",
            actual_value=actual,
        )

    def describe(self) -> str:
        match_type = "exactly" if self.exact else "containing"
        return f"location {match_type} '{self.expected}'"


class ContainsTextAssertion(Assertion):
    """Assert the last output contains specific text."""

    def __init__(self, expected: str, case_sensitive: bool = False) -> None:
        """Initialize contains text assertion.

        Args:
            expected: Text that should be present.
            case_sensitive: Whether match is case-sensitive.
        """
        self.expected = expected
        self.case_sensitive = case_sensitive

    def check(self, state: TestState) -> AssertionResult:
        actual = state.last_output or ""
        if self.case_sensitive:
            passed = self.expected in actual
        else:
            passed = self.expected.lower() in actual.lower()

        return AssertionResult(
            passed=passed,
            assertion=self,
            message=f"Expected output to contain '{self.expected}'"
            if not passed
            else f"Output contains '{self.expected}'",
            actual_value=actual[:200] + "..." if len(actual) > 200 else actual,
        )

    def describe(self) -> str:
        return f"output contains '{self.expected}'"


class NotContainsTextAssertion(Assertion):
    """Assert the last output does NOT contain specific text."""

    def __init__(self, forbidden: str, case_sensitive: bool = False) -> None:
        """Initialize not contains text assertion.

        Args:
            forbidden: Text that should NOT be present.
            case_sensitive: Whether match is case-sensitive.
        """
        self.forbidden = forbidden
        self.case_sensitive = case_sensitive

    def check(self, state: TestState) -> AssertionResult:
        actual = state.last_output or ""
        if self.case_sensitive:
            passed = self.forbidden not in actual
        else:
            passed = self.forbidden.lower() not in actual.lower()

        return AssertionResult(
            passed=passed,
            assertion=self,
            message=f"Output should not contain '{self.forbidden}'"
            if not passed
            else f"Output correctly does not contain '{self.forbidden}'",
            actual_value=actual[:200] + "..." if len(actual) > 200 else actual,
        )

    def describe(self) -> str:
        return f"output does not contain '{self.forbidden}'"


class InventoryAssertion(Assertion):
    """Assert the player has a specific item."""

    def __init__(self, item: str) -> None:
        """Initialize inventory assertion.

        Args:
            item: Item name that should be in inventory.
        """
        self.item = item

    def check(self, state: TestState) -> AssertionResult:
        # Check if item appears in inventory list or last output after "inventory" command
        inventory_text = " ".join(state.inventory) if state.inventory else ""
        passed = self.item.lower() in inventory_text.lower()

        return AssertionResult(
            passed=passed,
            assertion=self,
            message=f"Expected '{self.item}' in inventory"
            if not passed
            else f"Inventory contains '{self.item}'",
            actual_value=inventory_text or "(empty)",
        )

    def describe(self) -> str:
        return f"inventory contains '{self.item}'"


class ScoreAssertion(Assertion):
    """Assert the player has a specific score."""

    def __init__(self, expected: int, comparison: str = "eq") -> None:
        """Initialize score assertion.

        Args:
            expected: Expected score value.
            comparison: Comparison type: 'eq', 'gt', 'gte', 'lt', 'lte'.
        """
        self.expected = expected
        self.comparison = comparison

    def check(self, state: TestState) -> AssertionResult:
        actual = state.score
        if actual is None:
            return AssertionResult(
                passed=False,
                assertion=self,
                message="Score not available",
                actual_value=None,
            )

        comparisons = {
            "eq": (actual == self.expected, "=="),
            "gt": (actual > self.expected, ">"),
            "gte": (actual >= self.expected, ">="),
            "lt": (actual < self.expected, "<"),
            "lte": (actual <= self.expected, "<="),
        }
        passed, symbol = comparisons.get(self.comparison, (False, "?"))

        return AssertionResult(
            passed=passed,
            assertion=self,
            message=f"Expected score {symbol} {self.expected}, got {actual}"
            if not passed
            else f"Score is {actual}",
            actual_value=str(actual),
        )

    def describe(self) -> str:
        symbols = {"eq": "==", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
        return f"score {symbols.get(self.comparison, '==')} {self.expected}"


class TurnsAssertion(Assertion):
    """Assert the number of turns taken."""

    def __init__(self, expected: int, comparison: str = "lte") -> None:
        """Initialize turns assertion.

        Args:
            expected: Expected turn count.
            comparison: Comparison type: 'eq', 'gt', 'gte', 'lt', 'lte'.
        """
        self.expected = expected
        self.comparison = comparison

    def check(self, state: TestState) -> AssertionResult:
        actual = state.turns

        comparisons = {
            "eq": (actual == self.expected, "=="),
            "gt": (actual > self.expected, ">"),
            "gte": (actual >= self.expected, ">="),
            "lt": (actual < self.expected, "<"),
            "lte": (actual <= self.expected, "<="),
        }
        passed, symbol = comparisons.get(self.comparison, (False, "?"))

        return AssertionResult(
            passed=passed,
            assertion=self,
            message=f"Expected turns {symbol} {self.expected}, got {actual}"
            if not passed
            else f"Completed in {actual} turns",
            actual_value=str(actual),
        )

    def describe(self) -> str:
        symbols = {"eq": "==", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
        return f"turns {symbols.get(self.comparison, '<=')} {self.expected}"


def parse_assertion(line: str) -> Assertion | None:
    """Parse an assertion directive from a walkthrough file.

    Supported formats:
        @expect-location "Kitchen"
        @expect-location-exact "The Kitchen"
        @expect-contains "You see a lamp"
        @expect-not-contains "grue"
        @expect-inventory "brass lantern"
        @expect-score 10
        @expect-score-gte 5
        @expect-turns-lte 50

    Args:
        line: Line from walkthrough file.

    Returns:
        Assertion instance or None if not an assertion.
    """
    line = line.strip()
    if not line.startswith("@expect-"):
        return None

    # Parse quoted strings
    def extract_quoted(s: str) -> str | None:
        match = re.search(r'"([^"]*)"', s)
        return match.group(1) if match else None

    # Parse integer values
    def extract_int(s: str) -> int | None:
        match = re.search(r"\b(\d+)\b", s)
        return int(match.group(1)) if match else None

    if line.startswith("@expect-location-exact"):
        value = extract_quoted(line)
        if value:
            return LocationAssertion(value, exact=True)
    elif line.startswith("@expect-location"):
        value = extract_quoted(line)
        if value:
            return LocationAssertion(value, exact=False)
    elif line.startswith("@expect-not-contains"):
        value = extract_quoted(line)
        if value:
            return NotContainsTextAssertion(value)
    elif line.startswith("@expect-contains"):
        value = extract_quoted(line)
        if value:
            return ContainsTextAssertion(value)
    elif line.startswith("@expect-inventory"):
        value = extract_quoted(line)
        if value:
            return InventoryAssertion(value)
    elif line.startswith("@expect-score-gte"):
        int_value = extract_int(line)
        if int_value is not None:
            return ScoreAssertion(int_value, "gte")
    elif line.startswith("@expect-score-gt"):
        int_value = extract_int(line)
        if int_value is not None:
            return ScoreAssertion(int_value, "gt")
    elif line.startswith("@expect-score-lte"):
        int_value = extract_int(line)
        if int_value is not None:
            return ScoreAssertion(int_value, "lte")
    elif line.startswith("@expect-score-lt"):
        int_value = extract_int(line)
        if int_value is not None:
            return ScoreAssertion(int_value, "lt")
    elif line.startswith("@expect-score"):
        int_value = extract_int(line)
        if int_value is not None:
            return ScoreAssertion(int_value, "eq")
    elif line.startswith("@expect-turns-lte"):
        int_value = extract_int(line)
        if int_value is not None:
            return TurnsAssertion(int_value, "lte")
    elif line.startswith("@expect-turns-lt"):
        int_value = extract_int(line)
        if int_value is not None:
            return TurnsAssertion(int_value, "lt")
    elif line.startswith("@expect-turns-gte"):
        int_value = extract_int(line)
        if int_value is not None:
            return TurnsAssertion(int_value, "gte")
    elif line.startswith("@expect-turns"):
        int_value = extract_int(line)
        if int_value is not None:
            return TurnsAssertion(int_value, "eq")

    return None
