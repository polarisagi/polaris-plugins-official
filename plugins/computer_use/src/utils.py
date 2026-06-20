"""
跨平台工具类库，供 main.py 和各适配器（adapters）共享使用。
包含所有键盘、鼠标、剪贴板和系统辅助功能（置顶、截图等）的底层辅助方法。
"""

import json
import locale as _locale_mod
import platform
import subprocess
import time
from typing import Optional

from pynput.keyboard import Controller as KeyboardController, Key
from pynput.mouse import Controller as MouseController, Button

mouse = MouseController()
keyboard = KeyboardController()

# ---------------------------------------------------------------------------
# 语言环境检测 (Locale detection)
# ---------------------------------------------------------------------------


def detect_locale() -> str:
    """如果系统语言是中文，则返回 'zh'，否则返回 'en'。"""
    if platform.system() == "Darwin":
        try:
            import subprocess

            out = subprocess.check_output(
                ["defaults", "read", "-g", "AppleLanguages"], timeout=2
            ).decode()
            if "zh" in out.lower():
                return "zh"
        except Exception:
            pass
    try:
        lang = _locale_mod.getlocale()[0] or ""
    except Exception:
        lang = ""
    return "zh" if lang.startswith("zh") else "en"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PYNPUT_KEY_MAP = {
    "enter": Key.enter,
    "return": Key.enter,
    "esc": Key.esc,
    "escape": Key.esc,
    "tab": Key.tab,
    "space": Key.space,
    "backspace": Key.backspace,
    "delete": Key.delete,
    "del": Key.delete,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
    "home": Key.home,
    "end": Key.end,
    "pageup": Key.page_up,
    "pagedown": Key.page_down,
    "ctrl": Key.ctrl,
    "alt": Key.alt,
    "shift": Key.shift,
    "cmd": Key.cmd,
    "win": Key.cmd,
    "super": Key.cmd,
    "f1": Key.f1,
    "f2": Key.f2,
    "f3": Key.f3,
    "f4": Key.f4,
    "f5": Key.f5,
    "f6": Key.f6,
    "f7": Key.f7,
    "f8": Key.f8,
    "f9": Key.f9,
    "f10": Key.f10,
    "f11": Key.f11,
    "f12": Key.f12,
}

_OSA_KEY_CODES = {
    "enter": 36,
    "return": 36,
    "delete": 51,
    "backspace": 51,
    "esc": 53,
    "escape": 53,
    "tab": 48,
    "space": 49,
    "up": 126,
    "down": 125,
    "left": 123,
    "right": 124,
    "home": 115,
    "end": 119,
    "pageup": 116,
    "pagedown": 121,
    "f1": 122,
    "f2": 120,
    "f3": 99,
    "f4": 118,
    "f5": 96,
    "f6": 97,
    "f7": 98,
    "f8": 100,
    "f9": 101,
    "f10": 109,
    "f11": 103,
    "f12": 111,
}

_OSA_MOD_MAP = {
    "cmd": "command down",
    "command": "command down",
    "ctrl": "control down",
    "control": "control down",
    "alt": "option down",
    "option": "option down",
    "shift": "shift down",
}

# ---------------------------------------------------------------------------
# 通用键盘辅助方法 (pynput — 将按键发送到当前最前端的应用程序)
# ---------------------------------------------------------------------------


def press_shortcut(shortcut: str):
    """通过 pynput 触发键盘快捷键 (默认发送到当前焦点窗口)。"""
    keys = [k.strip() for k in shortcut.lower().split("+")]
    pressed = []
    try:
        for k in keys:
            target = _PYNPUT_KEY_MAP.get(k)
            if target:
                keyboard.press(target)
                pressed.append(target)
            elif len(k) == 1:
                keyboard.press(k)
                pressed.append(k)
            else:
                raise Exception(f"Unsupported key token: '{k}'")
    finally:
        for p in reversed(pressed):
            keyboard.release(p)


