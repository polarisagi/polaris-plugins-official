"""browser_bridge 的设置与状态操作（纯函数 + 显式路径，便于在临时目录中测试）。

职责：令牌、扩展目录同步、Native Messaging 宿主注册、连接状态、打开 Chrome 扩展页。
所有运行时文件只写入 ~/.config/polaris-plugins/browser/ 与 Chrome 的 NativeMessagingHosts 目录，
绝不写插件 src 目录。令牌明文永远不出现在返回值里。
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import native_host
from .bridge_const import EXTENSION_ID, NATIVE_HOST_NAME
from .paths import BridgePaths

# 握手文件新鲜度：中继每 20 秒心跳刷新一次，超过此时长视为已断开
HANDSHAKE_FRESH_S = 75.0
# 扩展目录里禁止出现的文件：签名私钥等
_EXT_EXCLUDE_SUFFIXES = {".pem", ".key"}


def extension_source_dir() -> Path:
    """插件随附的扩展源码目录（唯一源码）。"""
    return Path(__file__).resolve().parent.parent / "extension"


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    """临时文件 + os.replace 原子写入，并在落盘前就设好权限。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_manifest_version(ext_dir: Path) -> str | None:
    """读取扩展 manifest.json 的 version；缺失或损坏返回 None。"""
    try:
        data = json.loads((ext_dir / "manifest.json").read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    v = data.get("version") if isinstance(data, dict) else None
    return v if isinstance(v, str) else None


# ── 令牌 ─────────────────────────────────────────────────────────────────────


def ensure_token(paths: BridgePaths) -> bool:
    """确保令牌存在；返回是否本次新建。"""
    existed = paths.token_file.exists()
    native_host.get_or_create_token(paths.cfg)
    return not existed


def rotate_token(paths: BridgePaths) -> None:
    """重新生成令牌（原子写、0600）。"""
    native_host.write_token_atomic(secrets.token_hex(32), paths.cfg)


def token_info(paths: BridgePaths) -> dict[str, Any]:
    """令牌是否存在与权限是否安全（不含明文）。"""
    f = paths.token_file
    try:
        st = f.stat()
    except OSError:
        return {"exists": False, "path": str(f), "permissions_ok": False}
    mode_ok = platform.system() == "Windows" or (st.st_mode & 0o077) == 0
    return {"exists": st.st_size > 0, "path": str(f), "permissions_ok": mode_ok}


# ── 扩展目录同步 ─────────────────────────────────────────────────────────────


def _extension_files(src: Path) -> list[Path]:
    return sorted(
        p
        for p in src.iterdir()
        if p.is_file()
        and not p.name.startswith(".")
        and p.suffix.lower() not in _EXT_EXCLUDE_SUFFIXES
    )


def sync_extension(paths: BridgePaths, source: Path | None = None) -> dict[str, Any]:
    """把扩展源码同步到稳定目录；只复制变化的文件，并清理已从源码删除的旧文件。"""
    src = source or extension_source_dir()
    dest = paths.ext_dir
    dest.mkdir(parents=True, exist_ok=True)
    changed: list[str] = []
    wanted = set()
    for f in _extension_files(src):
        wanted.add(f.name)
        target = dest / f.name
        if target.is_file() and _file_sha256(target) == _file_sha256(f):
            continue
        _atomic_write(target, f.read_bytes(), 0o644)
        changed.append(f.name)
    removed: list[str] = []
    for old in dest.iterdir():
        if old.is_file() and old.name not in wanted:
            old.unlink()
            removed.append(old.name)
    return {
        "dir": str(dest),
        "version": read_manifest_version(dest),
        "changed": changed,
        "removed": removed,
    }


def extension_info(paths: BridgePaths, source: Path | None = None) -> dict[str, Any]:
    """稳定扩展目录是否就绪、版本、是否与插件内源码一致。"""
    src = source or extension_source_dir()
    dest = paths.ext_dir
    ready = (dest / "manifest.json").is_file()
    in_sync = ready
    if ready:
        try:
            for f in _extension_files(src):
                t = dest / f.name
                if not t.is_file() or _file_sha256(t) != _file_sha256(f):
                    in_sync = False
                    break
        except OSError:
            in_sync = False
    return {
        "dir": str(dest),
        "ready": ready,
        "version": read_manifest_version(dest),
        "source_version": read_manifest_version(src),
        "in_sync": in_sync,
        "extension_id": EXTENSION_ID,
    }


# ── Native Messaging 宿主 ────────────────────────────────────────────────────


def _wrapper_text(python: str, script: Path) -> str:
    """包装脚本：Chrome 启动宿主时 PATH 极少，必须写死解释器绝对路径。"""
    if platform.system() == "Windows":
        return f'@echo off\r\n"{python}" "{script}" %*\r\n'
    return f'#!/bin/sh\nexec {shlex.quote(python)} {shlex.quote(str(script))} "$@"\n'


def host_manifest_dict(paths: BridgePaths) -> dict[str, Any]:
    """宿主清单内容；allowed_origins 只含 Polaris Browser Bridge 扩展 ID。"""
    return {
        "name": NATIVE_HOST_NAME,
        "description": "Polaris Browser Bridge 自动配对宿主",
        "path": str(paths.host_wrapper),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"],
    }


def register_host(paths: BridgePaths, python: str | None = None) -> dict[str, Any]:
    """写宿主脚本、包装脚本，并向 Chrome 注册宿主清单。"""
    py = python or sys.executable
    src = Path(native_host.__file__).resolve()
    _atomic_write(paths.host_script, src.read_bytes(), 0o600)
    _atomic_write(
        paths.host_wrapper, _wrapper_text(py, paths.host_script).encode(), 0o700
    )
    manifest_bytes = json.dumps(
        host_manifest_dict(paths), ensure_ascii=False, indent=2
    ).encode("utf-8")
    manifest = paths.host_manifest
    if manifest is not None:
        _atomic_write(manifest, manifest_bytes + b"\n", 0o644)
        return {"supported": True, "manifest": str(manifest), "python": py}
    return _register_windows(paths, manifest_bytes, py)


def _register_windows(
    paths: BridgePaths, manifest_bytes: bytes, py: str
) -> dict[str, Any]:
    """Windows：清单放在配置目录，并在 HKCU 注册表指向它。未在真机验证。"""
    if sys.platform != "win32":
        return {
            "supported": False,
            "reason": "当前系统没有 Chrome Native Messaging 注册位置，请回退到手动粘贴令牌",
        }
    import winreg  # 仅 Windows 存在

    manifest = paths.host_dir / f"{NATIVE_HOST_NAME}.json"
    _atomic_write(manifest, manifest_bytes + b"\n", 0o644)
    key_path = rf"Software\Google\Chrome\NativeMessagingHosts\{NATIVE_HOST_NAME}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(manifest))
    return {"supported": True, "manifest": str(manifest), "python": py}


def host_info(paths: BridgePaths) -> dict[str, Any]:
    """检查宿主注册是否完整可用。"""
    manifest = paths.host_manifest
    if manifest is None and sys.platform != "win32":
        return {"supported": False, "registered": False}
    if manifest is None:
        manifest = paths.host_dir / f"{NATIVE_HOST_NAME}.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {"supported": True, "registered": False, "manifest": str(manifest)}
    origin_ok = data.get("allowed_origins") == [f"chrome-extension://{EXTENSION_ID}/"]
    wrapper = Path(str(data.get("path", "")))
    wrapper_ok = wrapper.is_file() and (
        platform.system() == "Windows" or os.access(wrapper, os.X_OK)
    )
    return {
        "supported": True,
        "registered": bool(
            data.get("name") == NATIVE_HOST_NAME
            and origin_ok
            and wrapper_ok
            and paths.host_script.is_file()
        ),
        "manifest": str(manifest),
        "allowed_origins_ok": origin_ok,
        "wrapper_ok": wrapper_ok,
    }


# ── 连接状态 ─────────────────────────────────────────────────────────────────


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        return True  # Windows 的 os.kill 会真的终止进程，不能探测；仅靠时间戳判断
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def connection_info(paths: BridgePaths, now: float | None = None) -> dict[str, Any]:
    """读取中继写入的握手文件，判断扩展当前是否已连接。"""
    t = time.time() if now is None else now
    info: dict[str, Any] = {
        "connected": False,
        "ever_paired": paths.ext_seen_file.exists(),
        "last_handshake_at": None,
        "ext_version": None,
        "age_s": None,
    }
    try:
        data = json.loads(paths.handshake_file.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return info
    if not isinstance(data, dict):
        return info
    ts = data.get("ts")
    if not isinstance(ts, int | float):
        return info
    age = max(0.0, t - float(ts))
    pid = data.get("pid")
    alive = _pid_alive(pid) if isinstance(pid, int) else True
    info.update(
        {
            "connected": bool(data.get("connected"))
            and age < HANDSHAKE_FRESH_S
            and alive,
            "last_handshake_at": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(float(ts))
            ),
            "ext_version": data.get("ext_version"),
            "age_s": round(age, 1),
            "last_error": data.get("last_error"),
        }
    )
    return info


def _next_steps(st: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    if not st["extension"]["ready"] or not st["extension"]["in_sync"]:
        steps.append("调用 bridge_setup 准备扩展目录并注册自动配对宿主")
    if st["host"]["supported"] and not st["host"]["registered"]:
        steps.append("自动配对宿主尚未注册：调用 bridge_setup")
    if not st["connection"]["connected"]:
        if not st["connection"]["ever_paired"]:
            steps.append(
                "在 Chrome 打开 chrome://extensions，开启开发者模式，点「加载已解压的扩展程序」选择扩展目录"
            )
        steps.append(
            "等待状态变绿（扩展每 30 秒探测一次本地中继；需要有插件进程正在使用浏览器）"
        )
    return steps


def build_status(paths: BridgePaths, now: float | None = None) -> dict[str, Any]:
    """汇总状态（不含令牌明文）。"""
    st: dict[str, Any] = {
        "token": token_info(paths),
        "host": host_info(paths),
        "extension": extension_info(paths),
        "connection": connection_info(paths, now),
    }
    st["next_steps"] = _next_steps(st)
    st["ok"] = bool(
        st["token"]["exists"]
        and st["extension"]["ready"]
        and (st["host"]["registered"] or not st["host"]["supported"])
    )
    return st


# ── 一键设置 / 打开 Chrome ───────────────────────────────────────────────────


def run_setup(paths: BridgePaths, python: str | None = None) -> dict[str, Any]:
    """一键准备：令牌 → 同步扩展 → 注册宿主。"""
    created = ensure_token(paths)
    ext = sync_extension(paths)
    host = register_host(paths, python)
    status = build_status(paths)
    status["setup"] = {"token_created": created, "extension": ext, "host": host}
    return status


def open_chrome_extensions(paths: BridgePaths) -> dict[str, Any]:
    """macOS：打开 chrome://extensions 并在 Finder 中定位扩展 manifest。参数一律走 argv，不经 shell。"""
    manifest = paths.ext_dir / "manifest.json"
    if platform.system() != "Darwin":
        return {
            "opened": False,
            "message": (
                "当前系统不支持自动打开。请手动在 Chrome 地址栏输入 chrome://extensions，"
                f"开启开发者模式后「加载已解压的扩展程序」，选择目录：{paths.ext_dir}"
            ),
            "extension_dir": str(paths.ext_dir),
        }
    if not manifest.is_file():
        return {
            "opened": False,
            "message": "扩展目录尚未准备，请先调用 bridge_setup。",
            "extension_dir": str(paths.ext_dir),
        }
    errors: list[str] = []
    cmds = [
        ["open", "-a", "Google Chrome", "chrome://extensions"],
        ["open", "-R", str(manifest)],
    ]
    for cmd in cmds:
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            errors.append(f"{cmd[0]} 失败: {e.__class__.__name__}")
            continue
        if r.returncode != 0:
            errors.append(f"{' '.join(cmd[:2])} 退出码 {r.returncode}")
    return {
        "opened": not errors,
        "errors": errors,
        "extension_dir": str(paths.ext_dir),
        "message": "已打开 Chrome 扩展页，并在 Finder 中显示扩展目录。把该文件夹拖入扩展页，或点「加载已解压的扩展程序」选择它。",
    }
