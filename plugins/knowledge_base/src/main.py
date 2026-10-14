"""Polaris 资料库（Knowledge Vault）MCP 服务器 (v2.0.0)。

把采集 / 摘要结果落成带 YAML front matter 的 Markdown（默认 ~/Polaris/Vault，Obsidian 兼容），
按 URL 去重，并提供列表、全文检索、读取、打标签、移动。写入严格限定在资料库目录内。
内核以 ObsidianConnector 把资料库目录同步进 RAG，本插件不做任何入库逻辑。

旧工具 list_files / read_content 保留原有行为（受 POLARIS_KB_ALLOWED_DIR 约束），新任务优先使用 kb_*。
"""

from __future__ import annotations

import os
import pathlib
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from .vault import MAX_DOCS_PER_CALL, Vault, VaultError

mcp = FastMCP("polaris-knowledge-base")

READ_ANN = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
SAVE_ANN = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
EDIT_ANN = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
)


class DocIn(BaseModel):
    """待保存的文档。兼容管线直接传入的条目（excerpt 可回退为 content，多余字段忽略）。"""

    model_config = ConfigDict(extra="ignore")

    url: str | None = Field(
        default=None, max_length=2048, description="原文地址，用于去重；digest 可省略"
    )
    title: str = Field(default="", max_length=500, description="标题；缺省时取正文首行")
    content: str = Field(
        default="", description="Markdown 正文（单篇上限 500KB，超出截断）"
    )
    excerpt: str | None = Field(default=None, description="content 为空时的回退正文")
    source: str | None = Field(
        default=None, max_length=100, description="来源，如 zhihu；缺省取 URL 域名"
    )
    author: str | None = Field(default=None, max_length=200)
    published_at: str | None = Field(
        default=None, max_length=64, description="发布时间，建议 ISO 8601"
    )
    tags: list[Annotated[str, Field(max_length=100)]] = Field(
        default_factory=list, max_length=60
    )
    metrics: dict[str, Any] | None = Field(
        default=None, description="点赞 / 评论等指标，写入 front matter"
    )


def _vault() -> Vault:
    return Vault()


def _err(e: VaultError) -> dict[str, Any]:
    return {"ok": False, "error": e.to_dict()}


@mcp.tool(annotations=SAVE_ANN)
def kb_save(
    docs: Annotated[list[DocIn], Field(min_length=1, max_length=MAX_DOCS_PER_CALL)],
    kind: Literal["raw", "digest"] = "raw",
    collection: Annotated[str, Field(max_length=200)] = "",
) -> dict[str, Any]:
    """把文档保存为资料库里的 Markdown（含 front matter）。按 url 去重：内容未变 -> unchanged，变了 -> 覆盖并更新 updated_at。
    kind=raw 存原文（需 url），kind=digest 存摘要（url 可省略）；collection 为可选子目录分组。单次 ≤100 条。
    返回 {saved, updated, unchanged, failed}，路径均为绝对路径。"""
    try:
        res = _vault().save(
            [d.model_dump(exclude_none=True) for d in docs],
            kind=kind,
            collection=collection,
        )
    except VaultError as e:
        return _err(e)
    return {"ok": True, **res}


@mcp.tool(annotations=READ_ANN)
def kb_list(
    source: str = "",
    tag: str = "",
    since: Annotated[
        str,
        Field(
            description="只列出该时间之后保存的，如 2026-10-01 或 2026-10-01T08:00:00Z"
        ),
    ] = "",
    kind: Literal["", "raw", "digest"] = "",
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    """按来源 / 标签 / 保存时间 / 类型列出资料库文档（最近保存的在前）。"""
    try:
        return {"ok": True, **_vault().list_docs(source, tag, since, kind, limit)}
    except VaultError as e:
        return _err(e)


@mcp.tool(annotations=READ_ANN)
def kb_search(
    query: Annotated[str, Field(min_length=1, max_length=200)],
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    """全文检索资料库（SQLite FTS5，支持中文；多个词为 AND）。返回路径、标题与 ≤200 字片段。"""
    try:
        return {"ok": True, **_vault().search(query, limit)}
    except VaultError as e:
        return _err(e)


@mcp.tool(annotations=READ_ANN)
def kb_read(
    path: Annotated[str, Field(min_length=1, max_length=1024)],
    max_chars: Annotated[int, Field(ge=200, le=100000)] = 20000,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict[str, Any]:
    """读取资料库内文档：返回 front matter 元信息与正文分页（truncated / next_offset）。path 必须在资料库内。"""
    try:
        return {"ok": True, **_vault().read(path, max_chars, offset)}
    except VaultError as e:
        return _err(e)


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def kb_tag(
    path: Annotated[str, Field(min_length=1, max_length=1024)],
    add: list[Annotated[str, Field(max_length=100)]] = [],  # noqa: B006 - 仅读取，不会被修改
    remove: list[Annotated[str, Field(max_length=100)]] = [],  # noqa: B006
) -> dict[str, Any]:
    """增删文档标签（只改 front matter 的 tags 与索引，不动正文）。"""
    try:
        return {"ok": True, **_vault().tag(path, add, remove)}
    except VaultError as e:
        return _err(e)


@mcp.tool(annotations=EDIT_ANN)
def kb_move(
    path: Annotated[str, Field(min_length=1, max_length=1024)],
    folder: Annotated[str, Field(min_length=1, max_length=1024)],
) -> dict[str, Any]:
    """把文档移动到资料库内的另一个文件夹（保留文件名；目标已有同名文件则拒绝）。"""
    try:
        return {"ok": True, **_vault().move(path, folder)}
    except VaultError as e:
        return _err(e)


# ---------------------------------------------------------------------------
# 旧工具（向后兼容，行为不变）：受 POLARIS_KB_ALLOWED_DIR 约束，返回文本
# ---------------------------------------------------------------------------


def is_path_allowed(target_path: str) -> bool:
    allowed = os.environ.get("POLARIS_KB_ALLOWED_DIR")
    if not allowed:
        return True
    try:
        abs_target = pathlib.Path(target_path).resolve()
        abs_root = pathlib.Path(allowed).resolve()
        return abs_root in abs_target.parents or abs_target == abs_root
    except (OSError, ValueError, RuntimeError):
        return False


@mcp.tool(annotations=READ_ANN)
def list_files(path: str) -> str:
    """List files in a given directory path (legacy; prefer kb_list / kb_search for the Vault)."""
    if not is_path_allowed(path):
        raise PermissionError(
            "path is outside the allowed directory (POLARIS_KB_ALLOWED_DIR)"
        )
    try:
        names = []
        for entry in os.listdir(path):
            names.append(
                f"{entry}/" if os.path.isdir(os.path.join(path, entry)) else entry
            )
        return f"Files in {path}:\n" + "\n".join(names)
    except OSError as e:
        return f"failed to read dir: {e}"


@mcp.tool(annotations=READ_ANN)
def read_content(path: str) -> str:
    """Read the textual content of a specific file (legacy; prefer kb_read for Vault documents)."""
    if not is_path_allowed(path):
        raise PermissionError(
            "path is outside the allowed directory (POLARIS_KB_ALLOWED_DIR)"
        )
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        return "failed to read file: File is binary or not UTF-8 encoded."
    except OSError as e:
        return f"failed to read file: {e}"


def main() -> None:
    """启动 MCP 服务端。"""
    mcp.run()


if __name__ == "__main__":
    main()
