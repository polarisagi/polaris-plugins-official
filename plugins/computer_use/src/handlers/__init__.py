from .screen import handle_screenshot, handle_get_screen_state, handle_get_ui_tree
from .apps import handle_open_app, handle_get_running_apps, handle_send_message_to
from .interaction import (
    handle_click_element_by_id,
    handle_click_element_by_name,
    handle_focus_input,
)
from .mouse import (
    handle_left_click,
    handle_right_click,
    handle_double_click,
    handle_mouse_move,
    handle_scroll,
    handle_left_click_drag,
)
from .keyboard import handle_type, handle_key, handle_clear_and_type

__all__ = [
    "handle_screenshot",
    "handle_get_screen_state",
    "handle_get_ui_tree",
    "handle_open_app",
    "handle_get_running_apps",
    "handle_send_message_to",
    "handle_click_element_by_id",
    "handle_click_element_by_name",
    "handle_focus_input",
    "handle_left_click",
    "handle_right_click",
    "handle_double_click",
    "handle_mouse_move",
    "handle_type",
    "handle_key",
    "handle_clear_and_type",
    "handle_scroll",
    "handle_left_click_drag",
]
