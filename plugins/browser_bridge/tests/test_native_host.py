"""Native Messaging 宿主单测：编解码、令牌原子创建与权限、端到端子进程应答。"""

from __future__ import annotations

import io
import json
import os
import stat
import struct
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from src import native_host


def test_encode_decode_roundtrip_utf8():
    """4 字节小端长度 + UTF-8 JSON，中文不被转义破坏。"""
    obj = {"type": "get_pairing", "note": "你好"}
    data = native_host.encode_message(obj)
    (length,) = struct.unpack("<I", data[:4])
    assert length == len(data) - 4
    assert data[4:].decode("utf-8") == '{"type":"get_pairing","note":"你好"}'
    assert native_host.read_message(io.BytesIO(data)) == obj


def test_read_message_eof_and_errors():
    assert native_host.read_message(io.BytesIO(b"")) is None
    with pytest.raises(ValueError, match="截断"):
        native_host.read_message(io.BytesIO(struct.pack("<I", 10) + b"{}"))
    with pytest.raises(ValueError, match="过长"):
        native_host.read_message(io.BytesIO(struct.pack("<I", 10_000_000)))
    with pytest.raises(ValueError):
        native_host.read_message(io.BytesIO(struct.pack("<I", 3) + b"{x}"))


def test_get_or_create_token_atomic_and_0600(tmp_path: Path):
    token = native_host.get_or_create_token(tmp_path)
    assert len(token) == 64 and int(token, 16) >= 0
    f = tmp_path / "bridge_token"
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    # 再次读取返回同一个令牌，不重新生成
    assert native_host.get_or_create_token(tmp_path) == token


def test_get_or_create_token_concurrent_single_winner(tmp_path: Path):
    """并发创建时只有一个令牌胜出，所有调用方拿到同一个值。"""
    results: list[str] = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        results.append(native_host.get_or_create_token(tmp_path))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(results)) == 1
    assert (tmp_path / "bridge_token").read_text() == results[0]


def test_write_token_atomic_replaces_with_0600(tmp_path: Path):
    old = native_host.get_or_create_token(tmp_path)
    native_host.write_token_atomic("f" * 64, tmp_path)
    assert native_host.get_or_create_token(tmp_path) == "f" * 64 != old
    assert stat.S_IMODE((tmp_path / "bridge_token").stat().st_mode) == 0o600
    assert not list(tmp_path.glob("*.tmp")), "不应遗留临时文件"


def test_handle_request_get_pairing(tmp_path: Path):
    resp = native_host.handle_request({"type": "get_pairing"}, tmp_path)
    assert resp["ok"] is True
    assert resp["token"] == (tmp_path / "bridge_token").read_text()
    assert resp["relay_ports"] == list(range(18790, 18800))
    assert resp["version"] == native_host.HOST_VERSION


def test_handle_request_rejects_unknown(tmp_path: Path):
    assert native_host.handle_request({"type": "nope"}, tmp_path)["ok"] is False
    assert native_host.handle_request("x", tmp_path)["ok"] is False
    assert not (tmp_path / "bridge_token").exists(), "非法请求不应创建令牌"


def test_serve_handles_multiple_messages(tmp_path: Path):
    stdin = io.BytesIO(
        native_host.encode_message({"type": "get_pairing"})
        + native_host.encode_message({"type": "bad"})
    )
    stdout = io.BytesIO()
    native_host.serve(stdin, stdout, tmp_path)
    out = io.BytesIO(stdout.getvalue())
    first = native_host.read_message(out)
    second = native_host.read_message(out)
    assert first["ok"] is True and second["ok"] is False
    assert native_host.read_message(out) is None


@pytest.mark.skipif(sys.platform == "win32", reason="用 HOME 重定向配置目录，仅 POSIX")
def test_host_subprocess_end_to_end(tmp_path: Path):
    """像 Chrome 一样拉起宿主进程：stdin 写一条请求，读回长度前缀应答。"""
    env = {**os.environ, "HOME": str(tmp_path)}
    script = Path(native_host.__file__)
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=native_host.encode_message({"type": "get_pairing"}),
        capture_output=True,
        env=env,
        timeout=20,
        check=True,
    )
    resp = native_host.read_message(io.BytesIO(proc.stdout))
    assert resp["ok"] is True
    token_file = tmp_path / ".config" / "polaris-plugins" / "browser" / "bridge_token"
    assert token_file.read_text() == resp["token"]
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    json.dumps(resp)
