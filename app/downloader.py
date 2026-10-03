from __future__ import annotations

import asyncio
import logging
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import yt_dlp

from app.config import Settings
from app.models import DownloadedVideo, VideoItem
from app.video_tools import process_video_if_enabled


SUPPORTED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "tiktok.com",
    "www.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
}


QUALITY_FORMATS = {
    "low": "bv*[ext=mp4][height<=480]+ba[ext=m4a]/b[ext=mp4][height<=480]/best[height<=480]/best",
    "medium": "bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4][height<=720]/best[height<=720]/best",
    "high": "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]/best[height<=1080]/best",
}


class DownloadError(RuntimeError):
    pass


class YtDlpLogger:
    """Routes yt-dlp diagnostics into the application log instead of stderr."""

    def debug(self, message: str) -> None:
        logging.debug("yt-dlp: %s", message)

    def warning(self, message: str) -> None:
        logging.warning("yt-dlp: %s", message)

    def error(self, message: str) -> None:
        logging.warning("yt-dlp: %s", message)


def is_supported_url(text: str) -> bool:
    try:
        parsed = urlparse(text.strip())
    except ValueError:
        return False
    host = parsed.netloc.lower()
    return parsed.scheme in {"http", "https"} and any(host == h or host.endswith("." + h) for h in SUPPORTED_HOSTS)


def is_single_video_url(text: str) -> bool:
    """Recognize direct YouTube, TikTok, and Instagram video links."""
    try:
        parsed = urlparse(text.strip())
    except ValueError:
        return False

    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/").lower()

    if host == "youtu.be" and path:
        return True
    if "youtube.com" in host:
        return (path == "/watch" and "v=" in parsed.query) or path.startswith(("/shorts/", "/live/", "/clip/"))
    if host in {"vm.tiktok.com", "vt.tiktok.com"}:
        return True
    if "tiktok.com" in host and "/video/" in path:
        return True
    return "instagram.com" in host and path.startswith(("/reel/", "/p/", "/tv/"))


