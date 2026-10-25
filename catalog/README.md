# catalog/ —— 插件目录覆盖层的人工数据（ADR-0123）

Polaris 插件页内置了多家厂商的官方市场（共数千个插件 / 技能 / 连接器），上游内容是英文且大多没有分类。
本目录维护**中文与分类的人工输入**；机器翻译与分类由 `.github/workflows/catalog.yml` 每 6 小时自动生成。

| 文件 | 作用 | 谁改 |
|---|---|---|
| `taxonomy.yaml` | 四维分类词表（主题 / 部门 / 行业 / 日常生活）+ 上游 category 映射 | 人工，谨慎（ID 不可改名、不可复用） |
| `overrides/zh-CN.yaml` | 人工校对：覆盖某个条目的中文名称 / 摘要 / 说明 / 分类，优先级最高 | 人工，随时 |
| `featured.yaml` | 精选权重：插件页「推荐」排序 | 人工，随时 |

## 数据流

```
各厂商市场（GitHub / MCP Registry）
        │  polaris/tools/catalog_overlay_gen.go（复用 polaris 的市场解析，条目 ID 与守护进程一致）
        ▼
只把新增 / 变更条目送 DeepSeek（一次调用同时出中文和分类）→ machine.json（机器结果缓存）
        │  叠加 overrides + featured
        ▼
catalog-data 分支 index.json ──► Polaris 守护进程联网同步市场后拉取（ETag 条件请求）
```

## 常见操作

- **改一个插件的中文**：在 `overrides/zh-CN.yaml` 里按条目 ID 加一段，推到 main 即自动重新生成。条目 ID 就是 Polaris 插件页
  条目的 ID（形如 `anthropic/claude-plugins-official/github`）。
- **加精选**：在 `featured.yaml` 里加一行 `条目ID: 权重`。
- **加一个分类取值**：在 `taxonomy.yaml` 对应维度下加一行（en / zh 必填）。只影响之后新翻译的条目；要让旧条目重新分类，
  在 catalog-data 分支的 `machine.json` 里删掉对应条目行。
- **手动触发**：Actions → Catalog Overlay → Run workflow（勾选 dry_run 则不调用 LLM）。

## 前置条件

- 仓库 Secrets 需配置 `CATALOG_LLM_API_KEY`（DeepSeek API Key）。
- 生成器在 polaris 仓库 main 分支上（`tools/catalog_overlay_gen.go`），workflow 每次 checkout 最新版。

## 成本

每条目只送名称与描述（不送 README），系统提示逐字固定以命中前缀缓存。首次全量约 3 千条目，
之后每轮只处理新增与变更条目。
