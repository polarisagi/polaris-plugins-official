# Polaris Plugins Official

🌎 [English](README.md) | 🇨🇳 [中文](README_zh.md)

[![Website](https://img.shields.io/badge/官网-polarisagi.online-brightgreen.svg)](https://polarisagi.online/)
[![MCP](https://img.shields.io/badge/Anthropic-MCP-blue.svg)](https://modelcontextprotocol.io)
[![Codex Plugin](https://img.shields.io/badge/OpenAI-Codex_Plugin-black.svg)](https://developers.openai.com/codex/plugins)

**Polaris Plugins Official** 是 [Polaris AI Agent](https://github.com/polarisagi/polaris) 的官方扩展库，同时完全兼容以下行业标准：

- **Anthropic MCP**（Model Context Protocol）—— stdio JSON-RPC 2.0，协议版本 `2024-11-05`
- **OpenAI Codex Plugin**（`.polaris-plugin/plugin.json` + `.mcp.json`）—— 当前现行标准

> **注**：旧版 `ai-plugin.json`（ChatGPT Plugin Store 格式）已于 2024 年 3 月废弃，本项目不再使用。

---

## 插件列表

### 1. [Computer Use (Python)](plugins/computer_use)

**功能**：屏幕截图、鼠标移动/点击/拖拽、键盘输入  
**底层驱动**：`mss`、`pynput`、`pywinauto`  
**亮点**：
- **原生跨平台**：纯 Python 编写，原生调用操作系统 API，全架构兼容（macOS / Windows / Linux）。
- **高鲁棒性与系统洁癖**：内置焦点锁定防劫持（Focus Hijack）机制、状态缓存 TTL 时效控制，以及每次调用前的截图磁盘垃圾自动回收（GC）。
- **安全沙盒**：内置 `config.json` 应用黑白名单拦截器，严格阻断对密码管理器等敏感软件的越权访问。
- **高级宏指令适配器**：针对复杂 GUI 设计的专项操作宏（如微信剪贴板高速防串键输入、智能 UI 截图漂移纠正重置）。

### 2. [Browser Use (Python)](plugins/browser_use)

**能力**：导航网页、点击元素、填写表单、截图  
**底层驱动**：Python 及 `uv`  
**特点**：纯 Python 自动化控制浏览器

### 3. [Knowledge Base (Python)](plugins/knowledge_base)

**功能**：列出目录内容、读取本地文件（用于 RAG 等）  
**底层驱动**：Python 原生 `os` 和 `pathlib` 模块  
**亮点**：纯 Python 编写，零外部依赖，支持 `POLARIS_KB_ALLOWED_DIR` 环境变量进行路径沙盒隔离白名单

---

## 安装方式

### 第一步：环境准备

请确保你的系统上已经安装了 **Python 3.10+** 和 **uv** (Astral 出品的极速 Python 包管理器)。

### 第二步：配置你的 Agent

#### Claude Code / Claude Desktop

在 `~/.claude.json` 中添加：

```json
{
  "mcpServers": {
    "polaris-computer-use": {
      "command": "uv",
      "args": ["run", "/absolute/path/to/polaris-plugins-official/plugins/computer_use/src/main.py"]
    },
    "polaris-browser-use": {
      "command": "uv",
      "args": ["run", "/absolute/path/to/polaris-plugins-official/plugins/browser_use/src/main.py"]
    },
    "polaris-knowledge-base": {
      "command": "uv",
      "args": ["run", "/absolute/path/to/polaris-plugins-official/plugins/knowledge_base/src/main.py"],
      "env": { "POLARIS_KB_ALLOWED_DIR": "/your/allowed/dir" }
    }
  }
}
```

#### OpenAI Codex（Plugin 市场安装）

```bash
codex plugin marketplace add polarisagi/polaris-plugins-official --sparse .agents/plugins
```

然后在 Codex App 中从 **Polaris Official Plugins** 市场浏览并安装。

#### Polaris AI Agent（自动）

Polaris 的 `pkg/extensions/marketplace/` 模块会自动发现并安装本仓库的插件，无需手动配置。了解更多请访问 [polarisagi.online](https://polarisagi.online/)。

---

## 项目结构

```
plugins/
  computer_use/
    .polaris-plugin/plugin.json   # Codex 插件清单
    .mcp.json                    # MCP 配置（command: uv）
    src/main.py                  # Python MCP 服务端
    pyproject.toml
  browser_use/
    .polaris-plugin/plugin.json
    .mcp.json                    # MCP 配置（command: uv）
    src/main.py
    pyproject.toml
  knowledge_base/
    .polaris-plugin/plugin.json
    .mcp.json                    # MCP 配置（command: uv）
    src/main.py                  # Python MCP 服务端
    pyproject.toml

.agents/plugins/
  marketplace.json               # 本仓库的 Codex Marketplace 索引
```

## 开源协议

本项目采用 **GNU AGPLv3** 协议开源 — 详见 [LICENSE](LICENSE) 文件。对于希望闭源商用的企业用户，请联系作者获取商业授权（Dual License）。

## 赞助与支持

如果您觉得这个项目对您有帮助，欢迎赞助作者，支持个人独立开发者的持续创作！☕️

## 关于 Polaris

**Polaris** 是一个开源自托管 AI Agent 项目。

- **官方网站**：[polarisagi.online](https://polarisagi.online/)
- **GitHub**：[github.com/polarisagi/polaris](https://github.com/polarisagi/polaris)
- **联系邮箱**：polarisagi.online@gmail.com

## 作者

**mrlaoliai** — 独立 AI 开发者

关注我：
- **小红书**：mrlaoliai
- **抖音**：mrlaoliai
- **TikTok**：mrlaoliai
- **X (Twitter)**：mrlaoliai

联系邮箱：polarisagi.online@gmail.com
