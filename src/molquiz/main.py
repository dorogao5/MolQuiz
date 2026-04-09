from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import ORJSONResponse, Response
from sqlalchemy import text
from structlog import get_logger

from molquiz.bot.router import build_bot, build_dispatcher
from molquiz.config import get_settings
from molquiz.container import ApplicationContext, create_application_context
from molquiz.logging import configure_logging
from molquiz.metrics import render_metrics, webhook_updates_total

logger = get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.environment != "development")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        context = await create_application_context(settings)
        bot = build_bot(settings.telegram_token.get_secret_value(), settings.telegram_parse_mode)
        dispatcher = build_dispatcher(context)
        app.state.context = context
        app.state.bot = bot
        app.state.dispatcher = dispatcher

        if settings.webhook_url:
            await bot.set_webhook(settings.webhook_url)
            logger.info("webhook_configured", webhook_url=settings.webhook_url)

        try:
            yield
        finally:
            if settings.webhook_url:
                await bot.delete_webhook(drop_pending_updates=False)
            await bot.session.close()
            await context.close()

    app = FastAPI(
        title="MolQuiz",
        version="0.1.0",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def health_ready(request: Request) -> dict[str, str]:
        context: ApplicationContext = request.app.state.context
        async with context.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        if context.redis is not None:
            await context.redis.ping()
        if not await context.opsin_client.healthcheck():
            raise HTTPException(status_code=503, detail="OPSIN sidecar unavailable")
        return {"status": "ready"}

    @app.get("/metrics")
    async def metrics() -> Response:
        body, content_type = render_metrics()
        return Response(content=body, media_type=content_type)

    @app.post(settings.webhook_path)
    async def telegram_webhook(request: Request) -> dict[str, str]:
        payload = await request.json()
        from aiogram.types import Update

        webhook_updates_total.inc()
        telegram_update = Update.model_validate(payload, context={"bot": request.app.state.bot})
        await request.app.state.dispatcher.feed_update(request.app.state.bot, telegram_update)
        return {"status": "ok"}

    return app


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "molquiz.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8081,
        reload=settings.environment == "development",
    )
