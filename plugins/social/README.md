# Polaris Social (polaris-social) — Social Platform Read & Write Plugin (v3.0.0)

🌎 [English](README.md) | 🇨🇳 [中文](README_zh.md)

> Full documentation: [docs/social.md](../../docs/social.md) (Chinese) · Recipes: [docs/recipes.md](../../docs/recipes.md) (Chinese)

Reading and writing live in one plugin: it reuses your signed-in Chrome to read search results, trending lists, user feeds, and post bodies on Zhihu / X / Weibo / Xiaohongshu,
and to post and interact across multiple platforms. **Reading, posting, and interacting share the same platform's rate limits and risk circuit breaker** (SQLite, cross-process),
so the frequencies do not add up when you collect and post at the same time.

> The former `social_poster` has been renamed `social` (MCP server `polaris-social`); the former `browser_use` tools
> `harvest` / `harvest_recipes` / `harvest_selftest` have moved into this plugin as `social_search` / `social_hot` /
> `social_feed` / `social_platforms` / `social_selftest`.

## Read Tools (all declare `readOnlyHint` + `openWorldHint`)

| Tool | Description |
|------|------|
| `social_platforms` | Lists platforms, read actions and parameters, recipe status (beta/stable), the signed-in state cache, and the remaining rate-limit quota |
| `social_search(platform, query, max_items=20)` | Keyword search; returns normalized items |
| `social_hot(platform, max_items=20)` | Trending list (Zhihu, Weibo); platforms without this action return `unsupported_action` |
| `social_feed(platform, handle="", max_items=20)` | A user's public feed (X); platforms without this action return `unsupported_action` |
| `social_read(url, max_chars=8000, offset=0)` | Opens a post/article in a page it created itself and extracts the body as Markdown, with pagination; counted against the matching platform's rate limit by domain (unknown domains use the default rate limit) |
| `social_selftest(platform)` | Runs a minimal self-test of all of that platform's read actions and reports the field completeness rate |

`platform` values: `zhihu`, `x`, `weibo`, `xiaohongshu` (see `recipes/*.toml` for the site recipes; users can override them in
`~/.config/polaris-plugins/browser/recipes/`). Results are uniformly `{"ok": true, ...}` or
`{"ok": false, "error": {"code", "message"}}`. Common error codes: `unsupported_action`, `not_logged_in`,
`needs_user_approval`, `rate_limited`, `cooling_down`, `out_of_hours`, `blocked`, `invalid_args`.

## Shared Rate Limits

- Reads and writes are counted per **platform**: `twitter` in the write tools and `x` in the read tools are the same key.
- Platforms with a recipe use the recipe's `[limits]`; platforms without a recipe (instagram, facebook, douyin, wechat, tiktok, linkedin, threads)
  and unknown domains use conservative defaults: a minimum interval of 10 seconds, 20 per hour, and 60 per day.
- Write tools (`auto_post`, `like_post`, `send_dm`, etc.) claim a quota slot before executing; when rate-limited or in a circuit-breaker cooldown they **return an error code without executing**;
  when `run_scheduled_posts` hits a rate limit, the task stays pending and runs next time.
- Risk-control signals such as CAPTCHAs / 403 / 429 trigger a cooldown automatically, during which both reads and writes are rejected. **Never try to bypass it.**

## Live Smoke Test (run manually, not in CI)

```bash
cd plugins/social && POLARIS_BROWSER_BACKEND=cdp uv run python scripts/live_smoke.py | tee /tmp/live_smoke.log
```

Read-only, single connection, at most 15 navigations per site; results are written to `/tmp/polaris-vault-smoke` and never touch the real vault.


## Supported Platforms

| Platform | Post | Video | Story | Like | Repost | DM | Analytics | Trending |
|------|:----:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
| Twitter/X | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| Instagram | ✅ | ✅ | ✅ | ✅ | — | — | — | — |
| Facebook | ✅ | ✅ | ✅ | ✅ | — | — | — | — |
| Weibo | ✅ | ✅ | — | ✅ | — | — | — | — |
| Xiaohongshu | ✅ | ✅ | — | ✅ | — | — | — | — |
| Douyin | ✅ | ✅ | — | ✅ | — | — | ✅ | ✅ |
| WeChat Official Accounts | ✅ | — | — | — | — | — | — | — |
| TikTok | ✅ | ✅ | — | ✅ | — | — | ✅ | ✅ |
| LinkedIn | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | — |
| Threads | ✅ | ✅ | — | ✅ | ✅ | — | — | — |

## Quick Start

