"""bridge_setup 等操作的单测：全部在临时 HOME / 配置目录下运行，不碰真实环境。"""

from __future__ import annotations

import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest
from src import setup_ops
from src.bridge_const import EXTENSION_ID, HANDSHAKE_FILE, NATIVE_HOST_NAME
from src.paths import BridgePaths


@pytest.fixture
def paths(tmp_path: Path) -> BridgePaths:
    return BridgePaths(
        cfg=tmp_path / "cfg",
        home=tmp_path,
        chrome_hosts_dir=tmp_path / "chrome" / "NativeMessagingHosts",
    )


@pytest.fixture
def fake_source(tmp_path: Path) -> Path:
    """模拟扩展源码目录，其中混入签名私钥与隐藏文件，同步时必须被排除。"""
    src = tmp_path / "ext_src"
    src.mkdir()
    (src / "manifest.json").write_text('{"version": "9.9.9"}', encoding="utf-8")
    (src / "sw.js").write_text("// sw", encoding="utf-8")
    (src / "key.pem").write_text("PRIVATE", encoding="utf-8")
    (src / ".DS_Store").write_text("x", encoding="utf-8")
    return src


def test_run_setup_produces_all_artifacts(paths: BridgePaths, monkeypatch):
    monkeypatch.setattr(
        setup_ops,
        "extension_source_dir",
        lambda: Path(setup_ops.__file__).parent.parent / "extension",
    )
    res = setup_ops.run_setup(paths, python="/opt/py/bin/python3")

    # 令牌
    assert paths.token_file.is_file()
    assert stat.S_IMODE(paths.token_file.stat().st_mode) == 0o600
    # 扩展目录
    assert (paths.ext_dir / "manifest.json").is_file()
    assert res["extension"]["ready"] and res["extension"]["in_sync"]
    assert not list(paths.ext_dir.glob("*.pem"))
    # 宿主清单
    manifest = json.loads(paths.host_manifest.read_text(encoding="utf-8"))
    assert manifest["name"] == NATIVE_HOST_NAME == "online.polarisagi.bridge"
    assert manifest["type"] == "stdio"
    assert manifest["allowed_origins"] == [f"chrome-extension://{EXTENSION_ID}/"]
    assert manifest["path"] == str(paths.host_wrapper)
    # 包装脚本：绝对路径解释器、可执行
    wrapper = paths.host_wrapper.read_text(encoding="utf-8")
    assert "/opt/py/bin/python3" in wrapper and str(paths.host_script) in wrapper
    assert os.access(paths.host_wrapper, os.X_OK)
    assert stat.S_IMODE(paths.host_wrapper.stat().st_mode) == 0o700
    assert paths.host_script.is_file()
    # 返回值不含令牌明文
    assert paths.token_file.read_text() not in json.dumps(res)
    assert res["host"]["registered"] is True


def test_run_setup_is_idempotent(paths: BridgePaths):
    first = setup_ops.run_setup(paths, python=sys.executable)
    token = paths.token_file.read_text()
    second = setup_ops.run_setup(paths, python=sys.executable)
    assert first["setup"]["token_created"] is True
    assert second["setup"]["token_created"] is False
    assert second["setup"]["extension"]["changed"] == []
    assert paths.token_file.read_text() == token


def test_sync_excludes_secrets_and_removes_stale(paths: BridgePaths, fake_source: Path):
    paths.ext_dir.mkdir(parents=True)
    (paths.ext_dir / "old.js").write_text("stale", encoding="utf-8")
    res = setup_ops.sync_extension(paths, fake_source)
    names = sorted(p.name for p in paths.ext_dir.iterdir())
    assert names == ["manifest.json", "sw.js"]
    assert res["removed"] == ["old.js"]
    assert res["version"] == "9.9.9"
    # 源码更新后只同步变化文件
    (fake_source / "sw.js").write_text("// sw v2", encoding="utf-8")
    res2 = setup_ops.sync_extension(paths, fake_source)
    assert res2["changed"] == ["sw.js"]
    info = setup_ops.extension_info(paths, fake_source)
    assert info["in_sync"] and info["version"] == "9.9.9"


def test_extension_info_detects_drift(paths: BridgePaths, fake_source: Path):
    setup_ops.sync_extension(paths, fake_source)
    (fake_source / "sw.js").write_text("changed", encoding="utf-8")
    assert setup_ops.extension_info(paths, fake_source)["in_sync"] is False


