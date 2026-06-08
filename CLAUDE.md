# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指引。

## 项目概述

本仓库是 Polaris AI Agent 的官方插件库。每个插件都是独立的 MCP 服务器（stdio JSON-RPC 2.0），位于 `plugins/` 目录下，可通过 `uv` 独立运行。

## 运行插件

每个插件均自包含。在仓库根目录执行：

```bash
uv run plugins/computer_use/src/main.py
uv run plugins/browser_use/src/main.py
uv run plugins/knowledge_base/src/main.py
uv run plugins/system_info/src/main.py
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
- `src/main.py` — MCP 服务器入口（从 stdin 读取 JSON-RPC，写入 stdout）
- `.mcp.json` — Claude Desktop / Claude Code 使用的 MCP 服务器配置
- `pyproject.toml` — 依赖声明（computer_use 要求 Python ≥ 3.14）
- `skills/<插件名>/SKILL.md` — 随插件下发给 Agent 的使用决策指南

`computer_use` 和 `knowledge_base` 手动实现 MCP 协议（裸 `sys.stdin` 循环）；`browser_use` 使用 `mcp` SDK 的 `FastMCP`。

---

### computer_use — 桌面自动化插件

最复杂的插件，内部模块结构如下：

| 模块 | 职责 |
|------|------|
| `main.py` | MCP 服务器 + 动作路由 + 智能路由提示注入 |
| `schema.py` | `TOOL_SCHEMA` — 单一 `computer` 工具的定义 |
| `utils.py` | 跨平台共享工具：键盘（pynput）、鼠标、剪贴板注入、无障碍访问（osascript/JXA）、语言环境检测、截图 GC |
| `config.json` | `allowed_apps` / `blocked_apps` 安全拦截器 |
| `handlers/` | 按动作类型分文件：`screen`、`mouse`、`keyboard`、`interaction`、`apps` |
| `adapters/base.py` | `BaseAdapter` — 通用三策略搜索结果选择器（无障碍 A/B → 键盘 C） |
| `adapters/chat/wechat.py` | `WeChatAdapter` — 覆盖微信/QQ 的结果选择：OCR 优先（A）、多窗口无障碍（B）、键盘兜底（C） |
| `adapters/registry.py` | Bundle ID → 适配器类映射；新增适配器在此注册 |
| `profiles/*.json` | 每应用配置：快捷键、本地化标签、别名、Bundle ID |
| `profiles_loader.py` | 启动时加载并索引所有配置；解析语言相关字段（`zh`/`en`） |

**双层 API：**
- **高层：** `send_message_to` — 单次调用即可完成打开应用、搜索联系人、发送消息的全流程。需要在 `profiles/` 中存在对应配置文件。
- **低层：** 其他所有动作（`open_app`、`screenshot`、`get_screen_state`、`get_ui_tree`、`click_*`、`type`、`key`、鼠标动作）。适用于任意应用。

**新增聊天应用：** 参照 `wechat.json` 在 `src/profiles/` 中创建 JSON 文件，无需改代码。若该应用的搜索下拉框使用非标准 UI（如独立 NSWindow），则需继承 `BaseAdapter` 并覆盖相关方法。

**应用黑白名单：** 编辑 `src/config.json`。`"allowed_apps": ["*"]` 表示放行所有应用，`blocked_apps` 中的应用始终被拦截。

**状态文件：** `get_screen_state` 将元素坐标写入 `$TMPDIR/computer_use_state.json`，供后续 `click_element_by_id` 使用。执行 `open_app` 和 `send_message_to` 时该文件会被自动清除。

**macOS 键盘路由：** `send_message_to` 通过 `osascript tell process X to keystroke` 发送按键，无需目标应用处于最前台。低层 `key`/`type` 动作使用 pynput，要求目标应用处于最前台。

---

### browser_use — 浏览器自动化插件

使用 `FastMCP` + Playwright。启动时尝试通过 CDP 连接已运行的 Chrome 或 Edge（读取 `DevToolsActivePort`），失败则启动新的 headless=False Chromium 实例。暴露的工具：`navigate`、`get_interactive_dom`、`action_by_id`、`scroll_page`、`go_back`、`close_tab`、`get_page_content`、`get_current_state`。

---

### knowledge_base — 本地文件 RAG 插件

零外部依赖。通过 `POLARIS_KB_ALLOWED_DIR` 环境变量限制文件访问路径（不设则不限制）。暴露 `list_files` 和 `read_content` 两个工具。

---

### system_info — 系统环境信息插件

暴露 `check_app_installed`。在 macOS 搜索 `/Applications`，在 Windows 搜索 `Program Files`，在 Linux 搜索 `PATH` 和 `.desktop` 文件。
