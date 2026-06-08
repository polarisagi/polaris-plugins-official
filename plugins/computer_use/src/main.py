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
    handle_screenshot, handle_get_screen_state, handle_get_ui_tree,
    handle_open_app, handle_get_running_apps, handle_send_message_to,
    handle_click_element_by_id, handle_click_element_by_name, handle_focus_input, handle_clear_and_type,
    handle_left_click, handle_right_click, handle_double_click, handle_mouse_move, handle_scroll, handle_left_click_drag,
    handle_type, handle_key
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

def handle_computer(args):
    action = args.get("action")
    app_name = args.get("app_name") or args.get("app")
    
    if app_name and not check_app_permission(app_name):
        return [{"type": "text", "text": f"[SECURITY BLOCK] You are not permitted to access or operate the application '{app_name}'. It is not in the allowed_apps list."}]

    if action == "open_app":              return handle_open_app(args)
    if action == "get_ui_tree":           return handle_get_ui_tree(args)
    if action == "get_screen_state":      return handle_get_screen_state(args)
    if action == "get_running_apps":      return handle_get_running_apps(args)
    if action == "click_element_by_id":   return handle_click_element_by_id(args)
    if action == "click_element_by_name": return handle_click_element_by_name(args)
    if action == "focus_input":           return handle_focus_input(args)
    if action == "clear_and_type":        return handle_clear_and_type(args)
    if action == "send_message_to":       return handle_send_message_to(args)

    if action == "screenshot":     return handle_screenshot(args)
    if action == "mouse_move":     return handle_mouse_move(args)
    if action == "scroll":         return handle_scroll(args)
    if action == "left_click":     return handle_left_click(args)
    if action == "right_click":    return handle_right_click(args)
    if action == "double_click":   return handle_double_click(args)
    if action == "left_click_drag": return handle_left_click_drag(args)
    if action == "type":           return handle_type(args)
    if action == "key":            return handle_key(args)

    raise Exception(f"Unknown action: '{action}'")


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
                _send_result(req_id, {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "polaris-computer-mcp", "version": "1.0.0"},
                })
            elif method == "ping":
                _send_result(req_id, {})
            elif method == "tools/list":
                _send_result(req_id, {"tools": [TOOL_SCHEMA]})
            elif method == "tools/call":
                params = req.get("params", {})
                if params.get("name") == "computer":
                    args = params.get("arguments", {})
                    action = args.get("action")
                    app_name = args.get("app_name")
                    
                    import utils
                    utils.clean_screenshot_dir()
                    
                    if action in ("open_app", "send_message_to"):
                        import os
                        import tempfile
                        sf = os.path.join(tempfile.gettempdir(), "computer_use_state.json")
                        if os.path.exists(sf):
                            try:
                                os.remove(sf)
                            except Exception:
                                pass
                                
                    result = handle_computer(args)
                    
                    # [Smart Soft Routing]: Contextual injection for read actions
                    if action in ("screenshot", "get_screen_state", "get_ui_tree"):
                        # Attempt to resolve the targeted app name
                        if not app_name:
                            import utils
                            app_name = utils.get_frontmost_app_name()
                            
                        if app_name:
                            from profiles_loader import APP_PROFILES
                            app_lower = app_name.lower()
                            if app_lower in APP_PROFILES:
                                profile = APP_PROFILES[app_lower]
                                if "adapter" in profile or profile.get("type") == "chat":
                                    hint = f"[SYSTEM HINT] This application ('{app_name}') has a dedicated macro tool. To interact (e.g. send messages), DO NOT use manual actions like left_click or type. You MUST use 'send_message_to' instead for reliability."
                                    if isinstance(result, list):
                                        result.append({"type": "text", "text": hint})
                                    elif isinstance(result, str):
                                        result += f"\n\n{hint}"
                                        
                    _send_result(req_id, {"content": result})
                else:
                    _send_error(req_id, -32601, "Tool not found")
            else:
                if req_id is not None:
                    _send_error(req_id, -32601, "Method not found")
        except Exception as e:
            _send_error(req_id, -32603, str(e))


def _send_result(req_id, result):
    if req_id is None:
        return
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}) + "\n")
    sys.stdout.flush()


def _send_error(req_id, code, message):
    if req_id is None:
        return
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
