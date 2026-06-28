# Split schemas according to 2026 AI Agent standard (Strict Mode / No God Tool)

TOOL_SCHEMA_CORE = {
    "name": "computer_core",
    "description": (
        "Low-level OS operations: mouse, keyboard, clipboard, and screenshots.\n"
        "CRITICAL RULES:\n"
        "1. FOCUS & TARGETING: You MUST provide the 'app_name' parameter in 'get_screen_state' and 'screenshot'. "
        "Passing 'desktop' as the app_name will natively show the OS desktop across all platforms.\n"
        "2. LOCALE AWARENESS: UI languages may differ from system language. ALWAYS observe OCR text in 'get_screen_state' before clicking/typing.\n"
        "3. SECURITY: For high-risk actions (deleting data, financial transfers), you MUST pause and request explicit user confirmation BEFORE proceeding."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "screenshot",
                    "get_screen_state",
                    "get_screen_info",
                    "get_ui_tree",
                    "left_click",
                    "right_click",
                    "double_click",
                    "middle_click",
                    "triple_click",
                    "left_click_drag",
                    "mouse_move",
                    "scroll",
                    "cursor_position",
                    "type",
                    "key",
                    "clear_and_type",
                    "hold_key",
                    "wait",
                    "read_clipboard",
                    "write_clipboard",
                    "zoom",
                    "click_element_by_id",
                    "click_element_by_name",
                    "focus_input",
                ],
                "description": (
                    "Action to perform:\n"
                    "• screenshot — VISION MODELS: Capture screen as base64 PNG. Supply app_name to crop to that window, or 'desktop'.\n"
                    "• get_screen_state — TEXT-ONLY MODELS: Returns UI tree & OCR text with element IDs. Use with click_element_by_id.\n"
                    "• get_screen_info — Get screen resolution and scaling factor.\n"
                    "• get_ui_tree — Get raw accessibility UI tree as JSON.\n"
                    "• click_element_by_id — Click a UI element by its numeric ID from get_screen_state.\n"
                    "• click_element_by_name — Click a UI element matching a name substring.\n"
                    "• focus_input — Focus the primary input field in the frontmost window.\n"
                    "• type — Type text (ASCII, confirmed empty field). CJK: use clear_and_type.\n"
                    "• clear_and_type — Select-all, delete, then type. Safe for CJK/emoji/pre-filled fields.\n"
                    "• key — Press a key or shortcut (e.g. 'cmd+f', 'enter', 'esc').\n"
                    "• hold_key — Hold a modifier key for the duration_ms.\n"
                    "• read_clipboard / write_clipboard — Clipboard management.\n"
                    "• wait — Wait for duration_ms milliseconds.\n"
                    "• zoom — Zoom in/out based on amount.\n"
                    "• mouse_move / left_click / right_click / double_click / middle_click / triple_click / left_click_drag — Coordinate-based mouse actions.\n"
                    "• scroll — Scroll view at coordinate by amount.\n"
                    "• cursor_position — Get current mouse cursor coordinates."
                ),
            },
            "coordinate": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[x, y] screen coordinates for mouse actions. For left_click_drag, these are the destination coordinates.",
            },
            "start_coordinate": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[x, y] start coordinates for left_click_drag.",
            },
            "amount": {
                "type": "number",
                "description": "Scroll amount (positive=down, negative=up) or zoom amount.",
            },
            "text": {
                "type": "string",
                "description": "Text to type, key shortcut string (e.g. 'cmd+v'), clipboard content, or key to hold.",
            },
            "app_name": {
                "type": "string",
                "description": "Application name to target for focus, screenshot, close, minimize, etc. Use 'desktop' to show the OS desktop.",
            },
            "id": {
                "type": "integer",
                "description": "Element ID from get_screen_state for click_element_by_id.",
            },
            "element_name": {
                "type": "string",
                "description": "Name substring of UI element to click for click_element_by_name.",
            },
            "index": {
                "type": "integer",
                "description": "Match index: 0=first (default), -1=last.",
            },
            "hint": {
                "type": "string",
                "description": "Accessibility role hint for focus_input (e.g. 'AXTextArea', 'AXTextField').",
            },
            "duration_ms": {
                "type": "number",
                "description": "Duration in milliseconds for wait or hold_key actions.",
            },
            "mode": {
                "type": "string",
                "description": "Screenshot mode: 'base64' (default, for vision models) or 'path' (return local file path).",
            },
        },
        "required": ["action"],
    },
}

