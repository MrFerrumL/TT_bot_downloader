from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


QUALITY_LABELS = {
    "low": "Низкое",
    "medium": "Среднее",
    "high": "Высокое",
}


def main_keyboard(count: int, quality: str, cleanup: bool, processing: bool, watermark_set: bool) -> InlineKeyboardMarkup:
    """Settings panel shown below the welcome and settings messages."""
    cleanup_text = "Автоудаление: включено" if cleanup else "Автоудаление: выключено"
    processing_text = "Обработка своих видео: включена" if processing else "Обработка своих видео: выключена"
    watermark_text = "Изменить водяной знак" if watermark_set else "Добавить водяной знак"

    rows = [
        [
            InlineKeyboardButton(text=("Выбрано: 5 видео" if count == 5 else "5 видео"), callback_data="count:5"),
            InlineKeyboardButton(text=("Выбрано: 10 видео" if count == 10 else "10 видео"), callback_data="count:10"),
        ],
        [
            InlineKeyboardButton(text="Качество: низкое", callback_data="quality:low"),
            InlineKeyboardButton(text="Качество: среднее", callback_data="quality:medium"),
        ],
        [InlineKeyboardButton(text="Качество: высокое", callback_data="quality:high")],
        [InlineKeyboardButton(text=cleanup_text, callback_data="cleanup:toggle")],
        [InlineKeyboardButton(text=processing_text, callback_data="processing:toggle")],
        [InlineKeyboardButton(text=watermark_text, callback_data="watermark:edit")],
    ]
    if watermark_set:
        rows.append([InlineKeyboardButton(text="Удалить водяной знак", callback_data="watermark:clear")])
    rows.append([InlineKeyboardButton(text="Справка", callback_data="help:show")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def count_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Скачать 5 последних", callback_data="run:5"),
                InlineKeyboardButton(text="Скачать 10 последних", callback_data="run:10"),
            ],
            [
                InlineKeyboardButton(text="Настроить качество", callback_data="settings:show"),
                InlineKeyboardButton(text="Отменить", callback_data="pending:cancel"),
            ],
        ]
    )


def single_video_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Скачать видео", callback_data="run:single")],
            [
                InlineKeyboardButton(text="Настроить качество", callback_data="settings:show"),
                InlineKeyboardButton(text="Отменить", callback_data="pending:cancel"),
            ],
        ]
    )
