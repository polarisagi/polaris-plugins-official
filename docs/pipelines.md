# 确定性采集管线：把工具串起来

本页给出在 Polaris 里把 `feed_fetch`、`social_*`、`kb_save` 串成“确定性采集管线”的示例，并说明步骤种类、`skip_if_empty`、写类步骤审批和无头会话的限制。

结论先行：**管线里只有最后的 `llm` 步骤会花 token；抓取、去重、存档都是确定性步骤。没有新数据时整条管线跳过，一次 LLM 都不调。** 管线的 DSL、校验与执行属于内核（Polaris 仓库 `internal/automation/pipeline/`），本页的字段名逐字取自其中的 `spec.go` / `validate.go` / `template.go` / `runner.go`；内核有变动时以内核为准。

> 下面的示例 JSON 是按内核 DSL 校验规则人工核对过的，**我没有在内核里实际运行过它们**。第一次一定先用 `dry_run` 试跑（见第 6 节），再正式保存。知乎配方还是 beta，见 [social.md](social.md)。

## 1. 管线骨架

```json
{
  "kind": "pipeline",
  "name": "管线名称（1..60 字符）",
  "description": "可选描述",
  "trigger": { "type": "cron", "cron": "0 8 * * *" },
  "result_action": "session",
  "deliver_from": "某个 llm 或 agent 步骤的 key",
  "steps": [ ]
}
```

| 字段 | 说明 |
|------|------|
| `kind` | 固定 `pipeline` |
| `name` | 必填，≤60 字符 |
| `trigger.type` | `cron` 或 `manual`；`cron` 时必须给 `trigger.cron`（5 字段表达式） |
| `result_action` | 缺省 `session`；也可 `silent` 或 `channel:<id>` |
| `deliver_from` | 投递哪一步的结果；必须指向 `llm` 或 `agent` 步骤 |
| `steps` | 1..20 步（默认上限，来自内核阈值 `pipeline.max_steps`）；每步 `key` 须匹配 `^[a-z][a-z0-9_]{0,31}$`，不能叫 `run` / `item` / `steps` |

依赖：`needs` 只能引用**排在前面**的步骤的 `key`（不允许向后依赖与环）。

## 2. 步骤种类

| `kind` | 用途 | 主要字段 | 是否花 token |
|--------|------|----------|:------------:|
| `tool` | 调一个工具（内置或 MCP） | `tool`、`args`（JSON）、`items_path`、`approval`、`needs` | 否 |
| `transform` | 对条目做固定算子变换 | `ops`、`needs`（输入取 `needs` 的第一个） | 否 |
| `llm` | 单次 LLM 提炼 | `input`（必须在 `needs` 里）、`fields`、`prompt`（必填，≤4000 字符）、`output`（`markdown` \| `json`）、`json_schema`、`max_input_chars`、`max_output_tokens`、`thinking`（`off` \| `low`） | 是（一次） |
| `agent` | 跑一轮完整 Agent 会话（既有行为） | `prompt`（必填，≤4000 字符）、`reasoning_effort`（`low` \| `medium` \| `high` \| `ultra`） | 是（多轮） |

通用字段：`needs`、`skip_if_empty`、`max_retries`。

### `tool` 步骤

- 工具名：内置工具用原名（`feed_fetch`、`web_fetch`、`web_search`）；MCP 工具用 `mcp__<服务器名>__<工具名>`，例如 `mcp__polaris-social__social_hot`、`mcp__polaris-knowledge-base__kb_save`。
- 允许集（ADR-0114 决策一）：只读内置工具、`web_fetch`、`feed_fetch`、声明了 `readOnlyHint` 的 MCP 工具，加上写入白名单（默认 `knowledge_ingest` 与 `mcp__polaris-knowledge-base__kb_save`）。**`automation_*` 与 `privileged` 工具永远禁止。**
- 返回值归一化：如果工具返回合法 JSON，会先按 `items_path`（点路径）取数组，未指定时依次探测顶层的 `items` / `results` / `entries` / `data`；顶层本身是数组也行；取不到则把原始文本放进 `text`，`count` 为 0。`social_*` 返回的 `items` 因此可直接被识别。
- `args` 里引用了上游数据（`{{steps.*}}`）时，内核以高污点（TaintHigh）调用该工具。

