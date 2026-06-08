# Polaris Social Poster Plugin

A standard MCP plugin for Polaris AGI that provides multi-platform social media auto-posting capabilities.

## Supported Platforms
- Twitter (X)
- Weibo
- Xiaohongshu (RED)
- Douyin
- WeChat Official Accounts

## Features
- **Adapter Pattern**: Each platform has a dedicated adapter under `src/adapters/` for tailored browser automation.
- **Content Formatting**: Automatically chunks and formats content based on platform character limits and visual requirements.
- **Browser Automation**: Simulates human behavior to post content safely using browser automation.

## Usage
This plugin exposes the `auto_post` tool to the Polaris agent.

```json
{
  "name": "auto_post",
  "arguments": {
    "platform": "twitter",
    "content": "Hello World!",
    "image_paths": ["/path/to/image.jpg"]
  }
}
```
