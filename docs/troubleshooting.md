# 故障排查：症状 → 原因 → 处理

本页按“你看到了什么”列出常见问题，每行给出原因（来自源码行为）和处理办法。

结论先行：**先调 `browser_status`，看 `backend` 和 `reason` 是不是你以为的那个后端；绝大多数连接问题都出在后端没选对。** 遇到验证码 / 403 / 429 / `blocked` / `cooling_down`，唯一正确的处理是停手，不要重试、不要绕过。

## 1. 先做这三件事

1. `browser_status()`：看 `backend`（`extension` / `cdp` / `managed` / `none`）、`reason`、`connected`、`owned_tabs`。
2. `social_platforms()`（装了 `social` 时）：看每个平台的 `status`、`logged_in`、`rate.remaining_hour`、`rate.cooling_until` 与 `recipe_errors`。
3. 确认运行环境：Python ≥ 3.14、已安装 `uv`、在插件目录里运行 `uv run python -m src.main`。

## 2. 浏览器连接

| 症状 | 原因 | 处理 |
|------|------|------|
| `attach_failed`，消息含“无权读取 Chrome 数据目录中的 DevToolsActivePort”；或自己读该文件时报 `Operation not permitted` | macOS 上运行插件的终端 / 宿主进程没有权限读取 `~/Library/Application Support/Google/Chrome/` 下的 `DevToolsActivePort`。ADR-0114 的实测记录：非 Polaris 进程（如外部代理工具）可能无权读取，`cdp` 后端须由 Polaris 进程或你自己的终端运行 | ① 首选改用 Polaris Browser Bridge 扩展（不需要读该文件）；② 在 macOS 隐私设置里给运行该进程的应用授权（具体项目因系统版本而异）；③ 在你自己的终端里查看该文件，第一行是端口、第二行是 `/devtools/browser/<id>`，把 `ws://127.0.0.1:<端口>/devtools/browser/<id>` 设为 `POLARIS_BROWSER_CDP_URL`（Chrome 重启后会变）。注意：`chrome://inspect` 开关模式下 9222 端口不提供 HTTP 发现接口，源码也不再猜测端口 |
| `backend` 是 `managed`、`reason=managed_profile_fallback`，但你以为在用日常 Chrome | `auto` 模式下扩展没在 2 秒内握手、又读不到端口文件，于是静默落到了没有登录态的专用 profile | 装好扩展并显式设置 `POLARIS_BROWSER_BACKEND=extension`（此时最多等 30 秒）；或显式设为 `cdp` 以便得到明确错误 |
| 自己用 `--remote-debugging-port=9222` 启动日常 Chrome，端口不开 | Chrome 136+ 对**默认用户目录**忽略 `--remote-debugging-port`（ADR-0114 F1） | 这正是本仓库采用扩展桥接与独立 profile 的原因：改用扩展或 `chrome://inspect` 开关；托管后端用的是专用目录 `--user-data-dir`，不受影响 |
| `cdp`：Chrome 弹出「允许远程调试」；超过 60 秒没点 → `attach_failed` | 新版 Chrome 的 `chrome://inspect` 开关对**每条新连接**都弹窗，没有“始终允许” | 在 60 秒内点「允许」；每个插件进程只建一条长连接。需要无人值守请换扩展 |
| `needs_user_approval` | 无人值守的调用（`social_*` 读工具、管线）遇到尚未连接的 `cdp` 后端；插件有意不主动发起会弹窗的连接，避免半夜堆积弹窗 | 先手动触发一次连接并点「允许」，或安装扩展、改用 `managed` |
| 扩展没配对：`attach_failed`，消息“未检测到 Polaris Browser Bridge 扩展连接……” | 扩展没加载、令牌没粘贴或已过期、Chrome 没开、或扩展还没来得及重连（它每 1 分钟重新探测一次端口） | ① `chrome://extensions` 确认扩展已启用，ID 为 `ccdonkdehfibjcejkfjoicdklfdffjeh`；② 选项页重新粘贴 `browser_status` 返回的令牌（文件 `~/.config/polaris-plugins/browser/bridge_token`）；③ 选项页应能看到本地中继（端口 + 活动标签数），没有就等 1 分钟或重启插件进程 |
| 中继日志“拒绝非法扩展 Origin” | 加载的扩展 ID 不是预期值（例如换了 manifest 里的 `key`） | 使用仓库自带的 `extension/` 目录，不要改 manifest 的 `key` |
| `attach_failed`：“未能绑定 18790-18799 中任一空闲端口” | 10 个中继端口全被占用，通常是残留的插件进程 | `lsof -nP -iTCP:18790-18799 -sTCP:LISTEN` 找出占用者，结束多余的插件进程后重试 |
| 选项页里显示的客户端名都是 `browser_use` | `social` 带的是同一份中继代码，握手应答里固定写 `browser_use` | 只是显示名，不影响功能；用端口号区分两个插件 |
| 标签页顶部有“Polaris Browser Bridge 已开始调试此浏览器”横幅 | Chrome 对 `chrome.debugger` 附着的强制提示，无法关闭 | 正常现象；空闲释放后是否消失以实际为准 |
| `managed`：“启动托管 Chrome 并等待 DevToolsActivePort 超时（10s）” | 找不到可用的 Chrome / Edge，或同一个 profile 目录已被另一个 Chrome 占用 | 安装 Chrome；换 `POLARIS_BROWSER_PROFILE`；回落到驱动自带 Chromium 时需要先安装它（例如 `patchright install chromium`，`fingerprint_risk` 会是 `high`） |
| 扩展后端 `browser_open(new_tab=true)` 没有新标签 | 扩展后端是单标签模型，会复用当前工作标签（返回里有 `note`） | 预期行为；需要多标签请用 `cdp` / `managed` |
| `stale_ref` | `e<N>` 编号对应的元素已不在页面上（页面变了 / 跳转了） | 重新 `browser_snapshot`，不要猜编号 |
| `no_page` | 找不到自建页或 `tab_id` | 先 `browser_open`；用 `browser_tabs(action="list")` 看现有标签 |

