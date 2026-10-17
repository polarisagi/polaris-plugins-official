---
name: browser_bridge
description: "Setup guide for the Polaris Browser Bridge Chrome extension: one-click setup, automatic pairing, status and token rotation."
version: "1.0.0"
tags:
  - browser-bridge
  - chrome-extension
  - setup
exec_mode: ambient
risk_level: low
sandbox: L2
capability: read-write
---

# Browser Bridge 设置指南

本插件负责 Polaris Browser Bridge 浏览器扩展的**安装与配对**。浏览器的实际读写由 `polaris-browser-use` / `polaris-social` 插件完成，它们依赖本插件。

## 何时使用

- 用户说「设置浏览器扩展」「连接我的 Chrome」「扩展没连上」；
- `browser_*` / `social_*` 工具返回 `attach_failed`、提示未检测到扩展连接。

## 标准流程

1. 调用 `bridge_status` 看现状（令牌、自动配对宿主、扩展目录、是否已连接）。
2. 未就绪就调用 `bridge_setup`：生成令牌、把扩展同步到稳定目录、注册 Chrome 自动配对宿主。可重复执行（插件升级后再跑一次即可更新扩展）。
3. 调用 `bridge_open_chrome_extensions`（macOS）打开 `chrome://extensions` 并在 Finder 中定位扩展目录。
4. 请用户：开启「开发者模式」→「加载已解压的扩展程序」（或把文件夹拖入页面）→ 选择 `bridge_setup` 返回的扩展目录。
5. 扩展加载后会通过 Native Messaging 自动取得令牌并连接；用 `bridge_status` 确认 `connection.connected` 为 true（最多等约 1 分钟，且需要有插件进程正在使用浏览器）。

## 铁律

- **绝不向用户或对话输出令牌明文**；本插件的工具也不会返回它。
- 令牌泄露或怀疑被盗用时调用 `bridge_rotate_token`；自动配对的扩展会自行取新令牌。
- 扩展目录路径固定（`~/.config/polaris-plugins/browser/extension/`），升级插件后路径不变，**不要**让用户重新选择别的目录。
- 自动配对依赖 Chrome 的 Native Messaging，Windows 的注册表方式未经真机验证；失败时可让用户在扩展设置页手动粘贴令牌（令牌文件在 `~/.config/polaris-plugins/browser/bridge_token`，由用户自己查看，不要代为读取并回显）。
