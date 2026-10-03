from __future__ import annotations

import asyncio
import html
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.filters import Command
from aiogram.types import BotCommand, CallbackQuery, FSInputFile, Message

from app.config import Settings, load_settings
from app.downloader import DownloadError, cleanup_files, download_videos, extract_latest, is_single_video_url, is_supported_url
from app.keyboards import QUALITY_LABELS, count_keyboard, main_keyboard, single_video_keyboard
from app.models import DownloadedVideo
from app.video_tools import ffmpeg_available


NETWORK_RETRIES = 3
STARTUP_RETRY_MAX_DELAY = 60
VIDEO_UPLOAD_TIMEOUT_SECONDS = 180
VIDEO_UPLOAD_RETRIES = 2
T = TypeVar("T")
BOT_COMMANDS = [
    BotCommand(command="start", description="Открыть главное меню"),
    BotCommand(command="settings", description="Настройки загрузки"),
    BotCommand(command="help", description="Как пользоваться ботом"),
    BotCommand(command="cancel", description="Отменить текущее действие"),
]


@dataclass
class UserPrefs:
    count: int
    quality: str
    cleanup: bool
    processing: bool
    watermark_text: str


settings: Settings = load_settings()
dp = Dispatcher()
user_prefs: dict[int, UserPrefs] = {}
pending_urls: dict[int, str] = {}
active_jobs: set[int] = set()
awaiting_watermark: set[int] = set()


async def retry_telegram_request(
    request: Callable[[], Awaitable[T]],
    operation: str,
    retries: int = NETWORK_RETRIES,
) -> T | None:
    """Повторяет запрос к Telegram при кратковременном сетевом сбое."""
    for attempt in range(1, retries + 1):
        try:
            return await request()
        except TelegramNetworkError as exc:
            if attempt == retries:
                logging.error("Ошибка сети Telegram при %s: %s", operation, exc)
                return None
            delay = attempt * 2
            logging.warning(
                "Ошибка сети Telegram при %s (попытка %s/%s). Повтор через %s сек.: %s",
                operation,
                attempt,
                retries,
                delay,
                exc,
            )
            await asyncio.sleep(delay)


async def answer_text(message: Message, text: str, **kwargs: object) -> Message | None:
    return await retry_telegram_request(lambda: message.answer(text, **kwargs), "отправке сообщения")


async def answer_callback(callback: CallbackQuery, text: str, **kwargs: object) -> bool:
    result = await retry_telegram_request(lambda: callback.answer(text, **kwargs), "обработке нажатия кнопки")
    return result is not None


async def setup_commands(bot: Bot) -> None:
    await retry_telegram_request(
        lambda: bot.set_my_commands(BOT_COMMANDS, request_timeout=20),
        "обновлении меню команд",
    )


