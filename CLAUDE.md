# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指引。

## 项目概述

本仓库是 Polaris AI Agent 的官方插件库。每个插件都是独立的 MCP 服务器（stdio JSON-RPC 2.0），位于 `plugins/` 目录下，可通过 `uv` 独立运行。

## 运行插件

每个插件均自包含。在仓库根目录执行：

```bash
uv run plugins/computer_use/src/main.py
uv run plugins/browser_use/src/main.py
(cd plugins/knowledge_base && uv run python -m src.main)
uv run plugins/system_info/src/main.py
(cd plugins/social && uv run python -m src.main)
```

或进入插件目录执行：

```bash
cd plugins/computer_use
uv run src/main.py
```

## 安装 / 同步依赖

```bash
cd plugins/<插件名>
uv sync
```

## macOS 专用：编译 Swift OCR 二进制（仅 computer_use）

`find_text_on_screen` 二进制文件首次使用时会自动编译，也可手动构建：

```bash
swiftc plugins/computer_use/src/find_text_on_screen.swift \
       -o plugins/computer_use/src/find_text_on_screen
```

## 发布

推送 `v*` 格式的 tag 会触发 GitHub Actions 发布流程（`.github/workflows/release.yml`），自动生成 Release Notes。

---

## 架构

### 插件规范

每个插件遵循相同结构：
- `.codex-plugin/plugin.json` — 插件清单文件（元数据、分类、展示信息）。Polaris 内核按 ADR-0103 读取 `.codex-plugin/` / `.claude-plugin/` / 根 `plugin.json`。
- `src/main.py` — MCP 服务器入口
- `.mcp.json` — Claude Desktop / Claude Code 使用的 MCP 服务器配置
- `pyproject.toml` — 依赖声明（所有插件要求 Python ≥ 3.14）
- `skills/<插件名>/SKILL.md` — 随插件下发给 Agent 的使用决策指南（必须在二级子目录内）

**MCP 实现方式：**
- 手动 stdio 循环（`sys.stdin`）：`computer_use`、`system_info`
- 官方 `FastMCP` SDK（推荐，新插件应默认使用）：`browser_use`、`social`、`knowledge_base`

---

### computer_use — 桌面自动化插件

最复杂的插件，内部模块结构如下：

| 模块 | 职责 |
|------|------|
| `main.py` | MCP 服务器 + 动作路由 + 智能路由提示注入 |
| `schema.py` | `TOOL_SCHEMAS` — 三个工具的定义：`computer_core`（底层键鼠截图）、`computer_apps`（App 生命周期）、`computer_macro`（聊天宏/批处理） |
| `utils.py` | 跨平台共享工具：键盘（pynput）、鼠标、剪贴板注入、无障碍访问（osascript/JXA）、语言环境检测、截图 GC |
| `handlers/` | 按动作类型分文件：`screen`、`mouse`、`keyboard`、`interaction`、`apps` |
| `adapters/base.py` | `BaseAdapter` — 通用三策略搜索结果选择器（无障碍 A/B → 键盘 C） |
| `adapters/chat/wechat.py` | `WeChatAdapter` — 覆盖微信/QQ 的结果选择：OCR 优先（A）、多窗口无障碍（B）、键盘兜底（C） |
| `adapters/registry.py` | Bundle ID → 适配器类映射；新增适配器在此注册 |
| `profiles/*.json` | 每应用配置：快捷键、本地化标签、别名、Bundle ID |
| `profiles_loader.py` | 启动时加载并索引所有配置；解析语言相关字段（`zh`/`en`） |

**三层工具 API（2026 标准拆分）：**
- **`computer_macro`：** `send_message_to` / `send_file_to` / `read_messages_from` / `computer_batch` — 高层宏，单次调用完成聊天全流程。
- **`computer_apps`：** `open_app` / `close_window` / `minimize_app` / `quit_app` / `get_running_apps` / `get_window_list` — 应用生命周期管理。
- **`computer_core`：** 截图、键鼠、剪贴板、无障碍树等全部底层操作 — 适用于任意应用。

**新增聊天应用：** 参照 `wechat.json` 在 `src/profiles/` 中创建 JSON 文件，无需改代码。若该应用的搜索下拉框使用非标准 UI（如独立 NSWindow），则需继承 `BaseAdapter` 并覆盖相关方法。

**应用黑白名单：** 运行时配置文件路径为 `~/.config/polaris-computer-mcp/config.json`（首次调用涉及 `app_name` 的动作时自动创建）。`"allowed_apps": ["*"]` 表示放行所有应用，`blocked_apps` 中的应用始终被拦截。

**状态文件：** `get_screen_state` 将元素坐标写入 `$TMPDIR/computer_use_state.json`，供后续 `click_element_by_id` 使用。执行 `open_app` 和 `send_message_to` 时该文件会被自动清除。

**macOS 键盘路由：** `send_message_to` 通过 `osascript tell process X to keystroke` 发送按键，无需目标应用处于最前台。低层 `key`/`type` 动作使用 pynput，要求目标应用处于最前台。

---

### browser_use — 通用浏览器插件（v2.1.0）

