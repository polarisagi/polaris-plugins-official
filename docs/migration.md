# 变更说明与迁移指南

本页给从旧版本升级的用户：`social_poster` → `social`、`harvest*` 工具迁移对照、`browser_use` v1 → v2、`knowledge_base` v1 → v2、旧 `.polaris-plugin` 清单 → `.codex-plugin`。

结论先行：**升级后要改的主要是引用旧工具名 / 旧 MCP 前缀的地方（管线、提示词、客户端配置）。** 旧的 `list_files` / `read_content` 与全部发帖类工具名保持不变，但 MCP 服务器名从 `polaris-social-poster` 变成 `polaris-social`，所以带前缀的完整工具名变了。

本页依据仓库提交历史（`3fb4c30`、`f3f6bde`、`36467bc`、`5387b59`、`01e5a4e`）整理；内核侧背景见 Polaris 仓库 ADR-0114（决策四与 2026-10-14 追加的决策八）。

## 1. 总览

| 插件 | 旧 | 新 | 破坏性变更 |
|------|----|----|-----------|
| `browser_use` | v1：`navigate` 等 8 个旧工具；随后 v2.0.0：`browser_*` + `harvest*` | **v2.1.0**：仅 `browser_*` 8 个通用工具 | 是（工具名、参数、返回结构；`harvest*` 移走） |
| `social_poster` | v1.0.0，服务器 `polaris-social-poster` | **`social` v3.0.0**，服务器 `polaris-social` | 服务器名 / 完整工具名变化；新增 `social_*` 读工具 |
| `knowledge_base` | v1.0.0：只有 `list_files` / `read_content` | **v2.0.0**：Vault，新增 `kb_*` | 否（旧工具保留）；启动命令变化 |
| 清单目录 | `.polaris-plugin/plugin.json` | `.codex-plugin/plugin.json` | 对仓库使用者无感；内核只读新位置 |

## 2. `social_poster` → `social`

| 项 | 旧 | 新 |
|----|----|----|
| 目录 | `plugins/social_poster` | `plugins/social`（`git mv`，历史保留） |
| 清单 `name` | `polaris-social-poster` | `polaris-social` |
| MCP 服务器名 | `polaris-social-poster` | `polaris-social` |
| 完整工具名前缀 | `mcp__polaris-social-poster__<工具>` | `mcp__polaris-social__<工具>` |
| 版本 | 清单 1.0.0 | 3.0.0 |
| 启动命令 | `uv run src/main.py` | `uv run python -m src.main`（相对导入下旧命令无法启动） |
| 能力 | 仅写（发帖 / 互动 / 定时）与旧适配器读 | 读（`social_*`，配方 + XHR 拦截）+ 写，**读写共享按平台的限速与熔断** |
| 写工具标注 | 无 | `readOnlyHint=False, destructiveHint=True`；执行前占用限速名额，被限速返回错误码而不执行 |
| 旧读工具 | `search_posts`、`read_post`、`get_trending_topics`、`get_user_profile`、`get_my_posts`、`get_comments`、分析 / 通知类 | 保留，补上 `readOnlyHint` 并接入同一把限速键 |
| 定时队列 | `~/.polaris_social_scheduler.json` | 不变 |

需要你做的：

1. 把客户端 / 管线 / 提示词里的 `polaris-social-poster` 与 `mcp__polaris-social-poster__*` 改成 `polaris-social` / `mcp__polaris-social__*`。
2. 在内核/客户端里重新安装或刷新插件，使其以新服务器名注册。
3. 写工具现在可能返回 `{"ok": false, "error": {"code": "rate_limited" | "cooling_down" | "out_of_hours", ...}}`，调用方要能处理；`run_scheduled_posts` 遇到限速时任务保持 pending。
4. 发帖前仍然必须先 `get_platform_skill(platform)`。

## 3. `harvest*` 工具迁移对照

`harvest` / `harvest_recipes` / `harvest_selftest` 原属 `browser_use` v2.0.0，现已**从 `browser_use` 删除**，迁入 `social`（采集引擎 `harvest/`、限速 `ratelimit.py`、配方 `recipes/`、`live_smoke.py`、相关测试与夹具一并迁移）。

