# browser_use：通用浏览器插件（v2.1.0）

本页说明 `browser_use` 的三个后端、扩展安装与配对、环境变量、8 个工具的参数与返回值、隔离模型和典型调用流程。

结论先行：**日常使用装一次 Polaris Browser Bridge 扩展（`extension` 后端），免弹窗、可无人值守；没装扩展时才退回 `cdp` 开关或 `managed` 专用 profile。** 本插件不含任何站点知识、配方或限速，已知社交平台请用 [social](social.md)。

- MCP 服务器名：`polaris-browser-use`（FastMCP + Patchright，Python ≥ 3.14）
- 入口：`cd plugins/browser_use && uv run python -m src.main`
- 源码：`plugins/browser_use/src/{main,tools_browser,browser_hub,bridge_relay,bridge_const,cfg,extract,snapshot_js}.py`、`plugins/browser_use/extension/*`

## 1. 三后端对比

| 维度 | `extension`（推荐） | `cdp`（开关模式） | `managed`（托管 profile） |
|------|---------------------|-------------------|---------------------------|
| 是否弹窗 | 无弹窗；被附着标签顶部有 Chrome 强制的调试横幅 | 每条新连接都弹「允许」，等待上限 60 秒；无「始终允许」 | 无 |
| 可否无人值守 | 可（扩展在线时） | 不可：未连接时无人值守调用返回 `needs_user_approval`，不主动发起连接 | 可 |
| 登录态 | 复用日常 Chrome 的登录态（在其中新开独立窗口） | 复用日常 Chrome 的登录态 | 专用 profile，需在其中手动登录一次，之后持久 |
| 标签模型 | 单标签：`new_tab=true` 也复用当前工作标签 | 每次新开一个独立窗口 | 每次新开一个独立窗口 |
| 前提 | 加载扩展并粘贴配对令牌 | `chrome://inspect` 里开启开关，且进程有权读取 `DevToolsActivePort`（或设置 `POLARIS_BROWSER_CDP_URL`） | 本机有 Chrome / Edge；找不到时回落到驱动自带 Chromium（`fingerprint_risk` 变为 `high`） |
| 适用场景 | 日常与定时采集的首选 | 临时使用、已开着调试开关时 | VPS / 兜底 / 需要与日常浏览器隔离时 |
| `unattended_ok()` | `True` | `False` | `True` |

### 自动选择顺序（`POLARIS_BROWSER_BACKEND=auto`，默认）

1. 启动本进程的中继，**最多等 2 秒**看扩展是否握手成功 → 成功则用 `extension`（`reason=extension_handshake_ready`）。
2. 否则若能读到日常 Chrome / Edge 的 `DevToolsActivePort`（macOS：`~/Library/Application Support/Google/Chrome/` 或 `Microsoft Edge/`；Windows：`%LOCALAPPDATA%\Google\Chrome\User Data\`；Linux：`~/.config/google-chrome/`、`~/.config/microsoft-edge/`），或设置了 `POLARIS_BROWSER_CDP_URL` → `cdp`（`reason=cdp_devtools_port_active`）。
3. 否则 → `managed`（`reason=managed_profile_fallback`）。

两个容易踩的点（来自源码行为）：

- 扩展每 **1 分钟**才重新探测一次中继端口（`chrome.alarms`），所以插件刚启动的头 2 秒内扩展可能还没连上，`auto` 会悄悄落到 `cdp` / `managed`。要稳定使用扩展，请显式设 `POLARIS_BROWSER_BACKEND=extension`（此时最多等 30 秒）。
- `auto` 下读不到端口文件会**静默**落到 `managed`（一个没有登录态的新 profile）。用 `browser_status` 的 `backend` 与 `reason` 确认实际后端，见 [troubleshooting.md](troubleshooting.md)。

## 2. 安装 Polaris Browser Bridge 扩展并配对

扩展是纯 JS 的 MV3 扩展（权限：`debugger`、`tabs`、`storage`、`alarms`），随插件放在 `plugins/browser_use/extension/`，用“加载已解压的扩展程序”安装，一次性操作。

1. **取扩展目录与令牌**：先让 Polaris 调用 `browser_status`（会启动本进程的中继并生成令牌）。返回里的 `extension_dir` 是扩展目录的绝对路径，`bridge_token` 是配对令牌（同时保存在 `~/.config/polaris-plugins/browser/bridge_token`，权限 `0600`）。
2. **加载扩展**：Chrome 地址栏打开 `chrome://extensions` → 右上角开启「开发者模式」→「加载已解压的扩展程序」→ 选择 `extension_dir`。扩展 ID 由 manifest 里的固定公钥决定，应为 `ccdonkdehfibjcejkfjoicdklfdffjeh`（中继只接受这个来源）。
3. **配对**：点击工具栏上的 Polaris Browser Bridge 图标打开选项页，粘贴令牌并保存。选项页会显示当前连上的本地中继（端口与活动标签数）。
4. **验证**：再次调用 `browser_status`，`backend` 应为 `extension`，`connected` 为 `true`。若仍不是，等 1 分钟（扩展按分钟重连）或显式设置 `POLARIS_BROWSER_BACKEND=extension` 后重启插件。