**1. Connect your everyday Chrome (installing the Polaris Browser Bridge extension is recommended, see the browser_use plugin README; or use the chrome://inspect switch)**

If you have no permission to read `DevToolsActivePort` in Chrome's data directory (on macOS the process may need to be granted access), use the extension instead, or set the environment variable `POLARIS_BROWSER_CDP_URL` to specify the CDP endpoint explicitly.

**2. Sign in to each platform account manually in Chrome**

**3. Run the plugin**

```bash
cd plugins/social
uv run python -m src.main
```

## MCP Tools Overview

### Publishing
| Tool | Description |
|------|------|
| `auto_post` | Posts text + images/videos (main entry point) |
| `batch_post` | Syncs to multiple platforms in one click |
| `post_video` | Posts a video (with cover and background music) |
| `post_story` | Posts a Story (Instagram/Facebook) |
| `post_thread` | Posts a tweet thread (Twitter/LinkedIn) |

### Scheduled Publishing
| Tool | Description |
|------|------|
| `schedule_post` | Schedules a publish time |
| `list_scheduled_posts` | Views the pending queue |
| `cancel_scheduled_post` | Cancels a scheduled post |
| `run_scheduled_posts` | Runs the tasks that are due |

### Post Management
| Tool | Description |
|------|------|
| `delete_post` | Deletes a post |
| `edit_post` | Edits a post (supports Twitter Premium / LinkedIn) |
| `get_my_posts` | Gets your own post list |
| `pin_post` | Pins a post |
| `save_draft` | Saves a draft |

### Comment Management
| Tool | Description |
|------|------|
| `get_comments` | Gets the comment list |
| `reply_comment` | Replies to a comment |
| `delete_comment` | Deletes/hides a comment |

### Interaction
| Tool | Description |
|------|------|
| `like_post` | Likes a post |
| `unlike_post` | Removes a like |
| `repost` | Reposts |
| `quote_post` | Quote repost (with a comment) |

### Search & Discovery
| Tool | Description |
|------|------|
| `search_posts` | Searches posts |
| `read_post` | Reads a post's full text |
| `get_trending_topics` | Gets trending topics |

### User Actions
| Tool | Description |
|------|------|
| `get_user_profile` | Gets a user profile |
| `follow_user` | Follows |
| `unfollow_user` | Unfollows |
| `block_user` | Blocks |
| `mute_user` | Mutes |
| `send_dm` | Sends a direct message |

### Analytics
| Tool | Description |
|------|------|
| `get_post_analytics` | Post data (likes/comments/reposts/views) |
| `get_account_analytics` | Overall account data |
| `get_notifications` | Notification list |
| `get_mentions` | @mention list |

### Content Helpers
| Tool | Description |
|------|------|
| `get_platform_skill` | Platform content guidelines |
| `get_content_template` | Content templates |
| `suggest_hashtags` | AI-recommended hashtags |
| `split_text_into_thread` | Automatically splits long text into a tweet thread |
| `search_free_image` | Searches free images (Pexels) |
| `list_supported_platforms` | Views each platform's capability matrix |

## Directory Structure

```
social/
├── recipes/                 # 站点配方（zhihu/x/weibo/xiaohongshu）
├── scripts/live_smoke.py    # 真机冒烟
├── tests/                   # 配方 / 采集 / 限速 / 闸门单测（离线）
├── src/
│   ├── main.py              # MCP server 入口（所有 tools）
│   ├── gate.py              # 读写共享限速闸门
│   ├── ratelimit.py         # 跨进程 SQLite 限速与熔断
│   ├── tools_social.py      # social_* 读工具实现
│   ├── harvest/             # 配方采集引擎
│   ├── content_manager.py   # 格式化、截断、话题标签
│   ├── scheduler.py         # 定时发布队列
│   ├── utils/
│   │   ├── browser.py       # CDP 连接管理
│   │   └── media.py         # 媒体类型检测
│   └── adapters/
│       ├── base_adapter.py  # 接口定义（全量方法）
│       ├── twitter.py
│       ├── instagram.py
│       ├── facebook.py
│       ├── weibo.py
│       ├── xiaohongshu.py
│       ├── douyin.py
│       ├── wechat.py
│       ├── tiktok.py        # TikTok 国际版
│       ├── linkedin.py
│       └── threads.py
└── skills/
    ├── *_skill.md           # 各平台内容规范
    └── templates/           # 内容模板
```

## Notes

- All operations rely on a signed-in Chrome session; no API key is needed
- Browser automation may break when a platform's UI is updated, so selectors need regular maintenance
- Scheduled publishing (`schedule_post`) requires an external scheduler to call `run_scheduled_posts`
- Media file paths must be absolute paths on this machine