TOOL_SCHEMA_APPS = {
    "name": "computer_apps",
    "description": (
        "Application lifecycle and window management.\n"
        "CRITICAL RULES:\n"
        "1. FOCUS: You MUST provide the 'app_name' parameter in 'open_app', 'close_window', 'minimize_app', 'quit_app'.\n"
        "2. SECURITY GUARDRAILS: Built-in config.json strictly blocks access to password managers and sensitive apps."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "get_running_apps",
                    "get_window_list",
                    "open_app",
                    "close_window",
                    "minimize_app",
                    "quit_app",
                ],
                "description": (
                    "Action to perform:\n"
                    "• open_app — Launch or bring an application to the foreground. Requires app_name.\n"
                    "• get_running_apps — List all currently running applications.\n"
                    "• get_window_list — List all open windows with their titles and bounds.\n"
                    "• close_window — Close the frontmost window of an app. Requires app_name.\n"
                    "• minimize_app — Minimize an app's window. Requires app_name.\n"
                    "• quit_app — Quit an application entirely. Requires app_name."
                ),
            },
            "app_name": {
                "type": "string",
                "description": "Target application name (e.g. 'Safari', 'Visual Studio Code').",
            },
        },
        "required": ["action"],
    },
}

TOOL_SCHEMA_MACRO = {
    "name": "computer_macro",
    "description": (
        "High-level macro automation for chat apps and batch execution.\n"
        "CRITICAL RULES:\n"
        "1. MACRO PREFERENCE: For apps with dedicated macro support (e.g. WeChat, Slack, Lark, DingTalk, Telegram, QQ), "
        "you MUST use 'send_message_to' instead of manual computer_core clicks. It is far more reliable.\n"
        "2. SUPPORTED APPS: Supported chat apps are defined in src/profiles/. Aliases work case-insensitively (e.g. '微信', 'wechat').\n"
        "3. BATCH: Use 'computer_batch' to execute multiple actions atomically in a single call."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "send_message_to",
                    "send_file_to",
                    "read_messages_from",
                    "computer_batch",
                ],
                "description": (
                    "Action to perform:\n"
                    "• send_message_to — Send a chat message to a contact or group in a supported app. Requires app, contact_name, message.\n"
                    "• send_file_to — Send a file to a contact or group in a supported app. Requires app, contact_name, file_path.\n"
                    "• read_messages_from — Read recent messages from a contact or group. Requires app, contact_name, count.\n"
                    "• computer_batch — Execute a list of computer_core/computer_apps actions in sequence. Requires actions array."
                ),
            },
            "app": {
                "type": "string",
                "description": "Target app alias from src/profiles/. Examples: 'wechat', '微信', 'slack', 'lark', 'dingtalk', 'telegram', 'qq'.",
            },
            "contact_name": {
                "type": "string",
                "description": "Contact or group chat name for chat macros.",
            },
            "message": {
                "type": "string",
                "description": "Message content to send for send_message_to.",
            },
            "file_path": {
                "type": "string",
                "description": "Absolute local file path for send_file_to.",
            },
            "count": {
                "type": "integer",
                "description": "Number of recent messages to read in read_messages_from.",
            },
            "actions": {
                "type": "array",
                "description": "List of action dicts for computer_batch (same schema as individual tool calls).",
            },
            "stop_on_error": {
                "type": "boolean",
                "description": "Whether to stop computer_batch on first error (default: true).",
            },
            "wait_search": {
                "type": "number",
                "description": "Seconds to wait for search results in chat macros (default: 1.5).",
            },
            "wait_chat": {
                "type": "number",
                "description": "Seconds to wait for a chat window to open (default: 0.8).",
            },
        },
        "required": ["action"],
    },
}

TOOL_SCHEMAS = [TOOL_SCHEMA_CORE, TOOL_SCHEMA_APPS, TOOL_SCHEMA_MACRO]
