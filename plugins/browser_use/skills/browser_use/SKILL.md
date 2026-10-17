---
name: browser_use
description: "Standard operating procedure for the generic browser MCP tool: open, read, snapshot and act on arbitrary web pages."
version: "2.1.0"
tags:
  - browser-use
  - automation
  - web
exec_mode: ambient
risk_level: medium
sandbox: L2
capability: read-write
---

# Browser Use 操作与决策规范 (v2.1.0)

本技能定义 Agent 调度浏览器能力时的核心决策流、token 控制法则、隐私隔离约定与风控错误恢复策略。

---

## 1. 工具决策顺序 (由轻到重)

在获取网络信息时，必须严格按以下顺序递进，杜绝盲目拉起浏览器：

```
1. 内核 HTTP 数据面 (feed_fetch / web_fetch / web_search)
   ↓ 能拿到结构化数据或 Markdown 时，绝对不用浏览器 (0 渲染开销、VPS 通用)
2. 已知社交平台 (知乎、X、微博、小红书等)
   ↓ 一律改用 polaris-social 插件的 social_search / social_hot / social_feed / social_read（0 token 接口拦截 + 读写共享限速），不要用本插件手动浏览这些站点
3. 纯阅读获取 (browser_open + browser_read)
   ↓ 未知网页或无配方页面，打开后优先使用 article 或 markdown 模式提取内容
4. 深度交互操作 (browser_snapshot + browser_act)
   ↓ 仅在必须点击按钮、输入表单、展开折叠内容等交互场景下，才调用快照与动作
```

---

## 2. 省 Token 铁律

浏览器快照与全文抓取极易消耗海量上下文 token，必须执行以下准则：

1. **先 read 再 snapshot**：仅当页面需要交互（点击、登录、筛选）时才生成快照；若只需获取页面信息，使用 `browser_read(mode="article")` 或 `browser_extract`。
2. **Snapshot 默认视口优先**：`browser_snapshot(scope="viewport")` 默认仅扫描当前视口，避免一次性吐出几百个 DOM 元素淹没上下文。
3. **长文必须分页**：`browser_read` 返回的 `truncated: true` 与 `next_offset` 指示长文未读完，按需分批拉取，切勿无节制请求超大 `max_chars`。
4. **禁止死循环 snapshot**：执行 `browser_act` 后观察 `url_changed` 与操作预期，未发生重大 DOM 变动时切勿无意义重复 snapshot。

---

## 3. 后端架构与错误码恢复指引

本插件支持多后端隔离运行，当工具返回 `ok: false` 时，按错误码进行标准恢复：

- **`attach_failed`**：
  - *原因*：浏览器附着失败。可能因日常 Chrome 尚未开启 `chrome://inspect` 远程调试开关、未安装扩展且缺少 DevToolsActivePort 权限，或扩展尚未完成配对。
  - *对用户话术*：未能连接到您的浏览器。建议对 Polaris 说「设置浏览器扩展」（调用 polaris-browser-bridge 插件的 `bridge_setup`）完成一键设置与自动配对，开启免弹窗全自动连接（无需用户复制令牌，也不要向用户回显任何令牌）；或在 Chrome 打开 `chrome://inspect` 确保远程调试开关已开启。
- **`needs_user_approval`**：
  - *原因*：使用日常 Chrome (CDP 开关) 时，Chrome 136+ 强制要求用户在弹窗中允许远程调试。
  - *对用户话术*：请在 Chrome 弹窗中点击一次「允许远程调试」，或安装 Polaris Browser Bridge 扩展实现免弹窗无人值守。
- **`not_logged_in`**：
  - *原因*：目标平台未登录，无法获取登录后数据。
  - *对用户话术*：目标站点尚未登录，请在您的日常 Chrome 浏览器中登录该账号后重试。
- **`stale_ref`**：
  - *原因*：页面结构已变化或发生跳转，原快照编号（如 e12）已失效。
  - *处理*：重新调用 `browser_snapshot` 获取最新元素编码，切勿胡乱猜测 ref 编号。
- **遇到验证码 / 访问受限 / 403 / 429**：
  - *处理*：**立即停止对该站点的所有请求，绝对禁止自动重试绕过**，向用户汇报。
- **`invalid_args`**：
  - *原因*：URL 格式非法、CSS 选择器错误或 ref 格式不符合 `e<数字>` 规范。

---

## 4. 隐私与隔离铁律

1. **只在专属窗口操作**：Polaris 建立的所有会话均在独立的自建窗口运行，所有工具仅作用于自建标签页。
2. **严禁越界窥探**：严禁调用非自有标签页，绝不读取用户的日常打开标签，不触碰全局 cookie 导出。

---

## 5. 与 polaris-social 的分工

本插件只提供**平台无关**的浏览器能力（打开、正文读取、快照、交互）与浏览器连接，不含任何站点知识、配方或限速。

- 已知社交平台的读取（搜索 / 热榜 / 用户动态 / 帖文正文）与写入（发帖 / 互动）全部在 `polaris-social` 插件，读写共享同一账号的限速与风控熔断。
- 对未知网页，才使用本插件的 `browser_open` + `browser_read`；遇到风控信号时遵守第 3 节「立即停止」铁律。
