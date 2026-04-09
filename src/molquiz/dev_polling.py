from __future__ import annotations

import asyncio
import sys

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramConflictError,
    TelegramNetworkError,
    TelegramUnauthorizedError,
)
from pydantic import ValidationError
from structlog import get_logger

from molquiz.bot.router import build_bot, build_dispatcher
from molquiz.config import Settings, get_settings
from molquiz.container import create_application_context
from molquiz.logging import configure_logging

logger = get_logger(__name__)


async def _run_once(settings: Settings) -> None:
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


async def _main(settings: Settings) -> None:
    while True:
        try:
            await _run_once(settings)
            return
        except TelegramConflictError as exc:
            logger.error(
                "polling_conflict",
                error=str(exc),
                hint="another instance is already polling this bot; stop the other instance or wait",
            )
        except TelegramUnauthorizedError as exc:
            logger.error(
                "telegram_unauthorized",
                error=str(exc),
                hint="check MOLQUIZ_TELEGRAM_TOKEN or token in .env",
            )
            raise
        except TelegramNetworkError as exc:
            logger.error("telegram_network_error", error=str(exc), retry_in_seconds=5)
        except TelegramAPIError as exc:
            logger.error("telegram_api_error", error=str(exc), retry_in_seconds=5)
        except Exception as exc:  # noqa: BLE001
            logger.exception("polling_crashed", error=str(exc), retry_in_seconds=5)

        await asyncio.sleep(5)


def run() -> None:
    try:
        settings = get_settings()
    except ValidationError as exc:
        print(
            "MolQuiz config error: set MOLQUIZ_TELEGRAM_TOKEN or token in .env before starting the bot.",
            file=sys.stderr,
        )
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc

    configure_logging(settings.log_level, json_logs=False)
    asyncio.run(_main(settings))
