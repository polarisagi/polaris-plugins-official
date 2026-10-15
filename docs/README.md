# 文档索引与总览

本页是 `browser_use` / `social` / `knowledge_base` 三个插件文档的入口：先看总览与选用决策表，再按需跳到各专题页。

> 文档基于仓库提交 `01e5a4e` 的源码编写；内核侧设计见 Polaris 仓库的 `docs/arch/decisions/ADR-0114-info-acquisition-automation-pipeline.md`（下文简称 ADR-0114）。

## 一页总览

| 插件 | 版本 | MCP 服务器名 | 一句话 |
|------|------|--------------|--------|
| `browser_use` | v2.1.0 | `polaris-browser-use` | 平台无关的通用浏览器工具：打开、读正文、快照、交互；三个后端（扩展桥接 / CDP 开关 / 托管 profile），只在 Polaris 自建窗口里操作 |
| `social` | v3.0.0 | `polaris-social` | 知乎 / X / 微博 / 小红书的读（搜索、热榜、动态、正文）与 10 个平台的写（发帖、互动），读写共享按平台的限速与风控熔断；站点配方为 TOML |
| `knowledge_base` | v2.0.0 | `polaris-knowledge-base` | 资料库（Vault）：把采集结果与摘要落成带 YAML front matter 的 Markdown，按 URL 去重，SQLite FTS5 检索，Obsidian 兼容 |

仓库里另有 `computer_use`、`system_info` 两个插件，不在本组文档范围内。

## 选用决策表：该用哪个工具

结论：**能用内核 HTTP 工具就不开浏览器；已知社交平台走 `social`；未知网页才用 `browser_use`；要落地沉淀用 `knowledge_base`。**

| 你要做的事 | 用什么 | 原因 |
|------------|--------|------|
| 抓一个公开网页并转成 Markdown | 内核 `web_fetch` | 纯 HTTP，无浏览器开销，VPS 也能跑 |
| 订阅 RSS / Atom / JSON Feed（如 Hacker News） | 内核 `feed_fetch` | 结构化条目，参数 `url` / `max_items` / `since` |
| 关键词搜索公开网页 | 内核 `web_search` | 参数 `query` / `max_results`，引擎由内核配置决定 |
| 知乎 / X / 微博 / 小红书的搜索、热榜、用户动态 | `social_search` / `social_hot` / `social_feed` | 配方 + XHR 拦截，复用你已登录的 Chrome，带限速与熔断 |
| 读一篇社交平台的帖文 / 文章全文 | `social_read` | 在自建页抽取正文 Markdown，计入该域名对应平台的限速 |
| 发帖、点赞、评论、私信等写操作 | `social` 的写工具（`auto_post` 等） | 与读共享限速；写类工具需要运行期审批（由内核负责） |
| 打开一个未知网页、需要登录态才能看的页面 | `browser_open` + `browser_read` | 通用浏览器，复用日常 Chrome 登录态 |
| 需要点击 / 输入 / 展开折叠内容 | `browser_snapshot` + `browser_act` | 先快照得到 `e<N>` 编号，再按编号操作 |
| 把采集结果、摘要存下来供日后检索和 RAG | `kb_save`（及 `kb_search` / `kb_read` 等） | 落成 Markdown，内核同步目录进 RAG，见 [knowledge-base.md](knowledge-base.md) |
| 每天定时采集 → 去重 → 存档 → 一次 LLM 提炼 | 内核自动化管线串联上述工具 | 见 [pipelines.md](pipelines.md) |

要点：

- 云端 VPS / 无头服务器不建议安装 `browser_use` 与 `social`（`browser_use` README 的建议），使用内核 HTTP 工具即可。
- `browser_use` 不含任何站点知识、配方或限速；遇到验证码 / 403 / 429 应立即停止，不要绕过。
- `social` 的 4 个读配方（知乎 / X / 微博 / 小红书）均为 **beta**，目前只有夹具（离线）测试，**真机冒烟需要你自己运行**，见 [social.md](social.md)。

## 文档目录

| 页面 | 内容 | 读者 |
|------|------|------|
| [architecture.md](architecture.md) | 分层与数据流、安全边界、两张 mermaid 图 | 使用者 / 维护者 |
| [browser-use.md](browser-use.md) | 三后端对比、扩展安装与配对、环境变量、工具参数、隔离与空闲释放 | 使用者 |
| [social.md](social.md) | 读写工具分层、共享限速与熔断、错误码、平台现状、`live_smoke` | 使用者 |
| [recipes.md](recipes.md) | 站点配方 TOML 字段、XHR 优先 / CSS 兜底、用户覆盖、新增平台与维护流程 | 维护者 |
| [knowledge-base.md](knowledge-base.md) | Vault 布局、front matter、`kb_*` 工具、去重、中文检索、与内核 RAG 的关系 | 使用者 |
| [pipelines.md](pipelines.md) | 在 Polaris 里把工具串成确定性采集管线的示例 | 使用者 |
| [troubleshooting.md](troubleshooting.md) | 症状 → 原因 → 处理 | 使用者 |
| [development.md](development.md) | 仓库结构、`check.sh`、单测、检查清单、版本与提交规范 | 维护者 |
| [migration.md](migration.md) | `social_poster` → `social`、`harvest*` 迁移对照、v1 → v2 变更 | 升级用户 |

## 各插件自带的说明

- [`plugins/browser_use/README.md`](../plugins/browser_use/README.md)、[`SKILL.md`](../plugins/browser_use/skills/browser_use/SKILL.md)
- [`plugins/social/README.md`](../plugins/social/README.md)、[`SKILL.md`](../plugins/social/skills/social/SKILL.md)
- [`plugins/knowledge_base/README.md`](../plugins/knowledge_base/README.md)、[`SKILL.md`](../plugins/knowledge_base/skills/knowledge_base/SKILL.md)

`SKILL.md` 是随插件下发给 Agent 的决策指南；本目录的文档面向人。两者冲突时以源码为准，并请反馈修正。
