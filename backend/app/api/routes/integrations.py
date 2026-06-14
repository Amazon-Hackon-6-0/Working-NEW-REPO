from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.schemas.campusflow import AttendanceFeedback, ClassStatus

from app.schemas.integrations import (
    ClassroomSyncResponse,
    DiscordPromptResponse,
    DiscordScheduledPromptResponse,
    GoogleAuthUrlResponse,
    GoogleCallbackResponse,
    IntegrationStatus,
)
from app.services.campusflow_service import CampusFlowService
from app.services.discord_service import DiscordService
from app.services.google_classroom_service import GoogleClassroomService

router = APIRouter(prefix="/integrations", tags=["Integrations"])

campusflow_service = CampusFlowService()
google_classroom_service = GoogleClassroomService()
discord_service = DiscordService(campusflow_service)


@router.get("/status", response_model=IntegrationStatus)
async def get_integration_status() -> IntegrationStatus:
    return IntegrationStatus(
        google_classroom_connected=google_classroom_service.is_connected,
        discord_configured=discord_service.is_configured,
        discord_bot_configured=discord_service.bot_configured,
        discord_interactions_configured=discord_service.interactions_configured,
    )


@router.get("/google/auth-url", response_model=GoogleAuthUrlResponse)
async def get_google_auth_url() -> GoogleAuthUrlResponse:
    try:
        return google_classroom_service.build_auth_url()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/google/login")
async def login_google() -> RedirectResponse:
    try:
        auth = google_classroom_service.build_auth_url()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(auth.auth_url)


@router.get("/google/callback", response_model=GoogleCallbackResponse)
async def google_callback(
    code: str = Query(...),
    state: str | None = None,
) -> GoogleCallbackResponse:
    if state and state != "campusflow-local-demo":
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    try:
        return await google_classroom_service.handle_callback(code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Google OAuth failed: {exc}") from exc


@router.post("/google/classroom/sync", response_model=ClassroomSyncResponse)
async def sync_google_classroom() -> ClassroomSyncResponse:
    try:
        return await google_classroom_service.sync_assignments()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Google Classroom sync failed: {exc}") from exc


@router.post("/discord/scheduled-feedback/run-today", response_model=DiscordScheduledPromptResponse)
async def run_today_discord_scheduled_feedback() -> DiscordScheduledPromptResponse:
    try:
        return await discord_service.send_scheduled_class_prompts(include_future_today=True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Discord scheduled prompts failed: {exc}") from exc


@router.post("/discord/briefing", response_model=DiscordPromptResponse)
async def send_discord_briefing() -> DiscordPromptResponse:
    try:
        return await discord_service.send_briefing()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Discord briefing failed: {exc}") from exc


@router.post("/discord/interactions")
async def handle_discord_interaction(request: Request) -> dict:
    return await discord_service.handle_interaction(request)


@router.get("/discord/feedback-link", response_class=HTMLResponse)
async def submit_discord_feedback_link(
    subject_code: str,
    class_status: ClassStatus,
    attended: bool = False,
) -> str:
    try:
        result = campusflow_service.apply_feedback(
            AttendanceFeedback(
                subject_code=subject_code,
                class_status=class_status,
                attended=attended,
                note="Submitted from Discord feedback link",
            ),
            source="discord_feedback_link",
        )
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="Subject code not found") from exc

    subject = result.subject
    return f"""
    <!doctype html>
    <html>
      <head>
        <title>CampusFlow feedback saved</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
          body {{
            background: #f5f7fb;
            color: #121826;
            font-family: Arial, Helvetica, sans-serif;
            margin: 0;
            padding: 32px;
          }}
          main {{
            background: #ffffff;
            border: 1px solid #d8dee9;
            border-radius: 12px;
            margin: 0 auto;
            max-width: 560px;
            padding: 28px;
          }}
          h1 {{ margin-top: 0; }}
          p {{ color: #667085; line-height: 1.5; }}
          strong {{ color: #121826; }}
        </style>
      </head>
      <body>
        <main>
          <h1>Feedback saved</h1>
          <p>{result.message}</p>
          <p>
            <strong>{subject.code}</strong> is now previewed at
            <strong>{subject.attendance_percent}%</strong> attendance with
            <strong>{subject.bunk_budget}</strong> bunk(s) left.
          </p>
          <p>You can close this tab and return to Discord.</p>
        </main>
      </body>
    </html>
    """
