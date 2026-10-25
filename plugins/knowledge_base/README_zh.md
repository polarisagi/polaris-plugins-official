# Polaris 资料库（Polaris Knowledge Vault）MCP (v2.0.0)

🌎 [English](README.md) | 🇨🇳 [中文](README_zh.md)

> 完整文档：[docs/knowledge-base.md](../../docs/knowledge-base.md)

[Polaris](https://polarisagi.online/) 官方资料库插件：把采集结果与摘要落成带 YAML 元信息头的 Markdown（默认 `~/Polaris/Vault`，
Obsidian 兼容），按 URL 去重，并提供列表、全文检索（SQLite FTS5，支持中文）、读取、打标签与移动。
内核用 `ObsidianConnector` 把资料库目录同步进 RAG，本插件不做入库逻辑。MCP 服务器名保持 `polaris-knowledge-base`。

## 工具

| 工具 | 只读 | 说明 |
|------|:----:|------|
| `kb_save(docs, kind="raw", collection="")` | 否（幂等、非破坏性） | 保存 ≤100 条文档；按 URL 去重，返回 `{saved, updated, unchanged, failed}` |
| `kb_list(source, tag, since, kind, limit=50)` | 是 | 按来源 / 标签 / 保存时间 / 类型列出 |
| `kb_search(query, limit=20)` | 是 | FTS5 全文检索，返回路径、标题、≤200 字片段 |
| `kb_read(path, max_chars=20000, offset=0)` | 是 | 读取资料库文档（meta + 正文分页） |
| `kb_tag(path, add=[], remove=[])` | 否 | 改元信息头（front matter）里的 tags 与索引 |
| `kb_move(path, folder)` | 否 | 在资料库内移动文档 |
| `list_files(path)` / `read_content(path)` | 是 | 旧工具，行为不变（受 `POLARIS_KB_ALLOWED_DIR` 约束）；优先使用 `kb_*` |

## 目录与文件格式

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

## 安全

- 所有 `kb_*` 路径解析后必须位于资料库根目录内：拒绝 `..`、绝对路径越界、符号链接逃逸，且不得访问 `.polaris/`。
- 元信息头（front matter）的值一律以 JSON 风格转义写出，标题中的引号 / 冒号 / 换行不会破坏元信息头。
- 写入使用同目录临时文件 + 原子替换；单篇上限 500KB，超出截断并标记 `truncated: true`。

## 配置

| 环境变量 | 说明 |
|----------|------|
| `POLARIS_VAULT_DIR` | 资料库根目录，默认 `~/Polaris/Vault`（不用 `~/Documents`，macOS 对其有隐私保护）；首次写入时创建 |
| `POLARIS_KB_ALLOWED_DIR` | 仅约束旧工具 `list_files` / `read_content` |

## 运行与开发

```bash
cd plugins/knowledge_base
uv run python -m src.main          # 启动 MCP 服务器（stdio）
uv run --with pytest pytest -q     # 单元测试（全部离线）
```

## 要求
- Python ≥ 3.14，`uv`
