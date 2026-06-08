---
name: system_info
description: "Decision guide for using the system_info MCP plugin to gather environment context."
version: "1.0.0"
tags:
  - system-info
  - context
  - environment
exec_mode: ambient
risk_level: low
sandbox: L2
capability: read-only
---

## 1. Architecture

The `system_info` tool serves as the primary environmental context provider for the AI agent to verify software installations without triggering massive, context-bloating file system scans.
Note: General system properties (OS, locale, architecture, timezone) are automatically injected into the Agent's startup prompt by the core framework. Do not use MCP tools to fetch them.

| Tool | When to use | Operations |
|-------|-------------|------------|
| `check_app_installed` | To verify software availability | Returns true/false and paths if the requested software is installed. |

---

## 2. Decision Tree

```
Agent needs to know about the environment?
  └─ Is it about whether a specific app exists?
      └─ Yes → call `check_app_installed` with app_name
```

---

## 3. Checking Installed Apps

Instead of executing `find /` or scanning the entire disk, use `check_app_installed`.

```jsonc
{
  "action": "check_app_installed",
  "app_name": "WeChat"
}
```

This tool safely checks standard installation paths specific to the detected OS (`/Applications` on Mac, `C:\Program Files` on Windows) using case-insensitive substring matching.

**Expected Result**:
```jsonc
{
  "installed": true,
  "found_paths": [
    "/Applications/微信.app"
  ]
}
```

**Error Handling**: If `installed` is `false`, the agent should suggest alternative applications to the user or ask them to download the required software.