说明与注意：

- 令牌错误时中继以 4401 关闭连接，扩展按分钟重试；令牌更换后需在选项页重新粘贴。
- `browser_status` 的返回值包含 `bridge_token` 明文，它会出现在对话上下文里。令牌只对本机回环的中继有效，但请不要把含令牌的对话记录外发。
- 被附着的标签页顶部会出现 Chrome 的调试横幅，这是浏览器强制的提示，无法关闭。
- 扩展只对**它自己创建**的标签发送 CDP 命令；对不属于本连接的标签直接返回 `Tab <id> is not owned by this connection`。
- 扩展与中继之间的端口是 `127.0.0.1:18790–18799` 中第一个空闲端口；`browser_use` 与 `social` 同时运行会各占一个。端口全部被占用时报 `attach_failed`，见 [troubleshooting.md](troubleshooting.md)。

## 3. `cdp` 开关模式的开启步骤

1. 打开日常 Chrome，地址栏输入 `chrome://inspect`。
2. 确认页面顶部「Discover network targets」处于开启状态。
3. 插件首次附着时，Chrome 会弹出远程调试授权提示，在 60 秒内点击「允许」。

版本说明：ADR-0114（F1）记载该开关在 Chrome 144+ 的行为，`browser_use` README 与源码注释写的是 Chrome 155+。以你本机 `chrome://inspect` 里是否有该开关为准。无人值守的定时任务不要依赖 `cdp`。

## 4. 环境变量全表

| 变量 | 取值 / 默认 | 作用 |
|------|-------------|------|
| `POLARIS_BROWSER_BACKEND` | `auto`（默认）\| `extension` \| `cdp` \| `managed` | 选择后端；`extension` 时等待扩展最多 30 秒（auto 为 2 秒） |
| `POLARIS_BROWSER_DRIVER` | `patchright`（默认）\| `playwright` | 底层驱动；patchright 导入失败时自动回退 playwright |
| `POLARIS_BROWSER_PROFILE` | 默认 `default` | `managed` 的 profile 目录名：`<配置根>/profiles/<名>/` |
| `POLARIS_BROWSER_HEADLESS` | 默认 `0`；`1` / `true` / `yes` 为真 | `managed` 是否加 `--headless=new` |
| `POLARIS_BROWSER_IDLE_RELEASE_MIN` | 整数分钟；未设时 `extension` 为 10，`cdp` / `managed` 为 0（不释放） | 空闲多久自动断开连接；仅接受纯数字，`0` 表示不释放 |
| `POLARIS_BROWSER_CDP_URL` | 默认空 | 显式指定 CDP 端点（如 `http://127.0.0.1:9222` 或 `ws://...`），设置后 `cdp` 不再读 `DevToolsActivePort` |
| `POLARIS_BROWSER_DEV` | 默认 `0`（`cfg.py` 中定义） | 开发者模式：配方加载器会额外加载以下划线开头的配方文件（如 `_example.toml`），见 [recipes.md](recipes.md) |
| `APPDATA`（Windows） | 系统变量 | 配置根在 Windows 为 `%APPDATA%\polaris-plugins\browser` |