使用 `FastMCP` + Patchright。只做通用浏览器能力与浏览器连接（BrowserHub：扩展桥接 / CDP / 托管 profile），**不含任何平台知识、站点配方或限速**。暴露工具：`browser_open`、`browser_read`、`browser_snapshot`、`browser_act`、`browser_scroll`、`browser_extract`、`browser_tabs`、`browser_status`。已知社交平台请使用 `social` 插件。`POLARIS_BROWSER_CDP_URL` 可显式指定 CDP 端点；读不到 `DevToolsActivePort` 时不再猜测端口。

---

### knowledge_base — 资料库（Vault，v2.0.0）

`FastMCP` 实现，MCP 服务器名保持 `polaris-knowledge-base`（内核写入白名单按 `mcp__polaris-knowledge-base__kb_save`）。核心在 `src/vault.py`（纯标准库）：把文档落成带 YAML front matter 的 Markdown（默认 `~/Polaris/Vault`，由 `POLARIS_VAULT_DIR` 覆盖，Obsidian 兼容），按规范化 URL 去重，SQLite（WAL + FTS5，CJK 逐字切分）索引在 `<vault>/.polaris/index.sqlite`。所有路径 `resolve()` 后必须位于资料库内，拒绝 `..` 与符号链接越界。工具：`kb_save`（幂等、非破坏性）、`kb_list`、`kb_search`、`kb_read`、`kb_tag`、`kb_move`，以及保持原行为的旧工具 `list_files`、`read_content`（受 `POLARIS_KB_ALLOWED_DIR` 约束）。内核以 ObsidianConnector 同步资料库目录入 RAG，插件不做入库逻辑。

---

### system_info — 系统环境信息插件

暴露 `check_app_installed`。在 macOS 搜索 `/Applications`，在 Windows 搜索 `Program Files`，在 Linux 搜索 `PATH` 和 `.desktop` 文件。

---

### social — 社交平台读写插件（v3.0.0，MCP 服务器 `polaris-social`）

使用 `FastMCP` + Patchright，复用 `utils/browser_hub.py`（与 browser_use 逐字节一致，`check.sh` 校验）。读与写同处一个插件，**按平台共享限速与风控熔断**（`src/ratelimit.py`，SQLite 跨进程；`src/gate.py` 把写工具接入同一把键，`twitter` 与读侧的 `x` 同键）。

- **读工具**（`readOnlyHint` + `openWorldHint`）：`social_platforms`、`social_search`、`social_hot`、`social_feed`、`social_read`、`social_selftest`。平台为配方站点枚举 `zhihu`/`x`/`weibo`/`xiaohongshu`（`recipes/*.toml`，XHR 拦截优先、CSS 兜底），配方缺动作返回 `unsupported_action`。采集引擎在 `src/harvest/`，工具实现在 `src/tools_social.py`。
- **写工具**：`auto_post`、`batch_post`、`post_video`、`post_thread`、`like_post` 等原有工具，声明 `readOnlyHint=False, destructiveHint=True`；执行前经 `rate_limited_write` 占用名额，被限速时返回错误码而不执行。无配方平台使用保守默认限速（10 秒间隔、20 次/小时、60 次/天）。
- 支持写入的平台：`twitter`、`instagram`、`facebook`、`weibo`、`xiaohongshu`、`douyin`、`wechat`、`tiktok`、`linkedin`、`threads`。每个平台有独立 Adapter（`src/adapters/`）；调用写工具前**必须先执行 `get_platform_skill(platform)`**。
- 技能文件位于 `skills/social/`（入口 `SKILL.md`，平台规范 `*_skill.md`）。
- 真机冒烟：`cd plugins/social && POLARIS_BROWSER_BACKEND=cdp uv run python scripts/live_smoke.py | tee /tmp/live_smoke.log`（只读、单连接）。

---

## 2026 开发者指南与行业标准

为了符合最新的 AI Agent 与 MCP 行业规范，本仓库的所有插件开发必须遵循以下准则：

### 1. MCP (Model Context Protocol) 2025-11-25 规范
- **Tasks 与异步工作流**：耗时操作应使用 MCP 的 `Tasks` 原语，避免同步长轮询。
- **协议处理**：强烈建议放弃手动解析 `sys.stdin` 循环（如遗留的代码实现），全面拥抱官方 SDK（如 Python `mcp` 库或 `FastMCP`），以自动处理生命周期（`notifications/initialized`）、请求取消与分页等底层规范。

### 2. OpenAI Agent 与 Tool Schema 规范 (严格模式)
- **破除 God Tool**：避免将数十个功能塞入单一工具。工具需按逻辑边界拆分（例如 `computer` 工具应拆分为 `computer_core`、`computer_apps` 等）。
- **强制严格模式 (Strict Mode)**：通过 JSON Schema (如 Pydantic) 定义严格的必填项（required），坚决抵制扁平化全可选参数，有效消除 LLM 参数幻觉。

### 3. Claude Code 插件结构
- 插件以 `.codex-plugin/plugin.json` 为元数据核心。
- 使用 `skills/`（Markdown 指令与工作流）代替传统的斜杠命令。
- 提供 `hooks/` 与 `agents/` 来增强生命周期和任务隔离能力。

### 4. 安全性与工程化最佳实践
- **提示词注入防御**：LLM 传入的参数在拼接 Shell/AppleScript/JXA 脚本前，必须经过严格的 JSON 序列化转义（如 `json.dumps()`），严禁使用原生 f-string 裸插值。
- **配置持久化**：绝不污染只读的 `src/` 源码目录。运行时配置文件必须写入操作系统的标准用户目录（如 `~/.config/polaris-plugins/`）。
