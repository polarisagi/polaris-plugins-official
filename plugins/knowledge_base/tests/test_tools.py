"""资料库 MCP 工具层测试：注册 / 注解 / schema / 端到端 / 旧工具兼容。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from src import main


@pytest.fixture(autouse=True)
def _vault_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "Vault"
    monkeypatch.setenv("POLARIS_VAULT_DIR", str(root))
    monkeypatch.delenv("POLARIS_KB_ALLOWED_DIR", raising=False)
    return root


def _tools() -> dict[str, Any]:
    return {t.name: t for t in asyncio.run(main.mcp.list_tools())}


def test_tool_names_and_annotations() -> None:
    tools = _tools()
    assert set(tools) == {
        "kb_save",
        "kb_list",
        "kb_search",
        "kb_read",
        "kb_tag",
        "kb_move",
        "list_files",
        "read_content",
    }
    for name in ("kb_list", "kb_search", "kb_read", "list_files", "read_content"):
        assert tools[name].annotations.readOnlyHint is True, name
    save = tools["kb_save"].annotations
    assert (save.readOnlyHint, save.destructiveHint, save.idempotentHint) == (
        False,
        False,
        True,
    )
    for name in ("kb_tag", "kb_move"):
        assert tools[name].annotations.readOnlyHint is False
        assert tools[name].annotations.destructiveHint is False


def test_kb_save_schema_is_strict() -> None:
    schema = _tools()["kb_save"].inputSchema
    assert schema["required"] == ["docs"]
    assert schema["properties"]["kind"]["enum"] == ["raw", "digest"]
    assert schema["properties"]["docs"]["maxItems"] == 100
    assert schema["properties"]["docs"]["minItems"] == 1
    doc_schema = schema["$defs"]["DocIn"]["properties"]
    assert {
        "url",
        "title",
        "content",
        "source",
        "author",
        "published_at",
        "tags",
    } <= set(doc_schema)


def test_end_to_end_save_search_read_tag_move(_vault_env: Path) -> None:
    docs = [
        main.DocIn(
            url="https://www.zhihu.com/question/9",
            title="端到端测试",
            content="资料库端到端检索内容",
            tags=["t1"],
        )
    ]
    saved = main.kb_save(docs)
    assert saved["ok"] is True and len(saved["saved"]) == 1
    path = saved["saved"][0]
    assert path.startswith(str(_vault_env.resolve()))

    assert main.kb_save(docs)["unchanged"] == [path]
    hit = main.kb_search("端到端")
    assert hit["ok"] and hit["results"][0]["path"] == path
    assert main.kb_list(source="zhihu.com")["count"] == 1
    assert main.kb_read(path)["meta"]["title"] == "端到端测试"
    assert main.kb_tag(path, add=["t2"], remove=["t1"])["tags"] == ["t2"]
    moved = main.kb_move(path, "归档")
    assert moved["ok"] and Path(moved["path"]).is_file()


def test_errors_are_structured(_vault_env: Path) -> None:
    res = main.kb_read("../../etc/passwd")
    assert res == {
        "ok": False,
        "error": {"code": "path_outside_vault", "message": "路径不得包含 '..'"},
    }
    assert main.kb_search("   ")["error"]["code"] == "invalid_args"
    assert main.kb_move("/etc/hosts", "x")["error"]["code"] == "path_outside_vault"
    res2 = main.kb_save([main.DocIn(title="no url", content="c")])
    assert res2["ok"] is True and res2["failed"][0]["code"] == "missing_url"


def test_legacy_tools_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "bin.dat").write_bytes(b"\xff\xfe\x00\x81")

    listing = main.list_files(str(tmp_path))
    assert listing.startswith(f"Files in {tmp_path}:\n")
    assert "a.txt" in listing and "sub/" in listing
    assert main.read_content(str(tmp_path / "a.txt")) == "hello"
    assert main.read_content(str(tmp_path / "bin.dat")) == (
        "failed to read file: File is binary or not UTF-8 encoded."
    )
    assert main.read_content(str(tmp_path / "missing")).startswith(
        "failed to read file:"
    )
    assert main.list_files(str(tmp_path / "missing")).startswith("failed to read dir:")

    monkeypatch.setenv("POLARIS_KB_ALLOWED_DIR", str(tmp_path / "sub"))
    with pytest.raises(PermissionError):
        main.read_content(str(tmp_path / "a.txt"))
    with pytest.raises(PermissionError):
        main.list_files(str(tmp_path))
    assert main.list_files(str(tmp_path / "sub")).startswith("Files in")