配置根目录（`cfg.py`）：macOS / Linux 为 `~/.config/polaris-plugins/browser/`，Windows 为 `%APPDATA%\polaris-plugins\browser\`。其中会出现：

| 路径 | 内容 |
|------|------|
| `bridge_token` | 扩展配对令牌（`0600`） |
| `endpoint.json` | `managed` 后端记录的 Chrome 进程与调试地址，用于复用 |
| `profiles/<profile>/` | `managed` 的专用用户数据目录 |
| `recipes/` | 用户自定义 / 覆盖的站点配方（`social` 读取） |
| `ratelimit.db` | 跨进程限速数据库（`social` 使用） |

## 5. 工具参考

所有工具返回 JSON：成功 `{"ok": true, ...}`，失败 `{"ok": false, "error": {"code", "message", ...}}`。

| 工具 | 参数（默认值） | 成功返回要点 |
|------|----------------|--------------|
| `browser_open` | `url`（必须 `http://` 或 `https://`）、`new_tab=false` | `tab_id`、`url`、`title`；扩展后端 `new_tab=true` 时附 `note`（单标签，已复用工作标签）。导航超时 30 秒，随后最多再等 3 秒 networkidle |
| `browser_read` | `mode="article"`（`article` \| `markdown` \| `text` \| `links`）、`max_chars=6000`、`offset=0`、`selector=null` | `content`、`content_hash`（SHA-256 前 16 位）、`truncated`、`next_offset`、`url`、`title`。`article` 用 trafilatura 抽正文，失败降级为简化文本；`links` 最多 200 条并去重，格式 `- [文本](链接)` |
| `browser_snapshot` | `scope="viewport"`（或 `page`）、`max_items=80` | `snapshot`（每行 `e12 button "登录"`，末行 `共 N 个，已显示 M 个`）、`total`、`displayed`、`url`、`title`。给元素打 `data-polaris-ref="e<N>"` |
| `browser_act` | `ref`（`e<数字>`，1–5 位）、`action`（`click` \| `fill` \| `fill_and_enter` \| `hover` \| `select` \| `press` \| `back`）、`text=""` | `url_changed`、`url`、`title`。`fill*` / `select` 的值与 `press` 的按键名都放在 `text`；`back` 时 `ref` 仍是必填参数但被忽略；单次操作超时 10 秒，操作后固定等 0.5 秒 |
| `browser_scroll` | `direction="down"`（或 `up`）、`times=1`（限制在 1–10） | `scroll_y`、`at_bottom`；每次滚 600 像素 |
| `browser_extract` | `container`（CSS）、`fields`（`{字段名: "css" 或 "css@属性"}`）、`max_items=50` | `items`、`count`；以 `/`、`./`、`../` 开头的值会补全为绝对 URL；选择器非法返回 `invalid_args` |
| `browser_tabs` | `action="list"`（`list` \| `switch` \| `close`）、`tab_id=""` | `list`：`tabs[{tab_id,url,title}]`、`count`；`switch`：`active_tab`、`url`；`close`：`closed_tab`。`switch` / `close` 必须给 `tab_id` |
| `browser_status` | 无 | `backend`、`reason`、`connected`、`driver`、`profile`、`owned_tabs`、`fingerprint_risk`、`sites`、`extension_dir`、`bridge_token`、`bridge_token_path`、`pair_instruction` |

字段说明：

- `backend` 为 `extension` / `cdp` / `managed` / `none`（尚未选择）；`reason` 可能是 `explicit_*`、`extension_handshake_ready`、`cdp_devtools_port_active`、`managed_profile_fallback`、`init`。
- `fingerprint_risk`：`cdp` 与 `extension` 为 `low`；`managed` 找到系统 Chrome / Edge 时 `low`，回落到驱动自带 Chromium 时 `high`。
- `sites`：站点登录态缓存。该缓存由 `social` 的采集引擎写入、且按进程隔离，所以在 `browser_use` 自己的进程里通常是空列表。
- `readOnlyHint`：`browser_open`、`browser_read`、`browser_snapshot`、`browser_scroll`、`browser_extract`、`browser_status` 标注为只读；`browser_act`、`browser_tabs` 标注为非只读。注意 `browser_open` 实际会导航页面，只读标注是工具层面的约定。

