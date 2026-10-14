"""采集提取结果的标准化与规范化清洗。

为何输出键格式固定：
内核自动化管线依赖统一的数据契约：id, url, title, author, published_at, excerpt, metrics, source。
无论目标站点是知乎、X 还是微博，无论使用 XHR JSON 还是 CSS 选择器提取，
都必须清洗为一致的 RFC3339 时间戳、绝对化 URL、去标签纯文本与度量指标字典。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import dateparser

HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def get_dot_path(data: Any, path: str) -> Any:
    """按点路径提取多层级嵌套字典或列表中的数据。

    支持例如: 'data.items.0.title' 或 'post.author.name'。
    """
    if not path or data is None:
        return None

    parts = path.split(".")
    curr = data
    for part in parts:
        if curr is None:
            return None
        if isinstance(curr, list):
            if part.isdigit():
                idx = int(part)
                if 0 <= idx < len(curr):
                    curr = curr[idx]
                else:
                    return None
            else:
                return None
        elif isinstance(curr, dict):
            curr = curr.get(part)
        else:
            return None
    return curr


def strip_html(text: str | None) -> str:
    """去除 HTML 标签并合并多余空白。"""
    if not text:
        return ""
    cleaned = HTML_TAG_PATTERN.sub(" ", text)
    return " ".join(cleaned.split()).strip()


def normalize_timestamp(val: Any) -> str | None:
    """将秒、毫秒时间戳或多种自然语言日期字符串统一转换为 RFC3339 (UTC) 格式。"""
    if val is None or val == "":
        return None

    try:
        if isinstance(val, (int, float)):
            # 区分毫秒与秒时间戳
            sec = val / 1000.0 if val > 1e11 else float(val)
            dt = datetime.fromtimestamp(sec, tz=UTC)
            return dt.isoformat()

        if isinstance(val, str):
            val_clean = val.strip()
            if not val_clean:
                return None
            # 优先解析纯数字字符串
            if val_clean.isdigit():
                n = int(val_clean)
                sec = n / 1000.0 if n > 1e11 else float(n)
                return datetime.fromtimestamp(sec, tz=UTC).isoformat()

            parsed = dateparser.parse(val_clean)
            if parsed:
                if parsed.tzinfo is None:
                    # 本地无时区时间视为 UTC
                    parsed = parsed.replace(tzinfo=UTC)
                else:
                    parsed = parsed.astimezone(UTC)
                return parsed.isoformat()
    except (ValueError, OSError, OverflowError):
        pass

    return str(val) if val else None


def normalize_item(
    raw_item: dict[str, Any], site_id: str, base_url: str
) -> dict[str, Any]:
    """标准化单条采集记录为符合内核契约的标准字典。"""
    raw_id = raw_item.get("id") or ""
    item_id = str(raw_id).strip()

    raw_url = raw_item.get("url") or ""
    url = urljoin(base_url, str(raw_url).strip()) if raw_url else base_url

    title = strip_html(str(raw_item.get("title") or ""))
    author = strip_html(str(raw_item.get("author") or ""))

    raw_pub = raw_item.get("published_at")
    published_at = normalize_timestamp(raw_pub)

    excerpt = strip_html(str(raw_item.get("excerpt") or ""))
    if len(excerpt) > 500:
        excerpt = excerpt[:497] + "..."

    # 提取所有形如 metrics.* 的度量指标
    metrics: dict[str, Any] = {}
    for k, v in raw_item.items():
        if k.startswith("metrics."):
            metric_key = k[len("metrics.") :]
            metrics[metric_key] = v
        elif k == "metrics" and isinstance(v, dict):
            metrics.update(v)

    return {
        "id": item_id,
        "url": url,
        "title": title,
        "author": author,
        "published_at": published_at,
        "excerpt": excerpt,
        "metrics": metrics,
        "source": site_id,
    }


def normalize_items(
    items: list[dict[str, Any]], site_id: str, base_url: str
) -> list[dict[str, Any]]:
    """批量清洗并返回标准记录列表。"""
    return [normalize_item(it, site_id, base_url) for it in items]
