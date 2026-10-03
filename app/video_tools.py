from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from app.config import Settings

try:
    import imageio_ffmpeg
except ImportError:  # The project still works when optional video processing is unavailable.
    imageio_ffmpeg = None


@lru_cache(maxsize=1)
def ffmpeg_path() -> str | None:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    if imageio_ffmpeg is None:
        return None

    try:
        bundled_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
    return bundled_ffmpeg if Path(bundled_ffmpeg).is_file() else None


def ffmpeg_available() -> bool:
    return ffmpeg_path() is not None


def process_video_if_enabled(video_path: Path, settings: Settings) -> Path | None:
    """Сжимает и добавляет подпись только к роликам, на которые есть права."""
    if not settings.process_own_videos:
        return None
    executable = ffmpeg_path()
    if not executable:
        return None

    output_path = video_path.with_name(video_path.stem + "_processed.mp4")
    vf_parts = ["scale='min(720,iw)':-2"]

    if settings.watermark_text:
        text = (
            settings.watermark_text.replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "\\'")
            .replace(",", "\\,")
            .replace("%", "\\%")
        )
        vf_parts.append(
            "drawtext="
            f"text='{text}':"
            "fontcolor=white@0.85:"
            "fontsize=24:"
            "box=1:"
            "boxcolor=black@0.35:"
            "boxborderw=8:"
            "x=w-tw-24:"
            "y=h-th-24"
        )

    command = [
        executable,
        "-y",
        "-i",
        str(video_path),
        "-vf",
        ",".join(vf_parts),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    completed = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if completed.returncode != 0 or not output_path.exists():
        return None
    return output_path
