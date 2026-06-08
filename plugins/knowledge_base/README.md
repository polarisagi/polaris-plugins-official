# Polaris Knowledge Base MCP

[![npm version](https://img.shields.io/npm/v/polaris-knowledge-base.svg)](https://www.npmjs.com/package/polaris-knowledge-base)

An official Model Context Protocol (MCP) server plugin for [Polaris](https://polarisagi.online/), enabling agents to securely read local files and directories.

## Features

- **List Files**: Explore directory structures.
- **Read Content**: Read the textual contents of local files for RAG or context injection.
- **Sandboxed**: Restricts file reading strictly to a permitted directory via environment variables.

## Architecture

This plugin is written in pure **Python** with zero external dependencies. It uses `uv` for seamless execution and environment isolation.

## Usage with Polaris

Configure your AI agent with the following MCP server setting:

```json
{
  "mcpServers": {
    "polaris-knowledge-base": {
      "command": "uv",
      "args": ["run", "/path/to/polaris-plugins-official/plugins/knowledge_base/src/main.py"],
      "env": {
        "POLARIS_KB_ALLOWED_DIR": "/path/to/your/knowledge/base/folder"
      }
    }
  }
}
```

## Requirements
- Python 3.10+
- `uv` (Astral's Python package manager)
