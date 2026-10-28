"""Polaris Browser Bridge — Chrome Native Messaging 宿主（仅标准库，可独立运行）。

为何存在：
扩展无法读取本机文件，用户也不该手动复制令牌。Chrome 允许扩展通过
Native Messaging 启动一个本地进程并与之交换 JSON；本宿主据此把配对令牌交给扩展。
安全边界：宿主清单的 allowed_origins 只含 Polaris Browser Bridge 的扩展 ID，
其他扩展 / 网页无法启动本宿主。

协议（Chrome Native Messaging）：每条消息 = 4 字节小端长度 + UTF-8 JSON。
支持的请求：
- {"type": "get_pairing"} → {"ok": true, "token", "relay_ports", "version"}
- {"type": "hello", "ext_version", "token_fp"} → {"ok": true, "token_fp", "version"}：扩展报到。
  宿主记录扩展在场信息（bridge_ext_presence.json）供状态判定——此前只有中继握手能证明扩展已加载，
  只装 browser_bridge 时没有中继，状态永远是「未握手」。token_fp 为令牌 SHA-256 前 16 位，
  扩展据此发现本机令牌已变化并自动重新配对；令牌明文不出现在报到往返里。

本文件会被复制到 ~/.config/polaris-plugins/browser/native-host/ 由包装脚本调用，
因此不得依赖插件内其他模块；令牌创建规则须与 bridge_relay.get_or_create_token 保持一致。
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import struct
import sys
import time
from pathlib import Path
from typing import Any, BinaryIO

HOST_VERSION = "1.1.0"
PRESENCE_FILE = "bridge_ext_presence.json"
EXT_SEEN_FILE = "bridge_ext_seen"
RELAY_PORTS = list(range(18790, 18800))
# Chrome 规定宿主发往浏览器的单条消息不得超过 1 MiB，浏览器发给宿主的不得超过 4 GiB；本宿主只收小消息
MAX_INCOMING = 64 * 1024


def cfg_dir() -> Path:
    """运行时配置目录，规则与插件 cfg.cfg_root 一致（不在此创建目录）。"""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "polaris-plugins" / "browser"
    return Path.home() / ".config" / "polaris-plugins" / "browser"


def _read_nonempty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def get_or_create_token(cfg: Path | None = None) -> str:
    """读取配对令牌；不存在则按 0600 原子创建 32 字节 hex（与 bridge_relay 同规则）。"""
    token_file = (cfg or cfg_dir()) / "bridge_token"
    existing = _read_nonempty(token_file)
    if existing:
        return existing

    token = secrets.token_hex(32)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        # O_EXCL 保证并发时只有一方创建成功，且创建即为 0600，无「先写后 chmod」的可读窗口
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        for _ in range(20):
            t = _read_nonempty(token_file)
            if t:
                return t
            time.sleep(0.05)
        return token
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)
    return token


def write_token_atomic(token: str, cfg: Path | None = None) -> None:
    """原子覆盖写入令牌（临时文件 0600 + os.replace），供令牌轮换使用。"""
    token_file = (cfg or cfg_dir()) / "bridge_token"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = token_file.with_name(f"bridge_token.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(token)
        os.replace(tmp, token_file)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def token_fingerprint(token: str) -> str:
    """令牌指纹：SHA-256 前 16 位 hex。用于比对一致性，不可反推令牌。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def record_presence(cfg: Path, ext_version: str, token_match: bool | None) -> None:
    """原子写入扩展在场记录；首次报到同时创建 bridge_ext_seen（与中继同语义）。"""
    data = {
        "ts": time.time(),
        "ext_version": ext_version[:32],
        "token_match": token_match,
        "host_version": HOST_VERSION,
    }
    cfg.mkdir(parents=True, exist_ok=True)
    target = cfg / PRESENCE_FILE
    tmp = target.with_name(f".{PRESENCE_FILE}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target)
    (cfg / EXT_SEEN_FILE).touch(exist_ok=True)


def encode_message(obj: Any) -> bytes:
    """编码一条 Native Messaging 消息：4 字节小端长度 + UTF-8 JSON。"""
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return struct.pack("<I", len(body)) + body


def read_message(stream: BinaryIO) -> Any | None:
    """读取一条消息；流已结束返回 None；长度超限或 JSON 非法抛 ValueError。"""
    header = stream.read(4)
    if len(header) < 4:
        return None
    (length,) = struct.unpack("<I", header)
    if length > MAX_INCOMING:
        raise ValueError(f"消息过长: {length}")
    body = stream.read(length)
    if len(body) < length:
        raise ValueError("消息被截断")
    return json.loads(body.decode("utf-8"))


def handle_request(msg: Any, cfg: Path | None = None) -> dict[str, Any]:
    """处理单条请求并返回应答。"""
    if not isinstance(msg, dict):
        return {"ok": False, "error": "bad_request"}
    if msg.get("type") == "get_pairing":
        try:
            token = get_or_create_token(cfg)
        except OSError as e:
            return {"ok": False, "error": f"token_unavailable: {e.__class__.__name__}"}
        return {
            "ok": True,
            "token": token,
            "relay_ports": RELAY_PORTS,
            "version": HOST_VERSION,
        }
    if msg.get("type") == "hello":
        c = cfg or cfg_dir()
        try:
            fp = token_fingerprint(get_or_create_token(c))
        except OSError as e:
            return {"ok": False, "error": f"token_unavailable: {e.__class__.__name__}"}
        ext_fp = msg.get("token_fp")
        match = ext_fp == fp if isinstance(ext_fp, str) and ext_fp else None
        try:
            record_presence(c, str(msg.get("ext_version") or ""), match)
        except OSError as e:
            return {
                "ok": False,
                "error": f"presence_unwritable: {e.__class__.__name__}",
            }
        return {"ok": True, "token_fp": fp, "version": HOST_VERSION}
    return {"ok": False, "error": "unknown_type"}


def serve(stdin: BinaryIO, stdout: BinaryIO, cfg: Path | None = None) -> None:
    """循环应答直到浏览器关闭管道。"""
    while True:
        try:
            msg = read_message(stdin)
        except ValueError:  # JSON / Unicode 解码错误均为其子类
            stdout.write(encode_message({"ok": False, "error": "bad_request"}))
            stdout.flush()
            return
        if msg is None:
            return
        stdout.write(encode_message(handle_request(msg, cfg)))
        stdout.flush()


def main() -> None:
    """宿主入口：Chrome 通过 stdin/stdout 二进制管道通信。"""
    serve(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    main()
