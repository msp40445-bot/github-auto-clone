"""Configuration management for GitHub Auto Clone."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # GitHub
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    github_api_url: str = Field(default="https://api.github.com", alias="GITHUB_API_URL")

    # OpenAI
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")

    # Paths
    work_dir: Path = Field(default=Path.home() / ".github-auto-clone", alias="GAC_WORK_DIR")
    clone_dir: Path = Field(default=Path.home() / ".github-auto-clone" / "repos")
    output_dir: Path = Field(default=Path.cwd() / "extracted_features")

    # Limits
    max_repo_size_mb: int = Field(default=500, alias="GAC_MAX_REPO_SIZE_MB")
    max_file_size_kb: int = Field(default=500, alias="GAC_MAX_FILE_SIZE_KB")
    max_files_to_analyze: int = Field(default=1000, alias="GAC_MAX_FILES")
    ai_max_tokens: int = Field(default=4096, alias="GAC_AI_MAX_TOKENS")

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}

    def ensure_dirs(self) -> None:
        """Create working directories if they don't exist."""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.clone_dir.mkdir(parents=True, exist_ok=True)

    @property
    def has_github_token(self) -> bool:
        return bool(self.github_token)

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key)


def get_settings() -> Settings:
    """Get application settings (singleton-like via module-level caching)."""
    return Settings()
