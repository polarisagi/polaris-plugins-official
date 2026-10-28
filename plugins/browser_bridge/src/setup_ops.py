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


def host_python() -> str:
    """宿主解释器取基础解释器而非插件 venv：宿主只用标准库，venv 随插件重装/重建而消失，
    写死 venv 路径会让自动配对在重装后静默失效。"""
    base = getattr(sys, "_base_executable", "") or ""
    return base if base and Path(base).is_file() else sys.executable


def _wrapper_python(wrapper: Path) -> str:
    """从包装脚本里取出解释器路径；解析不了返回空串。"""
    try:
        text = wrapper.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("exec "):
            try:
                return shlex.split(line)[1]
            except ValueError, IndexError:
                return ""
        if line.startswith('"'):  # Windows .bat
            return line.split('"')[1]
    return ""


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
    py = python or host_python()
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
    py = _wrapper_python(wrapper) if wrapper_ok else ""
    python_ok = bool(py) and Path(py).is_file()
    try:
        script_in_sync = _file_sha256(paths.host_script) == _file_sha256(
            Path(native_host.__file__).resolve()
        )
    except OSError:
        script_in_sync = False
    return {
        "supported": True,
        "registered": bool(
            data.get("name") == NATIVE_HOST_NAME
            and origin_ok
            and wrapper_ok
            and python_ok
            and script_in_sync
        ),
        "python_ok": python_ok,
        "script_in_sync": script_in_sync,
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
            "ts": float(ts),
            "age_s": round(age, 1),
            "last_error": data.get("last_error"),
        }
    )
    return info


def presence_info(paths: BridgePaths, now: float | None = None) -> dict[str, Any]:
    """读取扩展报到记录：不依赖中继即可判断扩展是否已在 Chrome 中加载、版本与令牌是否一致。"""
    t = time.time() if now is None else now
    info: dict[str, Any] = {
        "seen": False,
        "ext_version": None,
        "token_match": None,
        "last_seen_at": None,
        "age_s": None,
    }
    try:
        data = json.loads(paths.presence_file.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return info
    ts = data.get("ts") if isinstance(data, dict) else None
    if not isinstance(ts, int | float):
        return info
    tm = data.get("token_match")
    info.update(
        {
            "seen": True,
            "ts": float(ts),
            "ext_version": data.get("ext_version")
            if isinstance(data.get("ext_version"), str)
            else None,
            "token_match": tm if isinstance(tm, bool) else None,
            "last_seen_at": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(float(ts))
            ),
            "age_s": round(max(0.0, t - float(ts)), 1),
        }
    )
    return info


def _running_extension(st: dict[str, Any]) -> tuple[str | None, str | None]:
    """Chrome 中正在运行的扩展版本与最近一次证据时间：报到与中继握手取较新者。"""
    pres, conn = st["presence"], st["connection"]
    cands: list[tuple[float, str | None, str | None]] = []
    if pres.get("seen"):
        cands.append((pres["ts"], pres.get("ext_version"), pres.get("last_seen_at")))
    if conn.get("last_handshake_at") and conn.get("ts") is not None:
        cands.append(
            (conn["ts"], conn.get("ext_version"), conn.get("last_handshake_at"))
        )
    if not cands:
        return None, None
    _, ver, at = max(cands, key=lambda c: c[0])
    return ver, at


# 新协议（双向 HMAC 握手）扩展的最低版本：低于它的扩展无法与当前中继配对
MIN_PAIRED_EXT_VERSION = "1.2.0"


def _version_tuple(v: object) -> tuple[int, ...]:
    """把 "1.2.0" 解析为 (1, 2, 0)；无法解析返回空元组（视为最低）。"""
    if not isinstance(v, str):
        return ()
    parts: list[int] = []
    for seg in v.strip().split("."):
        if not seg.isdigit():
            break
        parts.append(int(seg))
    return tuple(parts)


