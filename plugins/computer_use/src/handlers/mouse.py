import utils
from utils import mouse, Button


def _has_coords(args) -> bool:
    """Return True when explicit coordinate was provided (including [0,0])."""
    c = args.get("coordinate")
    return isinstance(c, (list, tuple)) and len(c) >= 2


def _get_coords(args):
    c = args.get("coordinate", [0, 0])
    return int(c[0]), int(c[1])


def handle_mouse_move(args):
    utils.restore_focus_if_needed()
    x, y = _get_coords(args)
    mouse.position = (x, y)
    return [{"type": "text", "text": "success"}]


def handle_left_click(args):
    utils.restore_focus_if_needed()
    if _has_coords(args):
        x, y = _get_coords(args)
        mouse.position = (x, y)
    mouse.click(Button.left)
    return [{"type": "text", "text": "success"}]


def handle_right_click(args):
    utils.restore_focus_if_needed()
    if _has_coords(args):
        x, y = _get_coords(args)
        mouse.position = (x, y)
    mouse.click(Button.right)
    return [{"type": "text", "text": "success"}]


def handle_double_click(args):
    utils.restore_focus_if_needed()
    if _has_coords(args):
        x, y = _get_coords(args)
        mouse.position = (x, y)
    mouse.click(Button.left, 2)
    return [{"type": "text", "text": "success"}]


def handle_middle_click(args):
    """中键点击：在浏览器中可新标签打开链接。"""
    utils.restore_focus_if_needed()
    if _has_coords(args):
        x, y = _get_coords(args)
        mouse.position = (x, y)
    mouse.click(Button.middle)
    return [{"type": "text", "text": "success"}]


def handle_triple_click(args):
    """三击：选中整行或整段文字。"""
    utils.restore_focus_if_needed()
    if _has_coords(args):
        x, y = _get_coords(args)
        mouse.position = (x, y)
    mouse.click(Button.left, 3)
    return [{"type": "text", "text": "success"}]


def handle_left_click_drag(args):
    """
    拖拽鼠标。
    - start_coordinate: [x, y] 拖拽起点（可选，不传则从当前位置开始）
    - coordinate: [x, y] 拖拽终点（必须）
    """
    utils.restore_focus_if_needed()
    import time

    # 移动到起点
    sc = args.get("start_coordinate")
    if isinstance(sc, (list, tuple)) and len(sc) >= 2:
        mouse.position = (int(sc[0]), int(sc[1]))
        time.sleep(0.05)

    if not _has_coords(args):
        return [{"type": "text", "text": "Invalid destination coordinates for drag"}]

    x, y = _get_coords(args)
    mouse.press(Button.left)
    time.sleep(0.1)
    mouse.position = (x, y)
    time.sleep(0.1)
    mouse.release(Button.left)
    return [{"type": "text", "text": f"Dragged to ({x}, {y})"}]


def handle_scroll(args):
    """
    在指定坐标处滚动。
    - coordinate: [x, y] 滚动位置（可选，不传则在当前鼠标位置滚动）
    - amount: 滚动量（正值向上，负值向下）
    """
    utils.restore_focus_if_needed()
    if _has_coords(args):
        x, y = _get_coords(args)
        mouse.position = (x, y)
    try:
        amount = float(args.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0
    if amount == 0:
        return [{"type": "text", "text": "Invalid or missing scroll amount"}]
    mouse.scroll(0, amount)
    return [{"type": "text", "text": f"Scrolled by {amount}"}]


def handle_cursor_position(args):
    """返回当前鼠标光标的屏幕坐标（格式：x,y）。"""
    pos = mouse.position
    x, y = int(pos[0]), int(pos[1])
    return [{"type": "text", "text": f"{x},{y}"}]