async def safe_update_settings_card(callback: CallbackQuery) -> None:
    prefs = prefs_for(callback.from_user.id)
    try:
        if callback.message is None:
            return
        await retry_telegram_request(
            lambda: callback.message.edit_text(
                settings_card(prefs),
                reply_markup=settings_keyboard(prefs),
            ),
            "обновлении настроек",
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


def prefs_for(user_id: int) -> UserPrefs:
    prefs = user_prefs.get(user_id)
    if prefs:
        return prefs
    prefs = UserPrefs(
        count=settings.default_video_count,
        quality=settings.default_quality,
        cleanup=settings.cleanup_after_send,
        processing=settings.process_own_videos,
        watermark_text=settings.watermark_text,
    )
    user_prefs[user_id] = prefs
    return prefs


def effective_settings(prefs: UserPrefs) -> Settings:
    return Settings(
        bot_token=settings.bot_token,
        download_dir=settings.download_dir,
        max_upload_mb=settings.max_upload_mb,
        default_video_count=prefs.count,
        default_quality=prefs.quality,
        cleanup_after_send=prefs.cleanup,
        ytdlp_cookies_file=settings.ytdlp_cookies_file,
        ytdlp_cookies_from_browser=settings.ytdlp_cookies_from_browser,
        process_own_videos=prefs.processing,
        watermark_text=prefs.watermark_text,
        telegram_proxy=settings.telegram_proxy,

    )


def settings_keyboard(prefs: UserPrefs):
    return main_keyboard(
        prefs.count,
        prefs.quality,
        prefs.cleanup,
        prefs.processing,
        bool(prefs.watermark_text),
    )


def settings_card(prefs: UserPrefs) -> str:
    ffmpeg_status = "доступен" if ffmpeg_available() else "не найден"
    cleanup = "включено" if prefs.cleanup else "выключено"
    processing = "включена" if prefs.processing else "выключена"
    watermark = "задан" if prefs.watermark_text else "не задан"
    return (
        "<b>Настройки загрузки</b>\n\n"
        f"Количество: <b>{prefs.count}</b>\n"
        f"Качество: <b>{QUALITY_LABELS[prefs.quality]}</b>\n"
        f"Автоудаление файлов: <b>{cleanup}</b>\n"
        f"Обработка своих видео: <b>{processing}</b>\n"
        f"Водяной знак: <b>{watermark}</b>\n"
        f"ffmpeg: <b>{ffmpeg_status}</b>"
    )


def welcome_text(prefs: UserPrefs) -> str:
    return (
        "<b>Загрузчик Shorts и TikTok</b>\n\n"
        "Отправьте ссылку на YouTube-канал, Shorts, TikTok или Instagram. "
        "После этого выберите 5 или 10 последних роликов.\n\n"
        f"Текущие настройки: <b>{prefs.count} видео</b>, "
        f"качество <b>{QUALITY_LABELS[prefs.quality].lower()}</b>.\n\n"
        "Для изменения параметров используйте кнопки ниже."
    )


def help_text() -> str:
    return (
        "<b>Как пользоваться ботом</b>\n\n"
        "1. Отправьте ссылку на канал YouTube, Shorts или профиль TikTok.\n"
        "2. Нажмите «Скачать 5 последних» или «Скачать 10 последних».\n"
        "3. Бот пришлёт найденные видео в этот чат.\n\n"
        "Поддерживаются ссылки вида:\n"
        "<code>youtube.com/@имя/shorts</code>\n"
        "<code>youtube.com/channel/...</code>\n"
        "<code>tiktok.com/@имя</code>\n"
        "<code>youtube.com/watch?v=...</code>\n"
        "<code>tiktok.com/@имя/video/...</code>\n\n"
        "<code>instagram.com/reel/...</code>\n"
        "<code>instagram.com/p/...</code>\n\n"
        "Обработка своих видео добавляет водяной знак и сжимает файл. "
        "Используйте её только для роликов, на которые у Вас есть права.\n\n"
        "Команды: /start, /settings, /help, /cancel"
    )


async def keep_typing(bot: Bot, chat_id: int, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(
                chat_id=chat_id,
                action=ChatAction.UPLOAD_VIDEO,
                request_timeout=10,
            )
        except TelegramNetworkError:
            logging.debug("Не удалось отправить временный статус загрузки.")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=8)
        except asyncio.TimeoutError:
            continue


def file_size_mb(path: Path) -> float:
    return path.stat().st_size / 1024 / 1024


async def send_downloaded(message: Message, videos: list[DownloadedVideo], prefs: UserPrefs) -> tuple[int, int]:
    max_mb = settings.max_upload_mb
    sent = 0
    failed = 0
    for index, video in enumerate(videos, start=1):
        path = video.send_path
        com = mix(parser)
        size = file_size_mb(path)
        title = html.escape(video.item.title)
        caption = f"{index}. <b>{title}</b>\n{html.escape(video.item.url)}"

        if size > max_mb:
            await answer_text(
                message,
                f"{index}. <b>{title}</b>\n"
                f"Размер файла: {size:.1f} МБ. Это больше установленного лимита Telegram: {max_mb} МБ.\n"
                f"Ссылка: {html.escape(video.item.url)}\n"
                f"Файл на компьютере: <code>{html.escape(str(path))}</code>"
            )
            failed += 1
            continue

        async def upload_video() -> Message:
            method = message.answer_video(
                video=FSInputFile(path),
                caption=caption,
                supports_streaming=True,
            )
            return await message.bot(method, request_timeout=VIDEO_UPLOAD_TIMEOUT_SECONDS)

        delivered = await retry_telegram_request(
            upload_video,
            "отправке видео",
            retries=VIDEO_UPLOAD_RETRIES,
        )
        if delivered is not None:
            sent += 1
        else:
            failed += 1

        await answer_text(message, f"Готово. Отправлено видео: {sent} из {len(videos)}.")
    return sent, failed


async def run_download(
    message: Message,
    url: str,
    count: int,
    user_id: int,
    save_default_count: bool = True,
) -> None:
    chat_id = message.chat.id
    if chat_id in active_jobs:
        await answer_text(message, "В этом чате уже идёт загрузка. Дождитесь завершения текущей задачи.")
        return

    prefs = prefs_for(user_id)
    if save_default_count:
        prefs.count = count
    local_settings = effective_settings(prefs)
    active_jobs.add(chat_id)
    stop_event = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(message.bot, chat_id, stop_event))

    try:
        source_label = "видео" if count == 1 else "канал или профиль"
        await answer_text(message, f"Проверяю {source_label} и выбираю последние {count} видео...")
        items = await extract_latest(url, count, local_settings)
        lines = "\n".join(f"{i}. {html.escape(item.title)}" for i, item in enumerate(items, start=1))
        await answer_text(message, f"<b>Найдено:</b>\n{lines}\n\nНачинаю загрузку.")

        videos = await download_videos(items, prefs.quality, local_settings, chat_id)
        sent, failed = await send_downloaded(message, videos, prefs)
        if failed:
            await answer_text(
                message,
                "Не все видео удалось отправить из-за нестабильной связи с Telegram. "
                f"Скачанные файлы сохранены на компьютере: <code>{html.escape(str(local_settings.download_dir / str(chat_id)))}</code>",
            )
        else:
            cleanup_files(videos, chat_id, local_settings)
    except DownloadError as exc:
        await answer_text(message, f"<b>Ошибка загрузки:</b> {html.escape(str(exc))}")
    except Exception as exc:
        logging.exception("Непредвиденная ошибка загрузки")
        await answer_text(message, f"<b>Непредвиденная ошибка:</b> {html.escape(str(exc))}")
    finally:
        active_jobs.discard(chat_id)
        stop_event.set()
        await typing_task


