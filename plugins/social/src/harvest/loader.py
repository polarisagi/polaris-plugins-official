"""站点配方文件（TOML）的加载与校验。

为何支持双目录加载：
1. 内置配方随插件发布（recipes/*.toml）；
2. 用户自定义或覆盖配方置于操作系统标准配置目录（CFG/recipes/*.toml）；
3. 遵循开发调试隔离约定：_ 开头的文件仅在 POLARIS_BROWSER_DEV=1 时加载。
"""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..utils.cfg import CFG, ENV_DEV
from .recipe import Recipe

logger = logging.getLogger("polaris.harvest.loader")


def get_builtin_recipes_dir() -> Path:
    """获取插件内置配方目录。"""
    # 位于 plugins/browser_use/recipes
    return Path(__file__).resolve().parent.parent.parent / "recipes"


def get_user_recipes_dir() -> Path:
    """获取用户自定义配方目录。"""
    return CFG / "recipes"


def load_all_recipes() -> tuple[dict[str, Recipe], dict[str, dict[str, Any]]]:
    """加载所有有效配方，并返回 (成功配方字典, 失败或带有诊断信息的站点字典)。

    覆盖规则：用户目录中具有相同 site.id 的配方覆盖内置配方。
    """
    dev_mode = os.environ.get(ENV_DEV, "0").strip() in ("1", "true", "yes")

    builtin_dir = get_builtin_recipes_dir()
    user_dir = get_user_recipes_dir()

    toml_files: dict[str, tuple[Path, str]] = {}  # site_id -> (path, origin)

    def scan_dir(d: Path, origin: str) -> None:
        if not d.exists():
            return
        for p in sorted(d.glob("*.toml")):
            if p.name.startswith("_") and not dev_mode:
                continue
            # 临时读取站点 ID
            try:
                data = tomllib.loads(p.read_text(encoding="utf-8"))
                site_id = data.get("site", {}).get("id") or p.stem.lstrip("_")
                toml_files[site_id] = (p, origin)
            except (tomllib.TOMLDecodeError, OSError, ValueError) as e:
                # 记录损坏的 TOML 文件
                logger.warning("解析配方文件 %s 语法错误: %s", p, e)
                toml_files[p.stem] = (p, origin)

    # 先扫描内置，后扫描用户目录实现覆盖
    scan_dir(builtin_dir, "builtin")
    scan_dir(user_dir, "user")

    valid_recipes: dict[str, Recipe] = {}
    diagnostics: dict[str, dict[str, Any]] = {}

    for site_id, (path, origin) in toml_files.items():
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
            recipe = Recipe.model_validate(raw)
            valid_recipes[recipe.site.id] = recipe
            diagnostics[recipe.site.id] = {
                "id": recipe.site.id,
                "name": recipe.site.name,
                "origin": origin,
                "path": str(path),
                "status": recipe.status,
                "error": None,
            }
        except ValidationError as ve:
            diagnostics[site_id] = {
                "id": site_id,
                "name": site_id,
                "origin": origin,
                "path": str(path),
                "status": "error",
                "error": ve.errors(),
            }
        except (tomllib.TOMLDecodeError, OSError, ValueError) as e:
            diagnostics[site_id] = {
                "id": site_id,
                "name": site_id,
                "origin": origin,
                "path": str(path),
                "status": "error",
                "error": str(e),
            }

    return valid_recipes, diagnostics
