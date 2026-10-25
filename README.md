# Polaris Plugins Official

🌎 [English](README.md) | 🇨🇳 [中文](README_zh.md)

[![Website](https://img.shields.io/badge/Website-polarisagi.online-brightgreen.svg)](https://polarisagi.online/)
[![MCP](https://img.shields.io/badge/Anthropic-MCP-blue.svg)](https://modelcontextprotocol.io)
[![Codex Plugin](https://img.shields.io/badge/OpenAI-Codex_Plugin-black.svg)](https://developers.openai.com/codex/plugins)

**Polaris Plugins Official** is the official extension library for [Polaris AI Agent](https://github.com/polarisagi/polaris), fully compatible with:

- **Anthropic MCP** (Model Context Protocol) — stdio JSON-RPC 2.0, protocol version `2024-11-05`
- **OpenAI Codex Plugin** (`.codex-plugin/plugin.json` + `.mcp.json`) — current standard. The Polaris kernel reads `.codex-plugin/`, `.claude-plugin/`, and the root `plugin.json` (ADR-0103).

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

### 2a. [Browser Bridge (Python)](plugins/browser_bridge)

**Version**: `v1.1.0`  
**Capabilities**: Sole source of the Polaris Browser Bridge Chrome extension; one-click setup (`bridge_setup`), Chrome Native Messaging auto-pairing (no token copy/paste), status and token rotation, with an MCP Apps setup card  
**Powered by**: Python, FastMCP and `uv`  
**Highlights**: `browser_use` and `social` depend on it; mutual HMAC handshake (the token never travels over the wire)

### 2. [Browser Use (Python)](plugins/browser_use)

**Version**: `v2.1.0`  
**Capabilities**: Multi-backend browser isolation (Polaris Bridge extension / CDP / managed profile), DOM snapshot, low-token reading and interaction — platform-agnostic  
**Powered by**: Python, Patchright and `uv`  
**Highlights**: Unattended extension bridge; for known social platforms use `polaris-social`

### 3. [Knowledge Vault (Python)](plugins/knowledge_base)

**Version**: `v2.0.0` (MCP server `polaris-knowledge-base`)  
**Capabilities**: Save collected results and digests as Markdown with YAML front matter (`kb_save`, de-duplicated by URL), plus `kb_list` / `kb_search` / `kb_read` / `kb_tag` / `kb_move`; legacy `list_files` / `read_content` kept  
**Highlights**: Default vault `~/Polaris/Vault` (`POLARIS_VAULT_DIR`), Obsidian-compatible, SQLite FTS5 search, strictly sandboxed writes

### 4. [Social (Python)](plugins/social)

**Version**: `v3.0.0` (formerly `social_poster`; MCP server `polaris-social`)  
**Capabilities**: Read (`social_search` / `social_hot` / `social_feed` / `social_read` / `social_platforms` / `social_selftest`) and write (post, interact, schedule) for Zhihu, X, Weibo, Xiaohongshu and more  
**Highlights**: Zero-token XHR-intercepting site recipes; reads and writes share one per-platform rate limit and block-signal cooldown

### 5. [System Info (Python)](plugins/system_info)

**Version**: `v1.0.0` (MCP server `polaris-systeminfo-mcp`)  
**Capabilities**: Reads the OS type and version, architecture, locale and timezone; `check_app_installed` checks whether a given application is installed (without scanning the entire filesystem)  
**Highlights**: Pure Python with no external dependencies; **not listed in the Polaris plugin marketplace** (it is not in `.agents/plugins/marketplace.json`) — configure it manually as described under Installation

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
      "args": ["run", "--directory", "/absolute/path/to/polaris-plugins-official/plugins/browser_use", "python", "-m", "src.main"]
    },
    "polaris-knowledge-base": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/polaris-plugins-official/plugins/knowledge_base", "python", "-m", "src.main"],
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
    .codex-plugin/plugin.json   # Codex plugin manifest
    .mcp.json                    # MCP server config (command: uv)
    src/main.py                  # Python MCP server
    pyproject.toml
  browser_bridge/
    .codex-plugin/plugin.json
    extension/                   # Chrome extension (single source)
    src/main.py
  browser_use/
    .codex-plugin/plugin.json
    .mcp.json                    # MCP server config (command: uv)
    src/main.py
    pyproject.toml
  social/
    .codex-plugin/plugin.json
    .mcp.json
    src/main.py
    recipes/
    pyproject.toml
  knowledge_base/
    .codex-plugin/plugin.json
    .mcp.json                    # MCP server config (command: uv)
    src/main.py                  # Python MCP server
    pyproject.toml
  system_info/
    .codex-plugin/plugin.json
    .mcp.json                    # MCP server config (command: uv)
    src/main.py                  # Python MCP server
    pyproject.toml

.agents/plugins/
  marketplace.json               # Codex repo-level marketplace catalog
```

## Documentation

Usage, architecture, recipes, pipelines and troubleshooting (in Chinese): [docs/README.md](docs/README.md)

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
