"""让已配对的 Polaris Browser Bridge 扩展从磁盘重新加载（开发调试用）。

运行方式（在 plugins/social 目录）：
    uv run python scripts/bridge_reload.py

仅对「加载已解压的扩展程序」方式安装的开发版有效；修改 extension/ 下的代码后执行一次，
免去到 chrome://extensions 手动点「重新加载」。扩展日志见
~/.config/polaris-plugins/browser/bridge_ext.log。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.bridge_relay import get_or_start_relay
from src.utils.browser_hub import HubError


async def main() -> int:
    relay = await get_or_start_relay()
    # 扩展每 30 秒探测一次中继端口（存活期内 2 秒重试），等待一个完整周期
    if not await relay.wait_for_extension(timeout=40.0):
        print(
            json.dumps(
                {"ok": False, "error": "40 秒内扩展未连接中继"}, ensure_ascii=False
            )
        )
        return 1
    try:
        res = await relay.reload_extension()
    except HubError as e:
        print(json.dumps({"ok": False, "error": e.message}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {"ok": True, "previous_version": res.get("version")}, ensure_ascii=False
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
