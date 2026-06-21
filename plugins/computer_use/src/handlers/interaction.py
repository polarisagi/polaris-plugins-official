import os
import json
import subprocess
import time
import platform
import tempfile
import utils
from utils import mouse, Button

import mss


def handle_click_element_by_id(args):
    element_id = str(args.get("id"))
    if not element_id:
        raise Exception("Missing id parameter")

    state_file = os.path.join(tempfile.gettempdir(), "computer_use_state.json")
    if not os.path.exists(state_file):
        raise Exception("No screen state found. Call get_screen_state first.")

    try:
        with open(state_file, "r") as f:
            state_data = json.load(f)
    except Exception as e:
        raise Exception(f"Failed to read screen state: {e}")

    app_name = state_data.get("metadata", {}).get("app_name")
    id_map = state_data.get("elements", {})

    if element_id not in id_map:
        raise Exception(f"Element ID {element_id} not found in current screen state.")

    target = id_map[element_id]

    # Restore context focus before execution
    if app_name and platform.system() == "Darwin":
        utils.ensure_frontmost(app_name, app_name)
        time.sleep(0.3)

    utils.safe_click(int(target["x"]), int(target["y"]), "", "")
    return [
        {
            "type": "text",
            "text": f"Clicked element {element_id} ({target.get('name') or target.get('text')}) at ({target['x']}, {target['y']})",
        }
    ]


def _click_by_jxa(elem_name: str, match_index: int) -> tuple[int, int] | None:
    """Try to find element via JXA accessibility tree. Returns (x, y) or None."""
    js_name = json.dumps(elem_name)
    js_idx = int(match_index)
    jxa = f"""
    function run() {{
        const se = Application('System Events');
        const procs = se.processes.whose({{ frontmost: true }})();
        if (!procs.length) return "Not found";
        const win = procs[0].windows()[0];
        const needle = {js_name};
        let matches = [];
        function traverse(el, depth) {{
            if (depth > 6) return;
            try {{
                const name = el.name();
                if (name && name.indexOf(needle) !== -1) {{
                    const pos = el.position(), sz = el.size();
                    if (pos && sz) matches.push({{x: Math.round(pos[0]+sz[0]/2),
                                                   y: Math.round(pos[1]+sz[1]/2)}});
                }}
                const kids = el.uiElements();
                for (let i = 0; i < kids.length; i++) traverse(kids[i], depth + 1);
            }} catch(e) {{}}
        }}
        if (win) traverse(win, 0);
        if (!matches.length) return "Not found";
        const idx = {js_idx} < 0 ? matches.length + {js_idx} : {js_idx};
        const m = matches[Math.min(Math.max(idx, 0), matches.length - 1)];
        return m.x + "," + m.y;
    }}
    """
    out = (
        subprocess.check_output(
            ["osascript", "-l", "JavaScript", "-e", jxa], timeout=10
        )
        .decode()
        .strip()
    )
    if out == "Not found":
        return None
    x, y = map(int, out.split(","))
    return x, y


def _click_by_ocr(elem_name: str, match_index: int) -> tuple[int, int]:
    """Find element via Swift OCR fallback. Returns (x, y) or raises."""
    base = os.path.join(os.path.dirname(__file__), "..")
    swift_exe = os.path.join(base, "find_text_on_screen")
    if not os.path.exists(swift_exe):
        subprocess.run(
            [
                "swiftc",
                os.path.join(base, "find_text_on_screen.swift"),
                "-o",
                swift_exe,
            ],
            check=True,
        )

    tmp_path = os.path.join(
        tempfile.gettempdir(), f"ocr_temp_{os.urandom(4).hex()}.png"
    )
    with mss.MSS() as sct:
        filename = sct.shot(output=tmp_path)
    try:
        ocr_out = (
            subprocess.check_output([swift_exe, filename, elem_name], timeout=15)
            .decode()
            .strip()
        )
    finally:
        if os.path.exists(filename):
            os.remove(filename)

    if not ocr_out or "Failed" in ocr_out:
        raise Exception(f"Element '{elem_name}' not found (OCR failed)")
    lines = [ln for ln in ocr_out.split("\n") if "," in ln]
    if not lines:
        raise Exception(f"Element '{elem_name}' not found on screen")
    idx = match_index if match_index >= 0 else max(0, len(lines) + match_index)
    x, y = map(float, lines[min(idx, len(lines) - 1)].split(","))
    return int(x), int(y)