### `transform` 的固定算子

只有这 8 个，没有表达式语言（ADR-0114 反例守护：不引入表达式 / 脚本）。

| `op` | 必填字段 | 说明 |
|------|----------|------|
| `concat` | `from`（步骤 key 列表，须都在 `needs` 里） | 合并多个上游的条目 |
| `dedup` | `by`（字段点路径）；可选 `scope`：`run`（缺省，仅本次运行内）\| `workflow`（跨运行） | `workflow` 范围用去重表，且只在整次运行成功收尾后才写入，失败的运行下次会重试；缺少 `by` 字段的条目保留 |
| `filter` | `field`、`cmp`（`==` `!=` `>` `>=` `<` `<=` `contains` `not_contains` `regex`）、`value`；可选 `keep_missing` | `regex` 的 `value` 必须是合法正则字符串 |
| `sort` | `by`；可选 `desc` | 排序 |
| `limit` | `n`（≥1） | 取前 n 条 |
| `pick` | `fields`（点路径列表） | 只保留这些字段 |
| `rename` | `map`（`{旧名: 新名}`） | 重命名字段 |
| `truncate` | `field`、`max_chars`（≥1，按 rune） | 截断某字段 |

### 模板变量

用在 `tool.args` 的字符串值里：

| 写法 | 含义 |
|------|------|
| `{{steps.<key>.items}}` | 上游条目数组；整值替换时是真正的 JSON 数组 |
| `{{steps.<key>.count}}` | 上游条目数（数字） |
| `{{steps.<key>.text}}` | 上游文本（如 `llm` 步骤的回答） |
| `{{run.date}}` / `{{run.since}}` | 运行日期 / 上次时间 |

规则：整个字符串恰好是一个 `{{...}}` 时做整值替换，否则按字符串插值（对象会被序列化为紧凑 JSON，单个插值结果 ≤64KiB）；被引用的步骤必须出现在本步的 `needs` 里；引用未定义变量会报错。

### `skip_if_empty`

某步产出的 `count == 0` 且该步**不是 `llm`** 时，该步标记为 `skipped`，并且**所有依赖它的下游步骤也会被标记为 `skipped`**。因此把 `skip_if_empty: true` 放在去重后的 `transform` 上，就能让“没有新数据”的那次运行跳过存档和 LLM，既不花 token 也不投递。`llm` 步骤上的 `skip_if_empty` 不起作用。

## 3. 示例一：每日 HN / RSS 摘要

流程：拉 RSS → 跨运行去重 → 存原文进 Vault → 一次 LLM 提炼 → 把摘要也存进 Vault。

```json
{
  "kind": "pipeline",
  "name": "每日 HN 摘要",
  "trigger": { "type": "cron", "cron": "0 8 * * *" },
  "result_action": "session",
  "deliver_from": "digest",
  "steps": [
    {
      "key": "fetch",
      "kind": "tool",
      "tool": "feed_fetch",
      "args": { "url": "https://news.ycombinator.com/rss", "max_items": 30 }
    },
    {
      "key": "fresh",
      "kind": "transform",
      "needs": ["fetch"],
      "skip_if_empty": true,
      "ops": [
        { "op": "dedup", "by": "url", "scope": "workflow" },
        { "op": "limit", "n": 15 }
      ]
    },
    {
      "key": "save_raw",
      "kind": "tool",
      "needs": ["fresh"],
      "tool": "mcp__polaris-knowledge-base__kb_save",
      "args": { "docs": "{{steps.fresh.items}}", "kind": "raw", "collection": "hn" }
    },
    {
      "key": "digest",
      "kind": "llm",
      "needs": ["fresh"],
      "input": "fresh",
      "fields": ["title", "url", "excerpt"],
      "prompt": "用中文写一份今日 Hacker News 要点摘要：按主题分组，每条一句话，保留原始链接。",
      "output": "markdown",
      "max_output_tokens": 1200,
      "thinking": "off"
    },
    {
      "key": "save_digest",
      "kind": "tool",
      "needs": ["digest"],
      "tool": "mcp__polaris-knowledge-base__kb_save",
      "args": {
        "docs": [
          {
            "title": "Hacker News 每日摘要 {{run.date}}",
            "content": "{{steps.digest.text}}",
            "source": "hn-digest",
            "tags": ["摘要", "hn"]
          }
        ],
        "kind": "digest",
        "collection": "日报"
      }
    }
  ]
}
```

