---
name: computer_use
description: "Decision guide for the computer_use MCP tools (computer_core, computer_apps, computer_macro) — universal desktop automation with layered operations."
version: "1.0.0"
tags:
  - computer-use
  - automation
  - desktop
exec_mode: ambient
risk_level: medium
sandbox: L2
capability: read-write
---

## 1. Architecture

The `computer_use` plugin exposes three tools with two logical layers:

| Layer | Tool | When to use | Key Operations |
|-------|------|-------------|----------------|
| **High-level** | `computer_macro` | Known app with a profile in `src/profiles/` | `send_message_to`, `send_file_to`, `read_messages_from`, `computer_batch` |
| **Mid-level** | `computer_apps` | App lifecycle management | `open_app`, `quit_app`, `close_window`, `get_running_apps` |
| **Low-level** | `computer_core` | Any app, any situation | `screenshot`, `get_ui_tree`, `click_element_by_name`, `type`, `key`, mouse actions |

**Rule:** always prefer a higher-level tool when one exists. Fall back to `computer_core` low-level primitives for apps without a profile, or tasks not covered by macros.

---

## 2. Vision Mode vs Text-Only Mode

Choose the screen-inspection tool based on whether the model can process images:

| Model capability | "See" the screen with | Config |
|---|---|---|
| Multimodal (Gemini, Claude, GPT-4V…) | `screenshot` → base64 PNG | `VISION_CAPABLE=true` (default) |
| Text-only (DeepSeek v4, Qwen, etc.) | `get_screen_state` → text + coords | `VISION_CAPABLE=false` |

**How to switch modes:**

Option A — server-wide (recommended): set `VISION_CAPABLE=false` in `.mcp.json` env for text-only agents.

Option B — per call: pass `"mode": "text"` to any `screenshot` call (overrides server setting).

Option C — call `get_screen_state` directly (always returns text, regardless of server setting).

`get_screen_state` returns:
```
=== UI Elements (Accessibility) ===
[AXButton] "发送" at (850, 620)
[AXTextField] "" at (600, 580)

=== Screen Text (OCR) ===
"张三" at (200, 120)
"今天下午开会" at (400, 300)
```
Coordinates are logical screen pixels — pass directly to `left_click`.

---

## 3. Decision Tree

```
Task involves sending a message?
  └─ Yes → Is the app in the known profile list?
              └─ Yes → computer_macro: send_message_to  (single call, handles everything)
              └─ No  → computer_apps: open_app
                        → computer_core: get_ui_tree → click/type → verify
  └─ No  → Multimodal model?
              └─ Yes → computer_apps: open_app → computer_core: screenshot → interact → verify
              └─ No  → computer_apps: open_app → computer_core: get_screen_state → click by coords → verify
```

---

## 4. Sending a Message (High-Level)

Use `computer_macro` with `send_message_to` for any chat app that has a profile in `src/profiles/`:

```jsonc
{
  "action": "send_message_to",
  "contact_name": "小伙子",
  "message": "这是一条来自 AI 的测试消息",
  "app": "微信"
}
```

**Supported `app` values** (any alias works, case-insensitive):

| App | Aliases |
|-----|---------|
| WeChat / 微信 | `微信`, `wechat` |
| Slack | `slack` |

> [!WARNING]
> **WeChat Limitations**: The WeChat adapter currently **ONLY supports** searching and sending messages to **Contacts (联系人)** and **Group Chats (群聊)**. It does **NOT support** Official Accounts (公众号), Mini Programs (小程序), or other entities. When a name is ambiguous, use the `contact_type` parameter ('contact' or 'group') to disambiguate.
| 飞书 / Lark | `飞书`, `lark`, `feishu` |
| 钉钉 / DingTalk | `钉钉`, `dingtalk` |
| Telegram | `telegram` |
| QQ | `qq` |

**i18n is handled automatically.** The tool detects the OS locale at startup and resolves locale-specific labels (e.g. `群聊` on Chinese systems, `Group Chats` on English systems). No caller action required.

**Adding a new app:** create a JSON file in `src/profiles/` — no code change needed.

---

## 4. Low-Level Workflow (`computer_apps` + `computer_core`)

Use this for apps without a profile, or for interactions that aren't "send a message":

```
1. computer_apps: open_app      — launch / focus the target application
2. computer_core: get_ui_tree   — inspect accessibility elements as JSON
3. computer_core: click_element_by_name / left_click — interact with elements
4. computer_core: type / clear_and_type / key — enter text or trigger shortcuts
5. computer_core: screenshot / get_ui_tree   — verify the result
```

**Example: open VS Code and trigger Command Palette**
```jsonc
// Tool: computer_apps
{ "action": "open_app", "app_name": "Visual Studio Code" }
// Tool: computer_core
{ "action": "key", "text": "cmd+shift+p" }
{ "action": "clear_and_type", "text": "Git: Commit" }
{ "action": "key", "text": "enter" }
```

---

## 5. Text Input Rules

| Scenario | Action |
|----------|--------|
| Field may already have content | `clear_and_type` |
| Chinese, emoji, or special chars | `clear_and_type` (clipboard injection — always safe) |
| Confirmed empty field, ASCII only | `type` |

---

## 6. Focusing an Input Field

```jsonc
{ "action": "focus_input", "hint": "AXTextArea" }
```

Scans the accessibility tree for the first editable area. Falls back to bottom-center of the active window.

---

## 7. Keyboard Shortcuts

```jsonc
{ "action": "key", "text": "cmd+f" }
{ "action": "key", "text": "enter" }
{ "action": "key", "text": "ctrl+shift+p" }
```

Modifiers: `cmd`, `ctrl`, `alt`, `shift`.
Special keys: `enter`, `esc`, `tab`, `space`, `backspace`, `delete`, `up`, `down`, `left`, `right`, `home`, `end`, `pageup`, `pagedown`, `f1`–`f12`.

---

## 8. Error Recovery

| Problem | Recovery |
|---------|----------|
| Dialog / modal blocking | `key: esc` |
| Wrong element clicked | `get_ui_tree` → re-examine → retry |
| Search field has old text | `clear_and_type` (always clears first) |
| App lost focus unexpectedly | `open_app` again to re-activate |

---

## 9. Platform Notes

- **macOS**: `send_message_to` for WeChat uses a pure-visual OCR + coordinate-based approach to prevent focus-stealing bugs native to the macOS Accessibility tree.
- **Windows**: uses `pywinauto` for UI tree and element interaction.
- **Linux**: uses `pyatspi` for accessibility tree access.