def clipboard_type(text: str):
    """通过系统剪贴板粘贴文本 (比模拟键盘逐字输入更稳定且支持中文)。"""
    if platform.system() == "Darwin":
        try:
            prev = subprocess.check_output(["pbpaste"]).decode(
                "utf-8", errors="replace"
            )
        except Exception:
            prev = ""
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        time.sleep(0.05)
        press_shortcut("cmd+v")
        time.sleep(0.15)
        try:
            subprocess.run(["pbcopy"], input=prev.encode("utf-8"))
        except Exception:
            pass
    else:
        keyboard.type(text)


def clear_field():
    """在当前聚焦的输入框中执行全选并删除 (模拟 Cmd+A / Ctrl+A 然后 Delete)。"""
    press_shortcut("cmd+a" if platform.system() == "Darwin" else "ctrl+a")
    time.sleep(0.05)
    press_shortcut("delete")
    time.sleep(0.05)


# ---------------------------------------------------------------------------
# macOS AppleScript 辅助方法 — 进程级键盘操作 (可无视焦点后台发送)
# ---------------------------------------------------------------------------


def osa_send_key(proc_name: str, shortcut: str) -> bool:
    """
    通过 AppleScript 将按键直接发送给目标进程 `proc_name`。
    目标进程不需要处于最前台即可生效。
    快捷键示例: "cmd+f", "enter", "down", "cmd+a"
    """
    parts = [p.strip().lower() for p in shortcut.split("+")]
    mods, key = [], None
    for p in parts:
        if p in _OSA_MOD_MAP:
            mods.append(_OSA_MOD_MAP[p])
        else:
            key = p
    if not key:
        return False
    mod_clause = " using {" + ", ".join(mods) + "}" if mods else ""
    if key in _OSA_KEY_CODES:
        stmt = f"key code {_OSA_KEY_CODES[key]}{mod_clause}"
    elif len(key) == 1:
        stmt = f"keystroke {json.dumps(key)}{mod_clause}"
    else:
        return False
    script = f'tell application "System Events" to tell process "{proc_name}" to {stmt}'
    try:
        return (
            subprocess.run(
                ["osascript", "-e", script], capture_output=True, timeout=5
            ).returncode
            == 0
        )
    except Exception:
        return False


def osa_paste(proc_name: str, text: str) -> bool:
    """将文本复制到剪贴板，并通过进程级快捷键(Cmd+V)粘贴到 proc_name 中。"""
    try:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=3)
        time.sleep(0.08)
        return osa_send_key(proc_name, "cmd+v")
    except Exception:
        return False


def osa_clear(proc_name: str):
    """在 proc_name 当前的输入框中执行进程级全选(Cmd+A)和删除(Delete)。"""
    osa_send_key(proc_name, "cmd+a")
    time.sleep(0.06)
    osa_send_key(proc_name, "delete")
    time.sleep(0.06)


# ---------------------------------------------------------------------------
# macOS App 聚焦与窗口截图辅助方法
# ---------------------------------------------------------------------------


def ensure_frontmost(
    proc_name: str, open_name: str, bundle_id: str = "", retries: int = 2
) -> bool:
    """
    死磕到底，确保目标应用程序处于最前端 (聚焦状态)。
    特殊处理：如果目标是 "desktop" (桌面)，则自动触发跨平台的“显示桌面”操作。
    对于普通应用，如果在 macOS 上，会通过 AppleScript 多次尝试强制激活它。
    成功聚焦返回 True，否则返回 False。
    """
    plat = platform.system()

    # SPECIAL CASE: Desktop handling (cross-platform)
    target = (open_name or proc_name).strip().lower()
    if target == "desktop":
        if plat == "Darwin":
            subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to key code 103']
            )
        elif plat == "Windows":
            subprocess.run(
                [
                    "powershell",
                    "-command",
                    "(New-Object -ComObject shell.application).toggleDesktop()",
                ]
            )
        else:
            subprocess.run(["wmctrl", "-k", "on"])
        return True

    # Regular app focusing is currently macOS only
    if plat != "Darwin":
        return True

    for attempt in range(retries + 1):
        front = get_frontmost_app_name()
        if proc_name.lower() in (front or "").lower():
            return True
        if attempt < retries:
            if bundle_id:
                subprocess.run(["open", "-b", bundle_id], capture_output=True)
            else:
                subprocess.run(
                    ["osascript", "-e", f'tell application "{open_name}" to activate'],
                    capture_output=True,
                )
            # Force frontmost via System Events if bundleId can be resolved
            jxa = f"""
            try {{
                const bundleId = Application("{open_name}").id();
                if (bundleId) {{
                    Application('System Events').processes.whose({{bundleIdentifier: bundleId}})[0].frontmost = true;
                }} else {{
                    Application('System Events').processes.whose({{name: "{open_name}"}})[0].frontmost = true;
                }}
            }} catch(e) {{}}
            """
            subprocess.run(
                ["osascript", "-l", "JavaScript", "-e", jxa], capture_output=True
            )
            time.sleep(0.8)
    return False


