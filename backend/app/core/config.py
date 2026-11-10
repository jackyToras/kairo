from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProviderName = Literal["auto", "ollama", "groq", "gemini", "openrouter", "openai_compat"]
SearchProviderName = Literal["auto", "duckduckgo", "tavily", "brave"]


@dataclass(frozen=True)
class ResolvedLLMConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    is_free_tier: bool
    is_local: bool
    extra_headers: dict[str, str]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Kairo"
    llm_provider: LLMProviderName = "auto"

    # Free / Local Ollama
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "mistral:latest"
    ollama_embed_model: str = "nomic-embed-text:latest"

    # Free Tier Cloud APIs
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"

    openai_compat_base_url: str = ""
    openai_compat_api_key: str = ""
    openai_compat_model: str = ""

    # Search (strictly exposed via single web_search tool)
    search_provider: SearchProviderName = "auto"
    tavily_api_key: str = ""
    brave_api_key: str = ""

    # Storage & Temporal Defaults
    database_path: str = "data/kairo.db"
    default_timezone: str = "Asia/Kolkata"

    # Performance & Guardrails
    max_search_rounds: int = 2
    search_timeout_seconds: float = 6.0
    page_extract_timeout_seconds: float = 1.3
    enable_page_extraction: bool = True
    search_cache_ttl_seconds: int = 3600
    breaking_cache_ttl_seconds: int = 300
    llm_timeout_seconds: float = 45.0

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"

    @property
    def db_file(self) -> Path:
        return Path(self.database_path)

    def resolve_search_provider(self) -> str:
        if self.search_provider != "auto":
            return self.search_provider
        if self.tavily_api_key.strip():
            return "tavily"
        if self.brave_api_key.strip():
            return "brave"
        return "duckduckgo"

    def resolve_llm(
        self,
        override_provider: str | None = None,
        override_model: str | None = None,
        override_api_key: str | None = None,
    ) -> ResolvedLLMConfig:
        provider = (override_provider or self.llm_provider).strip().lower()

        if provider == "auto":
            if self.groq_api_key.strip():
                provider = "groq"
            elif self.gemini_api_key.strip():
                provider = "gemini"
            elif self.openrouter_api_key.strip():
                provider = "openrouter"
            elif self.openai_compat_base_url.strip() and self.openai_compat_api_key.strip():
                provider = "openai_compat"
            else:
                provider = "ollama"

        if provider == "groq":
            return ResolvedLLMConfig(
                provider="groq",
                base_url="https://api.groq.com/openai/v1",
                api_key=(override_api_key or self.groq_api_key).strip(),
                model=(override_model or self.groq_model).strip(),
                is_free_tier=True,
                is_local=False,
                extra_headers={},
            )

        if provider == "gemini":
            return ResolvedLLMConfig(
                provider="gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                api_key=(override_api_key or self.gemini_api_key).strip(),
                model=(override_model or self.gemini_model).strip(),
                is_free_tier=True,
                is_local=False,
                extra_headers={},
            )

        if provider == "openrouter":
            return ResolvedLLMConfig(
                provider="openrouter",
                base_url="https://openrouter.ai/api/v1",
                api_key=(override_api_key or self.openrouter_api_key).strip(),
                model=(override_model or self.openrouter_model).strip(),
                is_free_tier=True,
                is_local=False,
                extra_headers={
                    "HTTP-Referer": "https://github.com/jackyToras/kairo",
                    "X-Title": "Kairo Agent",
                },
            )

        if provider == "openai_compat":
            return ResolvedLLMConfig(
                provider="openai_compat",
                base_url=self.openai_compat_base_url.rstrip("/"),
                api_key=(override_api_key or self.openai_compat_api_key).strip(),
                model=(override_model or self.openai_compat_model).strip(),
                is_free_tier=False,
                is_local=False,
                extra_headers={},
            )

        # Default: local Ollama (100% free, zero-key)
        return ResolvedLLMConfig(
            provider="ollama",
            base_url=self.ollama_base_url.rstrip("/"),
            api_key=(override_api_key or "ollama").strip(),
            model=(override_model or self.ollama_model).strip(),
            is_free_tier=True,
            is_local=True,
            extra_headers={},
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
