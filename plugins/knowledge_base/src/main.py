#!/usr/bin/env python3
"""
Polaris Knowledge Base MCP Server
Provides safe access to local files for RAG purposes, with path sandboxing.
"""
import sys
import json
import os
import pathlib


ALLOWED_DIR = os.environ.get("POLARIS_KB_ALLOWED_DIR")

def is_path_allowed(target_path: str) -> bool:
    if not ALLOWED_DIR:
        return True
    
    try:
        abs_target = pathlib.Path(target_path).resolve()
        abs_root = pathlib.Path(ALLOWED_DIR).resolve()
        
        # Check if abs_target is relative to abs_root
        return abs_root in abs_target.parents or abs_target == abs_root
    except Exception:
        return False


def handle_list_files(args):
    target_path = args.get("path")
    if not isinstance(target_path, str):
        raise ValueError("path is required and must be a string")
        
    if not is_path_allowed(target_path):
        raise PermissionError("path is outside the allowed directory (POLARIS_KB_ALLOWED_DIR)")
        
    try:
        entries = os.listdir(target_path)
        file_names = []
        for entry in entries:
            full_path = os.path.join(target_path, entry)
            if os.path.isdir(full_path):
                file_names.append(f"{entry}/")
            else:
                file_names.append(entry)
                
        result = f"Files in {target_path}:\n" + "\n".join(file_names)
        return [{"type": "text", "text": result}]
    except Exception as e:
        return [{"type": "text", "text": f"failed to read dir: {str(e)}"}]


def handle_read_content(args):
    target_path = args.get("path")
    if not isinstance(target_path, str):
        raise ValueError("path is required and must be a string")
        
    if not is_path_allowed(target_path):
        raise PermissionError("path is outside the allowed directory (POLARIS_KB_ALLOWED_DIR)")
        
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = f.read()
        return [{"type": "text", "text": data}]
    except UnicodeDecodeError:
        return [{"type": "text", "text": "failed to read file: File is binary or not UTF-8 encoded."}]
    except Exception as e:
        return [{"type": "text", "text": f"failed to read file: {str(e)}"}]


# ---------------------------------------------------------------------------
# MCP JSON-RPC server
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "list_files",
        "description": "List files in a given directory path",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The absolute path to the directory"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "read_content",
        "description": "Read the textual content of a specific file",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The absolute path to the file"
                }
            },
            "required": ["path"]
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
                    "serverInfo": {"name": "polaris-knowledge-base-mcp", "version": "1.0.0"},
                })
            elif method == "ping":
                _send_result(req_id, {})
            elif method == "tools/list":
                _send_result(req_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = req.get("params", {})
                tool_name = params.get("name")
                args = params.get("arguments", {})
                
                if tool_name == "list_files":
                    result = handle_list_files(args)
                    _send_result(req_id, {"content": result})
                elif tool_name == "read_content":
                    result = handle_read_content(args)
                    _send_result(req_id, {"content": result})
                else:
                    _send_error(req_id, -32601, f"Tool not found: {tool_name}")
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
