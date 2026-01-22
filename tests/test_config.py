"""Tests for configuration loading."""

import tempfile
from pathlib import Path

import pytest
import yaml

from gruebot.config import Config, GameConfig, LLMConfig, load_config


class TestConfig:
    """Tests for Config class."""

    def test_default_config(self) -> None:
        """Test that default config loads with sensible defaults."""
        config = Config()

        assert config.game_path is None
        assert config.max_retries == 3
        assert config.stuck_threshold == 5

    def test_llm_config_defaults(self) -> None:
        """Test LLM config defaults."""
        config = Config()

        assert config.llm.backend == "anthropic_api"
        assert config.llm.model == "claude-sonnet-4-20250514"
        assert config.llm.max_tokens == 1024
        assert config.llm.temperature == 0.7

    def test_memory_config_defaults(self) -> None:
        """Test memory config defaults."""
        config = Config()

        assert config.memory.max_recent_turns == 20
        assert config.memory.summarize_threshold == 15
        assert config.memory.max_summary_tokens == 1000

    def test_game_config_defaults(self) -> None:
        """Test game config defaults."""
        config = Config()

        assert config.game.backend == "auto"
        assert config.game.dfrotz_path == "dfrotz"
        assert config.game.glulxe_path == "glulxe-remglk"

    def test_logging_config_defaults(self) -> None:
        """Test logging config defaults."""
        config = Config()

        assert config.logging.enable_json is True
        assert config.logging.enable_markdown is True


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_no_file(self) -> None:
        """Test loading config without a file."""
        config = load_config()

        assert config.game_path is None

    def test_load_config_with_game_path(self) -> None:
        """Test loading config with game path override."""
        game_path = Path("/path/to/game.z5")
        config = load_config(game_path=game_path)

        assert config.game_path == game_path

    def test_load_config_from_yaml(self) -> None:
        """Test loading config from YAML file."""
        config_data = {
            "game_path": "/path/to/game.z8",
            "llm": {
                "backend": "claude_cli",
                "model": "claude-3-opus",
                "temperature": 0.5,
            },
            "memory": {
                "max_recent_turns": 30,
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = Path(f.name)

        try:
            config = load_config(config_path=config_path)

            assert config.game_path == Path("/path/to/game.z8")
            assert config.llm.backend == "claude_cli"
            assert config.llm.model == "claude-3-opus"
            assert config.llm.temperature == 0.5
            assert config.memory.max_recent_turns == 30
            # Other values should be defaults
            assert config.memory.summarize_threshold == 15
        finally:
            config_path.unlink()

    def test_load_config_game_path_override(self) -> None:
        """Test that game_path argument overrides config file."""
        config_data = {
            "game_path": "/config/game.z5",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = Path(f.name)

        try:
            override_path = Path("/override/game.z8")
            config = load_config(config_path=config_path, game_path=override_path)

            assert config.game_path == override_path
        finally:
            config_path.unlink()


class TestLLMConfig:
    """Tests for LLMConfig model."""

    def test_valid_backends(self) -> None:
        """Test valid LLM backend values."""
        config1 = LLMConfig(backend="anthropic_api")
        assert config1.backend == "anthropic_api"

        config2 = LLMConfig(backend="claude_cli")
        assert config2.backend == "claude_cli"

    def test_invalid_backend(self) -> None:
        """Test invalid LLM backend raises error."""
        with pytest.raises(ValueError):
            LLMConfig(backend="invalid")  # type: ignore[arg-type]


class TestGameConfig:
    """Tests for GameConfig model."""

    def test_valid_backends(self) -> None:
        """Test valid game backend values."""
        for backend in ["auto", "zmachine", "glulx"]:
            config = GameConfig(backend=backend)  # type: ignore[arg-type]
            assert config.backend == backend

    def test_invalid_backend(self) -> None:
        """Test invalid game backend raises error."""
        with pytest.raises(ValueError):
            GameConfig(backend="invalid")  # type: ignore[arg-type]
