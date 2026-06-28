import subprocess
import platform
import time
from utils import ensure_frontmost, get_frontmost_app_name, get_window_id_for_process
from adapters.registry import get_adapter
from profiles_loader import APP_PROFILES, resolve
from .interaction import handle_focus_input


def _app_exists_mac(app_name: str, open_name: str, bundle_id: str) -> bool:
    import shutil
    import os

    if bundle_id:
        try:
            result = subprocess.run(
                ["mdfind", f"kMDItemCFBundleIdentifier == '{bundle_id}'"],
                capture_output=True,
                timeout=3,
            )
            if result.stdout.strip():
                return True
        except Exception:
            pass
    search_name = open_name or app_name
    for base in ["/Applications", os.path.expanduser("~/Applications")]:
        if os.path.isdir(os.path.join(base, f"{search_name}.app")):
            return True
    return bool(shutil.which(app_name))


def _app_exists_win(app_name: str) -> bool:
    import shutil
    import os

    if shutil.which(app_name):
        return True
    for base in [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.path.expanduser(r"~\AppData\Local"),
    ]:
        if base and os.path.isfile(os.path.join(base, app_name, f"{app_name}.exe")):
            return True
    try:
        import importlib
        winreg = importlib.import_module("winreg")  # type: ignore[assignment]  # Windows-only
        key = winreg.OpenKey(  # type: ignore[attr-defined]
            winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
        )
        try:
            winreg.QueryValue(key, f"{app_name}.exe")  # type: ignore[attr-defined]
            return True
        except FileNotFoundError:
            pass
    except Exception:
        pass
    return False


def _app_exists_linux(app_name: str, open_name: str) -> bool:
    import shutil
    import os

    if shutil.which(app_name):
        return True
    desktop_dirs = [
        "/usr/share/applications",
        "/usr/local/share/applications",
        os.path.expanduser("~/.local/share/applications"),
    ]
    search = (open_name or app_name).lower()
    for d in desktop_dirs:
        if os.path.isdir(d):
            for fname in os.listdir(d):
                if search in fname.lower() and fname.endswith(".desktop"):
                    return True
    return False


def _app_exists(app_name: str, open_name: str = "", bundle_id: str = "") -> bool:
    """跨平台检测应用是否已安装。"""
    plat = platform.system()
    if plat == "Darwin":
        return _app_exists_mac(app_name, open_name, bundle_id)
    elif plat == "Windows":
        return _app_exists_win(app_name)
    else:
        return _app_exists_linux(app_name, open_name)


def handle_open_app(args):
    app_name = args.get("app_name", "")
    open_name = args.get("open_name", "") or app_name
    bundle_id = args.get("bundle_id", "")
    if not app_name and not open_name:
        raise Exception("Missing app_name")

    plat = platform.system()

    # 1. 跨平台预检机制：在尝试唤醒之前，先检查应用在系统中是否真正安装
    if open_name and open_name.lower() != "desktop":
        if not _app_exists(app_name, open_name=open_name, bundle_id=bundle_id):
            return [
                {
                    "type": "text",
                    "text": f"App '{app_name}' is not installed or not found",
                }
            ]

    # 2. 跨平台启动与聚焦 (Launch / Focus)
    if plat == "Darwin":
        # macOS: 将应用的拉起和置顶任务全权委托给强大的 ensure_frontmost 引擎
        success = ensure_frontmost(app_name, open_name, bundle_id, retries=2)
        if not success and open_name.lower() != "desktop":
            # 兜底方案：如果 App 彻底死掉了(AppleScript 叫不醒)，强行调用底层 open 命令拉起
            try:
                subprocess.run(
                    ["open", "-a", open_name], check=True, capture_output=True
                )
                ensure_frontmost(app_name, open_name, bundle_id, retries=1)
            except subprocess.CalledProcessError:
                pass

    elif plat == "Windows":
        if open_name.lower() == "desktop":
            ensure_frontmost(app_name, open_name)
        else:
            subprocess.Popen(["cmd", "/c", "start", "", open_name])

    else:  # Linux
        if open_name.lower() == "desktop":
            ensure_frontmost(app_name, open_name)
        else:
            subprocess.Popen(["xdg-open", open_name])

    return [{"type": "text", "text": f"Opened or searched for {open_name or app_name}"}]


