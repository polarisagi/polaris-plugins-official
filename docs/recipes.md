# 站点配方（Recipes）：TOML 字段、写法与维护

本页逐项说明 `plugins/social/recipes/*.toml` 的字段（以 `src/harvest/recipe.py` 的校验模型和 `loader.py` 为准）、XHR 优先 / CSS 兜底的写法、用户覆盖目录、新增平台与自测流程、改版后的维护流程。

结论先行：**配方是“声明式的采集脚本”：先走几步页面动作，再优先从页面发出的 XHR JSON 里按点路径取字段（0 token），取不到就退回 CSS 选择器。模型校验是严格的（`extra="forbid"`），写错字段名会直接报错而不是静默忽略。**

> **硬性规则：配方不得由 LLM 自动改写并生效。** 网页内容是不可信数据，把它写进持久配置等于注入持久化（ADR-0114 反例守护：“失败后由 LLM 自动改写站点配方并直接生效”被拒绝）。工具层面也没有“写配方”的接口。配方失效时，最多由 LLM 生成**修复提议**，必须由人审阅后手动落盘。

## 1. 文件位置与加载规则

| 项 | 规则 |
|----|------|
| 内置配方 | `plugins/social/recipes/*.toml`（现有：`zhihu`、`x`、`weibo`、`xiaohongshu`，另有示例 `_example.toml`） |
| 用户配方目录 | `~/.config/polaris-plugins/browser/recipes/*.toml`（Windows：`%APPDATA%\polaris-plugins\browser\recipes\`） |
| 覆盖规则 | 先扫内置、后扫用户目录；`site.id` 相同则用户文件**整体覆盖**内置文件（不是字段级合并） |
| 下划线前缀 | 以 `_` 开头的文件只在 `POLARIS_BROWSER_DEV=1`（也接受 `true` / `yes`）时加载，用于示例与开发 |
| 文件名与 id | 站点 id 取 `[site].id`；读不到时取文件名去掉前导 `_` |
| 损坏的文件 | TOML 语法或字段校验错误会出现在 `social_platforms` 的 `recipe_errors` 中；该平台随后返回 `recipe_error`。**用户目录里一个损坏的同名文件会让对应的内置配方一起失效**（因为覆盖发生在解析之前） |

重要限制：`social_search` / `social_hot` / `social_feed` / `social_selftest` 的 `platform` 参数是写死的枚举 `ReadPlatform = Literal["zhihu","x","weibo","xiaohongshu"]`（`src/main.py`）。这意味着：

- 用户目录里的配方可以**覆盖这 4 个平台**的行为；
- 放一个新 `site.id` 的用户配方，`social_platforms` 能列出它，但 `social_*` 工具会在参数校验阶段拒绝该平台名。要新增内置平台，必须按第 6 节改代码。

## 2. 顶层结构

```toml
status = "beta"            # 必须写在所有 [表] 之前；"beta"（默认）或 "stable"

[site]                     # 站点信息
[site.login_check]         # 可选：登录态探测
[limits]                   # 限速与活跃时间
[block_signals]            # 风控特征
[actions.<动作名>]          # 一个或多个动作
```

`Recipe` 必填：`site`、`limits`、`actions`。`block_signals` 缺省为空（不做风控检测），`status` 缺省 `beta`。

## 3. 字段逐项说明

### `[site]`

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `id` | 字符串 | 是 | 站点唯一标识，同时是限速键与 `items[].source`，如 `zhihu`、`x` |
| `name` | 字符串 | 是 | 展示名 |
| `base_url` | 字符串 | 是 | 站点基础 URL；用于把相对 URL 补全为绝对 URL。测试要求内置配方以 `https://` 开头 |

### `[site.login_check]`（可选）

| 字段 | 类型 | 说明 |
|------|------|------|
| `url` | 字符串 | 验证登录态的页面 URL（`live_smoke` 会用它做登录探测） |
| `logged_in_selector` | 字符串 | 已登录时一定出现的元素的 CSS 选择器（可用逗号写多个候选） |

引擎在执行完全部 `steps` 之后检查该选择器；找不到元素返回 `not_logged_in`，并把结果缓存到本进程（`social_platforms` 的 `logged_in`）。

