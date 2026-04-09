from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from molquiz.db.models import Mode
from molquiz.services.practice_service import SUPPORTED_TOPICS


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="Новая молекула"), KeyboardButton(text="Показать ответ")],
        [KeyboardButton(text="Режим"), KeyboardButton(text="Сложность")],
        [KeyboardButton(text="Темы"), KeyboardButton(text="Подсказка")],
        [KeyboardButton(text="Повторить ошибки"), KeyboardButton(text="Статистика")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def card_actions_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Подсказка", callback_data="card:hint")
    builder.button(text="Показать ответ", callback_data="card:reveal")
    builder.button(text="Следующая", callback_data="card:next")
    builder.adjust(2, 1)
    return builder.as_markup()


def mode_keyboard(current_mode: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for mode in Mode:
        marker = "• " if mode.value == current_mode else ""
        title = "IUPAC" if mode is Mode.IUPAC else "Рациональная"
        builder.button(text=f"{marker}{title}", callback_data=f"mode:{mode.value}")
    builder.adjust(1)
    return builder.as_markup()


def difficulty_keyboard(current_difficulty: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for difficulty in range(1, 6):
        marker = "• " if difficulty == current_difficulty else ""
        builder.button(text=f"{marker}{difficulty}", callback_data=f"difficulty:{difficulty}")
    builder.adjust(5)
    return builder.as_markup()


def topics_keyboard(active_topics: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="• Все" if not active_topics else "Все",
        callback_data="topic:all",
    )
    for key, title in SUPPORTED_TOPICS:
        marker = "• " if key in active_topics else ""
        builder.button(text=f"{marker}{title}", callback_data=f"topic:{key}")
    builder.adjust(1, 2, 2, 2)
    return builder.as_markup()
