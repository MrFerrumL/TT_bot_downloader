from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    bot_token: str
    download_dir: Path
    max_upload_mb: int
    default_video_count: int
    default_quality: str
    cleanup_after_send: bool
    ytdlp_cookies_file: Path | None
    ytdlp_cookies_from_browser: str | None
    process_own_videos: bool
    watermark_text: str
    telegram_proxy: str | None


def load_settings() -> Settings:
    load_dotenv(BASE_DIR / ".env")

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is missing. Create .env from .env.example and paste your token.")

    download_dir_raw = os.getenv("DOWNLOAD_DIR", "downloads").strip() or "downloads"
    download_dir = Path(download_dir_raw)
    if not download_dir.is_absolute():
        download_dir = BASE_DIR / download_dir

    count = _int_env("DEFAULT_VIDEO_COUNT", 5)
    if count not in {5, 10}:
        count = 5

    quality = os.getenv("DEFAULT_QUALITY", "medium").strip().lower()
    if quality not in {"low", "medium", "high"}:
        quality = "medium"

    cookies_raw = os.getenv("YTDLP_COOKIES_FILE", "").strip()
    cookies_file = Path(cookies_raw) if cookies_raw else None
    cookies_from_browser = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip() or None
    telegram_proxy = os.getenv("TELEGRAM_PROXY", "").strip() or None

    return Settings(
        bot_token=token,
        download_dir=download_dir,
        max_upload_mb=max(1, _int_env("MAX_UPLOAD_MB", 49)),
        default_video_count=count,
        default_quality=quality,
        cleanup_after_send=_bool_env("CLEANUP_AFTER_SEND", True),
        ytdlp_cookies_file=cookies_file,
        ytdlp_cookies_from_browser=cookies_from_browser,
        process_own_videos=_bool_env("PROCESS_OWN_VIDEOS", False),
        watermark_text=os.getenv("WATERMARK_TEXT", "").strip(),
        telegram_proxy=telegram_proxy,
    )