### `[limits]`

| 字段 | 类型 | 缺省 | 说明 |
|------|------|------|------|
| `min_interval_s` | 浮点 | `4.0` | 同一平台两次请求的最小间隔（秒） |
| `jitter_s` | `[下限, 上限]` | `[0.5, 1.5]` | 间隔上叠加的随机抖动（秒） |
| `max_per_hour` | 整数 | `60` | 滚动 1 小时请求上限 |
| `max_per_day` | 整数 | `300` | 滚动 24 小时请求上限 |
| `active_hours` | `"HH:MM-HH:MM"` | `"08:00-23:30"` | 本地时间活跃窗口，可跨午夜（如 `22:00-04:00`） |
| `cooldown_on_block_h` | 浮点 | `6.0` | 命中风控后的冷却小时数 |

判定细节见 [social.md](social.md) 第 3 节。读写共用这套限速，所以不要为了“采集快一点”调小它；内置配方的测试要求 `min_interval_s >= 4.0`。

### `[block_signals]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | 整数列表 | 响应状态码命中即视为风控（如 `[403, 429]`，小红书额外有 `461`） |
| `url_contains` | 字符串列表 | 当前 URL 含任一子串即视为风控（验证码 / 登录重定向特征） |
| `text_contains` | 字符串列表 | 页面 `innerText` 含任一子串即视为风控 |

检查发生在每个 `goto` 之后；命中后写入冷却并返回 `blocked`。内置配方的测试要求这三项都非空。

### `[actions.<name>]`

动作名自由，但与工具的对应是固定的：`search` ↔ `social_search`（参数 `q`），`hot` ↔ `social_hot`，`user_timeline` ↔ `social_feed`（参数 `handle`）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `description` | 字符串 | 动作说明，出现在 `social_platforms` 里 |
| `params.<名>` | 表 | 参数规格，见下表 |
| `steps` | 表数组 `[[actions.<name>.steps]]` | 页面动作序列，按书写顺序执行 |
| `extract` | 表 | **必填**，首选提取（`xhr` 或 `css`） |
| `extract_fallback` | 表 | 可选，只能是 `css`；首选提取为空时启用 |

**`params.<名>`**

| 字段 | 取值 | 说明 |
|------|------|------|
| `type` | `string`（默认）\| `number` \| `boolean` | 仅作声明与展示，引擎不做类型转换 |
| `description` | 字符串 | 说明 |
| `default` | 任意 | URL 模板里参数缺失时使用 |
| `required` | 布尔，默认 `false` | 仅作声明，真正的非空校验在工具层（如 `query` 不能为空） |

**`steps` 的键**（同一个 step 里可以写多个键，固定按下表顺序执行）：

| 键 | 说明 |
|----|------|
| `goto` | 打开 URL，等到 `domcontentloaded`；支持参数模板；之后立刻做风控检查 |
| `wait_for` | 等待该 CSS 选择器出现 |
| `timeout_s` | 本 step 的 `goto` / `wait_for` / `click` 超时秒数，缺省 `10.0` |
| `scroll` | 内联表 `{ direction = "down" \| "up", times = N }`，每次滚 600 像素，间隔 0.2 秒 |
| `click` | 点击该 CSS 选择器 |
| `sleep` | `[下限, 上限]` 秒，随机睡眠 |

**URL 模板**：`goto` 里可写 `{参数名}`、`{参数名|urlencode}`、`{参数名|json}`。取值顺序是调用参数 → `default` → 空字符串。例如 `https://www.zhihu.com/search?type=content&q={q|urlencode}`。

### `[actions.<name>.extract]` —— XHR 方式（首选）

| 字段 | 说明 |
|------|------|
| `method = "xhr"` | 拦截页面发出的网络响应 |
| `url_glob` | 匹配响应 URL 的通配模式（`fnmatch`），如 `*/api/v4/search_v3*` |
| `items` | 响应 JSON 中**列表**所在的点路径，如 `data`、`data.statuses`；支持 `a[0].b` 写法（等价于 `a.0.b`） |
| `fields` | `{ 输出字段 = "条目内点路径" }` |

