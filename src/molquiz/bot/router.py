from __future__ import annotations

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message
from structlog import get_logger

from molquiz.bot.keyboards import (
    card_actions_keyboard,
    difficulty_keyboard,
    main_menu_keyboard,
    mode_keyboard,
    topics_keyboard,
)
from molquiz.container import ApplicationContext
from molquiz.db.models import ErrorCategory, Mode
from molquiz.metrics import attempts_total, cards_issued_total

logger = get_logger(__name__)


def build_bot(token: str, parse_mode: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode(parse_mode)))


def build_dispatcher(app_context: ApplicationContext) -> Dispatcher:
    router = Router(name="molquiz")

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        await app_context.practice_service.ensure_user(message.from_user)
        await message.answer(
            ("MolQuiz готов. Я присылаю скелетную формулу, а ты отвечаешь названием на русском или английском."),
            reply_markup=main_menu_keyboard(),
        )

    @router.message(F.text == "Новая молекула")
    async def new_card(message: Message) -> None:
        await app_context.practice_service.ensure_user(message.from_user)
        await _send_new_card(message, repeat_errors=False)

    @router.message(F.text == "Повторить ошибки")
    async def repeat_errors(message: Message) -> None:
        await app_context.practice_service.ensure_user(message.from_user)
        await _send_new_card(message, repeat_errors=True)

    @router.message(F.text == "Подсказка")
    async def hint(message: Message) -> None:
        hint_text = await app_context.practice_service.next_hint(message.from_user.id)
        if hint_text is None:
            await message.answer("Сначала получи карточку кнопкой «Новая молекула».")
            return
        await message.answer(hint_text, reply_markup=card_actions_keyboard())

    @router.message(F.text == "Показать ответ")
    async def reveal(message: Message) -> None:
        practice_card = await app_context.practice_service.reveal_answer(message.from_user.id)
        if practice_card is None:
            await message.answer("Активной карточки нет.")
            return
        await message.answer(
            _format_answer_reveal(practice_card),
            reply_markup=card_actions_keyboard(),
        )

    @router.message(F.text == "Режим")
    async def choose_mode(message: Message) -> None:
        settings = await app_context.practice_service.get_settings(message.from_user.id)
        await message.answer("Выбери режим тренировки.", reply_markup=mode_keyboard(settings.mode))

    @router.message(F.text == "Сложность")
    async def choose_difficulty(message: Message) -> None:
        settings = await app_context.practice_service.get_settings(message.from_user.id)
        await message.answer(
            "Выбери уровень сложности.",
            reply_markup=difficulty_keyboard(settings.difficulty_min),
        )

    @router.message(F.text == "Темы")
    async def choose_topics(message: Message) -> None:
        settings = await app_context.practice_service.get_settings(message.from_user.id)
        await message.answer(
            "Включи фильтры по темам.",
            reply_markup=topics_keyboard(settings.topic_tags),
        )

    @router.message(F.text == "Статистика")
    async def stats(message: Message) -> None:
        stats_row = await app_context.practice_service.get_stats(message.from_user.id)
        if stats_row is None:
            await message.answer("Статистика пока пуста.")
            return
        await message.answer(
            f"Попыток: <b>{stats_row.total_attempts}</b>\n"
            f"Верно: <b>{stats_row.correct_answers}</b>\n"
            f"Ошибок: <b>{stats_row.wrong_answers}</b>\n"
            f"Текущий стрик: <b>{stats_row.current_streak}</b>\n"
            f"Лучший стрик: <b>{stats_row.best_streak}</b>"
        )

    @router.callback_query(F.data.startswith("mode:"))
    async def set_mode(callback: CallbackQuery) -> None:
        mode = Mode(callback.data.split(":", 1)[1])
        settings = await app_context.practice_service.set_mode(callback.from_user.id, mode)
        await callback.message.edit_text(
            f"Режим обновлён: <b>{'IUPAC' if mode is Mode.IUPAC else 'Рациональная'}</b>.",
            reply_markup=mode_keyboard(settings.mode),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("difficulty:"))
    async def set_difficulty(callback: CallbackQuery) -> None:
        difficulty = int(callback.data.split(":", 1)[1])
        settings = await app_context.practice_service.set_difficulty(
            callback.from_user.id,
            difficulty,
        )
        await callback.message.edit_text(
            f"Сложность обновлена: <b>{settings.difficulty_min}</b>.",
            reply_markup=difficulty_keyboard(settings.difficulty_min),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("topic:"))
    async def toggle_topic(callback: CallbackQuery) -> None:
        topic = callback.data.split(":", 1)[1]
        settings = await app_context.practice_service.toggle_topic(callback.from_user.id, topic)
        await callback.message.edit_text(
            "Фильтр тем обновлён.",
            reply_markup=topics_keyboard(settings.topic_tags),
        )
        await callback.answer()

    @router.callback_query(F.data == "card:hint")
    async def hint_callback(callback: CallbackQuery) -> None:
        hint_text = await app_context.practice_service.next_hint(callback.from_user.id)
        if hint_text is None:
            await callback.answer("Нет активной карточки.", show_alert=True)
            return
        await callback.message.answer(hint_text, reply_markup=card_actions_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "card:reveal")
    async def reveal_callback(callback: CallbackQuery) -> None:
        practice_card = await app_context.practice_service.reveal_answer(callback.from_user.id)
        if practice_card is None:
            await callback.answer("Нет активной карточки.", show_alert=True)
            return
        await callback.message.answer(
            _format_answer_reveal(practice_card),
            reply_markup=card_actions_keyboard(),
        )
        await callback.answer()

    @router.callback_query(F.data == "card:next")
    async def next_callback(callback: CallbackQuery) -> None:
        await _send_new_card(callback.message, repeat_errors=False)
        await callback.answer()

    @router.message(F.text)
    async def answer(message: Message) -> None:
        result = await app_context.practice_service.evaluate_answer(
            message.from_user.id,
            message.text,
        )
        if result is None:
            await message.answer("Активной карточки нет. Нажми «Новая молекула».")
            return

        practice_card, outcome = result
        if outcome.accepted:
            attempts_total.labels(mode=practice_card.card.mode, verdict="correct").inc()
            await message.answer(
                (f"Верно.\nRU: <b>{practice_card.primary_ru}</b>\nEN: <b>{practice_card.primary_en}</b>"),
                reply_markup=card_actions_keyboard(),
            )
            return

        attempts_total.labels(mode=practice_card.card.mode, verdict="wrong").inc()
        error_title = _format_error_title(outcome.error_category)
        await message.answer(
            f"Пока нет.\n{error_title}\n{outcome.explanation}",
            reply_markup=card_actions_keyboard(),
        )

    async def _send_new_card(message: Message, *, repeat_errors: bool) -> None:
        practice_card = await app_context.practice_service.issue_card(
            message.from_user.id,
            repeat_errors=repeat_errors,
        )
        if practice_card is None:
            await message.answer("Подходящих карточек пока нет. Сначала загрузи контент или ослабь фильтры.")
            return

        cards_issued_total.labels(
            mode=practice_card.card.mode,
            repeat_errors=str(repeat_errors).lower(),
        ).inc()
        caption = (
            f"Режим: <b>{'IUPAC' if practice_card.card.mode == Mode.IUPAC.value else 'Рациональная'}</b>\n"
            f"Сложность: <b>{practice_card.card.difficulty}</b>\n"
            "Напиши название молекулы в чат."
        )
        sent_message = await _send_depiction(
            bot=message.bot,
            message=message,
            practice_card=practice_card,
            caption=caption,
        )
        if sent_message.photo:
            await app_context.practice_service.remember_telegram_file_id(
                practice_card.depiction.id,
                sent_message.photo[-1].file_id,
            )

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher


async def _send_depiction(*, bot: Bot, message: Message, practice_card, caption: str) -> Message:
    if practice_card.depiction.telegram_file_id:
        return await bot.send_photo(
            chat_id=message.chat.id,
            photo=practice_card.depiction.telegram_file_id,
            caption=caption,
            reply_markup=card_actions_keyboard(),
        )

    photo = FSInputFile(practice_card.image_path)
    return await bot.send_photo(
        chat_id=message.chat.id,
        photo=photo,
        caption=caption,
        reply_markup=card_actions_keyboard(),
    )


def _format_answer_reveal(practice_card) -> str:
    return f"Правильный ответ:\nRU: <b>{practice_card.primary_ru}</b>\nEN: <b>{practice_card.primary_en}</b>"


def _format_error_title(category: ErrorCategory | None) -> str:
    mapping = {
        ErrorCategory.LOCANTS: "Категория ошибки: локанты.",
        ErrorCategory.SUBSTITUENT_ORDER: "Категория ошибки: порядок заместителей.",
        ErrorCategory.MULTIPLICATIVE_PREFIX: "Категория ошибки: кратная приставка.",
        ErrorCategory.SUFFIX_MAIN_FUNCTION: "Категория ошибки: главная функция / суффикс.",
        ErrorCategory.PARENT_CHAIN: "Категория ошибки: главная цепь.",
        ErrorCategory.UNSUPPORTED_ALTERNATIVE_FORM: "Категория ошибки: форма названия не принята.",
        None: "Категория ошибки не определена.",
    }
    return mapping[category]