### 错误码

| `error.code` | 触发条件 | 处理 |
|--------------|----------|------|
| `invalid_args` | URL 不是 http(s)、ref 格式不符、选择器非法、缺少 `tab_id`、`browser_act` 的底层调用失败（非超时） | 修正参数 |
| `attach_failed` | 浏览器附着失败：扩展未连接 / 未配对、端口文件不可读、托管 Chrome 10 秒内没起来、中继端口全被占、`cdp` 授权超时 | 见 [troubleshooting.md](troubleshooting.md) |
| `needs_user_approval` | 无人值守调用且当前后端是未连接的 `cdp` | 点一次「允许」，或改用扩展 |
| `stale_ref` | `e<N>` 在当前页面找不到（页面变化 / 跳转） | 重新 `browser_snapshot`，不要猜编号 |
| `no_page` | 找不到自建页或 `tab_id` | 先 `browser_open`，或 `browser_tabs` 看列表 |
| `timeout` | `browser_act` 单次操作超时；扩展 RPC 超时（20 秒） | 重试前先确认页面状态 |
| `internal_error` | `browser_status` 内部异常 | 查看日志 |

> `SKILL.md` 里提到的 `not_logged_in`、`blocked`、`rate_limited` 等由 `social` 的采集引擎产生，`browser_use` 自己不会返回。遇到验证码 / 403 / 429 应立即停止对该站点的请求，不要自动重试。

## 6. 隔离模型

| 项 | 行为 |
|----|------|
| 窗口 | `cdp` / `managed`：每次新建标签都用 `Target.createTarget(newWindow=true, background=true)` 开新窗口；`extension`：首次 `chrome.windows.create(focused=false)`，之后在同一窗口内 `tabs.create(active=false)` |
| 定位 | 新页初始 URL 为 `about:blank#polaris-<uuid>`，之后只按该 marker 在 `contexts[0].pages` 中找页，不对任何页面开 CDP 会话 |
| 可见范围 | `owned_pages()` 只返回 Hub 记录的自建页（扩展后端返回其 `contexts[0].pages`），工具不会枚举用户日常标签 |
| 凭证 | 不读 cookie 文件、不复制 profile 目录、不自动登录 |
| 并发 | 所有工具共用一把 `page_lock`，同一进程内串行操作 |
| 来源校验 | 中继绑定 `127.0.0.1`，校验 `Origin` 与令牌 |

## 7. 空闲释放

- `extension` 默认空闲 **10 分钟**后断开（未设置 `POLARIS_BROWSER_IDLE_RELEASE_MIN` 时），`cdp` / `managed` 默认不释放；设置该变量会覆盖默认值。
- 后台守护每 15 秒检查一次；到点后调用后端 `close()`，清空 Hub 中的自建页记录，下一次工具调用会重新连接。
- README 称释放后调试横幅消失；源码中中继在 Playwright 断开时只清理自己的连接对象，本文未做真机验证，横幅是否即时消失请以实际为准。

## 8. 典型调用流程

### 读一篇文章

```text
browser_status()                                   # 确认 backend=extension
browser_open(url="https://example.com/post/1")     # -> {ok, tab_id, url, title}
browser_read(mode="article", max_chars=6000)       # -> {content, truncated:true, next_offset:6000}
browser_read(mode="article", max_chars=6000, offset=6000)   # 按 next_offset 续读
```

### 填表并提交（需要交互时才快照）

```text
browser_open(url="https://example.com/search")
browser_snapshot(scope="viewport")                 # e1 link "首页" / e2 text_input "搜索" / e3 button "搜索"
browser_act(ref="e2", action="fill", text="polaris")
browser_act(ref="e3", action="click")              # -> {url_changed:true, url:..., title:...}
browser_read(mode="markdown")
```

### 批量抽取一个列表

```text
browser_open(url="https://example.com/list")
browser_extract(container="li.item", fields={"title": "h3", "url": "a@href"}, max_items=30)
```

省 token 的顺序是：**先 `browser_read`，需要交互再 `browser_snapshot`；快照默认只扫视口；动作后看 `url_changed` 再决定是否重新快照。**