def handle_get_running_apps(args):
    plat = platform.system()
    apps = []
    if plat == "Darwin":
        try:
            out = (
                subprocess.check_output(
                    [
                        "osascript",
                        "-e",
                        'tell application "System Events" to get name of every process whose background only is false',
                    ],
                    timeout=5,
                )
                .decode()
                .strip()
            )
            apps = [name.strip() for name in out.split(",") if name.strip()]
        except Exception as e:
            return [{"type": "text", "text": f"Error getting apps: {e}"}]
    elif plat == "Windows":
        try:
            out = (
                subprocess.check_output(
                    [
                        "powershell",
                        "-command",
                        "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select-Object -ExpandProperty Name",
                    ],
                    timeout=5,
                )
                .decode()
                .strip()
            )
            apps = list(
                set([name.strip() for name in out.splitlines() if name.strip()])
            )
        except Exception as e:
            return [{"type": "text", "text": f"Error getting apps: {e}"}]
    else:
        try:
            out = subprocess.check_output(["wmctrl", "-l"], timeout=5).decode().strip()
            apps = [
                line.split(None, 3)[-1]
                for line in out.splitlines()
                if len(line.split()) >= 4
            ]
        except Exception as e:
            return [
                {"type": "text", "text": f"Error getting apps (requires wmctrl): {e}"}
            ]

    return [
        {
            "type": "text",
            "text": "Running applications:\n" + "\n".join(f"- {app}" for app in apps),
        }
    ]


def _validate_send_args(contact_name: str, message: str):
    """Raise if required fields are missing or contain control characters."""
    if not contact_name:
        raise Exception("send_message_to requires 'contact_name'")
    if not message:
        raise Exception("send_message_to requires 'message'")
    for field, val in (("contact_name", contact_name), ("message", message)):
        if any(ord(c) < 0x20 and c not in ("\t",) for c in val):
            raise Exception(f"'{field}' contains disallowed control characters")


def _activate_app_macos(open_name: str, proc_name: str, profile: dict, steps, _log):
    """macOS: verify foreground app and cache window bounds."""
    front = get_frontmost_app_name()
    if proc_name.lower() not in (front or "").lower():
        _log(f"[1b] Retrying focus (frontmost='{front}')")
        subprocess.run(
            ["osascript", "-e", f'tell application "{open_name}" to activate']
        )
        time.sleep(1.5)
        front = get_frontmost_app_name()
    _log(f"[1] Frontmost: '{front}'")

    winfo = get_window_id_for_process(proc_name)
    if winfo and winfo.get("w", 0) > 50:
        profile["_window_id"] = winfo["id"]
        profile["_window_bounds"] = {k: winfo[k] for k in ("x", "y", "w", "h")}
        _log(f"[1] Window id={winfo['id']} bounds={profile['_window_bounds']}")


def _ensure_frontmost_step(
    plat: str, proc_name: str, open_name: str, bundle_id: str, _log
):
    """Re-focus the app after search-result selection (macOS only)."""
    if plat != "Darwin":
        return
    ok = ensure_frontmost(proc_name, open_name, bundle_id)
    front = get_frontmost_app_name()
    _log(f"[5] ensure_frontmost={'ok' if ok else 'FAILED'}, frontmost='{front}'")


