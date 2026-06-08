import utils
from utils import mouse, Button

def _get_coords(args):
    x, y = 0, 0
    if args.get("coordinate") and len(args["coordinate"]) >= 2:
        x, y = int(args["coordinate"][0]), int(args["coordinate"][1])
    return x, y

def handle_mouse_move(args):
    utils.restore_focus_if_needed()
    x, y = _get_coords(args)
    mouse.position = (x, y)
    return [{"type": "text", "text": "success"}]

def handle_left_click(args):
    utils.restore_focus_if_needed()
    x, y = _get_coords(args)
    if x > 0 or y > 0:
        mouse.position = (x, y)
    mouse.click(Button.left)
    return [{"type": "text", "text": "success"}]

def handle_right_click(args):
    utils.restore_focus_if_needed()
    x, y = _get_coords(args)
    if x > 0 or y > 0:
        mouse.position = (x, y)
    mouse.click(Button.right)
    return [{"type": "text", "text": "success"}]

def handle_double_click(args):
    utils.restore_focus_if_needed()
    x, y = _get_coords(args)
    if x > 0 or y > 0:
        mouse.position = (x, y)
    mouse.click(Button.left, 2)
    return [{"type": "text", "text": "success"}]

def handle_left_click_drag(args):
    utils.restore_focus_if_needed()
    x, y = _get_coords(args)
    if x <= 0 and y <= 0:
        return [{"type": "text", "text": "Invalid destination coordinates for drag"}]
    
    import time
    mouse.press(Button.left)
    time.sleep(0.1)
    mouse.position = (x, y)
    time.sleep(0.1)
    mouse.release(Button.left)
    return [{"type": "text", "text": f"Dragged to ({x}, {y})"}]

def handle_scroll(args):
    utils.restore_focus_if_needed()
    try:
        amount = float(args.get("amount", 0))
    except ValueError:
        amount = 0
    
    if amount == 0:
        return [{"type": "text", "text": "Invalid or missing scroll amount"}]
        
    mouse.scroll(0, amount)
    return [{"type": "text", "text": f"Scrolled by {amount}"}]
