# 国际社交媒体风控指南 (Western Social Skill: Twitter, IG, FB)

## 1. Core Format & Layout (排版与配图规范)
- **多媒体/配图限制**：
  - **Instagram**：强烈依赖视觉。图片画幅最佳为 `4:5`（竖向 1080x1350）或 `1:1`（方形 1080x1080）。单贴最多 10 张图（Carousel）。如果没有配图，请务必调用搜图工具获取。
  - **Twitter/Facebook**：配图最佳比例为 `16:9`，单条最多 4 张图。

## 2. Tone & Style (语言风格与表情包规范)
- **表情包密度 (Emoji Density)**：【中等】。
  - **Twitter**: 喜欢使用极客/梗向 Emoji（如 🚀💀🤡👀🔥）。
  - **Instagram**: 喜欢极简、氛围感 Emoji（如 ✨☕️📸🤍）。
  - 不要把多种表情包密密麻麻地挤在一起。
- **Twitter (X)**：文字精炼（注意字数限制），善用 Thread（连击推文），要有态度、梗（Meme）和鲜明的观点。
- **Instagram**：视觉至上。图片要精美，文字部分注重生活方式的描绘，配合 5-10 个精准的 `#hashtags`。
- **Facebook**：注重社区感、家庭与朋友。长短皆可，适合发起群组讨论或分享生活大事件。

## 3. Red Lines (违规词库与红线)
> [!WARNING]
> 虽然西方平台言论相对自由，但在特定类别上有全球通用的极严红线。
- **仇恨言论与暴力（Hate Speech & Violence）**：严禁针对种族、宗教、性取向、国籍、残疾等群体发表歧视、攻击或威胁性言论。
- **NSFW（不适宜工作场所内容）**：Facebook 和 Instagram 对露点、色情、过度性暗示的图片和词汇“零容忍”，极易直接封禁。Twitter 允许合规标记的 NSFW，但未经标记的发布会被处罚。
- **虚假信息（Misinformation）**：关于选举、新冠疫情、公共卫生、气候变化的公认虚假信息会被打上“Community Notes（社区笔记）”标签，或者直接被降权/删除。
- **版权侵犯（Copyright）**：发布未授权的音乐（尤其是视频BGM）极易被下架或静音（针对 IG 和 FB）。

## 3. Anti-Shadowban (防限流策略)
- **避免 Spam 行为（防机器识别）**：
  - 严禁在短时间内使用大量不相关的热门 `#Hashtags`（例如发一篇美食文却带上 `#crypto` `#politics`），这被称为 Hashtag Abuse，会被算法关入“小黑屋（Shadowban）”。
  - 严禁同一条评论（如复制粘贴的 “Nice post!”）在多处刷屏。
- **停止 Algospeak 的滥用**：为了规避审核故意拼错敏感词（如 unalive 代替 dead，seggs 代替 sex）已经被新一代 AI 算法识别，虽然能短时间规避，但长远看降低了账号的健康度。
- **冷号养护**：新注册账号应避免立刻进行大量关注（Follow）或发布带有多重外部链接的推文。这会触发 Twitter 的反机器人（Anti-Bot）系统。

## 4. Comment Management (评论管理风控)
> [!IMPORTANT]
> **AI 主动防御机制**：当调用 `get_comments` 获取评论时，作为 AI Agent，你必须主动进行风控。
> 如果发现评论包含以下内容，你必须立刻调用 `delete_comment` 工具将其删除（Twitter平台由于机制限制，`delete_comment` 的实际效果是 Hide Reply 隐藏回复），绝不可回复：
> 1. 仇恨言论（Hate Speech）、种族歧视、恐怖主义。
> 2. 骚扰（Harassment）、人身攻击、粗俗语言。
> 3. 明显的 Spam 垃圾广告（如推销加密货币的机器人）。
