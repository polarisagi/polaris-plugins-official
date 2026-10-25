# Polaris Social（polaris-social）— 社交平台读写插件 (v3.0.0)

🌎 [English](README.md) | 🇨🇳 [中文](README_zh.md)

> 完整文档：[docs/social.md](../../docs/social.md) · 配方：[docs/recipes.md](../../docs/recipes.md)

读与写同处一个插件：复用你已登录的 Chrome，读取知乎 / X / 微博 / 小红书的搜索、热榜、用户动态与帖文正文，
并在多平台发帖与互动。**读取与发帖、互动共享同一平台的限速与风控熔断**（SQLite 跨进程），
一边采集一边发帖时频率不会叠加。

> 原 `social_poster` 已更名为 `social`（MCP 服务器 `polaris-social`）；原 `browser_use` 中的
> `harvest` / `harvest_recipes` / `harvest_selftest` 已迁入本插件，对应 `social_search` / `social_hot` /
> `social_feed` / `social_platforms` / `social_selftest`。

## 读工具（均声明 `readOnlyHint` + `openWorldHint`）

| Tool | 说明 |
|------|------|
| `social_platforms` | 列出平台、读动作与参数、配方状态（beta/stable）、登录态缓存、限速余量 |
| `social_search(platform, query, max_items=20)` | 关键词搜索，返回标准化条目 |
| `social_hot(platform, max_items=20)` | 热榜（知乎、微博）；无该动作返回 `unsupported_action` |
| `social_feed(platform, handle="", max_items=20)` | 用户公开动态（X）；无该动作返回 `unsupported_action` |
| `social_read(url, max_chars=8000, offset=0)` | 在自建页打开帖文/文章并抽取正文 Markdown，支持分页；按域名计入对应平台限速（未知域名用默认限速） |
| `social_selftest(platform)` | 对该平台全部读动作做最小自测，报告字段完整率 |

`platform` 取值：`zhihu`、`x`、`weibo`、`xiaohongshu`（站点配方见 `recipes/*.toml`，用户可在
`~/.config/polaris-plugins/browser/recipes/` 覆盖）。统一返回 `{"ok": true, ...}` 或
`{"ok": false, "error": {"code", "message"}}`。常见错误码：`unsupported_action`、`not_logged_in`、
`needs_user_approval`、`rate_limited`、`cooling_down`、`out_of_hours`、`blocked`、`invalid_args`。

## 共享限速

- 读取与写入按**平台**计数：写工具里的 `twitter` 与读工具里的 `x` 是同一把键。
- 有配方的平台使用配方的 `[limits]`；没有配方的平台（instagram、facebook、douyin、wechat、tiktok、linkedin、threads）
  及未知域名使用保守默认值：最小间隔 10 秒、每小时 20 次、每天 60 次。
- 写工具（`auto_post`、`like_post`、`send_dm` 等）执行前先占用名额，被限速或处于熔断冷却期时**返回错误码而不执行**；
  `run_scheduled_posts` 遇到限速时任务保持 pending，下次再执行。
- 遇到验证码 / 403 / 429 等风控信号时自动进入冷却，期间读写都被拒绝。**严禁尝试绕过。**

## 真机冒烟（手工运行，不进 CI）

```bash
cd plugins/social && POLARIS_BROWSER_BACKEND=cdp uv run python scripts/live_smoke.py | tee /tmp/live_smoke.log
```

仅只读、单连接、每站 ≤15 次导航；结果写入 `/tmp/polaris-vault-smoke`，不碰真实资料库。


## 支持平台

| 平台 | 发帖 | 视频 | 故事 | 点赞 | 转发 | 私信 | 数据 | 热搜 |
|------|:----:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
| Twitter/X | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| Instagram | ✅ | ✅ | ✅ | ✅ | — | — | — | — |
| Facebook | ✅ | ✅ | ✅ | ✅ | — | — | — | — |
| 微博 | ✅ | ✅ | — | ✅ | — | — | — | — |
| 小红书 | ✅ | ✅ | — | ✅ | — | — | — | — |
| 抖音 | ✅ | ✅ | — | ✅ | — | — | ✅ | ✅ |
| 微信公众号 | ✅ | — | — | — | — | — | — | — |
| TikTok | ✅ | ✅ | — | ✅ | — | — | ✅ | ✅ |
| LinkedIn | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | — |
| Threads | ✅ | ✅ | — | ✅ | ✅ | — | — | — |

