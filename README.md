# Polaris Plugins Official

🌎 [English](README.md) | 🇨🇳 [中文](README_zh.md)

[![Website](https://img.shields.io/badge/Website-polarisagi.online-brightgreen.svg)](https://polarisagi.online/)
[![MCP](https://img.shields.io/badge/Anthropic-MCP-blue.svg)](https://modelcontextprotocol.io)
[![Codex Plugin](https://img.shields.io/badge/OpenAI-Codex_Plugin-black.svg)](https://developers.openai.com/codex/plugins)

**Polaris Plugins Official** is the official extension library for [Polaris AI Agent](https://github.com/polarisagi/polaris), fully compatible with:

- **Anthropic MCP** (Model Context Protocol) — stdio JSON-RPC 2.0, protocol version `2024-11-05`
- **OpenAI Codex Plugin** (`.polaris-plugin/plugin.json` + `.mcp.json`) — current standard

> **Note**: The legacy `ai-plugin.json` format (ChatGPT Plugin Store) was deprecated in March 2024 and is not used here.

---

## Plugins

### 1. [Computer Use (Python)](plugins/computer_use)

**Capabilities**: Screenshot, mouse move/click/drag, keyboard input  
**Drivers**: `mss`, `pynput`, `pywinauto`  
**Highlights**: 
- **Native & Cross-Platform**: Pure Python, natively calls OS APIs (macOS / Windows / Linux).
- **Robustness & Hygiene**: Built-in state cache TTL, macro-level focus hijacking prevention, and automatic screenshot garbage collection to ensure zero disk leaks.
- **Security**: Strict app blacklisting/whitelisting interceptor (`config.json`).
- **Macro Adapters**: Specialized automation handlers to bypass complex GUI limitations (e.g., WeChat clipboard injection, smart UI OCR drift recovery).

### 2. [Browser Use (Python)](plugins/browser_use)

**Capabilities**: Navigate URLs, click elements, fill forms, capture screenshots  
**Powered by**: Python and `uv`  
**Highlights**: Automate browsers directly from Python

### 3. [Knowledge Base (Python)](plugins/knowledge_base)

**Capabilities**: List directory contents, read file content for RAG  
**Drivers**: Native Python `os` and `pathlib` modules  
**Highlights**: Pure Python, zero external dependencies; `POLARIS_KB_ALLOWED_DIR` env var for path sandboxing

---

## Installation

### Step 1: Prerequisites

Ensure you have **Python 3.10+** and **uv** (Astral's fast Python package manager) installed on your system.

### Step 2: Configure your agent

#### Claude Code / Claude Desktop

Add to `~/.claude.json`:

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

#### OpenAI Codex (plugin marketplace)

```bash
codex plugin marketplace add polarisagi/polaris-plugins-official --sparse .agents/plugins
```

Then browse and install from the **Polaris Official Plugins** marketplace in the Codex App.

#### Polaris AI Agent (automatic)

Polaris `pkg/extensions/marketplace/` auto-discovers and installs plugins from this repo. Learn more at [polarisagi.online](https://polarisagi.online/).

---

## Repository Structure

```
plugins/
  computer_use/
    .polaris-plugin/plugin.json   # Codex plugin manifest
    .mcp.json                    # MCP server config (command: uv)
    src/main.py                  # Python MCP server
    pyproject.toml
  browser_use/
    .polaris-plugin/plugin.json
    .mcp.json                    # MCP server config (command: uv)
    src/main.py
    pyproject.toml
  knowledge_base/
    .polaris-plugin/plugin.json
    .mcp.json                    # MCP server config (command: uv)
    src/main.py                  # Python MCP server
    pyproject.toml

.agents/plugins/
  marketplace.json               # Codex repo-level marketplace catalog
```

## License

This project is licensed under the **GNU AGPLv3 License** — see the [LICENSE](LICENSE) file for details. For commercial use without open sourcing your code, please contact the author for a commercial license.

## Support & Sponsorship

If this project helps you, consider sponsoring the author to support independent development! ☕️

## About Polaris

**Polaris** is an open-source self-hosted AI Agent project.

- **Official Website**: [polarisagi.online](https://polarisagi.online/)
- **GitHub**: [github.com/polarisagi/polaris](https://github.com/polarisagi/polaris)
- **Contact**: polarisagi.online@gmail.com

## Author

**mrlaoliai** — Independent AI Developer

Find me on:
- **Xiaohongshu (小红书)**: mrlaoliai
- **Douyin (抖音)**: mrlaoliai
- **TikTok**: mrlaoliai
- **X (Twitter)**: mrlaoliai

Contact: polarisagi.online@gmail.com
