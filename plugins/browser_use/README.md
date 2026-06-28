# Polaris Browser Use MCP

An official Model Context Protocol (MCP) server plugin for [Polaris](https://polarisagi.online/), providing browser automation via **DOM extraction** and precise element interaction — no screenshot coordinates required.

## Key Features

- **DOM-Based Automation**: Extracts all interactive elements (links, buttons, inputs) and assigns unique `polaris-id` attributes, eliminating coordinate-guessing hallucination.
- **CDP Connection**: Connects to an already-running Chrome or Edge browser via Chrome DevTools Protocol (CDP) — no login required. Falls back to launching a new headless=False Chromium instance.
- **Shadow DOM Support**: Traverses shadow roots for modern web components.
- **Tab Management**: Open, read, and close browser tabs programmatically.

## Architecture

Built with **Python**, [FastMCP](https://github.com/jlowin/fastmcp), and **Playwright**. The server connects to the browser once at startup and maintains a persistent page session across all tool calls.

## Usage with Polaris

Configure your AI agent with the following MCP server setting:

```json
{
  "mcpServers": {
    "polaris-browser-use": {
      "command": "uv",
      "args": ["run", "/path/to/polaris-plugins-official/plugins/browser_use/src/main.py"]
    }
  }
}
```

## Exposed Tools

| Tool | Description |
|------|-------------|
| `navigate` | Navigate to a URL |
| `get_interactive_dom` | Extract all interactive elements with unique `polaris-id` |
| `action_by_id` | Click, fill, or hover an element by its `polaris-id` |
| `scroll_page` | Scroll up or down by one viewport |
| `go_back` | Navigate back in browser history |
| `close_tab` | Close current tab and switch to previous |
| `get_page_content` | Get visible text content of the page |
| `get_current_state` | Get current URL and page title |

## Requirements

- Python 3.10+
- `uv` (Astral's Python package manager)
- Chrome or Edge browser (for CDP connection), **or** Playwright's bundled Chromium

**Install Playwright browsers (first-time setup):**
```bash
cd plugins/browser_use
uv run playwright install chromium
```
