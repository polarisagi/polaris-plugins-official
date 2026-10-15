# social：社交平台读写插件（v3.0.0）

本页说明 `social` 的读 / 写工具分层、`readOnlyHint` 标注、读写共享的限速与熔断（默认值已对照源码）、错误码、各平台能力现状，以及真机冒烟脚本 `live_smoke.py` 的用法。

结论先行：**读用 `social_*`，写用 `auto_post` 等原有工具；同一平台的读和写共用一把限速键，一边采集一边发帖不会叠加频率；4 个读配方全部是 beta，只有夹具测试，没有真机验证。**

- MCP 服务器名：`polaris-social`（原 `social_poster`，工具名前缀随之变化，见 [migration.md](migration.md)）
- 入口：`cd plugins/social && uv run python -m src.main`
- 源码：`plugins/social/src/{main,gate,ratelimit,tools_social,tools_harvest,scheduler,content_manager}.py`、`src/harvest/*.py`、`src/adapters/*.py`、`recipes/*.toml`

## 1. 工具分层

| 层 | 工具 | 标注 | 限速 |
|----|------|------|------|
| **读（配方）** | `social_platforms`、`social_search`、`social_hot`、`social_feed`、`social_read`、`social_selftest` | `readOnlyHint=True, openWorldHint=True` | 读工具内部直接 `acquire` |
| **读（旧适配器）** | `get_my_posts`、`get_comments`、`search_posts`、`read_post`、`get_trending_topics`、`get_user_profile`、`get_post_analytics`、`get_account_analytics`、`get_notifications`、`get_mentions` | `readOnlyHint=True, openWorldHint=True` | `@rate_limited_read`（与写同键） |
| **读（外部图库）** | `search_free_image`（Pexels，下载到系统临时目录） | `readOnlyHint=True, openWorldHint=True` | 不计入平台限速 |
| **纯本地** | `list_scheduled_posts`、`get_platform_skill`、`get_content_template`、`suggest_hashtags`、`split_text_into_thread`、`list_supported_platforms` | `readOnlyHint=True, openWorldHint=False` | 无 |
| **写** | `auto_post`、`post_story`、`post_thread`、`delete_post`、`edit_post`、`pin_post`、`save_draft`、`reply_comment`、`delete_comment`、`like_post`、`unlike_post`、`repost`、`quote_post`、`follow_user`、`unfollow_user`、`block_user`、`mute_user`、`send_dm` | `readOnlyHint=False, destructiveHint=True` | `@rate_limited_write` |
| **写（委托）** | `batch_post`、`post_video`、`run_scheduled_posts` | 同上 | 通过调用 `auto_post` / `post_thread` 间接受限 |
| **写（本地队列）** | `schedule_post`、`cancel_scheduled_post` | 同上 | 仅改本地队列文件，不占名额 |

要点：

- **只读标注就是内核判定“能否免审批进管线”的依据**：内核对 MCP 工具只看 `readOnlyHint`（ADR-0114 决策一）。读工具可以直接放进管线 `tool` 步骤；写工具必须声明 `approval:"hitl"`，由内核在运行期审批，见 [pipelines.md](pipelines.md)。
- 写工具有两种返回：正常执行返回字符串（成功以 `✅` 开头，失败以 `❌` 开头，不是错误码）；被限速或熔断时**不执行**并返回 `{"ok": false, "error": {...}}`。
- 调用写工具前必须先 `get_platform_skill(platform)` 读取该平台的内容规范（SKILL.md 的硬性要求）。
- 定时发布队列保存在 `~/.polaris_social_scheduler.json`，需要外部周期性调用 `run_scheduled_posts` 才会执行；被限速的任务保持 pending，下次再执行。

## 2. 读工具参考

`platform` 取值固定为 `zhihu` / `x` / `weibo` / `xiaohongshu`（对应 `recipes/*.toml`）。