def _readiness(st: dict[str, Any]) -> tuple[bool, str]:
    """供 Polaris 插件页 statusTool 使用的 ready / message。

    ready 表示「一次性设置已完成」，而不是「此刻已连接」：中继只在使用浏览器的插件
    进程运行时存在，若以实时连接为准，插件页会在空闲时误报「需要设置」。
    判定：本机准备就绪（令牌、扩展目录、自动配对宿主）；扩展已在 Chrome 中运行新协议版本
    （证据取扩展报到与中继握手中较新的一条）且与稳定目录版本一致；扩展持有的令牌与本机一致。
    """
    ext = st["extension"]
    if not st["ok"]:
        return False, "尚未准备扩展：点击「设置」完成一键准备。"
    ver, at = _running_extension(st)
    running = _version_tuple(ver)
    if ver is None or running < _version_tuple(MIN_PAIRED_EXT_VERSION):
        return False, (
            "扩展尚未在 Chrome 中加载或仍是旧版本：打开 chrome://extensions，"
            f"加载已解压的扩展程序并选择 {ext.get('dir')}。"
        )
    if ext.get("version") and running < _version_tuple(ext.get("version")):
        return False, (
            f"扩展已更新到 {ext.get('version')}，Chrome 中仍运行 {ver}："
            "请在 chrome://extensions 点击该扩展的「重新加载」。"
        )
    if st["presence"].get("token_match") is False:
        return False, (
            "扩展持有的令牌与本机不一致：扩展会自动重新配对（最长约 5 分钟）；"
            "也可在扩展选项页点「重新自动配对」。"
        )
    if st["connection"].get("connected"):
        return True, f"已连接（扩展 {ver}）。"
    return True, (
        f"设置已完成（扩展 {ver}，最近在线 {at}）。浏览器连接会在 browser-use、social "
        "等插件使用浏览器时自动建立。"
    )


def _checks(st: dict[str, Any]) -> list[dict[str, Any]]:
    """逐项检查清单（Polaris 插件详情页「设置」页按此渲染）。ok=None 表示仅供参考、不影响就绪。"""
    tok, host, ext, pres, conn = (
        st["token"],
        st["host"],
        st["extension"],
        st["presence"],
        st["connection"],
    )
    ver, at = _running_extension(st)
    host_detail = (
        "已注册"
        if host.get("registered")
        else (
            "不支持（请手动粘贴令牌）"
            if not host.get("supported")
            else "解释器已失效，请点「设置」重新注册"
            if host.get("wrapper_ok") and not host.get("python_ok")
            else "宿主脚本需要更新，请点「设置」"
            if host.get("python_ok") and not host.get("script_in_sync")
            else "未注册，请点「设置」"
        )
    )
    return [
        {
            "key": "token",
            "label": "配对令牌",
            "ok": bool(tok.get("exists") and tok.get("permissions_ok")),
            "detail": "已生成（0600）" if tok.get("exists") else "未生成",
        },
        {
            "key": "extension_dir",
            "label": "扩展目录",
            "ok": bool(ext.get("ready") and ext.get("in_sync")),
            "detail": f"{ext.get('dir')}（v{ext.get('version')}）"
            if ext.get("ready")
            else "未准备",
        },
        {
            "key": "host",
            "label": "自动配对宿主",
            "ok": bool(host.get("registered") or not host.get("supported")),
            "detail": host_detail,
        },
        {
            "key": "loaded",
            "label": "Chrome 中的扩展",
            "ok": ver is not None
            and _version_tuple(ver)
            >= _version_tuple(ext.get("version") or MIN_PAIRED_EXT_VERSION),
            "detail": f"v{ver}，最近在线 {at}" if ver else "尚未加载",
        },
        {
            "key": "token_match",
            "label": "扩展令牌一致",
            "ok": pres.get("token_match"),  # None = 扩展尚未报到，仅供参考
            "detail": {
                True: "一致",
                False: "不一致，正在重新配对",
                None: "未知（扩展尚未报到）",
            }[pres.get("token_match")],
        },
        {
            "key": "connection",
            "label": "浏览器连接",
            "ok": None,
            "detail": f"已连接（{conn.get('age_s')} 秒前心跳）"
            if conn.get("connected")
            else "空闲：browser-use、social 等插件使用浏览器时自动连接",
        },
    ]


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
        "presence": presence_info(paths, now),
    }
    st["next_steps"] = _next_steps(st)
    st["ok"] = bool(
        st["token"]["exists"]
        and st["extension"]["ready"]
        and (st["host"]["registered"] or not st["host"]["supported"])
    )
    st["ready"], st["message"] = _readiness(st)
    st["checks"] = _checks(st)
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


def refresh_installed(paths: BridgePaths) -> dict[str, Any] | None:
    """插件进程启动时调用：曾经设置过（令牌已存在）才静默刷新扩展目录与宿主。

    插件重装或升级后扩展源码、宿主脚本、解释器路径都可能变化；此前要用户再点一次「设置」，
    不点就停在「宿主失效 / 版本不一致」。从未设置过则什么都不做，首次设置仍由用户触发。
    """
    if not paths.token_file.exists():
        return None
    return {"extension": sync_extension(paths), "host": register_host(paths)}


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