要点：

- `feed_fetch` 的参数：`url`（必填）、`max_items`（1–200，默认 30）、`since`（RFC 3339，只留该时间之后的条目）。它的条目字段是 `id`、`title`、`url`、`author`、`published_at`、`excerpt`、`source`。
- `kb_save` 默认免审批：它在内核写入白名单里（阈值 `m13_interface.pipeline_write_allowlist`）。`kb_save` 会忽略多余字段，`raw` 文档需要 `url`，正文为空时回退到 `excerpt`。
- 去重放在 `transform` 里、`save_raw` 与 `digest` 都依赖 `fresh`：同一批新条目既存档又提炼。
- 摘要文本通过 `{{steps.digest.text}}` 进入 `kb_save(kind="digest")`，不需要再调一次 LLM。

## 4. 示例二：知乎热榜 → `kb_save` → 一次 LLM 提炼

```json
{
  "kind": "pipeline",
  "name": "知乎热榜日报",
  "trigger": { "type": "cron", "cron": "0 9 * * *" },
  "result_action": "session",
  "deliver_from": "digest",
  "steps": [
    {
      "key": "hot",
      "kind": "tool",
      "tool": "mcp__polaris-social__social_hot",
      "args": { "platform": "zhihu", "max_items": 20 }
    },
    {
      "key": "fresh",
      "kind": "transform",
      "needs": ["hot"],
      "skip_if_empty": true,
      "ops": [
        { "op": "dedup", "by": "url", "scope": "workflow" },
        { "op": "limit", "n": 10 }
      ]
    },
    {
      "key": "save_raw",
      "kind": "tool",
      "needs": ["fresh"],
      "tool": "mcp__polaris-knowledge-base__kb_save",
      "args": { "docs": "{{steps.fresh.items}}", "kind": "raw", "collection": "zhihu-hot" }
    },
    {
      "key": "digest",
      "kind": "llm",
      "needs": ["fresh"],
      "input": "fresh",
      "fields": ["title", "url", "excerpt"],
      "prompt": "用中文提炼今天知乎热榜的 3 个主要话题，每个话题 2 句话，保留原始链接。",
      "output": "markdown",
      "max_output_tokens": 800,
      "thinking": "off"
    }
  ]
}
```

要点与风险：

- `social_hot` 带 `readOnlyHint`，所以免审批；`platform` 只能是 `zhihu` / `x` / `weibo` / `xiaohongshu`，且 X 没有热榜（`unsupported_action`）。
- 知乎配方的活跃时间是本地 08:00–23:30，深夜触发会得到 `out_of_hours`；每次调用要受共享限速约束（见 [social.md](social.md)）。
- 浏览器后端要能**无人值守**：用 `extension`（或 `managed`）。`cdp` 未连接时 `social_hot` 返回 `needs_user_approval`，无人时没有办法点“允许”。
- **失败可能被悄悄当成“没数据”**：`social_*` 的错误（`not_logged_in`、`cooling_down`、`rate_limited` 等）是以 `{"ok": false, "error": ...}` 的 JSON 正常返回的，按内核的归一化规则它没有 `items`，`count` 为 0，原始 JSON 被放进 `text`，于是 `fresh` 因 `skip_if_empty` 被跳过。以上是根据 `Normalize` / `RunStep` 的代码推断的行为：首次试跑请看每一步的 Preview / `text`，不要只看“是否被跳过”。
- `live_smoke.py` 里有一个 `fix_zhihu_url` 兜底，把 `api.zhihu.com/questions/…` 形式的地址转成 `www.zhihu.com/question/…`，说明知乎接口返回的 `url` 可能是 API 形式。`kb_save` 与 `dedup` 都以 `url` 为键，这种地址能去重，但在浏览器里未必能直接打开；正式使用前请先看一次真实返回。
- 知乎配方 beta、仅夹具测试，真机冒烟待你运行。