def restore_focus_if_needed():
    """
    Reads the last 'app_name' from computer_use_state.json and pulls the app
    to the front if necessary. Called right before keyboard or mouse interactions.
    """
    import os
    import tempfile
    import time

    state_file = os.path.join(tempfile.gettempdir(), "computer_use_state.json")
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                state_data = json.load(f)
                metadata = state_data.get("metadata", {})
                if time.time() - metadata.get("timestamp", 0) > 300:
                    return
                app_name = metadata.get("app_name")
                if app_name and platform.system() == "Darwin":
                    ensure_frontmost(app_name, app_name)
                    time.sleep(0.3)
        except Exception:
            pass


# ---------------------------------------------------------------------------
def get_largest_window_bounds(proc_name: str) -> dict:
    """
    Return {x, y, w, h} of the largest visible window of proc_name.
    More reliable than windows()[0] for apps like WeChat that have small
    auxiliary windows (e.g. search dropdown) as windows()[0].
    Returns {} on failure.
    """
    js_proc = json.dumps(proc_name)
    jxa = f"""
    function run() {{
        const js_proc = {js_proc};
        let bundleId = null;
        try {{ bundleId = Application(js_proc).id(); }} catch(e) {{}}
        const se = Application('System Events');
        let procs = [];
        if (bundleId) {{
            procs = se.processes.whose({{bundleIdentifier: bundleId}})();
        }}
        if (!procs || !procs.length) {{
            procs = se.processes.whose({{name: js_proc}})();
        }}
        if (!procs || !procs.length) return 'null';
        const wins = procs[0].windows();
        let best = null, bestArea = 0;
        for (let i = 0; i < wins.length; i++) {{
            try {{
                const pos = wins[i].position(), sz = wins[i].size();
                if (!pos || !sz) continue;
                const area = sz[0] * sz[1];
                if (area > bestArea) {{
                    bestArea = area;
                    best = {{x: pos[0], y: pos[1], w: sz[0], h: sz[1]}};
                }}
            }} catch(e) {{}}
        }}
        return best ? JSON.stringify(best) : 'null';
    }}
    """
    try:
        out = (
            subprocess.check_output(
                ["osascript", "-l", "JavaScript", "-e", jxa], timeout=5
            )
            .decode()
            .strip()
        )
        if out and out != "null":
            return json.loads(out)
    except Exception:
        pass
    return {}