def normalize_source_url(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    is_single_video = is_single_video_url(url)

    if "youtube.com" in host and path:
        lower_path = path.lower()
        is_channel_page = (
            re.match(r"^/@[^/]+$", path)
            or re.match(r"^/channel/[^/]+$", path)
            or re.match(r"^/c/[^/]+$", path)
            or re.match(r"^/user/[^/]+$", path)
        )
        if is_channel_page and not lower_path.endswith(("/shorts", "/videos")):
            path = path + "/shorts"

    cleaned = parsed._replace(path=path or parsed.path, query=parsed.query if is_single_video else "", fragment="")
    return urlunparse(cleaned)


def _profile_requires_login(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return not is_single_video_url(url) and ("tiktok.com" in host or "instagram.com" in host)


def _base_ytdlp_options(settings: Settings) -> dict[str, Any]:
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "noplaylist": False,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "logger": YtDlpLogger(),
    }
    if settings.ytdlp_cookies_file:
        options["cookiefile"] = str(settings.ytdlp_cookies_file)
    if settings.ytdlp_cookies_from_browser:
        browser, separator, profile = settings.ytdlp_cookies_from_browser.partition(":")
        browser = browser.strip().lower()
        supported_browsers = {"brave", "chrome", "chromium", "edge", "firefox", "opera", "vivaldi", "whale"}
        if browser not in supported_browsers:
            raise DownloadError(
                "Неизвестный браузер в YTDLP_COOKIES_FROM_BROWSER. "
                "Используйте chrome, edge, firefox, brave, opera, vivaldi или chromium."
            )
        options["cookiesfrombrowser"] = (browser, profile.strip()) if separator and profile.strip() else (browser,)
    return options


def _access_error_message(error: Exception) -> str:
    details = str(error).lower()
    if any(fragment in details for fragment in ("private", "login", "cookies", "not available", "login required")):
        return (
            "Платформа не даёт гостевой доступ к этому аккаунту или ролику. "
            "Войдите в аккаунт, который имеет право на просмотр, и добавьте в .env строку "
            "YTDLP_COOKIES_FROM_BROWSER=chrome (или edge/firefox), затем перезапустите бота."
        )
    return f"yt-dlp не смог получить видео: {error}"


def _entry_url(entry: dict[str, Any]) -> str | None:
    for key in ("webpage_url", "url", "original_url"):
        value = entry.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value

    extractor = str(entry.get("ie_key") or entry.get("extractor_key") or "").lower()
    video_id = entry.get("id")
    if video_id and ("youtube" in extractor or re.match(r"^[A-Za-z0-9_-]{11}$", str(video_id))):
        return f"https://www.youtube.com/watch?v={video_id}"

    return None


def _title(entry: dict[str, Any], fallback: str) -> str:
    title = str(entry.get("title") or fallback).strip()
    return title[:120]


def _extract_latest_sync(url: str, count: int, settings: Settings) -> list[VideoItem]:
    source_url = normalize_source_url(url)
    options = _base_ytdlp_options(settings)
    options.update(
        {
            "extract_flat": "in_playlist",
            "playlistend": count,
            "skip_download": True,
            "ignoreerrors": not (is_single_video_url(source_url) or _profile_requires_login(source_url)),
        }
    )

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(source_url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise DownloadError(_access_error_message(exc)) from exc

    if not info:
        if _profile_requires_login(source_url):
            raise DownloadError(
                "TikTok или Instagram не показал видео без входа в аккаунт. "
                "Добавьте в .env: YTDLP_COOKIES_FROM_BROWSER=chrome, затем перезапустите бота."
            )
        raise DownloadError("Не удалось прочитать канал или профиль. Проверьте ссылку или файл cookies.txt.")

    entries = info.get("entries") if isinstance(info, dict) else None
    raw_entries = list(entries or [info])
    items: list[VideoItem] = []

    for index, entry in enumerate(raw_entries, start=1):
        if not isinstance(entry, dict):
            continue
        video_url = _entry_url(entry)
        if not video_url:
            continue
        items.append(
            VideoItem(
                title=_title(entry, f"Video {index}"),
                url=video_url,
                source=source_url,
                duration=entry.get("duration") if isinstance(entry.get("duration"), int) else None,
            )
        )
        if len(items) >= count:
            break

    if not items:
        raise DownloadError("Видео не найдены. Для YouTube попробуйте ссылку на /shorts или /videos канала.")

    return items


def _download_one_sync(item: VideoItem, folder: Path, quality: str, settings: Settings) -> DownloadedVideo:
    folder.mkdir(parents=True, exist_ok=True)
    output_template = str(folder / "%(extractor_key)s_%(id)s.%(ext)s")

    before = {path.resolve() for path in folder.glob("*") if path.is_file()}
    options = _base_ytdlp_options(settings)
    options.update(
        {
            "format": QUALITY_FORMATS.get(quality, QUALITY_FORMATS["medium"]),
            "outtmpl": output_template,
            "merge_output_format": "mp4",
            "noplaylist": True,
            "writethumbnail": False,
            "overwrites": True,
            "ignoreerrors": False,
        }
    )

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            result = ydl.extract_info(item.url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        raise DownloadError(_access_error_message(exc)) from exc

    if not result:
        raise DownloadError(f"Не удалось скачать: {item.title}")

    after = [path for path in folder.glob("*") if path.is_file() and path.resolve() not in before]
    if not after:
        requested = ydl.prepare_filename(result)
        candidate = Path(requested)
        if candidate.exists():
            after = [candidate]

    video_files = [path for path in after if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}]
    if not video_files:
        raise DownloadError(f"Не найден скачанный файл для: {item.title}")

    video_path = max(video_files, key=lambda path: path.stat().st_size)
    processed = process_video_if_enabled(video_path, settings)
    return DownloadedVideo(item=item, path=video_path, processed_path=processed)


async def extract_latest(url: str, count: int, settings: Settings) -> list[VideoItem]:
    return await asyncio.to_thread(_extract_latest_sync, url, count, settings)


async def download_videos(
    items: list[VideoItem],
    quality: str,
    settings: Settings,
    chat_id: int,
) -> list[DownloadedVideo]:
    session_dir = settings.download_dir / str(chat_id)
    if session_dir.exists():
        shutil.rmtree(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[DownloadedVideo] = []
    for item in items:
        downloaded.append(await asyncio.to_thread(_download_one_sync, item, session_dir, quality, settings))
    return downloaded


def cleanup_files(files: list[DownloadedVideo], chat_id: int, settings: Settings) -> None:
    if not settings.cleanup_after_send:
        return
    session_dir = settings.download_dir / str(chat_id)
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)