def handle_send_message_to(args):
    import utils

    contact_name = args.get("contact_name", "").strip()
    message = args.get("message", "").strip()
    app_key = args.get("app", args.get("app_name", "")).strip().lower()
    if not app_key:
        # 取所有 chat 类应用的 key，优先微信，否则取第一个
        chat_keys = [k for k, v in APP_PROFILES.items() if v.get("category") == "chat"]
        preferred = [k for k in chat_keys if "wechat" in k or "微信" in k]
        app_key = (
            preferred[0] if preferred else (chat_keys[0] if chat_keys else "wechat")
        )

    wait_search = float(args.get("wait_search", 1.5))
    wait_chat = float(args.get("wait_chat", 0.8))

    _validate_send_args(contact_name, message)

    profile = APP_PROFILES.get(app_key)
    if not profile:
        known = sorted(
            {k for k, v in APP_PROFILES.items() if v.get("category") == "chat"}
        )
        raise Exception(
            f"Unknown app '{app_key}'. Known chat apps: {', '.join(known)}."
        )

    plat = platform.system()
    proc_name = profile.get("process_name", profile.get("open_name", app_key))
    actual_app = profile.get("app_name", app_key)
    open_name = profile.get("open_name", actual_app)
    bundle_id = profile.get("bundle_id", "")
    search_sc = resolve(profile.get("search_shortcut", "cmd+f"))
    send_sc = resolve(profile.get("send_shortcut", "enter"))
    input_hint = resolve(profile.get("input_role_hint", "AXTextArea"))
    search_sect = resolve(profile.get("search_result_section"))
    pre_reset = bool(profile.get("pre_search_reset", False))

    steps: list[str] = []

    def _log(msg):
        steps.append(msg)

    # Step 1 — launch / focus
    _log(f"[1] Activating {actual_app}")
    handle_open_app(
        {"app_name": actual_app, "open_name": open_name, "bundle_id": bundle_id}
    )
    time.sleep(2.0)
    if plat == "Darwin":
        _activate_app_macos(open_name, proc_name, profile, steps, _log)

    adapter = get_adapter(profile)

    # Step 2 — optional pre-reset + open search
    if pre_reset:
        _log("[2] Resetting state")
        adapter.press_escape(proc_name, plat)
        time.sleep(0.3)
    _log(f"[2] Search shortcut: {search_sc}")
    adapter.press_search_shortcut(proc_name, plat, search_sc)
    time.sleep(0.8)

    # Step 3 — type contact name
    _log(f"[3] Searching for '{contact_name}'")
    utils.clear_field()
    time.sleep(0.15)
    utils.clipboard_type(contact_name)
    time.sleep(wait_search)

    # Step 4 — select result
    _log(f"[4] Selecting '{contact_name}'")
    adapter.select_search_result(
        contact_name, search_sect, profile, proc_name, plat, _log
    )
    time.sleep(wait_chat + 0.5)

    # Step 5 — re-focus after selection
    _ensure_frontmost_step(plat, proc_name, open_name, bundle_id, _log)

    # Step 6 — focus message input
    adapter.press_escape(proc_name, plat)
    time.sleep(0.2)
    if plat == "Darwin":
        ensure_frontmost(proc_name, open_name, bundle_id)
    _log(f"[6] Focusing input ({input_hint})")
    handle_focus_input({"hint": input_hint, "app_name": actual_app})
    time.sleep(0.3)

    # Step 7 — type message
    preview = message[:60] + ("..." if len(message) > 60 else "")
    _log(f"[7] Typing: '{preview}'")
    utils.clear_field()
    time.sleep(0.15)
    utils.clipboard_type(message)
    time.sleep(0.2)

    # Step 8 — send
    _log(f"[8] Sending via: {send_sc}")
    adapter.press_send_shortcut(proc_name, plat, send_sc)

    return [
        {
            "type": "text",
            "text": f"✅ Sent to '{contact_name}' via {actual_app}\n\n"
            + "\n".join(steps),
        }
    ]


def handle_get_window_list(args):
    """
    返回所有可见窗口的详细信息（app 名、标题、位置、大小）。
    比 get_running_apps 更详细，适合多窗口操作。
    """
    import json as _json

    plat = platform.system()

    if plat == "Darwin":
        jxa = """
        function run() {
            const se = Application('System Events');
            const result = [];
            const procs = se.processes.whose({ backgroundOnly: false })();
            for (let p = 0; p < procs.length; p++) {
                try {
                    const proc = procs[p];
                    const appName = proc.name();
                    const wins = proc.windows();
                    for (let w = 0; w < wins.length; w++) {
                        try {
                            const win = wins[w];
                            const pos = win.position();
                            const sz = win.size();
                            const title = win.name() || '';
                            if (pos && sz && sz[0] > 50 && sz[1] > 50) {
                                result.push({
                                    app: appName, title: title,
                                    x: pos[0], y: pos[1],
                                    width: sz[0], height: sz[1]
                                });
                            }
                        } catch(e) {}
                    }
                } catch(e) {}
            }
            return JSON.stringify(result);
        }
        """
        try:
            out = (
                subprocess.check_output(
                    ["osascript", "-l", "JavaScript", "-e", jxa], timeout=12
                )
                .decode()
                .strip()
            )
            windows = _json.loads(out)
            if not windows:
                return [{"type": "text", "text": "No visible windows found"}]
            lines = ["Windows:"]
            for w in windows:
                lines.append(
                    f'  [{w["app"]}] "{w["title"]}" @ ({w["x"]},{w["y"]}) {w["width"]}×{w["height"]}'
                )
            return [{"type": "text", "text": "\n".join(lines)}]
        except Exception as e:
            return [{"type": "text", "text": f"Error: {e}"}]

    elif plat == "Windows":
        try:
            from pywinauto import Desktop

            wins = Desktop(backend="uia").windows(visible_only=True)
            lines = ["Windows:"]
            for w in wins:
                r = w.rectangle()
                lines.append(
                    f'  "{w.window_text()}" @ ({r.left},{r.top}) {r.width()}×{r.height()}'
                )
            return [{"type": "text", "text": "\n".join(lines)}]
        except Exception as e:
            return [{"type": "text", "text": f"Error: {e}"}]

    else:
        try:
            out = subprocess.check_output(["wmctrl", "-lG"], timeout=5).decode()
            lines = ["Windows:"]
            for line in out.splitlines():
                parts = line.split(None, 7)
                if len(parts) >= 8:
                    lines.append(
                        f'  "{parts[7]}" @ ({parts[2]},{parts[3]}) {parts[4]}×{parts[5]}'
                    )
            return [{"type": "text", "text": "\n".join(lines)}]
        except Exception as e:
            return [{"type": "text", "text": f"Error (requires wmctrl): {e}"}]


