#!/usr/bin/env python3
"""
Polaris System Info MCP Server
Provides environmental context (OS, locale, timezone, installed apps) to the AI Agent.
"""
import sys
import json
import os
import platform
import locale
import time
import shutil



def handle_check_app_installed(args):
    """Check if an application exists in standard OS installation paths."""
    app_name = args.get("app_name", "").strip()
    if not app_name:
        raise Exception("Missing 'app_name' parameter")
        
    plat = platform.system()
    app_name_lower = app_name.lower()
    
    results = []
    
    if plat == "Darwin":
        for base in ["/Applications", "/System/Applications", os.path.expanduser("~/Applications")]:
            if not os.path.exists(base): continue
            try:
                for item in os.listdir(base):
                    if item.endswith(".app") and app_name_lower in item.lower():
                        results.append(os.path.join(base, item))
            except Exception:
                pass
                
    elif plat == "Windows":
        bases = [
            os.environ.get("ProgramFiles", "C:\\Program Files"), 
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", "")
        ]
        for base in bases:
            if not base or not os.path.exists(base): continue
            try:
                for item in os.listdir(base):
                    if app_name_lower in item.lower():
                        results.append(os.path.join(base, item))
            except Exception:
                pass
                
    elif plat == "Linux":
        path = shutil.which(app_name_lower)
        if path:
            results.append(path)
            
    if results:
        return [{"type": "text", "text": json.dumps({
            "installed": True,
            "found_paths": results
        }, indent=2, ensure_ascii=False)}]
    else:
        return [{"type": "text", "text": json.dumps({
            "installed": False,
            "message": f"Could not find '{app_name}' in standard installation paths."
        }, indent=2, ensure_ascii=False)}]


# ---------------------------------------------------------------------------
# MCP JSON-RPC server
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "check_app_installed",
        "description": (
            "Check if a specific application is installed on the computer. "
            "Searches standard directories (/Applications on Mac, Program Files on Windows)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Name of the application to search for (e.g. 'WeChat', 'Slack', 'Chrome')"
                }
            },
            "required": ["app_name"]
        }
    }
]


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
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "polaris-systeminfo-mcp", "version": "1.0.0"},
                })
            elif method == "ping":
                _send_result(req_id, {})
            elif method == "tools/list":
                _send_result(req_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = req.get("params", {})
                tool_name = params.get("name")
                args = params.get("arguments", {})
                
                if tool_name == "check_app_installed":
                    result = handle_check_app_installed(args)
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
