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

    支持例如: 'data.items.0.title', 'items[0].id' 或 'post.author.name'。
    """
    if not path or data is None:
        return None

    # 兼容方括号数组下标访问，如 a[0].b -> a.0.b
    normalized_path = re.sub(r"\[(\d+)\]", r".\1", path)
    parts = normalized_path.split(".")
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


def get_path_alternatives(data: Any, spec: str) -> Any:
    """支持「a | b | c」备选路径：返回第一个非空值。

    为何需要：站点接口字段会迁移（如 X 把 screen_name 从 legacy 移到 core），
    备选路径让配方同时兼容新旧结构，而不必每次改版都失效。
    """
    for alt in spec.split("|"):
        val = get_dot_path(data, alt.strip())
        if val not in (None, ""):
            return val
    return None


def get_path_wildcard(data: Any, spec: str) -> list[Any]:
    """支持「*」通配列表下标并展平结果，同时支持「a | b」备选路径。

    例：'data.timeline.instructions.*.entries' 会收集每个 instruction 下的 entries，
    避免把条目所在下标（不同页面为 0 或 2）写死在配方里。
    """
    results: list[Any] = []
    for alt in spec.split("|"):
        parts = re.sub(r"\[(\d+)\]", r".\1", alt.strip()).split(".")
        nodes: list[Any] = [data]
        for part in parts:
            nxt: list[Any] = []
            for node in nodes:
                if part == "*":
                    if isinstance(node, list):
                        nxt.extend(node)
                    elif isinstance(node, dict):
                        nxt.extend(node.values())
                else:
                    val = get_dot_path(node, part)
                    if val is not None:
                        nxt.append(val)
            nodes = nxt
        for node in nodes:
            if isinstance(node, list):
                results.extend(node)
            elif node is not None:
                results.append(node)
        if results:
            break
    return results


TEMPLATE_FIELD = re.compile(r"\{([A-Za-z0-9_.]+)\}")


def render_field_template(template: str, item: dict[str, Any]) -> str | None:
    """渲染「=前缀」模板字段，如 '=https://x.com/{author}/status/{tweet_id}'。

    任一占位字段为空时返回 None，避免生成残缺链接。
    """
    missing = False

    def repl(m: re.Match[str]) -> str:
        nonlocal missing
        val = item.get(m.group(1))
        if val in (None, ""):
            missing = True
            return ""
        return str(val)

    out = TEMPLATE_FIELD.sub(repl, template)
    return None if missing else out


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

            # X/Twitter 的 created_at 形如 "Fri Oct 16 16:28:00 +0000 2026"，dateparser 无法解析
            try:
                return (
                    datetime.strptime(val_clean, "%a %b %d %H:%M:%S %z %Y")
                    .astimezone(UTC)
                    .isoformat()
                )
            except ValueError:
                pass

            parsed = dateparser.parse(val_clean)
            if parsed:
                if parsed.tzinfo is None:
                    # 本地无时区时间视为 UTC
                    parsed = parsed.replace(tzinfo=UTC)
                else:
                    parsed = parsed.astimezone(UTC)
                return parsed.isoformat()
    except ValueError, OSError, OverflowError:
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
