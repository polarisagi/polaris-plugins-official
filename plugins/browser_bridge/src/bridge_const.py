"""Polaris Browser Bridge 常量定义。

为何定义为常量：
1. EXTENSION_ID 由固定 RSA 公钥 DER 的 SHA-256 哈希值计算得出，确保中继严格校验 Origin；
2. 端口范围 18790-18799 允许多个插件进程（如 browser_use、social）各占一个中继端口；
3. NATIVE_HOST_NAME 是 Chrome Native Messaging 宿主名（扩展自动获取配对令牌用），
   必须与扩展 sw.js 中的常量一致；
4. HANDSHAKE_VERSION 是中继与扩展的握手协议版本（2 = 双向 HMAC 证明，不再明文传令牌）。
"""

from __future__ import annotations

EXTENSION_ID = "ccdonkdehfibjcejkfjoicdklfdffjeh"
BRIDGE_PORT_START = 18790
BRIDGE_PORT_END = 18799
NATIVE_HOST_NAME = "online.polarisagi.bridge"
HANDSHAKE_VERSION = 2
# 握手结果文件（相对 CFG）：中继握手成功时写入，供 browser_bridge 插件廉价判断连接状态
HANDSHAKE_FILE = "bridge_last_handshake.json"
