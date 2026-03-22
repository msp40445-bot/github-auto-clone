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

    # Ollama (local AI - free, runs on macOS)
    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    ollama_model: str = Field(default="qwen2.5:1.5b", alias="OLLAMA_MODEL")

    # Rate limiting / safety
    github_requests_per_minute: int = Field(default=30, alias="GAC_RATE_LIMIT")
    request_delay_seconds: float = Field(default=1.0, alias="GAC_REQUEST_DELAY")

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
    def has_ollama(self) -> bool:
        return bool(self.ollama_host)


def get_settings() -> Settings:
    """Get application settings (singleton-like via module-level caching)."""
    return Settings()
