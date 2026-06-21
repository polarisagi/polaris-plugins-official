import os
import json
import time
import platform
import tempfile
import subprocess
import base64

import utils

_DESCRIBE_SRC = os.path.join(os.path.dirname(__file__), "..", "describe_screen.swift")
_DESCRIBE_BIN = os.path.join(os.path.dirname(__file__), "..", "describe_screen")


def _ensure_describe_binary() -> bool:
    """Compile describe_screen.swift if not already built. Returns True on success."""
    if os.path.exists(_DESCRIBE_BIN):
        return True
    if not os.path.exists(_DESCRIBE_SRC):
        return False
    try:
        subprocess.run(
            ["swiftc", _DESCRIBE_SRC, "-o", _DESCRIBE_BIN],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return True
    except Exception:
        return False


def handle_get_ui_tree(args):
    plat = platform.system()
    if plat == "Darwin":
        jxa = """
        function run() {
            const se = Application('System Events');
            const procs = se.processes.whose({ frontmost: true })();
            if (!procs.length) return JSON.stringify([]);
            const wins = procs[0].windows();
            let elements = [];
            function traverse(el, depth) {
                if (depth > 6) return;
                try {
                    const role = el.role(), name = el.name();
                    const pos = el.position(), sz = el.size();
                    if (pos && sz) {
                        if (name || role === 'AXButton' || role === 'AXTextField' || role === 'AXTextArea')
                            elements.push({role, name: name || '',
                                           x: Math.round(pos[0]+sz[0]/2),
                                           y: Math.round(pos[1]+sz[1]/2)});
                    }
                    const kids = el.uiElements();
                    for (let i = 0; i < kids.length; i++) traverse(kids[i], depth + 1);
                } catch(e) {}
            }
            for (let w = 0; w < wins.length; w++) {
                traverse(wins[w], 0);
            }
            return JSON.stringify(elements);
        }
        """
        try:
            out = subprocess.check_output(
                ["osascript", "-l", "JavaScript", "-e", jxa], timeout=10
            ).decode()
            return [{"type": "text", "text": out.strip()}]
        except Exception:
            return [{"type": "text", "text": "[]"}]

    elif plat == "Windows":
        try:
            from pywinauto import Desktop

            win = Desktop(backend="uia").windows(visible_only=True)[0]
            elements = [
                {
                    "role": c.friendly_class_name(),
                    "name": c.window_text(),
                    "x": c.rectangle().mid_point().x,
                    "y": c.rectangle().mid_point().y,
                }
                for c in win.descendants()
            ]
            return [{"type": "text", "text": json.dumps(elements)}]
        except Exception as e:
            return [{"type": "text", "text": json.dumps({"error": str(e)})}]

    else:
        try:
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
                return [{"type": "text", "text": "[]"}]
            elements = []

            def traverse(node, depth):
                if not node or depth > 6:
                    return
                try:
                    ext = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
                    if ext.width > 0:
                        elements.append(
                            {
                                "role": node.getRoleName(),
                                "name": node.name or "",
                                "x": ext.x + ext.width // 2,
                                "y": ext.y + ext.height // 2,
                            }
                        )
                except Exception:
                    pass
                for child in node:
                    traverse(child, depth + 1)

            traverse(active_win, 0)
            return [{"type": "text", "text": json.dumps(elements)}]
        except ImportError:
            return [
                {
                    "type": "text",
                    "text": json.dumps([{"error": "install python3-pyatspi"}]),
                }
            ]
        except Exception as e:
            return [{"type": "text", "text": json.dumps([{"error": str(e)}])}]


def _collect_ui_elements(
    app_name: str, lines: list, id_map: dict, start_id: int
) -> int:
    """Populate lines/id_map with accessibility-tree elements. Returns next free id."""
    current_id = start_id
    try:
        if app_name and platform.system() == "Darwin":
            utils.ensure_frontmost(app_name, app_name)
            time.sleep(0.5)

        ax_result = handle_get_ui_tree({})
        if not (ax_result and ax_result[0].get("text")):
            return current_id

        ax_data = json.loads(ax_result[0]["text"])
        if not isinstance(ax_data, list):
            return current_id

        lines.append("=== UI Elements ===")
        for el in ax_data[:80]:
            if "error" in el:
                continue
            role = el.get("role", "")
            name = el.get("name", "")
            x, y = el.get("x", 0), el.get("y", 0)
            if x > 0 and y > 0 and name:
                id_map[str(current_id)] = {"x": x, "y": y, "type": "UI", "name": name}
                lines.append(f'[{current_id}] [{role}] "{name}"')
                current_id += 1
    except Exception as exc:
        lines.append(f"UI tree unavailable: {exc}")
    return current_id


def _collect_ocr_text(app_name: str, lines: list, id_map: dict, start_id: int) -> int:
    """Populate lines/id_map with OCR-detected text (macOS only). Returns next free id."""
    current_id = start_id
    if platform.system() != "Darwin" or not _ensure_describe_binary():
        return current_id

    tmp_path = ""
    try:
        tmp_path, x_off, y_off = utils.capture_screen(app_name=app_name)
        if not (tmp_path and os.path.exists(tmp_path)):
            return current_id

        ocr_raw = (
            subprocess.check_output([_DESCRIBE_BIN, tmp_path], timeout=15)
            .decode()
            .strip()
        )
        if not ocr_raw:
            return current_id

        lines.append("\n=== Screen Text (OCR) ===")
        for ocr_line in ocr_raw.splitlines()[:100]:
            parts = ocr_line.split("|")
            if len(parts) == 3:
                text = parts[0]
                abs_x = int(float(parts[1])) + x_off
                abs_y = int(float(parts[2])) + y_off
                id_map[str(current_id)] = {
                    "x": abs_x,
                    "y": abs_y,
                    "type": "OCR",
                    "text": text,
                }
                lines.append(f'[{current_id}] "{text}"')
                current_id += 1
    except Exception as exc:
        lines.append(f"\nOCR unavailable: {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    return current_id


def handle_get_screen_state(args):
    """
    Returns a textual representation of the screen (or app window) with numeric IDs.
    Combines accessibility-tree UI elements and OCR-detected text.
    """
    app_name = args.get("app_name", "")
    lines: list[str] = []
    id_map: dict = {}

    next_id = _collect_ui_elements(app_name, lines, id_map, start_id=1)
    _collect_ocr_text(app_name, lines, id_map, start_id=next_id)

    state_file = os.path.join(tempfile.gettempdir(), "computer_use_state.json")
    try:
        with open(state_file, "w") as f:
            json.dump(
                {
                    "metadata": {"app_name": app_name, "timestamp": time.time()},
                    "elements": id_map,
                },
                f,
            )
    except Exception as e:
        lines.append(f"\nError saving state: {e}")

    return [{"type": "text", "text": "\n".join(lines) or "No screen state available"}]


def handle_screenshot(args):
    app_name = args.get("app_name", "")
    mode = args.get("mode", "base64")

    save_screenshots = False
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "config.json"
    )
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                c = json.load(f)
                save_screenshots = bool(c.get("save_screenshots", False))
        except Exception:
            pass

    # Save the app_name to state so that subsequent low-level mouse clicks restore focus
    state_file = os.path.join(tempfile.gettempdir(), "computer_use_state.json")
    try:
        # We only override metadata.elements if it doesn't exist, to avoid breaking text-only mode accidentally,
        # but screenshot is for multimodal so it's fine to just save the metadata.
        state_data = {
            "metadata": {"app_name": app_name, "timestamp": time.time()},
            "elements": {},
        }
        with open(state_file, "w") as f:
            json.dump(state_data, f)
    except Exception:
        pass

    try:
        tmp_path, _, _ = utils.capture_screen(app_name=app_name)
        if tmp_path and os.path.exists(tmp_path):
            if mode == "path":
                return [{"type": "text", "text": f"Screenshot saved to {tmp_path}"}]
            with open(tmp_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            return [{"type": "image", "data": b64, "mimeType": "image/png"}]
        return [{"type": "text", "text": "Screenshot failed"}]
    finally:
        if "tmp_path" in locals() and tmp_path and os.path.exists(tmp_path):
            if not save_screenshots and mode != "path":
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass


def handle_get_screen_info(args):
    """获取当前主显示器的分辨率、缩放比例(scale factor)"""
    plat = platform.system()
    if plat == "Darwin":
        jxa = """
        function run() {
            const app = Application('Finder');
            const b = app.desktop.window.bounds();
            return JSON.stringify({width: b.width, height: b.height, scale: 2.0});
        }
        """
        try:
            out = (
                subprocess.check_output(
                    ["osascript", "-l", "JavaScript", "-e", jxa], timeout=5
                )
                .decode()
                .strip()
            )
            return [{"type": "text", "text": out}]
        except Exception:
            pass
    import mss

    with mss.mss() as sct:
        m = sct.monitors[1]
        return [
            {
                "type": "text",
                "text": json.dumps(
                    {"width": m["width"], "height": m["height"], "scale": 1.0}
                ),
            }
        ]