@dp.message(Command("start"))
async def start_handler(message: Message) -> None:
    prefs = prefs_for(message.from_user.id)
    await answer_text(message, welcome_text(prefs), reply_markup=settings_keyboard(prefs))


@dp.message(Command("help"))
async def help_handler(message: Message) -> None:
    await answer_text(message, help_text())


@dp.message(Command("settings"))
async def settings_handler(message: Message) -> None:
    prefs = prefs_for(message.from_user.id)
    await answer_text(message, settings_card(prefs), reply_markup=settings_keyboard(prefs))


@dp.message(Command("cancel"))
async def cancel_handler(message: Message) -> None:
    user_id = message.from_user.id
    pending_link = pending_urls.pop(user_id, None)
    was_editing_watermark = user_id in awaiting_watermark
    awaiting_watermark.discard(user_id)
    if pending_link or was_editing_watermark:
        await answer_text(message, "Отменено.")
    else:
        await answer_text(message, "Сейчас нечего отменять.")


@dp.callback_query(F.data.startswith("count:"))
async def count_callback(callback: CallbackQuery) -> None:
    prefs = prefs_for(callback.from_user.id)
    count = int(callback.data.split(":", 1)[1])
    if count not in {5, 10}:
        await answer_callback(callback, "Можно выбрать только 5 или 10 видео.", show_alert=True)
        return
    prefs.count = count
    await safe_update_settings_card(callback)
    await answer_callback(callback, f"Выбрано: {prefs.count} видео")


@dp.callback_query(F.data.startswith("quality:"))
async def quality_callback(callback: CallbackQuery) -> None:
    prefs = prefs_for(callback.from_user.id)
    quality = callback.data.split(":", 1)[1]
    if quality not in QUALITY_LABELS:
        await answer_callback(callback, "Неизвестное качество.", show_alert=True)
        return
    prefs.quality = quality
    await safe_update_settings_card(callback)
    await answer_callback(callback, f"Качество: {QUALITY_LABELS[quality].lower()}")


@dp.callback_query(F.data == "cleanup:toggle")
async def cleanup_callback(callback: CallbackQuery) -> None:
    prefs = prefs_for(callback.from_user.id)
    prefs.cleanup = not prefs.cleanup
    await safe_update_settings_card(callback)
    await answer_callback(callback, "Автоудаление изменено")


@dp.callback_query(F.data == "processing:toggle")
async def processing_callback(callback: CallbackQuery) -> None:
    prefs = prefs_for(callback.from_user.id)
    if not prefs.processing and not ffmpeg_available():
        await answer_callback(
            callback,
            "ffmpeg не найден. Установите ffmpeg, чтобы включить обработку своих видео.",
            show_alert=True,
        )
        return
    prefs.processing = not prefs.processing
    await safe_update_settings_card(callback)
    if prefs.processing:
        await answer_callback(
            callback,
            "Используйте обработку только для видео, на которые у Вас есть права.",
            show_alert=True,
        )
    else:
        await answer_callback(callback, "Обработка своих видео выключена")


@dp.callback_query(F.data == "watermark:edit")
async def watermark_edit_callback(callback: CallbackQuery) -> None:
    awaiting_watermark.add(callback.from_user.id)
    await answer_callback(callback, "Отправьте текст водяного знака следующим сообщением.")
    if callback.message is not None:
        await answer_text(
            callback.message,
            "Отправьте текст водяного знака. Максимум 48 символов.\n"
            "Для отмены используйте /cancel.",
        )


@dp.callback_query(F.data == "watermark:clear")
async def watermark_clear_callback(callback: CallbackQuery) -> None:
    prefs = prefs_for(callback.from_user.id)
    prefs.watermark_text = ""
    awaiting_watermark.discard(callback.from_user.id)
    await safe_update_settings_card(callback)
    await answer_callback(callback, "Водяной знак удалён")


