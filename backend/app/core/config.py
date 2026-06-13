from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