细节：监听器在执行 `steps` 之前注册；只收 `content-type` 含 `json` 或 `javascript` 的响应；多个命中的响应会被依次合并；若一个都没捕获到，会再等 1 秒；`items` 路径取到的不是列表则忽略。

### `[actions.<name>.extract]` / `extract_fallback` —— CSS 方式

| 字段 | 说明 |
|------|------|
| `method = "css"` | 从渲染后的 DOM 抽取 |
| `container` | 每个条目容器的 CSS 选择器 |
| `fields` | `{ 输出字段 = "css" 或 "css@属性" }` |

字段值语法：`"h2"` 取子元素 `innerText`；`"a@href"` 取子元素的 `href` 属性（`href` / `src` 返回绝对地址）；`"@data-id"`（选择器留空）取**容器本身**的属性；找不到元素得 `null`。非法选择器返回 `invalid_args`。测试要求内置配方每个动作都有 `extract_fallback`，且至少 3 个字段。

### 输出字段名（标准化契约）

无论 XHR 还是 CSS，`fields` 的键只有这些会被保留（其余丢弃）：`id`、`url`、`title`、`author`、`published_at`、`excerpt`，以及 `metrics.<名>`（如 `"metrics.likes" = "object.voteup_count"`，会汇总进 `metrics` 字典）。时间戳（秒 / 毫秒 / 自然语言）统一转为 RFC 3339 UTC，HTML 标签会被去掉，`excerpt` 截断到 500 字符。`id` 与 `url` 是下游去重的关键，尽量给全。

## 4. XHR 优先 + CSS 兜底的写法

最小骨架（以搜索为例）：

```toml
status = "beta"

[site]
id = "example"
name = "示例站点"
base_url = "https://www.example.com"

[site.login_check]
url = "https://www.example.com/"
logged_in_selector = ".user-avatar, [aria-label='个人中心']"

[limits]
min_interval_s = 5.0
jitter_s = [1.0, 3.0]
max_per_hour = 50
max_per_day = 250
active_hours = "08:00-23:30"
cooldown_on_block_h = 6.0

[block_signals]
status = [403, 429]
url_contains = ["captcha"]
text_contains = ["验证码"]

[actions.search]
description = "搜索示例站点"

[actions.search.params.q]
type = "string"
description = "搜索关键词"
required = true

[[actions.search.steps]]
goto = "https://www.example.com/search?q={q|urlencode}"
wait_for = ".result-card"
timeout_s = 15.0

[[actions.search.steps]]
scroll = { direction = "down", times = 2 }

[actions.search.extract]
method = "xhr"
url_glob = "*/api/search*"
items = "data.items"

[actions.search.extract.fields]
id = "id"
url = "url"
title = "title"
author = "author.name"
"metrics.likes" = "stats.likes"

[actions.search.extract_fallback]
method = "css"
container = ".result-card"

[actions.search.extract_fallback.fields]
title = "h2"
url = "h2 a@href"
author = ".author"
excerpt = ".summary"
```

写法建议：

1. **先在浏览器开发者工具的 Network 面板找到列表接口**，把它的 URL 模式写成 `url_glob`，把响应里列表的点路径写成 `items`。
2. **一定写 CSS 兜底**：接口改版时 XHR 提取为空，引擎会自动用 `extract_fallback`，`social_selftest` 的 `method_used` 会显示实际用了 `css`。
3. `wait_for` 选一个稳定、尽早出现的元素，别选动态类名；超时在 `timeout_s` 里按需放宽。
4. 配方里不要写任何账号、cookie、令牌；登录永远由人完成。

## 5. 对照现有 4 个配方

