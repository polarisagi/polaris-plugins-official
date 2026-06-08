# Polaris Computer Use MCP

[![npm version](https://img.shields.io/npm/v/polaris-computer-mcp.svg)](https://www.npmjs.com/package/polaris-computer-mcp)

An official Model Context Protocol (MCP) server plugin for [Polaris](https://polarisagi.online/), providing advanced, secure, and cross-platform desktop automation capabilities.

## Key Features

- **Comprehensive UI Control**: Cross-platform support for mouse (move, click, double click, scroll, drag) and keyboard interactions via `pynput`.
- **Intelligent Screen Parsing**: Multi-modal screenshot generation (`mss`), targeted app window cropping, and accessibility UI tree extraction (UI Automation / pyatspi / macOS AX).
- **Application & Focus Management**: Smart app launching, process enumeration, and robust pre-interaction focus locking to ensure inputs are sent to the correct active window.
- **Desktop Environment Handling**: Native OS-level "Show Desktop" mapping across macOS, Windows, and Linux.
- **Security & Guardrails**: Built-in `config.json` application blacklist/whitelist interceptor, strictly preventing unauthorized access to sensitive software (e.g., Password Managers).
- **Macro Adapters**: Locale-aware, specialized automation handlers designed to bypass complex GUI layout limitations (e.g., Chat Client interactions).

## Architecture

This plugin is written in pure **Python** and prioritizes high cohesion and low coupling. It routes MCP requests through a centralized security interceptor before dispatching to specialized handlers (`mouse.py`, `keyboard.py`, `screen.py`, `apps.py`). 

## Usage with Polaris

Configure your AI agent with the following MCP server setting:

```json
{
  "mcpServers": {
    "polaris-computer-use": {
      "command": "python",
      "args": ["/path/to/polaris-plugins-official/plugins/computer_use/src/main.py"]
    }
  }
}
```

### Application Security Configuration
To restrict AI access to sensitive applications, modify `src/config.json`:
```json
{
  "allowed_apps": ["*"],
  "blocked_apps": ["1Password", "Keychain Access", "Bitwarden"]
}
```

## Requirements
- Python 3.10+
- `uv` (Astral's Python package manager)

**Optional Dependencies (for UI tree parsing):**
- Windows: `pywinauto` (Automatically installed via uv on Windows)
- Linux: `sudo apt install python3-pyatspi`