def handle_close_window(args):
    """
    关闭当前最前端窗口（或指定 app 的窗口）。
    - app_name: 目标应用名（可选，不传则关闭当前最前端窗口）
    """
    import utils as _u

    plat = platform.system()
    app_name = args.get("app_name", "")

    if plat == "Darwin":
        if app_name:
            _u.ensure_frontmost(app_name, app_name)
            time.sleep(0.3)
        # macOS 标准关闭窗口快捷键
        _u.press_shortcut("cmd+w")
        return [
            {
                "type": "text",
                "text": f"Closed window{' of ' + app_name if app_name else ''}",
            }
        ]

    elif plat == "Windows":
        _u.press_shortcut("alt+f4")
        return [{"type": "text", "text": "Closed window (Alt+F4)"}]

    else:
        _u.press_shortcut("alt+f4")
        return [{"type": "text", "text": "Closed window (Alt+F4)"}]


def handle_minimize_app(args):
    """
    最小化指定应用或当前最前端窗口。
    - app_name: 目标应用名（可选）
    """
    import utils as _u

    plat = platform.system()
    app_name = args.get("app_name", "")

    if plat == "Darwin":
        if app_name:
            _u.ensure_frontmost(app_name, app_name)
            time.sleep(0.3)
        _u.press_shortcut("cmd+m")
        return [
            {
                "type": "text",
                "text": f"Minimized{' ' + app_name if app_name else ' active window'}",
            }
        ]

    elif plat == "Windows":
        _u.press_shortcut("win+down")
        return [{"type": "text", "text": "Minimized window"}]

    else:
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-b", "add,hidden"], timeout=3)
        except Exception:
            _u.press_shortcut("super+h")
        return [{"type": "text", "text": "Minimized window"}]


def handle_quit_app(args):
    """
    退出（而非最小化）指定应用。
    - app_name: 目标应用名（必须）
    """
    app_name = args.get("app_name", "")
    if not app_name:
        raise Exception("quit_app requires 'app_name'")

    plat = platform.system()

    if plat == "Darwin":
        from utils import ensure_frontmost, press_shortcut

        ensure_frontmost(app_name, app_name)
        time.sleep(0.3)
        press_shortcut("cmd+q")
        return [{"type": "text", "text": f"Quit {app_name}"}]

    elif plat == "Windows":
        try:
            subprocess.run(["taskkill", "/IM", f"{app_name}.exe", "/F"], timeout=5)
        except Exception as e:
            return [{"type": "text", "text": f"Error: {e}"}]
        return [{"type": "text", "text": f"Quit {app_name}"}]

    else:
        try:
            subprocess.run(["pkill", "-x", app_name], timeout=5)
        except Exception as e:
            return [{"type": "text", "text": f"Error: {e}"}]
        return [{"type": "text", "text": f"Quit {app_name}"}]


