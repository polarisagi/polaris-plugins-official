# Polaris 电脑操控（Computer Use）MCP

🌎 [English](README.md) | 🇨🇳 [中文](README_zh.md)

[Polaris](https://polarisagi.online/) 官方的 Model Context Protocol（MCP）服务器插件，提供先进、安全、跨平台的桌面自动化能力。

## 核心特性

- **全面的界面操控**：通过 `pynput` 跨平台支持鼠标（移动、点击、双击、滚动、拖拽）与键盘交互。
- **智能屏幕解析**：多模态截图生成（`mss`）、针对特定应用窗口的裁剪，以及无障碍 UI 树提取（UI Automation / pyatspi / macOS AX）。
- **应用与焦点管理**：智能启动应用、枚举进程，并在交互前稳健地锁定焦点，确保输入发送到正确的活动窗口。
- **桌面环境处理**：在 macOS、Windows 和 Linux 上原生映射操作系统级的「显示桌面」。
- **安全与防护**：内置 `config.json` 应用黑名单/白名单拦截器，严格阻止对敏感软件（如密码管理器）的未授权访问。
- **宏适配器**：感知区域设置的专项自动化处理器，用于绕开复杂 GUI 布局的限制（如聊天客户端交互）。

## 架构

本插件使用纯 **Python** 编写，强调高内聚、低耦合。它先把 MCP 请求交给集中式安全拦截器，再分发给专门的处理器（`mouse.py`、`keyboard.py`、`screen.py`、`apps.py`）。 

## 在 Polaris 中使用

用以下 MCP 服务器配置来设置你的 AI 智能体：

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

### 应用安全配置
要限制 AI 访问敏感应用，请修改 `src/config.json`：
```json
{
  "allowed_apps": ["*"],
  "blocked_apps": ["1Password", "Keychain Access", "Bitwarden"]
}
```

## 要求
- Python ≥ 3.14
- `uv`（Astral 出品的 Python 包管理器）

**可选依赖（用于 UI 树解析）：**
- Windows：`pywinauto`（在 Windows 上通过 uv 自动安装）
- Linux：`sudo apt install python3-pyatspi`