def get_window_id_for_process(proc_name: str) -> dict:
    """
    Use Quartz CGWindowListCopyWindowInfo to find the largest visible window
    of proc_name (matched by PID via pgrep).

    Returns {'id': wid, 'x': x, 'y': y, 'w': w, 'h': h} or {} on failure.

    Why Quartz instead of JXA:
      - Pure Python call — no subprocess spawn, no focus change.
      - On macOS, apps like WeChat use the Chinese display name '微信' in
        System Events, not 'WeChat', so JXA name-matching can fail.
      - Quartz uses the OS-level PID to find windows, which is reliable.
    """
    try:
        import Quartz as _Q

        # pgrep is a lightweight process lookup; it does NOT touch System Events
        # and does NOT cause any window-focus changes.
        pid_lines = (
            subprocess.check_output(["pgrep", "-x", proc_name], timeout=3)
            .decode()
            .strip()
            .splitlines()
        )
        if not pid_lines:
            return {}
        pid = int(pid_lines[0])

        wl = _Q.CGWindowListCopyWindowInfo(
            _Q.kCGWindowListOptionAll, _Q.kCGNullWindowID
        )
        best = None
        best_area = 0
        for w in wl:
            if w.get("kCGWindowOwnerPID") != pid:
                continue
            if w.get("kCGWindowLayer", 99) != 0:
                continue
            if w.get("kCGWindowAlpha", 0) <= 0:
                continue
            b = w.get("kCGWindowBounds", {})
            ww, wh = int(b.get("Width", 0)), int(b.get("Height", 0))
            area = ww * wh
            if area > best_area and ww > 100 and wh > 100:
                best_area = area
                best = {
                    "id": int(w["kCGWindowNumber"]),
                    "x": int(b["X"]),
                    "y": int(b["Y"]),
                    "w": ww,
                    "h": wh,
                }
        return best or {}
    except Exception:
        return {}