@dp.callback_query(F.data == "help:show")
async def help_callback(callback: CallbackQuery) -> None:
    await answer_callback(callback, "Открываю справку")
    if callback.message is not None:
        await answer_text(callback.message, help_text())


@dp.callback_query(F.data == "settings:show")
async def settings_callback(callback: CallbackQuery) -> None:
    prefs = prefs_for(callback.from_user.id)
    await answer_callback(callback, "Открываю настройки")
    if callback.message is not None:
        await answer_text(callback.message, settings_card(prefs), reply_markup=settings_keyboard(prefs))


@dp.callback_query(F.data == "pending:cancel")
async def pending_cancel_callback(callback: CallbackQuery) -> None:
    pending_urls.pop(callback.from_user.id, None)
    await answer_callback(callback, "Ссылка отменена")
    if callback.message is not None:
        await answer_text(callback.message, "Ссылка отменена. Отправьте новую, когда будете готовы.")


@dp.callback_query(F.data == "run:single")
async def run_single_callback(callback: CallbackQuery) -> None:
    url = pending_urls.pop(callback.from_user.id, None)
    if not url:
        await answer_callback(callback, "Сначала отправьте ссылку на видео.", show_alert=True)
        return
    await answer_callback(callback, "Загрузка видео началась")
    if callback.message is None:
        return
    await run_download(callback.message, url, 1, callback.from_user.id, save_default_count=False)


@dp.callback_query(F.data.startswith("run:"))
async def run_callback(callback: CallbackQuery) -> None:
    url = pending_urls.get(callback.from_user.id)
    if not url:
        await answer_callback(callback, "Сначала отправьте ссылку на канал или профиль.", show_alert=True)
        return
    count = int(callback.data.split(":", 1)[1])
    if count not in {5, 10}:
        await answer_callback(callback, "Можно выбрать только 5 или 10 видео.", show_alert=True)
        return
    pending_urls.pop(callback.from_user.id, None)
    await answer_callback(callback, "Загрузка началась")
    if callback.message is None:
        return
    await run_download(callback.message, url, count, callback.from_user.id)


@dp.message(F.text)
async def text_handler(message: Message) -> None:
    text = (message.text or "").strip()
    user_id = message.from_user.id
    prefs = prefs_for(user_id)

    if user_id in awaiting_watermark:
        if is_supported_url(text):
            awaiting_watermark.discard(user_id)
        else:
            if len(text) > 48:
                await answer_text(message, "Текст слишком длинный. Укажите до 48 символов или отправьте ссылку на видео.")
                return
            prefs.watermark_text = text
            awaiting_watermark.discard(user_id)
            await answer_text(
                message,
                "Водяной знак сохранён. Для его применения включите «Обработка своих видео».\n\n" + settings_card(prefs),
                reply_markup=settings_keyboard(prefs),
            )
            return

    if not is_supported_url(text):
        await answer_text(
            message,
            "Отправьте ссылку на YouTube-канал, Shorts, TikTok или Instagram.\n"
            "Примеры:\n"
            "<code>https://www.youtube.com/@channel/shorts</code>\n"
            "<code>https://www.youtube.com/watch?v=...</code>\n"
            "<code>https://www.tiktok.com/@user</code>\n"
            "<code>https://www.tiktok.com/@user/video/...</code>\n"
            "<code>https://www.instagram.com/reel/...</code>",
        )
        return

    pending_urls[user_id] = text
    if is_single_video_url(text):
        await answer_text(
            message,
            "<b>Ссылка на видео сохранена.</b>\n\n"
            "Нажмите кнопку ниже, чтобы скачать этот ролик.",
            reply_markup=single_video_keyboard(),
        )
        return

    await answer_text(
        message,
        "<b>Ссылка сохранена.</b>\n\n"
        "Сколько последних видео скачать?\n"
        f"Текущее значение по умолчанию: <b>{prefs.count}</b>",
        reply_markup=count_keyboard(),
    )


async def main() -> None:
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    retry_delay = 2

    while True:
        session = AiohttpSession(proxy=settings.telegram_proxy, timeout=60)
        bot = Bot(
            token=settings.bot_token,
            session=session,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )

        try:
            logging.info("Подключение к Telegram...")
            await setup_commands(bot)
            await dp.start_polling(bot, close_bot_session=False)
            return
        except TelegramNetworkError as exc:
            logging.warning(
                "Нет соединения с api.telegram.org: %s. Повтор через %s сек.",
                exc,
                retry_delay,
            )
        finally:
            await bot.session.close()

        await asyncio.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, STARTUP_RETRY_MAX_DELAY)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
