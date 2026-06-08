# Polaris System Info MCP

An official Model Context Protocol (MCP) server plugin for [Polaris](https://polarisagi.online/), providing cross-platform system environment and context awareness.

## Features

- **Context Detection**: Detect OS version, architecture (Intel/ARM), system locale (language), and timezone instantly.
- **Hardware Telemetry**: View CPU core count and available disk space.
- **Application Discovery**: Safely check if specific applications (e.g., "WeChat", "Slack") are installed on standard paths without recursively scanning the entire hard drive.

## Architecture

This plugin is written in pure **Python** and uses only standard library modules (`platform`, `locale`, `shutil`, `os`). It requires zero external dependencies (`pip install` is not required). 

Cross-platform logic natively supports macOS, Windows, and Linux.

## Usage with Polaris

Configure your AI agent with the following MCP server setting:

```json
{
  "mcpServers": {
    "polaris-systeminfo-mcp": {
      "command": "python",
      "args": ["/path/to/polaris-plugins-official/plugins/system_info/src/main.py"]
    }
  }
}
```

## Requirements
- Python 3.8 or newer.