def test_rotate_token_changes_value_and_keeps_0600(paths: BridgePaths):
    setup_ops.ensure_token(paths)
    old = paths.token_file.read_text()
    setup_ops.rotate_token(paths)
    new = paths.token_file.read_text()
    assert new != old and len(new) == 64
    assert stat.S_IMODE(paths.token_file.stat().st_mode) == 0o600
    assert setup_ops.token_info(paths)["permissions_ok"] is True


def test_token_info_flags_loose_permissions(paths: BridgePaths):
    setup_ops.ensure_token(paths)
    os.chmod(paths.token_file, 0o644)
    assert setup_ops.token_info(paths)["permissions_ok"] is False


def _write_handshake(paths: BridgePaths, **kw):
    paths.cfg.mkdir(parents=True, exist_ok=True)
    data = {
        "ts": time.time(),
        "connected": True,
        "ext_version": "1.2.0",
        "pid": os.getpid(),
    }
    data.update(kw)
    (paths.cfg / HANDSHAKE_FILE).write_text(json.dumps(data), encoding="utf-8")


def test_connection_info_states(paths: BridgePaths):
    assert setup_ops.connection_info(paths)["connected"] is False
    _write_handshake(paths)
    info = setup_ops.connection_info(paths)
    assert info["connected"] is True and info["ext_version"] == "1.2.0"
    # 过期
    _write_handshake(paths, ts=time.time() - 600)
    assert setup_ops.connection_info(paths)["connected"] is False
    # 中继已标记断开
    _write_handshake(paths, connected=False)
    assert setup_ops.connection_info(paths)["connected"] is False
    # 损坏文件
    (paths.cfg / HANDSHAKE_FILE).write_text("{oops", encoding="utf-8")
    assert setup_ops.connection_info(paths)["connected"] is False


@pytest.mark.skipif(sys.platform == "win32", reason="pid 探测仅 POSIX")
def test_connection_info_dead_pid_not_connected(paths: BridgePaths):
    _write_handshake(paths, pid=2**22 + 12345)  # 极大概率不存在
    assert setup_ops.connection_info(paths)["connected"] is False


def test_build_status_never_contains_token(paths: BridgePaths):
    setup_ops.run_setup(paths, python=sys.executable)
    st = setup_ops.build_status(paths)
    assert paths.token_file.read_text() not in json.dumps(st)
    assert st["ok"] is True
    assert any("chrome://extensions" in s for s in st["next_steps"])


def test_open_chrome_uses_argv_lists(
    paths: BridgePaths, fake_source: Path, monkeypatch
):
    setup_ops.sync_extension(paths, fake_source)
    calls: list[list[str]] = []

    class R:
        returncode = 0

    def fake_run(cmd, **kw):
        assert isinstance(cmd, list) and kw.get("shell") is not True
        calls.append(cmd)
        return R()

    monkeypatch.setattr(setup_ops.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(setup_ops.subprocess, "run", fake_run)
    res = setup_ops.open_chrome_extensions(paths)
    assert res["opened"] is True
    assert calls[0] == ["open", "-a", "Google Chrome", "chrome://extensions"]
    assert calls[1] == ["open", "-R", str(paths.ext_dir / "manifest.json")]


def test_open_chrome_non_mac_gives_instructions(paths: BridgePaths, monkeypatch):
    monkeypatch.setattr(setup_ops.platform, "system", lambda: "Linux")
    res = setup_ops.open_chrome_extensions(paths)
    assert res["opened"] is False and "chrome://extensions" in res["message"]


def test_open_chrome_requires_setup_first(paths: BridgePaths, monkeypatch):
    monkeypatch.setattr(setup_ops.platform, "system", lambda: "Darwin")
    res = setup_ops.open_chrome_extensions(paths)
    assert res["opened"] is False and "bridge_setup" in res["message"]


def test_shipped_extension_matches_constants():
    """随插件的扩展源码：宿主名/权限/版本与常量一致，且目录里没有私钥。"""
    ext = setup_ops.extension_source_dir()
    manifest = json.loads((ext / "manifest.json").read_text(encoding="utf-8"))
    assert "nativeMessaging" in manifest["permissions"]
    assert manifest["version"] == "1.2.0"
    assert f'const NATIVE_HOST = "{NATIVE_HOST_NAME}";' in (ext / "sw.js").read_text(
        encoding="utf-8"
    )
    assert not list(ext.glob("*.pem"))
