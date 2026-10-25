# Polaris 系统信息（System Info）MCP

🌎 [English](README.md) | 🇨🇳 [中文](README_zh.md)

[Polaris](https://polarisagi.online/) 官方的 Model Context Protocol（MCP）服务器插件，提供跨平台的系统环境与上下文感知能力。

## 功能

- **环境检测**：即时检测操作系统版本、架构（Intel/ARM）、系统语言区域（语言）和时区。
- **硬件遥测**：查看 CPU 核心数与可用磁盘空间。
- **应用发现**：在标准路径下安全地检查指定应用（如「WeChat」「Slack」）是否已安装，无需递归扫描整个硬盘。

## 架构

本插件使用纯 **Python** 编写，只用到标准库模块（`platform`、`locale`、`shutil`、`os`），无需任何外部依赖（不需要 `pip install`）。 

跨平台逻辑原生支持 macOS、Windows 和 Linux。

## 在 Polaris 中使用

用以下 MCP 服务器配置来设置你的 AI 智能体：

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

## 要求
- Python ≥ 3.14。
