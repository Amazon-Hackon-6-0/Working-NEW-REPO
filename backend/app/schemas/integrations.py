from pydantic import BaseModel

from app.schemas.campusflow import AssignmentItem


class IntegrationStatus(BaseModel):
    google_classroom_connected: bool
    discord_configured: bool
    discord_bot_configured: bool
    discord_interactions_configured: bool


class GoogleAuthUrlResponse(BaseModel):
    auth_url: str
    scopes: list[str]


class GoogleCallbackResponse(BaseModel):
    connected: bool
    message: str


class ClassroomSyncResponse(BaseModel):
    source: str
    assignments: list[AssignmentItem]
    courses_scanned: int
    message: str


class DiscordPromptRequest(BaseModel):
    subject_code: str | None = None


class DiscordPromptResponse(BaseModel):
    sent: bool
    message: str
    feedback_url: str


class DiscordInteractionResponse(BaseModel):
    type: int
    data: dict | None = None