def handle_send_file_to(args):
    """
    向聊天联系人发送文件/图片（macOS 专用）。
    - contact_name: 联系人/群聊名称（必须）
    - file_path: 要发送的文件绝对路径（必须）
    - app: 聊天应用别名（默认 'wechat'）

    实现：先通过 send_message_to 逻辑定位对话，再拖入文件或通过剪贴板粘贴图片。
    """
    import os

    if platform.system() != "Darwin":
        return [{"type": "text", "text": "send_file_to is currently macOS only"}]

    contact_name = args.get("contact_name", "").strip()
    file_path = args.get("file_path", "").strip()
    if not contact_name:
        raise Exception("send_file_to requires 'contact_name'")
    if not file_path:
        raise Exception("send_file_to requires 'file_path'")
    if not os.path.exists(file_path):
        return [{"type": "text", "text": f"File not found: {file_path}"}]

    app_key = args.get("app", args.get("app_name", "wechat")).strip().lower()
    profile = APP_PROFILES.get(app_key)
    if not profile:
        raise Exception(f"Unknown app '{app_key}'")

    # Step 1: 打开对话（复用 open_app + 搜索选联系人逻辑）
    proc_name = profile.get("process_name", app_key)
    open_name = profile.get("open_name", proc_name)
    bundle_id = profile.get("bundle_id", "")
    input_hint = resolve(profile.get("input_role_hint", "AXTextArea"))

    handle_open_app(
        {"app_name": open_name, "open_name": open_name, "bundle_id": bundle_id}
    )
    time.sleep(1.5)

    import utils

    search_sc = resolve(profile.get("search_shortcut", "cmd+f"))
    utils.press_shortcut(search_sc)
    time.sleep(0.5)
    utils.clear_field()
    time.sleep(0.1)
    utils.clipboard_type(contact_name)
    time.sleep(float(profile.get("wait_before_ocr", 1.5)))
    utils.press_shortcut("down")
    time.sleep(0.2)
    utils.press_shortcut("enter")
    time.sleep(1.0)

    # Step 2: 聚焦输入框
    from handlers.interaction import handle_focus_input

    handle_focus_input({"hint": input_hint, "app_name": open_name})
    time.sleep(0.3)

    # Step 3: 将文件路径写入剪贴板并粘贴（支持图片文件直接粘贴）
    ext = os.path.splitext(file_path)[1].lower()
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}

    if ext in image_exts:
        # 图片：用 AppleScript 将图片写入剪贴板后粘贴
        osa = f"""
        set imgFile to POSIX file "{file_path}"
        set theImage to read imgFile as JPEG picture
        set the clipboard to theImage
        """
        try:
            subprocess.run(["osascript", "-e", osa], timeout=5)
            time.sleep(0.2)
            utils.press_shortcut("cmd+v")
            time.sleep(0.5)
            send_sc = resolve(profile.get("send_shortcut", "enter"))
            utils.press_shortcut(send_sc)
            return [
                {
                    "type": "text",
                    "text": f"✅ Sent image '{os.path.basename(file_path)}' to '{contact_name}'",
                }
            ]
        except Exception:
            pass

    # 非图片或图片粘贴失败：使用拖拽方式（通过 Finder）
    try:
        osa_drag = f"""
        tell application "Finder"
            set theFile to POSIX file "{file_path}" as alias
            reveal theFile
            activate
        end tell
        """
        subprocess.run(["osascript", "-e", osa_drag], timeout=5)
        time.sleep(0.5)
        bounds = utils.get_process_window_bounds(proc_name)
        if bounds:
            cx = bounds["x"] + bounds["w"] // 2
            cy = bounds["y"] + bounds["h"] // 2
            front_bounds = utils.get_frontmost_window_bounds()
            if front_bounds:
                file_x = front_bounds["x"] + front_bounds["w"] // 2
                file_y = front_bounds["y"] + front_bounds["h"] // 2
                from handlers.mouse import handle_left_click_drag

                handle_left_click_drag(
                    {"start_coordinate": [file_x, file_y], "coordinate": [cx, cy]}
                )
                time.sleep(1.0)
                utils.ensure_frontmost(proc_name, open_name, bundle_id)
                return [
                    {
                        "type": "text",
                        "text": f"✅ Dragged '{os.path.basename(file_path)}' to '{contact_name}'",
                    }
                ]
    except Exception as e:
        return [
            {
                "type": "text",
                "text": f"File send failed: {e}. Try opening the file manually and dragging it.",
            }
        ]

    return [
        {
            "type": "text",
            "text": f"File send attempted for '{os.path.basename(file_path)}'",
        }
    ]