| 配方 | 动作 | 首选提取 | 兜底 | 备注 |
|------|------|----------|------|------|
| `zhihu.toml` | `hot`、`search` | XHR（`*/api/v3/feed/topstory/hot-lists/total*`、`*/api/v4/search_v3*`） | CSS | 有 `login_check` |
| `x.toml` | `search`、`user_timeline` | XHR（`*/graphql/*/SearchTimeline*`、`*/graphql/*/UserTweets*`；`items` 用 `...instructions[0].entries`） | CSS | 全天可用 |
| `weibo.toml` | `hot`、`search` | XHR（`*/ajax/statuses/hot_band*`、`*/ajax/statuses/search*`） | CSS | |
| `xiaohongshu.toml` | `search` | XHR（`*/api/sns/web/v1/search/notes*`） | CSS | 冷却 12 小时、最严格限速 |
| `_example.toml` | `front` | 仅 CSS（Hacker News 首页） | — | 仅 `POLARIS_BROWSER_DEV=1` 时加载 |

观察（来自源码）：`x.toml` 的 `search.params.mode` 与 `xiaohongshu.toml` 的 `search.params.sort` 已声明，但 `goto` 模板里没有引用它们，`social_search` 也只传 `q`，所以这两个参数目前不起作用。

## 6. 新增平台与自测

### 只想覆盖 / 调整现有 4 个平台

1. 复制内置文件到 `~/.config/polaris-plugins/browser/recipes/<id>.toml`，保持 `site.id` 不变。
2. 修改后重启插件进程（配方在每次调用时重新加载，但 MCP 进程内的登录缓存等状态需要重启才清空）。
3. `social_platforms` 查看 `origin`（应为 `user`）和 `recipe_errors`。
4. `social_selftest(platform)` 做最小自测。

### 新增一个内置平台（需要改代码，提交前走 `check.sh`）

| 步骤 | 位置 | 说明 |
|------|------|------|
| 1 | `plugins/social/recipes/<id>.toml` | 文件名（去掉扩展名）必须等于 `site.id` |
| 2 | `src/main.py` 的 `ReadPlatform` | 把 `<id>` 加进 `Literal[...]`；`tests/test_tools_social.py::test_platform_literal_matches_builtin_recipes` 会强制它与 `recipes/*.toml` 一致 |
| 3 | `src/gate.py` 的 `DOMAIN_PLATFORMS` | 加域名后缀 → 限速键映射，`social_read` 才会把该域名计入这个平台的限速 |
| 4 | `tests/fixtures/<id>/*.json` 与 `tests/test_site_recipes.py` | 放响应夹具，断言 XHR 提取与标准化结果；测试要求内置配方有 `extract_fallback` |
| 5 | 文档 | 更新 `plugins/social/README.md`、`SKILL.md` 与本目录文档；新配方一律先标 `status = "beta"` |
| 6 | 自测 | 本地跑单测（见 [development.md](development.md)），再在真机用 `social_selftest(<id>)` 与 `scripts/live_smoke.py` 的思路验证 |

### 用 `social_selftest` 自测

- 对该平台全部动作各跑一次，返回每个动作的 `ok`、`item_count`、`field_fill_rate`、`method_used`、`error`。
- 判读：`method_used` 为 `css` 说明 XHR 没命中（接口可能改版）；`field_fill_rate` 里 `id` / `url` / `title` 偏低说明字段路径失效；`error` 里出现 `blocked` / `cooling_down` 就停手，不要重试。
- 自测会真实访问站点并占用限速名额，请勿连续运行。

## 7. 改版后的维护流程

1. **发现**：`social_selftest` 报 `ok:false`、`method_used` 退到 `css`、或字段填充率明显下降（ADR-0114 的下线 / 改用 RSSHub 或官方 API 的评估线是“连续 2 周低于 60%”）。
2. **定位**：在 Chrome 开发者工具里手动访问同一页面，看列表接口的 URL / 响应结构、DOM 选择器分别变成了什么。**不要让 Agent 去“自动修复”配方。**
3. **修改**：人工编辑 `recipes/<id>.toml`（先改用户目录副本验证，确认后再改内置文件）；同步更新 `tests/fixtures/<id>/` 的夹具与断言。
4. **验证**：跑离线单测；真机用 `social_selftest` 与 `live_smoke.py`（遵守限速，遇风控信号立即停）。
5. **发布**：按 [development.md](development.md) 的检查清单提交；配方状态保持 `beta`，直到你自己在真机上确认稳定后才改为 `stable`。
6. **记录**：把改动原因（接口 / 选择器变化）写进提交信息，方便下次对照。