## 3. 登录与风控（`social`）

| 症状 | 原因 | 处理 |
|------|------|------|
| `not_logged_in` | 配方 `login_check.logged_in_selector` 没在页面上找到（没登录，或站点改了 DOM） | 在**日常 Chrome**（extension / cdp）或 managed 的专用窗口里手动登录该平台。插件不会也不应该自动登录。若已登录仍报错，说明选择器过期，见 [recipes.md](recipes.md) |
| 登录后读到的数据为空 | 引擎把首次探测结果缓存在进程里；缓存为未登录时，后续调用不再报错，但抽取可能为空 | 登录后重启插件进程；用 `social_platforms` 看 `logged_in` |
| `rate_limited` | 超过每小时 / 每天上限，或排队等待要超过 60 秒 | 等待窗口滚动；不要循环重试；默认值见 [social.md](social.md) 第 3 节 |
| `cooling_down`（带 `until`） | 该平台刚命中过风控信号，读写都被拒绝 | 等到 `until`；期间不要换工具硬试 |
| `blocked` | 本次请求的状态码 / URL / 页面文案命中了配方的 `block_signals`，已自动进入冷却 | 立即停止并告知用户；检查账号是否需要人工验证 |
| `out_of_hours` | 当前本地时间不在该平台的 `active_hours` 内（知乎、微博 08:00–23:30，小红书 09:00–23:00） | 在活跃时间内再试，或（自担风险）调整你自己的用户配方 |
| `unsupported_action` | 该平台配方没有这个动作（X 没热榜；知乎 / 微博 / 小红书没 `social_feed`） | 换用别的工具，不要重试 |
| `unsupported_platform` / `recipe_error` | 没有该平台配方，或配方 TOML 出错（用户目录里损坏的同名文件会让内置配方一并失效） | `social_platforms` 看 `recipe_errors`；修正或删除用户目录里的 `~/.config/polaris-plugins/browser/recipes/<id>.toml` |
| 新增的用户配方 `social_search` 不认平台名 | 工具的 `platform` 参数是写死的枚举（zhihu / x / weibo / xiaohongshu） | 见 [recipes.md](recipes.md) 第 1、6 节 |
| `empty_content`（`social_read`） | 页面需要登录，或正文结构特殊抽不出来 | 先确认登录态；换用 `browser_open` + `browser_read(mode="markdown")` |
| 写工具返回 `{"ok": false, "error": ...}` 而不是 `✅` / `❌` | 被限速 / 熔断，**没有执行** | 按对应错误码处理；定时队列里的任务保持 pending |
| 写工具返回 `❌ Failed to post ...` | 适配器的页面自动化失败（UI 改版、未登录、媒体路径不对） | 确认已登录、媒体用本机绝对路径；平台 UI 改版需维护适配器 |

