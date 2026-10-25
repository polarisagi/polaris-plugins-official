# Polaris Knowledge Vault MCP (v2.0.0)

🌎 [English](README.md) | 🇨🇳 [中文](README_zh.md)

> Full documentation: [docs/knowledge-base.md](../../docs/knowledge-base.md) (Chinese)

The official [Polaris](https://polarisagi.online/) Knowledge Vault plugin: it saves collected results and digests as Markdown files with a YAML front matter (default `~/Polaris/Vault`,
Obsidian-compatible), deduplicates by URL, and provides listing, full-text search (SQLite FTS5, Chinese supported), reading, tagging, and moving.
The kernel syncs the vault directory into RAG through `ObsidianConnector`; this plugin does no ingestion itself. The MCP server name stays `polaris-knowledge-base`.

## Tools

| Tool | Read-only | Description |
|------|:----:|------|
| `kb_save(docs, kind="raw", collection="")` | No (idempotent, non-destructive) | Saves up to 100 documents; deduplicates by URL and returns `{saved, updated, unchanged, failed}` |
| `kb_list(source, tag, since, kind, limit=50)` | Yes | Lists by source / tag / save time / kind |
| `kb_search(query, limit=20)` | Yes | FTS5 full-text search; returns the path, title, and a snippet of at most 200 characters |
| `kb_read(path, max_chars=20000, offset=0)` | Yes | Reads a vault document (meta + paginated body) |
| `kb_tag(path, add=[], remove=[])` | No | Edits the tags in the front matter and in the index |
| `kb_move(path, folder)` | No | Moves a document within the vault |
| `list_files(path)` / `read_content(path)` | Yes | Legacy tools with unchanged behavior (constrained by `POLARIS_KB_ALLOWED_DIR`); prefer the `kb_*` tools |

## Directory and File Format

```
<vault>/<source>/<YYYY>/<MM>/<slug>.md        # 原文
<vault>/digests/<YYYY-MM-DD>-<slug>.md        # 摘要
<vault>/.polaris/index.sqlite                 # 索引（WAL；docs + FTS5 docs_fts）
```

```markdown
---
title: "如何构建 Agent 系统"
url: "https://www.zhihu.com/question/1"
source: "zhihu"
author: "张三"
published_at: "2026-09-30T08:00:00Z"
saved_at: "2026-10-14T08:00:00Z"
updated_at: "2026-10-14T08:00:00Z"
tags: ["ai", "agent"]
kind: raw
---

正文 Markdown……
```

## Security

- Every `kb_*` path must resolve to a location inside the vault root: `..`, absolute paths that escape the root, and symlink escapes are rejected, and `.polaris/` may not be accessed.
- Front matter values are always written with JSON-style escaping, so quotes / colons / newlines in a title cannot corrupt the front matter.
- Writes use a temporary file in the same directory followed by an atomic replace; a single document is capped at 500KB, and anything beyond that is truncated and marked `truncated: true`.

## Configuration

| Environment variable | Description |
|----------|------|
| `POLARIS_VAULT_DIR` | Vault root directory, default `~/Polaris/Vault` (not `~/Documents`, which macOS protects for privacy); created on first write |
| `POLARIS_KB_ALLOWED_DIR` | Constrains only the legacy tools `list_files` / `read_content` |

## Running and Development

```bash
cd plugins/knowledge_base
uv run python -m src.main          # 启动 MCP 服务器（stdio）
uv run --with pytest pytest -q     # 单元测试（全部离线）
```

## Requirements
- Python ≥ 3.14, `uv`
