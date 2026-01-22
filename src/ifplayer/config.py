"""Configuration management for IF Player."""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    """LLM-specific configuration."""

    backend: Literal["anthropic_api", "claude_cli"] = "anthropic_api"
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 1024
    temperature: float = 0.7


class MemoryConfig(BaseModel):
    """Memory and summarization settings."""

    max_recent_turns: int = 20
    summarize_threshold: int = 15
    max_summary_tokens: int = 1000


class GameConfig(BaseModel):
    """Game backend settings."""

    backend: Literal["auto", "zmachine", "glulx"] = "auto"
    dfrotz_path: str = "dfrotz"
    glulxe_path: str = "glulxe-remglk"
    save_directory: Path = Field(default_factory=lambda: Path("./saves"))


class LoggingConfig(BaseModel):
    """Logging and transcript settings."""

    transcript_dir: Path = Field(default_factory=lambda: Path("./transcripts"))
    enable_json: bool = True
    enable_markdown: bool = True


class Config(BaseSettings):
    """Main application configuration."""

    model_config = SettingsConfigDict(
        env_prefix="IFPLAYER_",
        env_nested_delimiter="__",
    )

    game_path: Path | None = None
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    game: GameConfig = Field(default_factory=GameConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # Error handling
    max_retries: int = 3
    stuck_threshold: int = 5


def load_config(
    config_path: Path | None = None,
    game_path: Path | None = None,
) -> Config:
    """Load configuration from file and environment.

    Args:
        config_path: Optional path to YAML config file.
        game_path: Optional game file path to override config.

    Returns:
        Loaded configuration.
    """
    config_data: dict[str, Any] = {}

    if config_path and config_path.exists():
        import yaml

        with open(config_path) as f:
            loaded = yaml.safe_load(f)
            if loaded:
                config_data = loaded

    if game_path:
        config_data["game_path"] = game_path

    return Config(**config_data)
