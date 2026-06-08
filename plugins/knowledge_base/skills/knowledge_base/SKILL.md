---
name: knowledge_base
description: "Use the knowledge base MCP tool to explore and read files within the allowed directory."
version: "1.0.0"
tags:
  - knowledge-base
  - search
  - context
exec_mode: ambient
risk_level: low
sandbox: L2
capability: read-only
---

When interacting with the knowledge base:
1. **Explore First**: Always list files in a directory using `list_files` first to understand its structure before attempting to read specific files.
2. **Targeted Reading**: Only use `read_content` for files that are strictly relevant to your current task to save context window and processing time.
3. **Security Boundary**: Be aware that the tool restricts access to an allowed directory (defined by `POLARIS_KB_ALLOWED_DIR`); do not attempt to read system files or sensitive data outside of this workspace.
