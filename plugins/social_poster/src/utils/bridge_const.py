"""Polaris Browser Bridge 常量定义。

为何定义为常量：
1. EXTENSION_ID 由固定 RSA 公钥 DER 的 SHA-256 哈希值计算得出，确保中继严格校验 Origin；
2. 端口范围 18790-18799 允许多个插件进程（如 browser_use、social_poster）各占一个中继端口。
"""

from __future__ import annotations

EXTENSION_ID = "ccdonkdehfibjcejkfjoicdklfdffjeh"
BRIDGE_PORT_START = 18790
BRIDGE_PORT_END = 18799
