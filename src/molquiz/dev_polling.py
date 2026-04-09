from __future__ import annotations

import asyncio

from structlog import get_logger

from molquiz.bot.router import build_bot, build_dispatcher
from molquiz.config import get_settings
from molquiz.container import create_application_context
from molquiz.logging import configure_logging

logger = get_logger(__name__)


async def _main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=False)
    context = await create_application_context(settings)
    bot = build_bot(settings.telegram_token.get_secret_value(), settings.telegram_parse_mode)
    dispatcher = build_dispatcher(context)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("polling_started")
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await context.close()


def run() -> None:
    asyncio.run(_main())
