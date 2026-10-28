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
    # 包装脚本里的解释器不存在：宿主必须判为失效，而不是「已注册」
    assert res["host"]["registered"] is False and res["host"]["python_ok"] is False


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
    # 不写死版本：只要求不低于新协议（双向 HMAC + 自动配对）所需的最低版本
    assert setup_ops._version_tuple(manifest["version"]) >= setup_ops._version_tuple(
        setup_ops.MIN_PAIRED_EXT_VERSION
    )
    assert f'const NATIVE_HOST = "{NATIVE_HOST_NAME}";' in (ext / "sw.js").read_text(
        encoding="utf-8"
    )
    assert not list(ext.glob("*.pem"))


def _write_pairing(paths: BridgePaths, ext_version: str, connected: bool) -> None:
    paths.handshake_file.parent.mkdir(parents=True, exist_ok=True)
    paths.handshake_file.write_text(
        json.dumps(
            {
                "ts": time.time(),
                "connected": connected,
                "ext_version": ext_version,
                "port": 18790,
                "pid": os.getpid(),
            }
        ),
        encoding="utf-8",
    )


def test_ready_requires_new_protocol_pairing(paths: BridgePaths) -> None:
    """ready 表示一次性设置完成：仅本机准备好、或只有旧版扩展留下的标记，都不算就绪。"""
    st = setup_ops.build_status(paths)
    assert st["ready"] is False and "设置" in st["message"]

    setup_ops.run_setup(paths, python=sys.executable)
    # 旧版扩展留下的 ext_seen 标记不能让 ready 变真
    paths.ext_seen_file.parent.mkdir(parents=True, exist_ok=True)
    paths.ext_seen_file.touch()
    st = setup_ops.build_status(paths)
    assert st["ok"] is True and st["ready"] is False
    assert "chrome://extensions" in st["message"]

    _write_pairing(paths, "1.1.0", connected=True)
    assert setup_ops.build_status(paths)["ready"] is False

    ext_ver = setup_ops.build_status(paths)["extension"]["version"]
    _write_pairing(paths, ext_ver, connected=False)
    st = setup_ops.build_status(paths)
    assert st["ready"] is True and "设置已完成" in st["message"]

    _write_pairing(paths, ext_ver, connected=True)
    st = setup_ops.build_status(paths)
    assert st["ready"] is True and "已连接" in st["message"]


def test_ready_false_when_chrome_runs_older_extension(paths: BridgePaths) -> None:
    """插件升级同步了新扩展、但 Chrome 仍运行旧版：提示重新加载。"""
    setup_ops.run_setup(paths, python=sys.executable)
    ext_dir = Path(setup_ops.build_status(paths)["extension"]["dir"])
    manifest = json.loads((ext_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["version"] = "9.0.0"  # 模拟插件升级后同步到稳定目录的新版扩展
    (ext_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    _write_pairing(paths, "1.2.0", connected=True)
    st = setup_ops.build_status(paths)
    assert st["ready"] is False and "重新加载" in st["message"]


def test_version_tuple() -> None:
    assert setup_ops._version_tuple("1.10.0") > setup_ops._version_tuple("1.9.9")
    assert setup_ops._version_tuple(None) == ()
    assert setup_ops._version_tuple("x") == ()


def _write_presence(
    paths: BridgePaths, ver: str, token_match: bool | None = True
) -> None:
    paths.presence_file.parent.mkdir(parents=True, exist_ok=True)
    paths.presence_file.write_text(
        json.dumps({"ts": time.time(), "ext_version": ver, "token_match": token_match}),
        encoding="utf-8",
    )


def test_ready_from_presence_without_relay(paths: BridgePaths) -> None:
    """只装 browser_bridge、没有中继时，扩展报到即可判定设置完成；连接一项只作参考。"""
    setup_ops.run_setup(paths, python=sys.executable)
    ver = setup_ops.build_status(paths)["extension"]["version"]
    _write_presence(paths, ver)
    st = setup_ops.build_status(paths)
    assert st["ready"] is True and "设置已完成" in st["message"]
    checks = {c["key"]: c for c in st["checks"]}
    assert checks["loaded"]["ok"] is True and checks["connection"]["ok"] is None
    assert all(c["ok"] is not False for c in st["checks"])


def test_not_ready_when_extension_token_mismatch(paths: BridgePaths) -> None:
    setup_ops.run_setup(paths, python=sys.executable)
    ver = setup_ops.build_status(paths)["extension"]["version"]
    _write_presence(paths, ver, token_match=False)
    st = setup_ops.build_status(paths)
    assert st["ready"] is False and "令牌" in st["message"]


def test_host_stale_script_not_registered(paths: BridgePaths) -> None:
    """插件升级后宿主脚本未更新：不能报「已注册」。"""
    setup_ops.run_setup(paths, python=sys.executable)
    paths.host_script.write_text("# old", encoding="utf-8")
    host = setup_ops.host_info(paths)
    assert host["registered"] is False and host["script_in_sync"] is False


def test_refresh_installed_only_after_first_setup(paths: BridgePaths) -> None:
    assert setup_ops.refresh_installed(paths) is None
    assert not paths.ext_dir.exists()
    setup_ops.run_setup(paths, python=sys.executable)
    paths.host_script.write_text("# old", encoding="utf-8")
    assert setup_ops.refresh_installed(paths) is not None
    assert setup_ops.host_info(paths)["script_in_sync"] is True


def test_host_python_prefers_base_interpreter() -> None:
    py = setup_ops.host_python()
    assert Path(py).is_file()
    base = getattr(sys, "_base_executable", "")
    if base and Path(base).is_file():
        assert py == base
