"""browser_bridge 使用的文件系统位置。

为何不复用 cfg.py：cfg.py 在 import 时就会创建真实 ~/.config 目录，
而本模块的所有函数都显式接收 home / cfg，便于测试在临时目录里运行，不碰用户真实环境。
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path

from .bridge_const import HANDSHAKE_FILE, NATIVE_HOST_NAME


def default_cfg(home: Path | None = None) -> Path:
    """运行时配置根目录（规则同 cfg.cfg_root，但不创建目录）。"""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "polaris-plugins" / "browser"
    return (home or Path.home()) / ".config" / "polaris-plugins" / "browser"


def chrome_host_dir(home: Path | None = None) -> Path | None:
    """Chrome 的 NativeMessagingHosts 目录；Windows 使用注册表，返回 None。"""
    h = home or Path.home()
    system = platform.system()
    if system == "Darwin":
        return (
            h
            / "Library"
            / "Application Support"
            / "Google"
            / "Chrome"
            / "NativeMessagingHosts"
        )
    if system == "Linux":
        return h / ".config" / "google-chrome" / "NativeMessagingHosts"
    return None


@dataclass(frozen=True)
class BridgePaths:
    """一组互相关联的路径；字段全部可在测试中指向临时目录。"""

    cfg: Path
    home: Path
    # 为 None 表示该平台用注册表（Windows）
    chrome_hosts_dir: Path | None

    @property
    def token_file(self) -> Path:
        return self.cfg / "bridge_token"

    @property
    def ext_dir(self) -> Path:
        """稳定的扩展目录：用户在 Chrome 里「加载已解压」的就是它，插件升级后路径不变。"""
        return self.cfg / "extension"

    @property
    def host_dir(self) -> Path:
        return self.cfg / "native-host"

    @property
    def host_script(self) -> Path:
        return self.host_dir / "native_host.py"

    @property
    def host_wrapper(self) -> Path:
        name = "run_host.bat" if platform.system() == "Windows" else "run_host.sh"
        return self.host_dir / name

    @property
    def host_manifest(self) -> Path | None:
        if self.chrome_hosts_dir is None:
            return None
        return self.chrome_hosts_dir / f"{NATIVE_HOST_NAME}.json"

    @property
    def handshake_file(self) -> Path:
        return self.cfg / HANDSHAKE_FILE

    @property
    def ext_seen_file(self) -> Path:
        return self.cfg / "bridge_ext_seen"

    @property
    def ext_log(self) -> Path:
        return self.cfg / "bridge_ext.log"


def real_paths() -> BridgePaths:
    """真实用户环境下的路径。"""
    home = Path.home()
    return BridgePaths(
        cfg=default_cfg(home), home=home, chrome_hosts_dir=chrome_host_dir(home)
    )
