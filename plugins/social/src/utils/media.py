"""Media type detection utilities."""

from pathlib import Path

IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".heic",
    ".bmp",
    ".tiff",
    ".avif",
}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".flv", ".ts"}
AUDIO_EXTS = {".mp3", ".wav", ".aac", ".m4a", ".ogg", ".flac"}


def media_type(path: str) -> str:
    """Return 'image', 'video', 'audio', or 'unknown'."""
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    return "unknown"


def split_by_type(paths: list) -> dict:
    """Split a list of paths into {'images': [...], 'videos': [...], 'audios': [...]}."""
    result: dict = {"images": [], "videos": [], "audios": []}
    for p in paths or []:
        t = media_type(p)
        if t == "image":
            result["images"].append(p)
        elif t == "video":
            result["videos"].append(p)
        elif t == "audio":
            result["audios"].append(p)
    return result


def has_video(paths: list) -> bool:
    return any(media_type(p) == "video" for p in (paths or []))


def has_audio(paths: list) -> bool:
    return any(media_type(p) == "audio" for p in (paths or []))