def capture_window_by_id(wid: int, x_off: int, y_off: int) -> tuple:
    """
    Capture a specific window using `screencapture -l <wid> -o`.

    Returns (tmp_path, x_off, y_off).

    Why this approach:
      - screencapture captures the ACTUAL window pixels even when the window
        is behind other windows (unlike mss/screencapture -R which captures
        whatever is visually on screen at those coordinates).
      - The -o flag omits the drop-shadow so the image size is exactly 2×
        the logical window size on Retina displays.
      - screencapture is a passive read-only utility; it does NOT spawn any
        UI-interactive process and does NOT cause window-focus changes.
        (Unlike osascript/JXA which communicates with System Events and can
        briefly steal focus, clearing WeChat's search input.)
    """
    import tempfile as _tf

    tmp = _tf.NamedTemporaryFile(suffix=".png", delete=False).name
    try:
        subprocess.run(
            ["screencapture", "-l", str(wid), "-o", tmp],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass
    return tmp, x_off, y_off


def get_screenshot_dir() -> str:
    import tempfile
    import os

    d = os.path.join(tempfile.gettempdir(), "polaris_computer_use_screenshots")
    os.makedirs(d, exist_ok=True)
    return d


def clean_screenshot_dir():
    import os
    import glob

    d = get_screenshot_dir()
    for f in glob.glob(os.path.join(d, "*.png")):
        try:
            os.remove(f)
        except Exception:
            pass


def capture_screen(app_name: str = "", bounds: Optional[dict] = None) -> tuple[str, int, int]:
    """
    大一统截图入口函数。
    - 如果提供了 `bounds`，则精准裁剪该区域。
    - 如果没有 `bounds` 但提供了 `app_name`，会自动寻找该 App 最大的窗口并裁剪。
    - 如果什么都没提供，或者裁剪失败了，安全降级为全屏截图。

    返回 (临时图片路径, x轴偏移量, y轴偏移量)。
    """
    import mss as _mss
    import mss.tools as _mss_tools
    import tempfile as _tf

    tmp = _tf.NamedTemporaryFile(
        suffix=".png", dir=get_screenshot_dir(), delete=False
    ).name

    if not bounds and app_name:
        bounds = get_largest_window_bounds(app_name)

    if bounds and bounds.get("w", 0) > 50 and bounds.get("h", 0) > 50:
        region = {
            "top": max(0, int(bounds["y"])),
            "left": max(0, int(bounds["x"])),
            "width": int(bounds["w"]),
            "height": int(bounds["h"]),
        }
        try:
            with _mss.MSS() as sct:
                img = sct.grab(region)
                _mss_tools.to_png(img.rgb, img.size, output=tmp)
            return tmp, int(bounds["x"]), int(bounds["y"])
        except Exception:
            pass  # fall through to full-screen

    # Full-screen fallback
    try:
        with _mss.MSS() as sct:
            sct.shot(output=tmp)
    except Exception:
        pass
    return tmp, 0, 0


def safe_click(
    x: int, y: int, proc_name: str, open_name: str, bundle_id: str = ""
) -> bool:
    """
    安全点击：先把目标 App 拽到最前面，然后再对绝对坐标 (x, y) 触发左键点击。
    如果在 Mac 上无法把 App 拽到前面，则果断放弃点击，防止误伤其他软件。
    """
    if platform.system() == "Darwin":
        if not ensure_frontmost(proc_name, open_name, bundle_id):
            return False
    mouse.position = (x, y)
    mouse.click(Button.left)
    return True


# ---------------------------------------------------------------------------
# macOS Accessibility helpers
# ---------------------------------------------------------------------------


def get_frontmost_app_name() -> str:
    """Return the process name of the currently frontmost macOS app."""
    try:
        script = 'tell application "System Events" to get name of first process whose frontmost is true'
        return (
            subprocess.check_output(["osascript", "-e", script], timeout=5)
            .decode()
            .strip()
        )
    except Exception:
        return ""


def get_frontmost_window_bounds() -> dict:
    """Return {x, y, w, h} of the frontmost window, or {} on failure."""
    jxa = """
    function run() {
        const se = Application('System Events');
        const procs = se.processes.whose({ frontmost: true })();
        if (!procs.length) return 'null';
        const wins = procs[0].windows();
        if (!wins.length) return 'null';
        const pos = wins[0].position(), size = wins[0].size();
        if (!pos || !size) return 'null';
        return JSON.stringify({x: pos[0], y: pos[1], w: size[0], h: size[1]});
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
        if out and out != "null":
            return json.loads(out)
    except Exception:
        pass
    return {}


def get_process_window_bounds(proc_name: str) -> dict:
    """
    Return {x, y, w, h} of the first window of a named process.
    Unlike get_frontmost_window_bounds(), this does NOT require the process
    to be frontmost — safe to call while our own script has focus.
    """
    js_proc = json.dumps(proc_name)
    jxa = f"""
    function run() {{
        const se = Application('System Events');
        const procs = se.processes.whose({{name: {js_proc}}})();
        if (!procs.length) return 'null';
        const wins = procs[0].windows();
        if (!wins.length) return 'null';
        const pos = wins[0].position(), size = wins[0].size();
        if (!pos || !size) return 'null';
        return JSON.stringify({{x: pos[0], y: pos[1], w: size[0], h: size[1]}});
    }}
    """
    try:
        out = (
            subprocess.check_output(
                ["osascript", "-l", "JavaScript", "-e", jxa], timeout=5
            )
            .decode()
            .strip()
        )
        if out and out != "null":
            return json.loads(out)
    except Exception:
        pass
    return {}


def find_input_field(role_hint: str = "AXTextArea"):
    """
    Scan the frontmost window's accessibility tree for an editable text field.
    Returns (x, y) or None.
    """
    js_hint = json.dumps(role_hint)
    jxa = f"""
    function run() {{
        const se = Application('System Events');
        const procs = se.processes.whose({{ frontmost: true }})();
        if (!procs.length) return "null";
        const win = procs[0].windows()[0];
        let result = null;
        const targets = [{js_hint}, "AXTextField", "AXTextArea"];
        function traverse(el, depth) {{
            if (result || depth > 10) return;
            try {{
                const role = el.role();
                if (targets.indexOf(role) !== -1) {{
                    const pos = el.position(), sz = el.size();
                    if (pos && sz && sz[0] > 100) {{
                        result = {{x: Math.round(pos[0]+sz[0]/2), y: Math.round(pos[1]+sz[1]/2)}};
                        return;
                    }}
                }}
                const kids = el.uiElements();
                for (let i = 0; i < kids.length; i++) traverse(kids[i], depth + 1);
            }} catch(e) {{}}
        }}
        if (win) traverse(win, 0);
        return result ? JSON.stringify(result) : "null";
    }}
    """
    try:
        out = (
            subprocess.check_output(
                ["osascript", "-l", "JavaScript", "-e", jxa], timeout=8
            )
            .decode()
            .strip()
        )
        if out and out != "null":
            c = json.loads(out)
            return c["x"], c["y"]
    except Exception:
        pass
    return None


def find_in_section(contact: str, section: str):
    """
    Generic: search the MAIN window of the frontmost process (depth 12).
    Find the first element containing `contact` below the `section` header.
    Returns (x, y) or None.

    For apps whose search dropdown is a separate NSWindow, override in the
    app-specific adapter instead of changing this function.
    """
    js_contact = json.dumps(contact)
    js_section = json.dumps(section)
    jxa = f"""
    function run() {{
        const se = Application('System Events');
        const procs = se.processes.whose({{frontmost: true}})();
        if (!procs.length) return "null";
        const win = procs[0].windows()[0];
        if (!win) return "null";
        const needle  = {js_contact};
        const secName = {js_section};
        let elems = [];
        function collect(el, d) {{
            if (d > 12) return;
            try {{
                const pos = el.position(), sz = el.size();
                if (pos && sz && sz[0] > 5)
                    elems.push({{
                        name: el.name() || '',
                        cx: Math.round(pos[0]+sz[0]/2),
                        cy: Math.round(pos[1]+sz[1]/2),
                        top: pos[1]
                    }});
                const kids = el.uiElements();
                for (let i = 0; i < kids.length; i++) collect(kids[i], d + 1);
            }} catch(e) {{}}
        }}
        collect(win, 0);
        let secTop = -1;
        for (const e of elems) {{
            if (e.name === secName) {{ secTop = e.top; break; }}
        }}
        if (secTop < 0) return "null";
        let best = null;
        for (const e of elems) {{
            if (e.top > secTop && e.name.indexOf(needle) !== -1)
                if (!best || e.top < best.top) best = e;
        }}
        return best ? best.cx + "," + best.cy : "null";
    }}
    """
    try:
        out = (
            subprocess.check_output(
                ["osascript", "-l", "JavaScript", "-e", jxa], timeout=12
            )
            .decode()
            .strip()
        )
        if out and out != "null" and "," in out:
            return tuple(map(int, out.split(",")))
    except Exception:
        pass
    return None


def find_element_in_window(name: str, match_index: int = 0):
    """
    Find an element by name ONLY inside the frontmost window's accessibility tree.
    Never falls back to full-screen OCR — cannot accidentally click other apps.
    Returns (x, y) or None.
    """
    js_name = json.dumps(name)
    js_idx = int(match_index)
    jxa = f"""
    function run() {{
        const se = Application('System Events');
        const procs = se.processes.whose({{frontmost: true}})();
        if (!procs.length) return "null";
        const win = procs[0].windows()[0];
        if (!win) return "null";
        const needle = {js_name};
        let matches = [];
        function traverse(el, depth) {{
            if (depth > 8) return;
            try {{
                const n = el.name() || '';
                if (n.indexOf(needle) !== -1) {{
                    const pos = el.position(), sz = el.size();
                    if (pos && sz && sz[0] > 0)
                        matches.push({{cx: Math.round(pos[0]+sz[0]/2), cy: Math.round(pos[1]+sz[1]/2)}});
                }}
                const kids = el.uiElements();
                for (let i = 0; i < kids.length; i++) traverse(kids[i], depth + 1);
            }} catch(e) {{}}
        }}
        traverse(win, 0);
        if (!matches.length) return "null";
        const idx = {js_idx} < 0 ? matches.length + {js_idx} : {js_idx};
        const m = matches[Math.min(Math.max(idx, 0), matches.length - 1)];
        return m.cx + "," + m.cy;
    }}
    """
    try:
        out = (
            subprocess.check_output(
                ["osascript", "-l", "JavaScript", "-e", jxa], timeout=10
            )
            .decode()
            .strip()
        )
        if out and out != "null" and "," in out:
            return tuple(map(int, out.split(",")))
    except Exception:
        pass
    return None