## 5. 写类步骤需要 HITL 审批

写类工具（非只读、也不在写入白名单里的工具）出现在 `tool` 步骤里必须声明 `"approval": "hitl"`，否则保存时校验就会报 `write tool "..." requires approval=hitl`。更关键的是**运行期**：内核在执行前经 HITL 网关请求人工审批（审批请求里带渲染后的参数预览，截断到 500 个字符），未声明、没有审批通道、被拒绝或超时一律不执行（fail-closed）。

仅演示审批字段的片段（不建议无人值守地把外部内容经 LLM 转手发帖）：

```json
{
  "key": "publish",
  "kind": "tool",
  "needs": ["digest"],
  "tool": "mcp__polaris-social__auto_post",
  "approval": "hitl",
  "args": { "platform": "weibo", "content": "{{steps.digest.text}}" }
}
```

说明：`dry_run` 试运行时写类步骤不会真的执行，只给出“将写入 N 条”的预览；`social` 的写工具还会占用与读取同一平台的限速名额。

## 6. 让 Agent 自己建：`automation_*` 与 `dry_run`

- 工具：`automation_list`、`automation_save`、`automation_run_now`、`automation_delete`（内核内置）。`automation_save` 的 `kind` 为 `prompt`（Agent 定时跑一轮，需 `prompt` 与 `cron`）或 `pipeline`（上面的 DSL）。
- **`dry_run: true`**（仅 `pipeline`；`prompt` 型会报错）：只校验并试运行，不调 LLM、不执行写工具、不写去重表，返回 `{ok, dry_run, errors}`，`errors` 是逐字段的校验错误（`path` / `code` / `message`）。建议每次修改后先 `dry_run`。
- **无头会话不能自建自动化**：后台 / 无头会话（`IsBackgroundWork`）调用 `automation_save`、`automation_run_now`、`automation_delete` 会在工具层被直接拒绝（`无头后台任务禁止…`）。这些要在有人的交互会话里做。
- 配额与间隔由内核阈值控制（默认值来自内核 `state.yaml`，以内核为准）：Agent 来源的启用自动化上限 20 个；管线最小触发间隔 15 分钟；`prompt` 型最小触发间隔 60 分钟；单步输出上限 1048576 字节；`llm` 步骤输入上限 24000 字符、输出上限 2000 token（未指定 `max_output_tokens` 时用 1200）。
- 去重条目默认保留 90 天，运行数据默认保留最近 20 轮。

> 内核侧观察：`automation_save` 的 JSON Schema 里把步骤 `kind` 的说明写成“tool, transform, llm, agent, sink”，但 `Spec` 与 `Validate` 只接受前四种，`sink` 会被判为非法；`deliver_from` 也不在该 Schema 的属性列表里。写管线时请以 `spec.go` / `validate.go` 为准。

## 7. 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| 每次都被 `skipped` | 去重后没有新条目；或上游工具失败被当成空数据 | 看每步 Preview / `text`；确认浏览器后端能无人值守 |
| `write tool ... requires approval=hitl` | 步骤里用了非只读且不在白名单的工具 | 加 `approval:"hitl"`，或改用只读工具 |
| `invalid_ref`（`must be in step needs`） | `args` / `input` / `from` 引用了未列入 `needs` 的步骤 | 把它加进 `needs` |
| `kb_save` 的 `failed` 里有 `missing_url` | `raw` 文档没有 `url` | 保证上游条目有 `url`，或改用 `kind: "digest"` |
| `tool ... is not allowed in pipeline` | 用了 `automation_*` 或 `privileged` 工具 | 这些永远禁止 |
