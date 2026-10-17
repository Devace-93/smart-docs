"""Settings for Smart Docs. Every value comes from the environment or `.env`."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Instance
    instance_name: str = "Smart Docs"
    public_base_url: str = "http://localhost:8000"
    footer_text: str = "Built with Smart Docs"
    footer_url: str = "https://github.com/Devace-93/smart-docs"
    info_url: str = "https://info.3m4.net"
    signups_open: bool = True
    # retro feedback widget (https://retro.3m4.net): the project's PUBLIC key. Empty = no widget.
    retro_project_key: str = ""
    retro_widget_url: str = "https://retro.3m4.net/widget.js"
    # metrics web analytics (https://metrics.3m4.net): the project's PUBLIC key. Empty = no tracker.
    metrics_project_key: str = ""
    metrics_tracker_url: str = "https://metrics.3m4.net/m.js"

    # Database
    database_url: str = "postgresql+psycopg://sd:sd@localhost:5432/sd"

    # Auth (SD-013): sessions come from accounts.3m4.net; this instance only verifies them.
    accounts_url: str = "http://localhost:8085"  # public origin: JWT issuer, login/signup redirects, browser calls
    accounts_internal_url: str | None = None  # where this process fetches the JWKS; defaults to accounts_url
    fernet_key: str | None = None

    # Model tiers
    default_tier: str = "local"
    hosted_enabled: bool = False
    hosted_base_url: str = "https://api.deepseek.com"
    hosted_api_key: str | None = None
    hosted_model: str = "deepseek-chat"
    hosted_daily_limit: int = 30
    local_enabled: bool = True
    ollama_url: str = "http://localhost:11434"
    local_model: str = "qwen2.5:3b"
    local_per_10s: int = 1
    local_per_hour: int = 20
    byok_enabled: bool = True
    embed_model: str = "nomic-embed-text"
    embed_dims: int = 768
    model_timeout_seconds: int = 120

    # Public rendering
    public_cache_seconds: int = 300
    reserved_handles: list[str] = Field(
        default_factory=lambda: [
            "api",
            "app",
            "mcp",
            "docs",
            "redoc",
            "openapi.json",
            "static",
            "health",
            "login",
            "signup",
            "logout",
            "admin",
            "assets",
            "favicon.ico",
            "og-image.png",
            "robots.txt",
            "sitemap.xml",
            "llms.txt",
        ]
    )

    @property
    def accounts_jwks_url(self) -> str:
        base = (self.accounts_internal_url or self.accounts_url).rstrip("/")
        return f"{base}/.well-known/jwks.json"

    @property
    def sync_database_url(self) -> str:
        """Plain libpq URL for tools that do not speak the SQLAlchemy dialect prefix."""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def tiers_available(self) -> list[str]:
        tiers = ["agent"]
        if self.local_enabled:
            tiers.append("local")
        if self.hosted_enabled and self.hosted_api_key:
            tiers.append("hosted")
        if self.byok_enabled:
            tiers.append("byok")
        return tiers


@lru_cache
def get_settings() -> Settings:
    return Settings()
