from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    app_name: str = "AmazonHackon Backend"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    aws_region: str | None = None
    bedrock_model_id: str | None = None

    public_base_url: str = "http://127.0.0.1:8000"

    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://127.0.0.1:8000/api/v1/integrations/google/callback"

    discord_webhook_url: str | None = None
    discord_public_key: str | None = None
    discord_bot_token: str | None = None
    discord_channel_id: str | None = None
    discord_scheduler_enabled: bool = False
    campusbuddy_discord_enabled: bool = False
    discord_guild_id: str | None = None
    discord_tech_support_channel_id: str | None = None

    campus_relay_email_enabled: bool = False
    campus_relay_smtp_host: str | None = None
    campus_relay_smtp_port: str | None = None
    campus_relay_smtp_username: str | None = None
    campus_relay_smtp_password: str | None = None
    campus_relay_from_email: str | None = None
    campus_relay_from_name: str = "Campus Process Relay"

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
