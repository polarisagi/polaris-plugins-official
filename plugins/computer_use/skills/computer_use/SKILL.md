---
name: computer_use
description: "Decision guide for the computer MCP tool — universal desktop automation with layered operations."
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

The `computer` tool has two layers:

| Layer | When to use | Operations |
|-------|-------------|------------|
| **High-level** | Known app with a profile in `src/profiles/` | `send_message_to` |
| **Low-level** | Any app, any situation | `open_app`, `get_ui_tree`, `click_element_by_name`, `focus_input`, `clear_and_type`, `type`, `key`, `screenshot`, mouse actions |

**Rule:** always prefer a high-level op when one exists. Fall back to low-level primitives for apps that have no profile, or for tasks that don't match any high-level op.

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
              └─ Yes → send_message_to  (single call, handles everything)
              └─ No  → low-level loop: open_app → get_ui_tree → click/type → verify
  └─ No  → Multimodal model?
              └─ Yes → open_app → screenshot → interact → verify
              └─ No  → open_app → get_screen_state → click by coords → get_screen_state → verify
```

---

## 4. Sending a Message (High-Level)

Use `send_message_to` for any chat app that has a profile in `src/profiles/`:

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
| 飞书 / Lark | `飞书`, `lark`, `feishu` |
| 钉钉 / DingTalk | `钉钉`, `dingtalk` |
| Telegram | `telegram` |
| QQ | `qq` |

**i18n is handled automatically.** The tool detects the OS locale at startup and resolves locale-specific labels (e.g. `群聊` on Chinese systems, `Group Chats` on English systems). No caller action required.

**Adding a new app:** create a JSON file in `src/profiles/` — no code change needed.

---

## 4. Low-Level Workflow (any app)

Use this for apps without a profile, or for interactions that aren't "send a message":

```
1. open_app      — launch / focus the target application
2. get_ui_tree   — inspect accessibility elements as JSON
3. click_element_by_name / left_click — interact with elements
4. type / clear_and_type / key — enter text or trigger shortcuts
5. screenshot / get_ui_tree   — verify the result
```

**Example: open VS Code and trigger Command Palette**
```jsonc
{ "action": "open_app", "app_name": "Visual Studio Code" }
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

- **macOS**: keyboard operations in `send_message_to` are sent directly to the target process via AppleScript (`tell process X to keystroke`), bypassing focus — the target app does not need to remain frontmost.
- **Windows**: uses `pywinauto` for UI tree and element interaction.
- **Linux**: uses `pyatspi` for accessibility tree access.
