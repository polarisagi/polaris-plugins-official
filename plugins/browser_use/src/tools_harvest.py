"""结构化采集工具集。

为何需要该模块：
1. 对齐管线数据源契约：Agent 或自动化引擎通过 harvest 接口直接获取标准化结构数据；
2. harvest_recipes 供 Agent 发现当前已安装、可用的站点采集能力与参数约束。
"""

from __future__ import annotations

import logging
from typing import Any

from patchright.async_api import Error as PwError

from .browser_hub import HubError
from .harvest.engine import run_harvest
from .harvest.loader import load_all_recipes

logger = logging.getLogger("polaris.tools_harvest")


async def tool_harvest(
    site: str,
    action: str,
    params: dict[str, Any] | None = None,
    max_items: int = 20,
) -> dict[str, Any]:
    """根据站点配方与动作执行无人值守的结构化采集，返回标准化数据列表。"""
    try:
        recipes, diag = load_all_recipes()
        recipe = recipes.get(site)
        if not recipe:
            err_info = diag.get(site, {}).get("error")
            if err_info:
                return {
                    "ok": False,
                    "error": {
                        "code": "recipe_error",
                        "message": f"站点 {site} 配方解析错误: {err_info}",
                    },
                }
            return {
                "ok": False,
                "error": {
                    "code": "invalid_args",
                    "message": f"未找到站点 {site} 的采集配方，请调用 harvest_recipes 查询可用站点",
                },
            }

        items = await run_harvest(
            recipe, action_name=action, params=params or {}, max_items=max_items
        )
        return {
            "ok": True,
            "site": site,
            "action": action,
            "items": items,
            "count": len(items),
        }
    except HubError as e:
        return {"ok": False, "error": e.to_dict()}
    except (PwError, OSError, ValueError, RuntimeError) as e:
        return {"ok": False, "error": {"code": "recipe_error", "message": str(e)}}


async def tool_harvest_recipes() -> dict[str, Any]:
    """列出当前已加载的所有站点配方、支持的动作、参数定义与风控状态。"""
    try:
        recipes, diag = load_all_recipes()
        site_list = []

        for site_id, recipe in recipes.items():
            actions_summary = {}
            for act_name, act_obj in recipe.actions.items():
                params_info = {}
                for p_name, p_spec in act_obj.params.items():
                    params_info[p_name] = {
                        "type": p_spec.type,
                        "description": p_spec.description,
                        "default": p_spec.default,
                        "required": p_spec.required,
                    }
                actions_summary[act_name] = {
                    "description": act_obj.description,
                    "params": params_info,
                    "method": act_obj.extract.method,
                }

            origin = diag.get(site_id, {}).get("origin", "builtin")
            site_list.append(
                {
                    "site": site_id,
                    "name": recipe.site.name,
                    "status": recipe.status,
                    "origin": origin,
                    "actions": actions_summary,
                }
            )

        # 追加解析失败的站点信息
        for site_id, d in diag.items():
            if d.get("status") == "error":
                site_list.append(
                    {
                        "site": site_id,
                        "name": d.get("name", site_id),
                        "status": "error",
                        "origin": d.get("origin", "unknown"),
                        "error": d.get("error"),
                        "actions": {},
                    }
                )

        return {"ok": True, "recipes": site_list, "total": len(site_list)}
    except (OSError, ValueError, RuntimeError) as e:
        return {"ok": False, "error": {"code": "recipe_error", "message": str(e)}}