| 工具 | 参数（默认值，范围） | 说明 |
|------|----------------------|------|
| `social_platforms()` | 无 | 平台清单：`platform`、`name`、`status`（beta / stable）、`origin`（builtin / user）、`actions`（含参数定义）、`logged_in`（本进程缓存）、`rate`（`min_interval_s`、`active_hours`、`remaining_hour`、`remaining_day`、`cooling_until`）；另有 `recipe_errors`、`write_only_platforms`、`rate_key_aliases`（`twitter→x`）、`default_rate_key`（`web`） |
| `social_search(platform, query, max_items=20)` | `query` 1–200 字符；`max_items` 1–100 | 关键词搜索，返回标准化条目 |
| `social_hot(platform, max_items=20)` | 同上 | 热榜；平台无 `hot` 动作返回 `unsupported_action` |
| `social_feed(platform, handle="", max_items=20)` | `handle` ≤100 字符，不带 `@` | 用户公开动态（动作名 `user_timeline`）；无该动作返回 `unsupported_action` |
| `social_read(url, max_chars=8000, offset=0)` | `url` 8–2048 字符；`max_chars` 200–50000 | 在自建页打开并抽取正文 Markdown，分页；按域名映射到平台限速 |
| `social_selftest(platform)` | 无 | 对该平台全部读动作各跑一次最小调用，报告字段填充率 |

### 标准化条目

`social_search` / `social_hot` / `social_feed` 成功时返回 `{"ok": true, "platform", "action", "items", "count"}`，每条 `items` 为：

| 字段 | 说明 |
|------|------|
| `id` | 字符串 ID |
| `url` | 绝对 URL（相对路径会按站点 `base_url` 补全；没有 URL 时回落为 `base_url`） |
| `title` / `author` | 已去 HTML 标签、合并空白的纯文本 |
| `published_at` | RFC 3339（UTC）；解析不了则保持原字符串，缺失为 `null` |
| `excerpt` | 纯文本，超过 500 字符截断为 497 + `...` |
| `metrics` | 字典，如 `{"likes": 1380}`；来自配方里的 `metrics.xxx` 字段 |
| `source` | 平台 id，如 `zhihu` |

`social_read` 成功返回：`platform`、`url`（最终 URL）、`title`、`author`、`published_at`、`content`、`content_hash`、`truncated`、`next_offset`。

`social_selftest` 返回 `{"ok", "platform", "status", "results": [{"action", "ok", "item_count", "field_fill_rate", "method_used", "error"}]}`。自测固定参数：`search` 用 `q="科技"`，`user_timeline` 用 `handle="OpenAI"`；每个动作都会真实访问站点、占用限速名额。代码只**报告**填充率（统计 `id` / `url` / `title` / `author` / `published_at` / `excerpt` / `metrics`），不设通过阈值；ADR-0114 的重评估触发条件是“任一平台字段完整率连续 2 周低于 60%”。

## 3. 共享限速与熔断

### 键与映射

- 限速键就是**平台 id**。写工具里的 `twitter` 与读工具里的 `x` 是同一把键（`PLATFORM_ALIASES`）。
- `social_read` 按 URL 域名映射：`zhihu.com`→`zhihu`；`x.com` / `twitter.com`→`x`；`weibo.com` / `weibo.cn`→`weibo`；`xiaohongshu.com` / `xhslink.com`→`xiaohongshu`；`instagram.com`、`facebook.com`、`douyin.com`、`mp.weixin.qq.com`（→`wechat`）、`tiktok.com`、`linkedin.com`、`threads.net` / `threads.com` 各归其平台；其余域名用键 `web`。
- 有配方的平台用配方的 `[limits]`；没有配方的平台（instagram、facebook、douyin、wechat、tiktok、linkedin、threads）和未知域名用下面的保守默认值。

### 默认值（`gate.DEFAULT_LIMITS`）与各配方值

| 平台 / 键 | 最小间隔 | 抖动 | 每小时 | 每天 | 活跃时间 | 风控冷却 |
|-----------|---------:|------|-------:|-----:|----------|---------:|
| **无配方默认**（含键 `web`） | 10 秒 | 0.5–1.5 秒 | 20 | 60 | 全天 | 6 小时 |
| `zhihu` | 4 秒 | 1.0–3.5 秒 | 60 | 300 | 08:00–23:30 | 6 小时 |
| `x`（= 写工具 `twitter`） | 5 秒 | 1.0–3.0 秒 | 50 | 250 | 全天 | 6 小时 |
| `weibo` | 5 秒 | 1.0–3.0 秒 | 50 | 250 | 08:00–23:30 | 6 小时 |
| `xiaohongshu` | 8 秒 | 2.0–4.0 秒 | 30 | 120 | 09:00–23:00 | 12 小时 |