def _click_darwin(elem_name: str, match_index: int) -> tuple[int, int]:
    """macOS: try JXA first, fall back to OCR."""
    coords = _click_by_jxa(elem_name, match_index)
    if coords is None:
        coords = _click_by_ocr(elem_name, match_index)
    return coords


def _click_windows(elem_name: str, match_index: int) -> tuple[int, int]:
    """Windows: use pywinauto accessibility."""
    from pywinauto import Desktop

    win = Desktop(backend="uia").windows(visible_only=True)[0]
    matches = [c for c in win.descendants() if elem_name in c.window_text()]
    if not matches:
        raise Exception(f"Element '{elem_name}' not found")
    idx = match_index if match_index >= 0 else max(0, len(matches) + match_index)
    pt = matches[min(idx, len(matches) - 1)].rectangle().mid_point()
    return pt.x, pt.y


def _click_linux(elem_name: str, match_index: int) -> tuple[int, int]:
    """Linux: use AT-SPI accessibility."""
    import pyatspi

    desktop = pyatspi.Registry.getDesktop(0)
    active_win = None
    for app in desktop:
        for window in app:
            if window.getState().contains(pyatspi.STATE_ACTIVE):
                active_win = window
                break
        if active_win:
            break
    if not active_win:
        raise Exception("No active window")

    matches: list[tuple[int, int]] = []

    def _traverse(node, depth):
        if not node or depth > 6:
            return
        try:
            if elem_name in (node.name or ""):
                ext = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
                if ext.width > 0:
                    matches.append((ext.x + ext.width // 2, ext.y + ext.height // 2))
        except Exception:
            pass
        for child in node:
            _traverse(child, depth + 1)

    _traverse(active_win, 0)
    if not matches:
        raise Exception(f"Element '{elem_name}' not found")
    idx = match_index if match_index >= 0 else max(0, len(matches) + match_index)
    return matches[min(idx, len(matches) - 1)]


def handle_click_element_by_name(args):
    elem_name = args.get("element_name") or args.get("text")
    match_index = int(args.get("index", 0))
    if not elem_name:
        raise Exception("Missing element_name")

    plat = platform.system()
    if plat == "Darwin":
        x, y = _click_darwin(elem_name, match_index)
        utils.safe_click(x, y, "", "")
        return [{"type": "text", "text": f"Clicked '{elem_name}' at {x},{y}"}]

    if plat == "Windows":
        x, y = _click_windows(elem_name, match_index)
        mouse.position = (x, y)
        mouse.click(Button.left)
        return [{"type": "text", "text": f"Clicked '{elem_name}'"}]

    # Linux
    pos = _click_linux(elem_name, match_index)
    mouse.position = pos
    mouse.click(Button.left)
    return [{"type": "text", "text": f"Clicked '{elem_name}' at {pos}"}]


def handle_focus_input(args):
    hint = args.get("hint", "AXTextArea")
    app_name = args.get("app_name")
    plat = platform.system()

    # Attempt to restore context focus if available in state and not passed explicitly
    state_file = os.path.join(tempfile.gettempdir(), "computer_use_state.json")
    if not app_name and os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                state_data = json.load(f)
                app_name = state_data.get("metadata", {}).get("app_name")
        except Exception:
            pass

    if plat == "Darwin":
        if app_name:
            utils.ensure_frontmost(app_name, app_name)
            time.sleep(0.3)

        coords = utils.find_input_field(role_hint=hint)
        if coords:
            x, y = coords
            mouse.position = (x, y)
            mouse.click(Button.left)
            time.sleep(0.1)
            return [
                {"type": "text", "text": f"Focused input at {x},{y} (accessibility)"}
            ]

        bounds = utils.get_frontmost_window_bounds()
        if bounds:
            x = bounds["x"] + bounds["w"] // 2
            y = bounds["y"] + int(bounds["h"] * 0.88)
            mouse.position = (x, y)
            mouse.click(Button.left)
            time.sleep(0.1)
            return [
                {"type": "text", "text": f"Focused input at {x},{y} (window fallback)"}
            ]

    with mss.MSS() as sct:
        m = sct.monitors[1]
        x = m["left"] + m["width"] // 2
        y = m["top"] + int(m["height"] * 0.88)
    mouse.position = (x, y)
    mouse.click(Button.left)
    time.sleep(0.1)
    return [{"type": "text", "text": f"Focused input at {x},{y} (screen fallback)"}]