| 旧工具（`browser_use` v2.0.0） | 新工具（`social` v3.0.0） | 变化 |
|--------------------------------|---------------------------|------|
| `harvest(site, "search", {"q": ...}, max_items)` | `social_search(platform, query, max_items=20)` | 参数改名；`query` 1–200 字符；`max_items` 1–100；返回里 `site` 变 `platform` |
| `harvest(site, "hot", {}, max_items)` | `social_hot(platform, max_items=20)` | 无热榜动作的平台返回 `unsupported_action` |
| `harvest(site, "user_timeline", {"handle": ...}, max_items)` | `social_feed(platform, handle="", max_items=20)` | `handle` 不带 `@` |
| `harvest_recipes()` | `social_platforms()` | 额外返回登录态缓存、限速余量、`write_only_platforms`、`rate_key_aliases` |
| `harvest_selftest(site)` | `social_selftest(platform)` | 返回里 `site` 变 `platform` |
| （无） | `social_read(url, max_chars=8000, offset=0)` | 新增：读帖文 / 文章正文 Markdown，计入平台限速 |

其他行为变化：

- `platform` 现在是枚举 `zhihu` / `x` / `weibo` / `xiaohongshu`（旧 `site` 是自由字符串，未知站点返回 `invalid_args`）；未知平台由参数校验直接拒绝。
- 错误码新增 `unsupported_action`、`unsupported_platform`、`read_failed`、`empty_content`、`selftest_failed`，见 [social.md](social.md)。
- 配方文件格式不变；用户覆盖目录与限速数据库路径不变（`~/.config/polaris-plugins/browser/recipes/`、`.../ratelimit.db`），已有的用户配方和限速记录继续有效。
- 完整工具名前缀由 `mcp__polaris-browser-use__harvest*` 变为 `mcp__polaris-social__social_*`。
- 配方仍是 beta，仅夹具测试；真机冒烟待你运行。

## 4. `browser_use` v1 → v2

v1 是手写的 8 个简单工具，返回字符串；v2 重写为 FastMCP + `BrowserHub`，返回统一 JSON。

| v1 工具 | v2 工具 | 说明 |
|---------|---------|------|
| `navigate(url)` | `browser_open(url, new_tab=false)` | 返回 `{ok, tab_id, url, title}`；仅接受 http(s) |
| `get_interactive_dom()` | `browser_snapshot(scope="viewport", max_items=80)` | 元素编号由整数 `polaris-id` 改为字符串 `e<N>`；默认只扫视口 |
| `action_by_id(id, action, text)` | `browser_act(ref, action, text="")` | `id: int` → `ref: "e12"`；新增 `select`、`press`、`back`；stale 引用返回 `stale_ref` |
| `scroll_page(direction)` | `browser_scroll(direction="down", times=1)` | 返回 `scroll_y`、`at_bottom` |
| `go_back()` | `browser_act(ref=…, action="back")` | `ref` 必填但被忽略 |
| `close_tab()` | `browser_tabs(action="close", tab_id)` | 只能操作自建标签 |
| `get_page_content()`（`innerText` 前 40000 字符） | `browser_read(mode="article" \| "markdown" \| "text" \| "links", max_chars=6000, offset=0, selector=null)` | 默认智能正文，支持分页 |
| `get_current_state()` | `browser_status()` / `browser_tabs(action="list")` | `browser_status` 返回后端、连接、令牌路径等 |
| （无） | `browser_extract(container, fields, max_items=50)` | 新增：按 CSS 批量抽取列表 |

v2 的结构性变化：

- 三个后端 `extension` / `cdp` / `managed`（v2.0.0 起），免弹窗扩展 Polaris Browser Bridge（后迁至 `browser_bridge/extension/`，中继端口 `18790–18799`），Chrome 136+ 兼容。
- 隔离：只在 Polaris 自建窗口内操作，按 marker URL 定位，不读 cookie，不自动登录。
- v2.1.0：去掉 `harvest*` 与限速依赖，`browser_use` 回归平台无关；移除了“猜测 9222 端点”的兜底，读不到 `DevToolsActivePort` 时给出明确指引（可设 `POLARIS_BROWSER_CDP_URL`）。
- 启动命令：`uv run src/main.py` → `uv run python -m src.main`。
- 云端 VPS / 无头服务器不建议安装本插件，请用内核的 `web_fetch` / `feed_fetch` / `web_search`。

