"""网页内容精炼提取与多模式阅读。

为何需要该模块：
1. 大模型阅读网页时，直接读取 raw HTML 会耗费海量 token 甚至超出上下文限制；
2. 提供 article（智能正文）、markdown（语义结构）、text（纯文本）、links（超链列表）四种低成本阅读模式；
3. 支持 sha256 校验与字符级透明分页，保证长文获取的确定性。
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal
from urllib.parse import urljoin

import trafilatura
from patchright.async_api import Page

from .browser_hub import HubError
from .snapshot_js import EXTRACT_JS


def paginate_content(
    full_content: str, offset: int = 0, max_chars: int = 6000
) -> tuple[str, str, bool, int | None]:
    """对提取得到的全文进行切片分页与内容哈希计算。"""
    content_hash = hashlib.sha256(full_content.encode("utf-8")).hexdigest()[:16]
    safe_offset = max(0, offset)
    slice_end = safe_offset + max_chars
    content_slice = full_content[safe_offset:slice_end]
    truncated = slice_end < len(full_content)
    next_offset = slice_end if truncated else None
    return content_slice, content_hash, truncated, next_offset


async def read_page_content(
    page: Page,
    mode: Literal["article", "markdown", "text", "links"] = "article",
    max_chars: int = 6000,
    offset: int = 0,
    selector: str | None = None,
) -> dict[str, Any]:
    """按指定模式提取页面文本或链接列表并分页返回。"""
    url = page.url
    title = await page.title()

    full_text = ""

    if mode == "article":
        html = await page.content()
        extracted = trafilatura.extract(
            html,
            output_format="markdown",
            include_links=True,
            url=url,
        )
        if extracted and extracted.strip():
            full_text = extracted.strip()
        else:
            # 智能提取失败时降级到 body/main 的文本转换
            full_text = await _extract_simplified_markdown(page, selector)

    elif mode == "markdown":
        full_text = await _extract_simplified_markdown(page, selector)

    elif mode == "text":
        js = "(sel) => (sel ? document.querySelector(sel) : document.body)?.innerText || ''"
        text_res = await page.evaluate(js, selector)
        full_text = (text_res or "").strip()

    elif mode == "links":
        links_js = """
        () => {
            const anchors = Array.from(document.querySelectorAll("a[href]"));
            const seen = new Set();
            const res = [];
            for (const a of anchors) {
                const text = (a.innerText || "").trim().replace(/\\s+/g, " ");
                const href = a.href;
                if (!href || href.startsWith("javascript:")) continue;
                const key = text + "|" + href;
                if (seen.has(key)) continue;
                seen.add(key);
                res.push([text, href]);
                if (res.length >= 200) break;
            }
            return res;
        }
        """
        links_data = await page.evaluate(links_js)
        # 转为规范换行文本列表
        full_text = "\n".join(
            f"- [{t}]({h})" if t else f"- <{h}>" for t, h in links_data
        )

    content, content_hash, truncated, next_offset = paginate_content(
        full_text, offset=offset, max_chars=max_chars
    )

    return {
        "content": content,
        "content_hash": content_hash,
        "truncated": truncated,
        "next_offset": next_offset,
        "url": url,
        "title": title,
    }


async def _extract_simplified_markdown(page: Page, selector: str | None = None) -> str:
    """提取页面或指定选择器的 innerHTML 并转换为简化的 Markdown 文本。"""
    if selector:
        js = """
        (sel) => {
            const el = document.querySelector(sel);
            return el ? el.innerHTML : '';
        }
        """
        html_segment = await page.evaluate(js, selector)
        if html_segment and html_segment.strip():
            txt = trafilatura.html2txt(html_segment)
            if txt and txt.strip():
                return txt.strip()

    # 兜底提取页面主要正文区域
    html = await page.content()
    txt = trafilatura.html2txt(html)
    return (txt or "").strip()


async def extract_structured(
    page: Page,
    container: str,
    fields: dict[str, str],
    max_items: int = 50,
) -> dict[str, Any]:
    """通过参数化 JS 常量函数提取结构化数据，自动补全相对 URL。"""
    res = await page.evaluate(
        EXTRACT_JS,
        {"container": container, "fields": fields, "max_items": max_items},
    )

    if isinstance(res, dict) and res.get("error"):
        raise HubError("invalid_args", f"无效的 CSS 选择器语法: {res.get('message')}")

    items = res.get("items", [])
    base_url = page.url

    # 将所有链接/图片属性绝对化
    for item in items:
        for k, v in item.items():
            if isinstance(v, str) and v.startswith(("/", "./", "../")):
                item[k] = urljoin(base_url, v)

    return {"items": items, "count": len(items)}
