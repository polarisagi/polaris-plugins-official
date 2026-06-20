#!/usr/bin/env python3
"""
Polaris Computer Use MCP Server — Universal Desktop Automation
Supports: macOS, Windows, Linux

Architecture:
  utils.py          — shared keyboard / mouse / accessibility helpers
  adapters/base.py  — BaseAdapter: generic search-result selection
  adapters/chat/    — app-specific adapters (only when generic is not enough)
  adapters/registry — maps bundle IDs to adapter classes
  profiles/*.json   — per-app config (shortcuts, locale-aware labels, etc.)
  handlers/         — cleanly separated execution handlers
  main.py           — MCP server + action routing
"""

import sys
import json

from schema import TOOL_SCHEMA
from handlers import (
    handle_screenshot,
    handle_get_screen_state,
    handle_get_ui_tree,
    handle_open_app,
    handle_get_running_apps,
    handle_send_message_to,
    handle_click_element_by_id,
    handle_click_element_by_name,
    handle_focus_input,
    handle_clear_and_type,
    handle_left_click,
    handle_right_click,
    handle_double_click,
    handle_mouse_move,
    handle_scroll,
    handle_left_click_drag,
    handle_type,
    handle_key,
)


def check_app_permission(app_name):
    if not app_name:
        return True
    import os

    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                app_lower = app_name.lower()

                # Check blacklist first
                blocked = config.get("blocked_apps", [])
                if any(b.lower() == app_lower for b in blocked):
                    return False

                # Then check whitelist
                allowed = config.get("allowed_apps", ["*"])
                if "*" in allowed:
                    return True
                return any(a.lower() == app_lower for a in allowed)
        except Exception:
            pass
    return True


# Dispatch table — maps action name → handler function.
# Add new actions here without touching handle_computer().
_ACTION_DISPATCH = {
    "open_app":              handle_open_app,
    "get_ui_tree":           handle_get_ui_tree,
    "get_screen_state":      handle_get_screen_state,
    "get_running_apps":      handle_get_running_apps,
    "click_element_by_id":   handle_click_element_by_id,
    "click_element_by_name": handle_click_element_by_name,
    "focus_input":           handle_focus_input,
    "clear_and_type":        handle_clear_and_type,
    "send_message_to":       handle_send_message_to,
    "screenshot":            handle_screenshot,
    "mouse_move":            handle_mouse_move,
    "scroll":                handle_scroll,
    "left_click":            handle_left_click,
    "right_click":           handle_right_click,
    "double_click":          handle_double_click,
    "left_click_drag":       handle_left_click_drag,
    "type":                  handle_type,
    "key":                   handle_key,
}


def handle_computer(args):
    action = args.get("action")
    app_name = args.get("app_name") or args.get("app")

    if app_name and not check_app_permission(app_name):
        return [
            {
                "type": "text",
                "text": (
                    f"[SECURITY BLOCK] You are not permitted to access or operate "
                    f"the application '{app_name}'. It is not in the allowed_apps list."
                ),
            }
        ]

    handler = _ACTION_DISPATCH.get(action)
    if handler is None:
        raise Exception(f"Unknown action: '{action}'")
    return handler(args)


_READ_ACTIONS = {"screenshot", "get_screen_state", "get_ui_tree"}
_RESET_STATE_ACTIONS = {"open_app", "send_message_to"}


def _clear_state_file():
    """Remove the screen-state cache before navigation actions."""
    import os
    import tempfile

    sf = os.path.join(tempfile.gettempdir(), "computer_use_state.json")
    if os.path.exists(sf):
        try:
            os.remove(sf)
        except Exception:
            pass


def _inject_routing_hint(action, app_name, result):
    """Append a soft-routing hint when a dedicated macro exists for the app."""
    if action not in _READ_ACTIONS:
        return result

    import utils
    from profiles_loader import APP_PROFILES

    resolved = app_name or utils.get_frontmost_app_name()
    if not resolved:
        return result

    profile = APP_PROFILES.get(resolved.lower())
    if profile and ("adapter" in profile or profile.get("type") == "chat"):
        hint = (
            f"[SYSTEM HINT] This application ('{resolved}') has a dedicated macro tool. "
            f"To interact (e.g. send messages), DO NOT use manual actions like left_click "
            f"or type. You MUST use 'send_message_to' instead for reliability."
        )
        if isinstance(result, list):
            result.append({"type": "text", "text": hint})
        elif isinstance(result, str):
            result += f"\n\n{hint}"
    return result


def _handle_tools_call(req_id, params):
    """Execute a tools/call request and send the result."""
    if params.get("name") != "computer":
        _send_error(req_id, -32601, "Tool not found")
        return

    args = params.get("arguments", {})
    action = args.get("action")
    app_name = args.get("app_name")

    import utils
    utils.clean_screenshot_dir()

    if action in _RESET_STATE_ACTIONS:
        _clear_state_file()

    result = handle_computer(args)
    result = _inject_routing_hint(action, app_name, result)
    _send_result(req_id, {"content": result})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            _send_error(None, -32700, "Parse error")
            continue

        req_id = req.get("id")
        method = req.get("method")

        try:
            if method == "initialize":
                _send_result(
                    req_id,
                    {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "polaris-computer-mcp", "version": "1.0.0"},
                    },
                )
            elif method == "ping":
                _send_result(req_id, {})
            elif method == "tools/list":
                _send_result(req_id, {"tools": [TOOL_SCHEMA]})
            elif method == "tools/call":
                _handle_tools_call(req_id, req.get("params", {}))
            else:
                if req_id is not None:
                    _send_error(req_id, -32601, "Method not found")
        except Exception as e:
            _send_error(req_id, -32603, str(e))


def _send_result(req_id, result):
    if req_id is None:
        return
    sys.stdout.write(
        json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}) + "\n"
    )
    sys.stdout.flush()


def _send_error(req_id, code, message):
    if req_id is None:
        return
    sys.stdout.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": code, "message": message},
            }
        )
        + "\n"
    )
    sys.stdout.flush()


if __name__ == "__main__":
    main()
