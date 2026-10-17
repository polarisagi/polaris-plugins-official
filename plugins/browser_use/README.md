# Polaris Browser Use MCP (v2.1.0)

> 完整文档：[docs/browser-use.md](../../docs/browser-use.md)

Polaris 官方通用浏览器自动化插件（打开、正文读取、快照、交互与浏览器连接）。
复用你日常已登录的 Chrome 浏览器会话，支持现代化省 token DOM 快照交互。

> 已知社交平台（知乎 / X / 微博 / 小红书等）的搜索、热榜、动态读取与发帖，请使用 **polaris-social** 插件的 `social_*` 工具；本插件不含任何平台知识、站点配方或限速。

---

## 核心特性

- **三种后端架构**：
  1. **Extension 模式 (推荐)**：配合 Polaris Browser Bridge 扩展（MV3），免弹窗，支持全自动无人值守定时采集。
  2. **CDP Toggle 模式**：通过 Chrome 155+ 的 `chrome://inspect` 远程调试开关即时连接，直接复用用户已登录平台。
  3. **Managed 模式**：使用系统 Chrome 启动专用 profile（`~/.config/polaris-plugins/browser/profiles/`），支持端点复用与独立运行。
- **Chrome 136+ 兼容背景**：自 Chrome 136 起，Google 禁用了默认用户目录的 `--remote-debugging-port` 命令行参数。本插件创新性地采用 `DevToolsActivePort` 动态发现与扩展桥接技术，实现零配置安全附着。
- **严格隐私隔离**：Polaris **只在自己创建的独立窗口内**操作，严禁读取或干扰用户的其他日常标签页。
- **省 Token 设计**：
  - `browser_read`：文章智能提取、精简 Markdown、纯文本与超链列表，字符级透明分页。
  - `browser_snapshot`：参数化精炼语义编码（`e12 button "登录"`），拒绝 raw HTML 倾倒。

---

## 安装扩展（推荐，一次性，支持免弹窗无人值守）

为了彻底解决日常 Chrome 每次连接都需要用户在弹窗中点击「允许」的问题，推荐安装官方配套的轻量级 MV3 扩展 **Polaris Browser Bridge**（纯 JS，无任何外部构建依赖与敏感权限）：

1. **一键设置**：扩展与自动配对由配套插件 **polaris-browser-bridge** 提供（本插件已在清单中依赖它）。对 Polaris 说「设置浏览器扩展」或调用 `bridge_setup`，它会准备扩展目录 `~/.config/polaris-plugins/browser/extension/` 并注册 Chrome 自动配对宿主。
2. **加载扩展并自动配对**：调用 `bridge_open_chrome_extensions`（macOS）打开 `chrome://extensions`，开启「开发者模式」→「加载已解压的扩展程序」，选择上述目录。扩展会经 Native Messaging 自动获取令牌，**无需复制粘贴令牌**。详见 [browser_bridge/README.md](../browser_bridge/README.md)。
3. **验证生效**：
   - 再次调用 `browser_status`，`backend` 将显示为 `extension`。
   - **安全提示**：被附着的标签页顶部会显示 Chrome 官方强制安全横幅「Polaris Browser Bridge 已开始调试此浏览器」，空闲 10 分钟后自动释放并消失；所有操作均在独立窗口完成，不触碰任何用户已有标签页。

---

## 日常 Chrome 开关开启步骤 (CDP Toggle 备用模式)

1. 打开平时使用的日常 Chrome 浏览器；
2. 在地址栏输入并回车：`chrome://inspect`；
3. 确保页面顶部的 **「Discover network targets」** 处于开启状态；
4. 当首次被 Polaris 附着时，Chrome 顶部会出现「允许远程调试」提示，点击 **「允许」** 即可。

> **提示**：如果希望定时任务全自动无人值守执行且不再弹出提示，强烈推荐安装上述 Polaris Browser Bridge 扩展。

---

## 运行环境与安装建议

- **本地桌面环境 (macOS / Windows / Linux)**：推荐安装并日常使用，能够最大化发挥复用已登录社交平台、获取个性化信息的能力。
- **云端 VPS / 无头服务器环境**：**不建议安装本插件**。无头服务器请直接使用内核内置的 HTTP 数据面工具（`feed_fetch`、`web_fetch`、`web_search`），无需任何浏览器进程与图形界面依赖。

---

## 运行时配置目录与环境变量

- **配置根目录**：
  - macOS / Linux：`~/.config/polaris-plugins/browser/`
  - Windows：`%APPDATA%\polaris-plugins\browser\`
- **主要环境变量**：
  - `POLARIS_BROWSER_BACKEND`：`auto`（默认）| `extension` | `cdp` | `managed`
  - `POLARIS_BROWSER_DRIVER`：`patchright`（默认）| `playwright`
  - `POLARIS_BROWSER_PROFILE`：managed 模式下的配置目录名称（默认 `default`）
  - `POLARIS_BROWSER_HEADLESS`：是否无头运行（默认 `0`）
  - `POLARIS_BROWSER_IDLE_RELEASE_MIN`：空闲释放分钟数（cdp 默认 `0` 不释放；extension 默认 `10`）

---

## 暴露工具一览

| 工具 | 类型 | 说明 |
|---|---|---|
| `browser_open` | 交互 | 打开 URL，支持创建新专属标签或复用工作页 |
| `browser_read` | 交互 | 省 token 多模式（article/markdown/text/links）阅读与分页 |
| `browser_snapshot`| 交互 | 提取当前视口或全页可交互元素打标（e<N>） |
| `browser_act` | 交互 | 对快照元素执行精准点击、输入、按键或回退 |
| `browser_scroll` | 交互 | 平滑滚动页面并返回位置 |
| `browser_extract` | 交互 | 基于 CSS 选择器批量结构化提取列表 |
| `browser_tabs` | 交互 | 专属标签页列表、切换与关闭 |
| `browser_status` | 状态 | 查看后端类型、连接健康度与已登录站点缓存 |

> `POLARIS_BROWSER_CDP_URL`：显式指定 CDP 端点（如无权读取 Chrome 数据目录中的 `DevToolsActivePort` 时）；未设置且端口文件不可读时，请改用 Polaris Browser Bridge 扩展。