## 5. `knowledge_base` v1 → v2

| 项 | v1 | v2 |
|----|----|----|
| 定位 | 带路径沙盒的本地文件读取 | 资料库（Vault）：Markdown + YAML front matter，Obsidian 兼容 |
| 实现 | 手写 stdio JSON-RPC 循环，仅标准库 | FastMCP（依赖 `mcp`、`pydantic`），核心 `vault.py` 仍是纯标准库 |
| 工具 | `list_files`、`read_content` | 保留这两个（行为不变，仍受 `POLARIS_KB_ALLOWED_DIR` 约束）+ `kb_save`、`kb_list`、`kb_search`、`kb_read`、`kb_tag`、`kb_move` |
| 环境变量 | `POLARIS_KB_ALLOWED_DIR` | 新增 `POLARIS_VAULT_DIR`（默认 `~/Polaris/Vault`） |
| 启动命令 | `uv run src/main.py` | `uv run python -m src.main` |
| MCP 服务器名 | `polaris-knowledge-base` | 不变（内核写入白名单按 `mcp__polaris-knowledge-base__kb_save` 匹配） |
| RAG | 无 | 内核用 ObsidianConnector 同步 `knowledge.vault_dirs`，默认含 `~/Polaris/Vault` |
| 版本 | 清单 1.0.0 | 2.0.0 |

升级后你可能要做的：

- 已有的 Markdown 笔记目录想让 `kb_*` 管理：把 `POLARIS_VAULT_DIR` 指向它，并在内核配置的 `knowledge.vault_dirs` 里加入同一目录（见 [knowledge-base.md](knowledge-base.md) 第 8 节）。已有文件不会自动进入 `kb_list` / `kb_search` 的索引，只有经 `kb_save` 写入的才会。
- 默认 `.mcp.json` 把 `POLARIS_KB_ALLOWED_DIR` 设为空，意味着旧工具不受限；需要限制请显式设置。

## 6. `.polaris-plugin` → `.codex-plugin`

| 项 | 内容 |
|----|------|
| 变更 | 提交 `3fb4c30`：5 个插件的 `.polaris-plugin/plugin.json` 整体重命名为 `.codex-plugin/plugin.json`（文件内容未改），同步更新根 README / README_zh / CLAUDE.md |
| 原因 | 旧目录已被内核 ADR-0103 删除，内核不再读取（ADR-0114 事实 F4）；内核现读 `.codex-plugin/`、`.claude-plugin/` 或根 `plugin.json` |
| 影响 | 手工安装 / 自建市场时，清单路径要用 `.codex-plugin/plugin.json`；`.mcp.json`、`skills/` 位置不变 |
| 检查 | 仓库里不应再有 `.polaris-plugin` 目录 |

## 7. 升级检查清单

- [ ] 把引用 `polaris-social-poster` 的配置 / 管线 / 提示词改为 `polaris-social`。
- [ ] 把 `harvest*` 调用改成 `social_*`，`site` → `platform`，`q` → `query`。
- [ ] 把 `navigate` / `get_interactive_dom` / `action_by_id` 等旧 `browser_use` 调用改为 `browser_*`，元素编号改用 `e<N>`。
- [ ] 安装 Polaris Browser Bridge 扩展并配对（可选但推荐），见 [browser-use.md](browser-use.md)。
- [ ] 确认 Python ≥ 3.14、`uv` 可用，用 `uv run python -m src.main` 启动。
- [ ] 需要无人值守采集的管线，使用 `extension` 或 `managed` 后端，见 [pipelines.md](pipelines.md)。
- [ ] 让 Vault 目录出现在内核的 `knowledge.vault_dirs` 中。
