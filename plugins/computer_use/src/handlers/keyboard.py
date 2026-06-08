import utils
from utils import mouse, Button
import time
import platform
try:
    import mss
except ImportError:
    pass

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
    return [{"type": "text", "text": f"Typed: {text[:60]}{'...' if len(text) > 60 else ''}"}]
