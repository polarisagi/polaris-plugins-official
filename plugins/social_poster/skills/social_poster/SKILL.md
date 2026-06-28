---
name: social_poster
description: "Standard operating procedure for the social_poster MCP plugin — multi-platform social media content publishing and management."
version: "1.0.0"
tags:
  - social-media
  - auto-post
  - content
exec_mode: ambient
risk_level: high
sandbox: L2
capability: read-write
---

## 1. Architecture

This plugin uses a **platform adapter pattern**. Each platform has a dedicated adapter. All tools accept a `platform` string to route to the correct adapter.

**Supported platforms**: `twitter`, `instagram`, `facebook`, `weibo`, `xiaohongshu`, `douyin`, `wechat`, `tiktok`, `linkedin`, `threads`

---

## 2. CRITICAL: Always Read Platform Guidelines First

**Before generating or posting any content**, ALWAYS call `get_platform_skill(platform)` to load the platform's specific content rules, character limits, hashtag guidelines, and compliance guardrails. Failure to do so risks shadowbans or account restrictions.

```
get_platform_skill("xiaohongshu")  → Load Xiaohongshu rules before posting
get_platform_skill("twitter")      → Load Twitter/X rules before posting
```

---

## 3. Standard Posting Workflow

```
1. get_platform_skill(platform)     — Load content rules and character limits
2. (Optional) suggest_hashtags()    — Get relevant hashtags for the content
3. (Optional) search_free_image()   — Get a royalty-free image if needed
4. auto_post(platform, content)     — Publish the post
5. get_my_posts(platform, limit=1)  — Verify the post was published
```

---

## 4. Tool Categories

| Category | Tools |
|----------|-------|
| **Publishing** | `auto_post`, `batch_post`, `post_video`, `post_story`, `post_thread` |
| **Scheduling** | `schedule_post`, `list_scheduled_posts`, `cancel_scheduled_post`, `run_scheduled_posts` |
| **Management** | `delete_post`, `edit_post`, `get_my_posts`, `pin_post`, `save_draft` |
| **Comments** | `get_comments`, `reply_comment`, `delete_comment` |
| **Engagement** | `like_post`, `unlike_post`, `repost`, `quote_post` |
| **Search** | `search_posts`, `read_post`, `get_trending_topics` |
| **Users** | `get_user_profile`, `follow_user`, `unfollow_user`, `block_user`, `mute_user`, `send_dm` |
| **Analytics** | `get_post_analytics`, `get_account_analytics`, `get_notifications`, `get_mentions` |
| **Helpers** | `get_platform_skill`, `get_content_template`, `suggest_hashtags`, `split_text_into_thread`, `search_free_image`, `list_supported_platforms` |

---

## 5. Safety Rules

- **High-risk actions** (delete_post, block_user, send_dm in bulk) MUST require explicit user confirmation before execution.
- **Never post without** reading platform guidelines via `get_platform_skill` first.
- The plugin uses **browser CDP automation** — the user must have the relevant platform logged in their browser.