## 快速开始

**1. 连接你的日常 Chrome（推荐安装 Polaris Browser Bridge 扩展，见 browser_use 插件 README；或使用 chrome://inspect 开关）**

无权读取 Chrome 数据目录中的 `DevToolsActivePort` 时（macOS 可能需要授予该进程访问权限），请改用扩展，或设置环境变量 `POLARIS_BROWSER_CDP_URL` 显式指定 CDP 端点。

**2. 在 Chrome 中手动登录各平台账号**

**3. 运行插件**

```bash
cd plugins/social
uv run python -m src.main
```

## MCP Tools 总览

### 发布
| Tool | 说明 |
|------|------|
| `auto_post` | 发文字 + 图片/视频（主入口） |
| `batch_post` | 一键同步多平台 |
| `post_video` | 发视频（含封面、配乐） |
| `post_story` | 发 Story（Instagram/Facebook） |
| `post_thread` | 发推文串（Twitter/LinkedIn） |

### 定时发布
| Tool | 说明 |
|------|------|
| `schedule_post` | 预约发布时间 |
| `list_scheduled_posts` | 查看待发队列 |
| `cancel_scheduled_post` | 取消预约 |
| `run_scheduled_posts` | 执行到期任务 |

### 帖子管理
| Tool | 说明 |
|------|------|
| `delete_post` | 删除帖子 |
| `edit_post` | 编辑帖子（支持 Twitter Premium / LinkedIn） |
| `get_my_posts` | 获取自己的帖子列表 |
| `pin_post` | 置顶帖子 |
| `save_draft` | 保存草稿 |

### 评论管理
| Tool | 说明 |
|------|------|
| `get_comments` | 获取评论列表 |
| `reply_comment` | 回复评论 |
| `delete_comment` | 删除/隐藏评论 |

### 互动
| Tool | 说明 |
|------|------|
| `like_post` | 点赞 |
| `unlike_post` | 取消点赞 |
| `repost` | 转发 |
| `quote_post` | 引用转发（带评论） |

### 搜索 & 发现
| Tool | 说明 |
|------|------|
| `search_posts` | 搜索帖子 |
| `read_post` | 读取帖子全文 |
| `get_trending_topics` | 获取热门话题 |

### 用户操作
| Tool | 说明 |
|------|------|
| `get_user_profile` | 获取用户资料 |
| `follow_user` | 关注 |
| `unfollow_user` | 取消关注 |
| `block_user` | 拉黑 |
| `mute_user` | 屏蔽 |
| `send_dm` | 发私信 |

### 数据分析
| Tool | 说明 |
|------|------|
| `get_post_analytics` | 帖子数据（点赞/评论/转发/播放） |
| `get_account_analytics` | 账号整体数据 |
| `get_notifications` | 通知列表 |
| `get_mentions` | @提及列表 |

### 内容辅助
| Tool | 说明 |
|------|------|
| `get_platform_skill` | 平台内容规范指南 |
| `get_content_template` | 内容模板 |
| `suggest_hashtags` | AI 推荐话题标签 |
| `split_text_into_thread` | 长文自动切割为推文串 |
| `search_free_image` | 搜索免费图片（Pexels） |
| `list_supported_platforms` | 查看各平台能力矩阵 |

## 目录结构

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

## 注意事项

- 所有操作依赖已登录的 Chrome 会话，无需 API Key
- 浏览器自动化可能因平台 UI 更新失效，选择器需定期维护
- 定时发布（`schedule_post`）需要外部定时调用 `run_scheduled_posts`
- 媒体文件路径必须是本机绝对路径
