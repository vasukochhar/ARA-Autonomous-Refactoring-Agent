"""
Configuration management for ARA using Pydantic Settings.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Gemini Configuration (FREE)
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    llm_provider: Literal["gemini"] = Field(
        default="gemini", description="LLM provider to use"
    )
    llm_model: str = Field(default="gemini-2.0-flash", description="LLM model name")

    # Database Configuration (Docker PostgreSQL)
    database_url: str = Field(
        default="postgresql://ara_user:ara_password@localhost:5432/ara_db",
        description="PostgreSQL connection string",
    )

    # Agent Configuration
    max_iterations: int = Field(
        default=3, description="Maximum retry iterations for self-correction"
    )
    default_timeout: int = Field(
        default=30, description="Default timeout for subprocess commands"
    )

    # Logging Configuration
    log_level: str = Field(default="INFO", description="Logging level")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
