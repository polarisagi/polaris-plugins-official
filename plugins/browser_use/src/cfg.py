"""配置根路径与环境变量约定。

为何独立为 cfg 模块：
跨模块（hub、ratelimit、harvest 等）以及跨插件（social_poster 等）
需要统一读取操作系统标准配置目录与通用环境变量，避免散落在各处产生路径分歧。
"""

from __future__ import annotations

import os
import platform
from pathlib import Path


def cfg_root() -> Path:
    """获取 Polaris 插件的统一运行时配置目录。

    遵循标准系统目录规范：
    - Windows: %APPDATA%/polaris-plugins/browser
    - macOS / Linux: ~/.config/polaris-plugins/browser
    """
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA")
        if base:
            root = Path(base) / "polaris-plugins" / "browser"
        else:
            root = Path.home() / ".config" / "polaris-plugins" / "browser"
    else:
        root = Path.home() / ".config" / "polaris-plugins" / "browser"

    root.mkdir(parents=True, exist_ok=True)
    return root


# 全局配置根路径单例
CFG: Path = cfg_root()

# 环境变量名称定义与默认值
ENV_BACKEND = "POLARIS_BROWSER_BACKEND"  # auto | extension | cdp | managed，默认 auto
ENV_DRIVER = "POLARIS_BROWSER_DRIVER"  # patchright | playwright，默认 patchright
ENV_PROFILE = "POLARIS_BROWSER_PROFILE"  # managed 用，默认 default
ENV_HEADLESS = "POLARIS_BROWSER_HEADLESS"  # managed 用，默认 0
ENV_IDLE_RELEASE_MIN = (
    "POLARIS_BROWSER_IDLE_RELEASE_MIN"  # cdp 默认 0；extension 默认 10
)
ENV_DEV = "POLARIS_BROWSER_DEV"  # 1 为开发者模式，默认 0
