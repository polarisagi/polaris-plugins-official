"""
read_messages_from: 从聊天应用读取最近消息（macOS 专用，使用 OCR）。
"""

import os
import subprocess
import time
import platform

import utils
from profiles_loader import APP_PROFILES, resolve


def handle_read_messages_from(args):
    """
    读取指定聊天联系人/群聊的最近消息。
    - contact_name: 联系人/群聊名称（必须）
    - app: 聊天应用别名（'wechat', 'slack', etc.）
    - count: 读取消息数量提示（实际通过 OCR 识别，默认尽可能多）

    实现策略（macOS）：
    1. 通过 send_message_to 的搜索逻辑打开目标对话
    2. 截图聊天区域
    3. 通过 describe_screen 进行 OCR 文字识别
    4. 返回识别出的文字内容
    """
    if platform.system() != "Darwin":
        return [{"type": "text", "text": "read_messages_from is currently macOS only"}]

    contact_name = args.get("contact_name", "").strip()
    if not contact_name:
        raise Exception("read_messages_from requires 'contact_name'")

    app_key = args.get("app", args.get("app_name", "wechat")).strip().lower()
    profile = APP_PROFILES.get(app_key)
    if not profile:
        raise Exception(f"Unknown app '{app_key}'")

    # Step 1: 打开对话（复用 open_app + 搜索逻辑）
    from handlers.apps import handle_open_app

    # 只做"打开并找到联系人"，不发消息 — 用空消息会报错，改为只搜索并点击
    # 通过复用 send_message_to 内部逻辑打开对话（发一个空白消息）
    # 注意：这里需要实际点击进入对话，但不发送消息
    # 实现：触发搜索 → 选择联系人 → 进入对话 → 截图
    proc_name = profile.get("process_name", app_key)
    open_name = profile.get("open_name", proc_name)
    bundle_id = profile.get("bundle_id", "")
    search_sc = resolve(profile.get("search_shortcut", "cmd+f"))

    # 激活应用
    handle_open_app(
        {"app_name": open_name, "open_name": open_name, "bundle_id": bundle_id}
    )
    time.sleep(1.5)

    # 打开搜索
    utils.press_shortcut(search_sc)
    time.sleep(0.5)
    utils.clear_field()
    time.sleep(0.1)
    utils.clipboard_type(contact_name)
    time.sleep(float(profile.get("wait_before_ocr", 1.5)))

    # 键盘选择第一个结果（下键 + 回车）
    utils.press_shortcut("down")
    time.sleep(0.2)
    utils.press_shortcut("enter")
    time.sleep(1.0)

    # Step 2: 截图聊天区域
    _DESCRIBE_BIN = os.path.join(os.path.dirname(__file__), "..", "describe_screen")
    _DESCRIBE_SRC = os.path.join(
        os.path.dirname(__file__), "..", "describe_screen.swift"
    )
    if not utils.compile_swift_binary(_DESCRIBE_SRC, _DESCRIBE_BIN):
        return [{"type": "text", "text": "OCR binary unavailable"}]

    tmp_path, x_off, y_off = utils.capture_screen(app_name=open_name)

    try:
        if not (tmp_path and os.path.exists(tmp_path)):
            return [{"type": "text", "text": "Screenshot failed"}]

        ocr_raw = (
            subprocess.check_output([_DESCRIBE_BIN, tmp_path], timeout=15)
            .decode()
            .strip()
        )

        if not ocr_raw:
            return [{"type": "text", "text": f"No text found in {contact_name}'s chat"}]

        # 整理 OCR 输出为消息列表（格式：text|x|y）
        lines = []
        for line in ocr_raw.splitlines():
            parts = line.split("|")
            if len(parts) >= 1:
                lines.append(parts[0])

        return [
            {
                "type": "text",
                "text": f"Messages in '{contact_name}':\n" + "\n".join(lines),
            }
        ]

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
