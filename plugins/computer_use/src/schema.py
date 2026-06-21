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
                    "screenshot",
                    "get_screen_state",
                    "get_screen_info",
                    "get_ui_tree",
                    "click_element_by_id",
                    "click_element_by_name",
                    "focus_input",
                    "get_running_apps",
                    "get_window_list",
                    "open_app",
                    "close_window",
                    "minimize_app",
                    "quit_app",
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
                    "send_message_to",
                    "send_file_to",
                    "read_messages_from",
                    "computer_batch",
                ],
                "description": (
                    "Action to perform:\n"
                    "• open_app / close_window / minimize_app / quit_app — App lifecycle management.\n"
                    "• get_running_apps / get_window_list — List active windows and apps.\n"
                    "• get_screen_state — TEXT-ONLY MODELS: Returns UI tree & OCR text IDs. Use with click_element_by_id.\n"
                    "• get_screen_info — Get resolution and scaling factor.\n"
                    "• click_element_by_id / click_element_by_name — Click UI elements.\n"
                    "• focus_input — Focus the primary input field.\n"
                    "• type / clear_and_type — Text input (CJK safe).\n"
                    "• key / hold_key — Shortcuts and modifier hold.\n"
                    "• read_clipboard / write_clipboard — Clipboard management.\n"
                    "• wait — Wait for duration_ms.\n"
                    "• zoom — Zoom in/out based on amount.\n"
                    "• screenshot — VISION MODELS: Capture screen. Supply app_name to crop, or 'desktop'. Use mode='path' for local file.\n"
                    "• mouse_move / left_click / right_click / double_click / middle_click / triple_click / left_click_drag — Coordinate mouse.\n"
                    "• scroll — Scroll view (needs 'amount').\n"
                    "• cursor_position — Get current mouse coordinates.\n"
                    "• send_message_to / send_file_to / read_messages_from — Macro actions for chat apps.\n"
                    "• computer_batch — Execute multiple actions in sequence."
                ),
            },
            "coordinate": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[x, y] screen coordinates for mouse actions. For drag, these are the destination coordinates.",
            },
            "start_coordinate": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[x, y] start coordinates for drag.",
            },
            "amount": {
                "type": "number",
                "description": "Scroll amount or Zoom amount.",
            },
            "text": {
                "type": "string",
                "description": "Text to type, key shortcut string, clipboard content, or key to hold.",
            },
            "app_name": {
                "type": "string",
                "description": "Application name to target for focus, screenshot, close, minimize, etc.",
            },
            "id": {
                "type": "integer",
                "description": "Element ID for click_element_by_id.",
            },
            "element_name": {
                "type": "string",
                "description": "Name substring of element to click.",
            },
            "index": {
                "type": "integer",
                "description": "Match index: 0=first, -1=last.",
            },
            "hint": {
                "type": "string",
                "description": "Accessibility role hint for focus_input.",
            },
            "contact_name": {
                "type": "string",
                "description": "Contact or group chat name for chat macros.",
            },
            "message": {
                "type": "string",
                "description": "Message to send for send_message_to.",
            },
            "app": {
                "type": "string",
                "description": "Target app alias from src/profiles/. Examples: 'wechat', 'slack', etc.",
            },
            "wait_search": {
                "type": "number",
                "description": "Wait for search results (default 1.5s).",
            },
            "wait_chat": {
                "type": "number",
                "description": "Wait for chat to open (default 0.8s).",
            },
            "duration_ms": {
                "type": "number",
                "description": "Duration in milliseconds for wait action.",
            },
            "file_path": {
                "type": "string",
                "description": "Absolute file path for send_file_to.",
            },
            "count": {
                "type": "integer",
                "description": "Count of messages to read in read_messages_from.",
            },
            "actions": {
                "type": "array",
                "description": "List of action dictionaries for computer_batch.",
            },
            "stop_on_error": {
                "type": "boolean",
                "description": "Whether to stop computer_batch on first error (default true).",
            },
            "mode": {
                "type": "string",
                "description": "Screenshot mode: 'base64' (default) or 'path' (return local path).",
            },
        },
        "required": ["action"],
    },
}
