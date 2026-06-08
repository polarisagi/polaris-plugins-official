TOOL_SCHEMA = {
    "name": "computer",
    "description": (
        "Advanced cross-platform desktop automation MCP. "
        "Use 'send_message_to' for macro-driven chat automation, or low-level actions (screenshot, click, type) for general apps. "
        "Supported chat apps are defined in src/profiles/. \n\n"
        "CRITICAL RULES:\n"
        "1. FOCUS & TARGETING: You MUST provide the 'app_name' parameter in 'open_app', 'get_screen_state', and 'screenshot'. "
        "Passing 'desktop' as the app_name will natively show the OS desktop across all platforms.\n"
        "2. LOCALE AWARENESS: UI languages may differ from system language. ALWAYS observe OCR text in 'get_screen_state' before clicking/typing.\n"
        "3. MACRO PREFERENCE: For apps with dedicated macro tools (e.g. WeChat), you MUST use 'send_message_to' for interactions rather than manual clicks.\n"
        "4. SECURITY GUARDRAILS: Built-in config.json strictly blocks access to password managers and sensitive apps. "
        "For high-risk actions (deleting data, financial transfers), you MUST pause and request explicit user confirmation BEFORE proceeding."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "screenshot", "get_screen_state", "click_element_by_id", "get_running_apps",
                    "left_click", "right_click", "double_click", "left_click_drag",
                    "mouse_move", "scroll", "type", "key",
                    "open_app", "get_ui_tree", "click_element_by_name",
                    "focus_input", "clear_and_type", "send_message_to",
                ],
                "description": (
                    "Action:\n"
                    "• open_app — Launch/focus an app. Passing 'desktop' reveals the OS desktop. Fails if uninstalled.\n"
                    "• get_running_apps — List active window titles.\n"
                    "• get_screen_state — TEXT-ONLY MODELS: Returns UI tree & OCR text IDs. Use with click_element_by_id.\n"
                    "• click_element_by_id — Click element returned by get_screen_state.\n"
                    "• click_element_by_name — Click element by label.\n"
                    "• focus_input — Focus the primary input field.\n"
                    "• clear_and_type / type — Text input (CJK safe).\n"
                    "• key — Shortcut (e.g. 'enter', 'cmd+f').\n"
                    "• screenshot — VISION MODELS: Capture screen. Supply app_name to crop, or 'desktop'.\n"
                    "• mouse_move / left_click / right_click / double_click / left_click_drag — Coordinate mouse.\n"
                    "• scroll — Scroll view (needs 'amount').\n"
                    "• send_message_to — Macro: open chat, find contact, send message."
                ),
            },
            "coordinate": {"type": "array", "items": {"type": "number"},
                           "description": "[x, y] screen coordinates for mouse actions. For drag, these are the destination coordinates."},
            "amount":      {"type": "number", "description": "Scroll amount (positive to scroll up, negative to scroll down)."},
            "text":        {"type": "string", "description": "Text to type or key shortcut string."},
            "app_name":    {"type": "string", "description": "Application name. Filters screenshot/get_screen_state to only this app's window, or specifies target for open_app."},
            "id":          {"type": "integer", "description": "Element ID for click_element_by_id."},
            "element_name":{"type": "string", "description": "Name substring of element to click."},
            "index":       {"type": "integer", "description": "Match index: 0=first, -1=last."},
            "hint":        {"type": "string", "description": "Accessibility role hint for focus_input."},
            "contact_name":{"type": "string", "description": "[send_message_to] Contact or group chat name."},
            "message":     {"type": "string", "description": "[send_message_to] Message to send."},
            "app":         {"type": "string",
                            "description": (
                                "[send_message_to] Target app alias from src/profiles/. "
                                "Examples: 'wechat', 'slack', 'lark', 'dingtalk', 'telegram'. "
                                "If omitted, defaults to the first available chat profile."
                            )},
            "wait_search": {"type": "number", "description": "[send_message_to] Wait for search results (default 1.5s)."},
            "wait_chat":   {"type": "number", "description": "[send_message_to] Wait for chat to open (default 0.8s)."},
        },
        "required": ["action"],
    },
}
