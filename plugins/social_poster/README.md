# social_poster — Polaris 社交媒体插件

通过 CDP 连接已登录的 Chrome 浏览器，对多平台社交媒体执行全自动操作。

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

**1. 以调试模式启动 Chrome（必须）**

```bash
# macOS
open -a "Google Chrome" --args --remote-debugging-port=9222

# Windows
chrome.exe --remote-debugging-port=9222

# Linux
google-chrome --remote-debugging-port=9222
```

**2. 在 Chrome 中手动登录各平台账号**

**3. 运行插件**

```bash
cd plugins/social_poster
uv run src/main.py
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
social_poster/
├── src/
│   ├── main.py              # MCP server 入口（所有 tools）
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