## 4. 启动与环境

| 症状 | 原因 | 处理 |
|------|------|------|
| `uv run src/main.py` 报相对导入错误 | 这些插件使用包内相对导入，必须以模块方式启动 | 在插件目录执行 `uv run python -m src.main`，或 `uv run --directory <插件目录> python -m src.main`（与各插件 `.mcp.json` 一致） |
| `uv` 找不到 | 未安装 uv | `brew install uv` 或 `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| uv 解析 / 创建环境失败，提示 Python 版本 | 插件要求 Python ≥ 3.14（`requires-python = ">=3.14"`） | 安装 3.14（例如 `uv python install 3.14`）后重试 |
| MCP 客户端里工具名对不上 | 升级后服务器名从 `polaris-social-poster` 变为 `polaris-social`，工具名前缀随之改变 | 更新引用旧前缀的管线 / 配置，见 [migration.md](migration.md) |
| 管线每次都 `skipped` | 去重后没有新条目，或上游工具失败被归一化为空数据 | 见 [pipelines.md](pipelines.md) 第 4 节 |
| `automation_save` 被拒：无头后台任务禁止创建 | 在后台 / 无头会话里调用了写类 `automation_*` | 在有人的交互会话里创建 |

## 5. Vault（`knowledge_base`）

| 症状 | 原因 | 处理 |
|------|------|------|
| `path_outside_vault` | 路径含 `..`、位于 Vault 之外或经符号链接逃逸 | 用相对 Vault 根的路径，或位于根目录内的绝对路径 |
| `path_forbidden` | 访问了 `.polaris/` 内部索引目录 | 不要直接碰索引 |
| `missing_url` / `invalid_url` | `raw` 文档没给 `url`，或不是 `http(s)://` 开头 | 补 `url`；摘要类用 `kind="digest"` |
| `empty_content` | `content` 和 `excerpt` 都为空 | 补正文 |
| `exists`（`kb_move`） | 目标目录里已有同名文件 | 先改名或换目录 |
| `kb_search` / `kb_list` 找不到你在 Obsidian 里手工新增的笔记 | 只有经 `kb_save` 写入的文档才有索引 | 用 `kb_read` 读取；内核 RAG 仍会同步该目录 |
| `fts5_unavailable` | 当前 Python 的 SQLite 没编译 FTS5 | 换用带 FTS5 的 Python 构建 |
| 改了 `POLARIS_VAULT_DIR` 后内核检索不到新内容 | 内核只同步 `knowledge.vault_dirs` 里列出的目录 | 把新目录加进内核配置 `[knowledge] vault_dirs`，见 [knowledge-base.md](knowledge-base.md) 第 8 节 |
| `list_files` / `read_content` 能读任意路径 | `POLARIS_KB_ALLOWED_DIR` 为空时不限制（插件默认 `.mcp.json` 就是空） | 设置该变量，或只用 `kb_*` |

## 6. 仍然解决不了

收集这些信息再反馈：`browser_status` 的输出（**抹掉其中的 `bridge_token`**）、`social_platforms` 的 `recipe_errors`、出错工具的 `error.code` 与 `message`、操作系统与 Chrome 版本、`uv --version`。
