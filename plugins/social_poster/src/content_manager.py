"""Content formatting, splitting, and hashtag utilities."""

import re

# ─── Per-platform limits ──────────────────────────────────────────────────────

PLATFORM_LIMITS = {
    "twitter": 280,
    "weibo": 2000,
    "xiaohongshu": 1000,
    "douyin": 150,
    "instagram": 2200,
    "facebook": 63206,
    "wechat": 20000,
    "tiktok": 2200,
    "linkedin": 3000,
    "threads": 500,
}

# ─── Smart truncation ─────────────────────────────────────────────────────────


def smart_truncate(text: str, max_length: int) -> str:
    """Truncate at max_length without breaking URLs or hashtags."""
    if len(text) <= max_length:
        return text
    protected = [m.span() for m in re.finditer(r"(https?://\S+|#\S+)", text)]
    cut = max_length - 3
    for start, end in protected:
        if start < cut < end:
            cut = start
            break
    return text[:cut].strip() + "..."


# ─── Thread splitting ─────────────────────────────────────────────────────────


def split_into_thread(text: str, max_len: int = 260) -> list:
    """Split long text into a list of tweet-sized chunks.
    Tries to split on sentence boundaries, adds n/N counter."""
    sentences = re.split(r"(?<=[。！？.!?])\s*", text.strip())
    chunks, current = [], ""
    for sentence in sentences:
        if not sentence:
            continue
        candidate = (current + " " + sentence).strip() if current else sentence
        if len(candidate) <= max_len:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # If a single sentence is too long, hard-split it
            while len(sentence) > max_len:
                chunks.append(sentence[: max_len - 1] + "…")
                sentence = sentence[max_len - 1 :]
            current = sentence
    if current:
        chunks.append(current)

    total = len(chunks)
    if total > 1:
        chunks = [f"{c} ({i + 1}/{total})" for i, c in enumerate(chunks)]
    return chunks


# ─── Hashtag suggestion ───────────────────────────────────────────────────────

# Simple keyword → hashtag map (extend as needed)
_KEYWORD_HASHTAGS: dict = {
    "科技": ["#科技", "#AI", "#互联网"],
    "技术": ["#技术", "#编程", "#开发者"],
    "ai": ["#AI", "#人工智能", "#ChatGPT"],
    "美食": ["#美食", "#吃货", "#料理"],
    "旅游": ["#旅行", "#旅游", "#度假"],
    "穿搭": ["#穿搭", "#时尚", "#OOTD"],
    "健身": ["#健身", "#运动", "#减脂"],
    "python": ["#Python", "#编程", "#开发"],
    "travel": ["#travel", "#explore", "#wanderlust"],
    "food": ["#food", "#foodie", "#delicious"],
    "tech": ["#tech", "#technology", "#innovation"],
    "fitness": ["#fitness", "#gym", "#workout"],
    "fashion": ["#fashion", "#style", "#OOTD"],
    "music": ["#music", "#nowplaying", "#musician"],
    "product": ["#review", "#unboxing", "#recommend"],
}


def suggest_hashtags(content: str, platform: str, max_tags: int = 5) -> list:
    """Return a list of suggested hashtag strings based on content keywords."""
    content_lower = content.lower()
    found: list = []
    seen: set = set()
    for kw, tags in _KEYWORD_HASHTAGS.items():
        if kw in content_lower:
            for tag in tags:
                if tag not in seen:
                    found.append(tag)
                    seen.add(tag)
    # Platform-specific limits
    if platform in ("twitter", "threads"):
        max_tags = min(max_tags, 3)
    elif platform in ("xiaohongshu",):
        max_tags = min(max_tags, 10)
    return found[:max_tags]


# ─── Main formatter ───────────────────────────────────────────────────────────


async def format_content_for_platform(platform: str, content: str) -> str:
    """Apply per-platform truncation and formatting."""
    limit = PLATFORM_LIMITS.get(platform, 5000)
    return smart_truncate(content, limit)
