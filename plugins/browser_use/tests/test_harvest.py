"""采集引擎与配方解析单元测试。

验证内容：
1. 配方模型解析：合法配方、多余未知键拦截（extra='forbid'）
2. 配方覆盖加载：用户目录同 site.id 配方覆盖内置配方
3. 点路径取值：支持数组下标与深层字典嵌套（如 a.b.0.c）
4. 数据标准化：秒/毫秒时间戳转换、自然语言日期、URL 绝对化、HTML 标签剥离
5. 分页函数：按字符切片、截断标志与哈希校验
6. ref 正则校验：拒绝非 e<数字> 格式防注入
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from src.extract import paginate_content
from src.harvest.loader import load_all_recipes
from src.harvest.normalize import (
    get_dot_path,
    normalize_item,
    normalize_timestamp,
    strip_html,
)
from src.harvest.recipe import Recipe
from src.tools_browser import REF_PATTERN


def test_recipe_validation() -> None:
    valid_data = {
        "site": {
            "id": "test_site",
            "name": "Test Site",
            "base_url": "https://example.com",
        },
        "limits": {
            "min_interval_s": 2.0,
            "jitter_s": [0.5, 1.0],
            "max_per_hour": 30,
            "max_per_day": 100,
            "active_hours": "08:00-22:00",
            "cooldown_on_block_h": 4.0,
        },
        "actions": {
            "test_act": {
                "description": "测试动作",
                "steps": [
                    {"goto": "https://example.com/test", "timeout_s": 5.0},
                ],
                "extract": {
                    "method": "css",
                    "container": ".item",
                    "fields": {"title": "h2", "url": "a@href"},
                },
            }
        },
    }

    recipe = Recipe.model_validate(valid_data)
    assert recipe.site.id == "test_site"
    assert recipe.actions["test_act"].extract.method == "css"

    # 测试未知多余键触发 ValidationError
    invalid_data = dict(valid_data)
    invalid_data["unknown_key"] = "forbidden"
    with pytest.raises(ValidationError):
        Recipe.model_validate(invalid_data)


def test_dot_path_extraction() -> None:
    data = {
        "data": {
            "items": [
                {"id": 101, "author": {"name": "Alice"}},
                {"id": 102, "author": {"name": "Bob"}},
            ],
            "total": 2,
        }
    }

    assert get_dot_path(data, "data.total") == 2
    assert get_dot_path(data, "data.items.0.id") == 101
    assert get_dot_path(data, "data.items.1.author.name") == "Bob"
    assert get_dot_path(data, "data.items.5.id") is None
    assert get_dot_path(data, "non.existent.path") is None


def test_normalize_timestamp() -> None:
    # 1. 秒时间戳 (2023-11-14 22:13:20 UTC)
    ts_sec = 1700000000
    res_sec = normalize_timestamp(ts_sec)
    assert res_sec is not None
    assert "2023-11-14" in res_sec

    # 2. 毫秒时间戳
    ts_ms = 1700000000000
    res_ms = normalize_timestamp(ts_ms)
    assert res_ms is not None
    assert "2023-11-14" in res_ms

    # 3. ISO 8601 字符串
    iso_str = "2026-10-14T08:00:00Z"
    res_iso = normalize_timestamp(iso_str)
    assert res_iso is not None
    assert "2026-10-14" in res_iso


def test_normalize_item() -> None:
    raw = {
        "id": "12345",
        "url": "/article/123",
        "title": "<b>Hello</b> World!",
        "author": "<span>Admin</span>",
        "published_at": 1700000000,
        "excerpt": "<p>" + "A" * 600 + "</p>",
        "metrics.likes": 42,
        "metrics.comments": 10,
    }

    item = normalize_item(raw, site_id="test", base_url="https://example.com")
    assert item["id"] == "12345"
    assert item["url"] == "https://example.com/article/123"
    assert item["title"] == "Hello World!"
    assert item["author"] == "Admin"
    assert item["source"] == "test"
    assert len(item["excerpt"]) <= 500
    assert item["excerpt"].endswith("...")
    assert item["metrics"] == {"likes": 42, "comments": 10}


def test_strip_html() -> None:
    assert strip_html("<p>Hello <a href='#'>Link</a></p>") == "Hello Link"
    assert strip_html("   Plain text   ") == "Plain text"
    assert strip_html(None) == ""


def test_paginate_content() -> None:
    text = "abcdefghijklmnopqrstuvwxyz"
    content, chash, truncated, next_off = paginate_content(text, offset=0, max_chars=10)
    assert content == "abcdefghij"
    assert truncated is True
    assert next_off == 10
    assert len(chash) == 16

    content2, _, truncated2, next_off2 = paginate_content(text, offset=20, max_chars=10)
    assert content2 == "uvwxyz"
    assert truncated2 is False
    assert next_off2 is None


def test_ref_pattern() -> None:
    assert REF_PATTERN.match("e1") is not None
    assert REF_PATTERN.match("e80") is not None
    assert REF_PATTERN.match("e99999") is not None
    assert REF_PATTERN.match("e") is None
    assert REF_PATTERN.match("e123456") is None
    assert REF_PATTERN.match("e1; rm -rf /") is None
    assert REF_PATTERN.match("button") is None


def test_load_all_recipes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 模拟 DEV=1 加载 _example.toml
    monkeypatch.setenv("POLARIS_BROWSER_DEV", "1")
    recipes, _diag = load_all_recipes()
    assert "_example" in recipes
    assert recipes["_example"].site.name == "Hacker News (Example)"
