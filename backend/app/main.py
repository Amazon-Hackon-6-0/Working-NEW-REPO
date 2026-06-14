import asyncio
from contextlib import suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import agent, campusflow, health, integrations
from app.core.config import settings
from app.routes.campusbuddy.router import router as campusbuddy_router


async def _discord_attendance_scheduler() -> None:
    while True:
        try:
            await integrations.discord_service.send_scheduled_class_prompts()
        except Exception as exc:
            print(f"Discord attendance scheduler skipped a run: {exc}")
        await asyncio.sleep(60)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="FastAPI backend template for HackOn with Amazon 2026.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(agent.router, prefix=settings.api_v1_prefix)
    app.include_router(campusflow.router, prefix=settings.api_v1_prefix)
    app.include_router(integrations.router, prefix=settings.api_v1_prefix)
    app.include_router(campusbuddy_router, prefix="/api/campusbuddy", tags=["campusbuddy"])

    @app.on_event("startup")
    async def start_discord_attendance_scheduler() -> None:
        if not settings.discord_scheduler_enabled:
            app.state.discord_attendance_scheduler_task = None
            return
        task = getattr(app.state, "discord_attendance_scheduler_task", None)
        if task and not task.done():
            return
        app.state.discord_attendance_scheduler_task = asyncio.create_task(
            _discord_attendance_scheduler()
        )

    @app.on_event("shutdown")
    async def stop_discord_attendance_scheduler() -> None:
        task = getattr(app.state, "discord_attendance_scheduler_task", None)
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    return app


app = create_app()