> 模型 `Limits` 自身的缺省值（配方未写某字段时）是 4 秒 / 抖动 0.5–1.5 / 60 每小时 / 300 每天 / `08:00-23:30` / 冷却 6 小时；它与上表的“无配方默认”是两套不同的值。

### `acquire` 的判定顺序

1. **活跃时间**：不在本地时间的 `active_hours` 内 → `out_of_hours`（支持跨午夜，区间两端含；`00:00-24:00` 等同全天；格式写错时放行）。
2. **冷却**：站点处于风控冷却 → `cooling_down`，返回 `until`（时间戳）。
3. **每小时上限**：最近 3600 秒内的请求数 ≥ `max_per_hour` → `rate_limited`。
4. **每天上限**：最近 86400 秒内的请求数 ≥ `max_per_day` → `rate_limited`。
5. **最小间隔 + 抖动**：计划时间 = max(现在, 上次请求时间 + `min_interval_s` + 随机抖动)；若需等待超过 **60 秒** → `rate_limited`；否则登记计划时间并 `sleep` 到点再返回。

实现要点：数据库是 `~/.config/polaris-plugins/browser/ratelimit.db`（SQLite WAL，`BEGIN IMMEDIATE`），所以多个插件进程之间串行并按序排队；窗口是滚动窗口，不是自然日；请求一经登记即计入，即使随后的导航失败；2 天前的记录会被清理。

### 熔断

- 引擎在每次 `goto` 之后检查配方的 `[block_signals]`：HTTP 状态码、当前 URL 子串、页面文本子串，任一命中就写入冷却（时长为该配方的 `cooldown_on_block_h`）并返回 `blocked`。
- 冷却期内**读和写都被拒绝**（`cooling_down`）。看到 `blocked` / `cooling_down` 应停止对该平台的请求并告知用户，**不要尝试绕过**。
- 取页失败（如 `needs_user_approval`）发生在占用名额之前，不会消耗限速配额。

## 4. 错误码

统一格式 `{"ok": false, "error": {"code", "message", ...}}`。

| `code` | 含义 | 常见来源 | 建议 |
|--------|------|----------|------|
| `unsupported_action` | 该平台配方没有这个动作（如 X 没有热榜、知乎没有 `social_feed`） | `social_hot` / `social_feed` | 换工具，不要重试 |
| `unsupported_platform` | 没有该平台的配方 | 读工具 | 检查 `platform` |
| `recipe_error` | 配方 TOML 语法错误、校验失败或采集执行异常 | 读工具 | 看 `social_platforms` 的 `recipe_errors`，见 [recipes.md](recipes.md) |
| `invalid_args` | 参数为空或格式不对（空 `query`、空 `handle`、非 http(s) URL 等） | 读工具 | 修正参数 |
| `not_logged_in` | 配方 `login_check` 探测到未登录 | 读工具 | 请用户在日常 Chrome 里登录该平台，插件不会自动登录 |
| `needs_user_approval` | `cdp` 后端尚未连接且当前是无人值守调用 | 读工具 | 点一次「允许」，或改用扩展 |
| `rate_limited` | 超出每小时 / 每天上限，或排队需等待 > 60 秒 | 读 / 写 | 等待，不要循环重试 |
| `cooling_down` | 平台处于风控冷却期（含 `until`） | 读 / 写 | 等冷却结束 |
| `out_of_hours` | 当前不在该平台允许的活跃时间段 | 读 / 写 | 在活跃时间内再试 |
| `blocked` | 本次请求命中风控信号，已触发冷却 | 读 | 立即停止并告知用户 |
| `read_failed` | `social_read` 页面访问失败 | `social_read` | 检查 URL 与网络 |
| `empty_content` | `social_read` 没抽到正文（可能需要登录或页面结构特殊） | `social_read` | 先确认登录态 |
| `selftest_failed` | 自测过程异常 | `social_selftest` | 看 `message` |
| `attach_failed` / `no_page` / `timeout` | 浏览器连接 / 页面 / 超时问题 | 所有浏览器相关调用 | 见 [troubleshooting.md](troubleshooting.md) |
| `internal_error` | `social_platforms` 内部异常 | `social_platforms` | 查看日志 |

