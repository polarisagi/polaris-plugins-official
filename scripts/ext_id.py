#!/usr/bin/env python3
"""计算 Chrome 扩展的公钥 Base64 与固定 Extension ID。

原理：
Chrome 扩展 ID 为其 RSA 公钥 SubjectPublicKeyInfo (DER) 的 SHA-256 哈希值
前 128 位（16 字节，32 个十六进制半字节）映射为 'a'-'p' 编码。
"""

from __future__ import annotations

import base64
import hashlib
import subprocess
import sys
from pathlib import Path


def get_public_der(pem_path: Path) -> bytes:
    """使用 openssl 提取 RSA 公钥的 DER 字节。"""
    cmd = ["openssl", "rsa", "-in", str(pem_path), "-pubout", "-outform", "DER"]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    return proc.stdout


def der_to_ext_id(der: bytes) -> str:
    """根据 DER 字节生成 32 字符的 Chrome 扩展 ID。"""
    h = hashlib.sha256(der).hexdigest()[:32]
    # 0 -> 'a' (ord 'a' + 0), 1 -> 'b', ... f -> 'p'
    table = {f"{i:x}": chr(ord("a") + i) for i in range(16)}
    return "".join(table[c] for c in h)


def main() -> None:
    # 签名私钥不在仓库内：默认位于运行时配置目录，也可由第一个参数指定
    key_pem = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path.home()
        / ".config"
        / "polaris-plugins"
        / "browser"
        / "extension-signing-key.pem"
    )
    if not key_pem.exists():
        print(f"Key file not found: {key_pem}")
        return

    der = get_public_der(key_pem)
    b64_key = base64.b64encode(der).decode("ascii")
    ext_id = der_to_ext_id(der)

    print("=== Extension Public Key (Base64) ===")
    print(b64_key)
    print("=== Chrome Extension ID ===")
    print(ext_id)


if __name__ == "__main__":
    main()
