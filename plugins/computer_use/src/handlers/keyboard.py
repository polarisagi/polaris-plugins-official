import utils
import time
import platform


def handle_type(args):
    utils.restore_focus_if_needed()
    utils.clipboard_type(args.get("text", ""))
    return [{"type": "text", "text": "success"}]


def handle_key(args):
    utils.restore_focus_if_needed()
    utils.press_shortcut(args.get("text", ""))
    return [{"type": "text", "text": "success"}]


def handle_clear_and_type(args):
    utils.restore_focus_if_needed()
    text = args.get("text", "")
    utils.clear_field()
    time.sleep(0.1)
    utils.clipboard_type(text)
    return [
        {"type": "text", "text": f"Typed: {text[:60]}{'...' if len(text) > 60 else ''}"}
    ]


def handle_hold_key(args):
    """
    按住修饰键的同时执行一次左键点击。
    - text: 要按住的键（'shift', 'cmd', 'ctrl', 'alt'）
    - coordinate: 点击坐标（可选）
    """
    from pynput.mouse import Controller as _MC, Button as _Btn

    key_str = args.get("text", "").lower().strip()
    if not key_str:
        raise Exception("hold_key requires 'text' (the key to hold, e.g. 'shift')")

    utils.restore_focus_if_needed()

    target = utils._PYNPUT_KEY_MAP.get(key_str)
    if target is None and len(key_str) == 1:
        target = key_str
    if target is None:
        raise Exception(f"Unsupported key for hold_key: '{key_str}'")

    m = _MC()
    coord = args.get("coordinate")
    if isinstance(coord, (list, tuple)) and len(coord) >= 2:
        m.position = (int(coord[0]), int(coord[1]))

    with utils.keyboard.pressed(target):
        m.click(_Btn.left)

    return [{"type": "text", "text": f"Held '{key_str}' and clicked"}]


def handle_wait(args):
    """等待指定毫秒，让 UI 动画/网络请求等完成。"""
    try:
        duration_ms = float(args.get("duration_ms", args.get("amount", 1000)))
    except (TypeError, ValueError):
        duration_ms = 1000
    duration_ms = max(0, min(duration_ms, 30000))  # 上限 30 秒
    time.sleep(duration_ms / 1000.0)
    return [{"type": "text", "text": f"Waited {duration_ms:.0f}ms"}]


def handle_read_clipboard(args):
    """读取系统剪贴板当前文本内容。"""
    import subprocess

    plat = platform.system()
    try:
        if plat == "Darwin":
            text = subprocess.check_output(["pbpaste"]).decode(
                "utf-8", errors="replace"
            )
        else:
            import pyperclip

            text = pyperclip.paste()
        return [{"type": "text", "text": text}]
    except Exception as e:
        return [{"type": "text", "text": f"[clipboard read error: {e}]"}]


def handle_write_clipboard(args):
    """将文本写入系统剪贴板，不触发粘贴。用于跨 action 传递内容。"""
    import subprocess

    text = args.get("text", "")
    plat = platform.system()
    try:
        if plat == "Darwin":
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        else:
            import pyperclip

            pyperclip.copy(text)
        return [{"type": "text", "text": f"Clipboard set ({len(text)} chars)"}]
    except Exception as e:
        return [{"type": "text", "text": f"[clipboard write error: {e}]"}]


def handle_zoom(args):
    """
    放大/缩小。
    - amount: 正数放大，负数缩小
    """
    import utils
    import platform

    amount = float(args.get("amount", 0))
    if amount == 0:
        return [{"type": "text", "text": "Zoom amount cannot be 0"}]

    plat = platform.system()
    if plat == "Darwin":
        sc = "cmd+=" if amount > 0 else "cmd+-"
    else:
        sc = "ctrl+=" if amount > 0 else "ctrl+-"

    utils.restore_focus_if_needed()
    utils.press_shortcut(sc)
    return [{"type": "text", "text": f"Zoomed {'in' if amount > 0 else 'out'}"}]