## 5. 各平台能力现状

> **配方状态说明**：下表“读”一栏的 4 个配方在 `recipes/*.toml` 里均为 `status = "beta"`，单元测试只用离线夹具（`tests/fixtures/`）验证 XHR 字段抽取与标准化，**没有真机验证**；平台改版会让选择器 / 接口失效。真机冒烟需要你自己运行，见第 6 节。写适配器依赖页面 UI 自动化，源码里没有 beta / stable 标记，同样随平台改版可能失效。

| 平台 | 读（配方动作） | 配方状态 | 写（`list_supported_platforms` 声明的能力） |
|------|----------------|----------|---------------------------------------------|
| 知乎 `zhihu` | `hot`、`search` | beta，仅夹具测试 | 无写适配器 |
| X `x` / 写侧 `twitter` | `search`、`user_timeline` | beta，仅夹具测试 | post、video、thread、like、repost、quote、dm、analytics、trending、schedule |
| 微博 `weibo` | `hot`、`search` | beta，仅夹具测试 | post、video、like、schedule |
| 小红书 `xiaohongshu` | `search` | beta，仅夹具测试 | post、video、like、schedule |
| Instagram | 无配方 | — | post、video、story、like、schedule |
| Facebook | 无配方 | — | post、video、story、like、schedule |
| 抖音 `douyin` | 无配方 | — | post、video、like、analytics、trending、schedule |
| 微信公众号 `wechat` | 无配方 | — | post、schedule |
| TikTok | 无配方 | — | post、video、like、analytics、trending、schedule |
| LinkedIn | 无配方 | — | post、video、like、repost、quote、dm、analytics、schedule |
| Threads | 无配方 | — | post、video、like、repost、schedule |

动作与工具的对应：`search` ↔ `social_search`，`hot` ↔ `social_hot`，`user_timeline` ↔ `social_feed`。

## 6. 真机冒烟：`scripts/live_smoke.py`

目的：在你自己的机器上，用真实 Chrome 验证知乎和 X 两个配方是否还能用。**手工运行，不进 CI。**

```bash
cd plugins/social
POLARIS_BROWSER_BACKEND=cdp uv run python scripts/live_smoke.py | tee /tmp/live_smoke.log
# 用扩展后端（免弹窗）：把 cdp 换成 extension
# 可选参数：--vault <目录>（默认 /tmp/polaris-vault-smoke）  --sites zhihu,x（默认）
```

行为（来自脚本源码）：

- 每步输出一行 JSON（具体步骤名以脚本输出为准）。
- 只读：不点赞、不关注、不评论、不发帖，不读 cookie，不碰用户已有标签；全程一条连接，只在自建窗口里操作。
- 最多把 3 条结果经 Vault 的 `save_docs` 写入 `--vault` 指定目录（默认 `/tmp/polaris-vault-smoke`），**不写你的真实资料库**。
- 任一站点出现 `blocked` / `cooling_down` 会输出 `RISK_STOP` 并停止该站点。
- 结束时只关闭自建页并断开驱动，不关闭你的 Chrome。

注意事项：

- 用 `cdp` 时，第一次取页会触发 Chrome 的「允许远程调试」弹窗，需在 60 秒内人工点击；读不到 `DevToolsActivePort` 时改用扩展或设置 `POLARIS_BROWSER_CDP_URL`。
- 先在 Chrome 里登录知乎和 X；未登录时会得到 `not_logged_in`。
- 冒烟本身会占用限速名额（登录探测也计入）；不要在短时间内反复跑。
- 输出里 `ok:false` 或字段为空就是该配方失效的证据，维护流程见 [recipes.md](recipes.md)。跑完后请自己记录结果，本文档不替你声明“已验证”。
