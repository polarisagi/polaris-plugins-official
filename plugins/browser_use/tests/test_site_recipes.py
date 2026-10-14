"""站点采集配方与测试夹具验证单元测试。

验证内容：
1. 4 大站点配方 (zhihu, xiaohongshu, x, weibo) 正确解析，状态均为 beta；
2. 站点限速、风控信号 (block_signals) 与活跃时间窗契约校验；
3. 各站点各个动作的 XHR 样本提取与 normalize_items 结构化清洗；
4. 各动作均包含合法的 CSS 选择器降级 (extract_fallback) 规则；
5. harvest_recipes 工具正确返回所有配方元数据；
6. _calc_field_rates 正确统计核心字段填充率。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from src.harvest.engine import _extract_xhr_items
from src.harvest.loader import load_all_recipes
from src.harvest.normalize import normalize_items
from src.harvest.recipe import XhrExtract
from src.tools_harvest import _calc_field_rates, tool_harvest_recipes

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(site: str, filename: str) -> Any:
    path = FIXTURES_DIR / site / filename
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_recipes_loaded_and_status() -> None:
    recipes, diags = load_all_recipes()
    errors = {k: v for k, v in diags.items() if v.get("error") is not None}
    assert not errors, f"配方加载存在诊断错误: {errors}"
    expected_sites = {"zhihu", "xiaohongshu", "x", "weibo"}
    assert expected_sites.issubset(set(recipes.keys()))

    for site_id in expected_sites:
        recipe = recipes[site_id]
        assert recipe.status == "beta"
        assert recipe.site.id == site_id
        assert recipe.site.base_url.startswith("https://")
        assert recipe.limits.min_interval_s >= 4.0
        assert recipe.limits.max_per_hour > 0
        assert recipe.limits.max_per_day > 0
        assert len(recipe.block_signals.status) > 0
        assert len(recipe.block_signals.url_contains) > 0
        assert len(recipe.block_signals.text_contains) > 0

    assert recipes["xiaohongshu"].limits.cooldown_on_block_h == 12.0
    assert recipes["zhihu"].limits.cooldown_on_block_h == 6.0


def test_zhihu_xhr_extraction() -> None:
    recipes, _ = load_all_recipes()
    recipe = recipes["zhihu"]

    # 1. hot
    hot_json = _load_fixture("zhihu", "hot.json")
    hot_act = recipe.actions["hot"]
    assert isinstance(hot_act.extract, XhrExtract)
    raw_hot = _extract_xhr_items([hot_json], hot_act.extract)
    assert len(raw_hot) == 2
    norm_hot = normalize_items(raw_hot, "zhihu", recipe.site.base_url)
    assert len(norm_hot) == 2
    assert norm_hot[0]["id"] == "89201928"
    assert "大模型" in norm_hot[0]["title"]
    assert norm_hot[0]["author"] == "极客观察员"
    assert norm_hot[0]["metrics"].get("hot") == "2450 万热度"

    # 2. search
    search_json = _load_fixture("zhihu", "search.json")
    search_act = recipe.actions["search"]
    assert isinstance(search_act.extract, XhrExtract)
    raw_search = _extract_xhr_items([search_json], search_act.extract)
    assert len(raw_search) == 1
    norm_search = normalize_items(raw_search, "zhihu", recipe.site.base_url)
    assert len(norm_search) == 1
    assert norm_search[0]["id"] == "7829102"
    assert "AI Agent" in norm_search[0]["title"]
    assert norm_search[0]["author"] == "架构演进实验室"
    assert norm_search[0]["metrics"].get("likes") == 1380


def test_xiaohongshu_xhr_extraction() -> None:
    recipes, _ = load_all_recipes()
    recipe = recipes["xiaohongshu"]

    search_json = _load_fixture("xiaohongshu", "search.json")
    search_act = recipe.actions["search"]
    assert isinstance(search_act.extract, XhrExtract)
    raw_search = _extract_xhr_items([search_json], search_act.extract)
    assert len(raw_search) == 1
    norm_search = normalize_items(raw_search, "xiaohongshu", recipe.site.base_url)
    assert len(norm_search) == 1
    assert norm_search[0]["id"] == "6612345678abcdef12345678"
    assert "本地大模型" in norm_search[0]["title"]
    assert norm_search[0]["author"] == "科技小达人"
    assert norm_search[0]["metrics"].get("likes") == "5.2万"


def test_x_xhr_extraction() -> None:
    recipes, _ = load_all_recipes()
    recipe = recipes["x"]

    # 1. search
    search_json = _load_fixture("x", "search.json")
    search_act = recipe.actions["search"]
    assert isinstance(search_act.extract, XhrExtract)
    raw_search = _extract_xhr_items([search_json], search_act.extract)
    assert len(raw_search) == 1
    norm_search = normalize_items(raw_search, "x", recipe.site.base_url)
    assert len(norm_search) == 1
    assert norm_search[0]["id"] == "tweet-189000111222333444"
    assert "Autonomous Agents" in norm_search[0]["title"]
    assert norm_search[0]["author"] == "ai_researcher"
    assert norm_search[0]["metrics"].get("likes") == 890
    assert norm_search[0]["metrics"].get("retweets") == 210

    # 2. user_timeline
    timeline_json = _load_fixture("x", "user_timeline.json")
    timeline_act = recipe.actions["user_timeline"]
    assert isinstance(timeline_act.extract, XhrExtract)
    raw_timeline = _extract_xhr_items([timeline_json], timeline_act.extract)
    assert len(raw_timeline) == 1
    norm_timeline = normalize_items(raw_timeline, "x", recipe.site.base_url)
    assert len(norm_timeline) == 1
    assert norm_timeline[0]["id"] == "tweet-189000555666777888"
    assert "Announcing" in norm_timeline[0]["title"]
    assert norm_timeline[0]["author"] == "OpenAI"
    assert norm_timeline[0]["metrics"].get("likes") == 4500


def test_weibo_xhr_extraction() -> None:
    recipes, _ = load_all_recipes()
    recipe = recipes["weibo"]

    # 1. hot
    hot_json = _load_fixture("weibo", "hot.json")
    hot_act = recipe.actions["hot"]
    assert isinstance(hot_act.extract, XhrExtract)
    raw_hot = _extract_xhr_items([hot_json], hot_act.extract)
    assert len(raw_hot) == 2
    norm_hot = normalize_items(raw_hot, "weibo", recipe.site.base_url)
    assert len(norm_hot) == 2
    assert "#自托管 AI Agent 落地实践#" in norm_hot[0]["id"]
    assert "探讨开箱即用" in norm_hot[0]["title"]
    assert norm_hot[0]["metrics"].get("hot") == 1892000
    assert norm_hot[0]["metrics"].get("num") == 1

    # 2. search
    search_json = _load_fixture("weibo", "search.json")
    search_act = recipe.actions["search"]
    assert isinstance(search_act.extract, XhrExtract)
    raw_search = _extract_xhr_items([search_json], search_act.extract)
    assert len(raw_search) == 1
    norm_search = normalize_items(raw_search, "weibo", recipe.site.base_url)
    assert len(norm_search) == 1
    assert norm_search[0]["id"] == "5089123456789012"
    assert "自动化流水线" in norm_search[0]["title"]
    assert norm_search[0]["author"] == "极客数码说"
    assert norm_search[0]["metrics"].get("likes") == 340


def test_css_fallback_presence() -> None:
    recipes, _ = load_all_recipes()
    for site_id, recipe in recipes.items():
        for act_name, action in recipe.actions.items():
            assert action.extract_fallback is not None, (
                f"{site_id}.{act_name} 缺少 extract_fallback"
            )
            assert action.extract_fallback.method == "css"
            assert action.extract_fallback.container
            assert len(action.extract_fallback.fields) >= 3


def test_calc_field_rates() -> None:
    items = [
        {
            "id": "1",
            "url": "https://example.com/1",
            "title": "Title 1",
            "author": "Author 1",
            "published_at": "2026-10-14T10:00:00Z",
            "excerpt": "Excerpt 1",
            "metrics": {"likes": 10},
        },
        {
            "id": "2",
            "url": "https://example.com/2",
            "title": "Title 2",
            "author": None,
            "published_at": None,
            "excerpt": "Excerpt 2",
            "metrics": {},
        },
    ]
    rates = _calc_field_rates(items)
    assert rates["id"] == 1.0
    assert rates["title"] == 1.0
    assert rates["author"] == 0.5
    assert rates["published_at"] == 0.5
    assert rates["metrics"] == 0.5


@pytest.mark.asyncio
async def test_tool_harvest_recipes() -> None:
    res = await tool_harvest_recipes()
    assert res["ok"] is True
    assert res["total"] >= 4
    recipe_ids = {r["site"] for r in res["recipes"]}
    assert {"zhihu", "xiaohongshu", "x", "weibo"}.issubset(recipe_ids)
