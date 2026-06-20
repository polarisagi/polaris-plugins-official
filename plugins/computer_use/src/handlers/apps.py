import subprocess
import platform
import time
from utils import ensure_frontmost, get_frontmost_app_name, get_window_id_for_process
from adapters.registry import get_adapter
from profiles_loader import APP_PROFILES, resolve
from .interaction import handle_focus_input


def handle_open_app(args):
    app_name = args.get("app_name", "")
    open_name = args.get("open_name", "") or app_name
    bundle_id = args.get("bundle_id", "")
    if not app_name and not open_name:
        raise Exception("Missing app_name")

    plat = platform.system()

    # 1. 跨平台预检机制：在尝试唤醒之前，先检查应用在系统中是否真正安装
    if open_name and open_name.lower() != "desktop":
        exists = False
        if plat == "Darwin":
            # Mac 下通过 bundle id 探测应用是否存在
            r_check = subprocess.run(
                ["osascript", "-e", f'id of application "{open_name}"'],
                capture_output=True,
            )
            exists = r_check.returncode == 0
        elif plat == "Windows":
            # Win 下先检查环境变量 PATH，然后利用 PowerShell 检索“开始”菜单
            import shutil

            if shutil.which(open_name):
                exists = True
            else:
                ps_cmd = (
                    f"Get-StartApps | Where-Object {{$_.Name -match '{open_name}'}}"
                )
                r_check = subprocess.run(
                    ["powershell", "-command", ps_cmd], capture_output=True, text=True
                )
                exists = bool(r_check.stdout.strip())
        else:  # Linux
            # Linux 下检索桌面应用启动图标
            import shutil

            if shutil.which(open_name):
                exists = True
            else:
                import glob as _glob
                import os as _os

                desktop_files = _glob.glob(
                    f"/usr/share/applications/*{open_name}*.desktop"
                ) + _glob.glob(
                    _os.path.expanduser(
                        f"~/.local/share/applications/*{open_name}*.desktop"
                    )
                )
                exists = bool(desktop_files)

        if not exists:
            return [
                {
                    "type": "text",
                    "text": f"Error: Application '{open_name}' is not installed or not found. Please try a different name or ask the user.",
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
        subprocess.run(["osascript", "-e", f'tell application "{open_name}" to activate'])
        time.sleep(1.5)
        front = get_frontmost_app_name()
    _log(f"[1] Frontmost: '{front}'")

    winfo = get_window_id_for_process(proc_name)
    if winfo and winfo.get("w", 0) > 50:
        profile["_window_id"] = winfo["id"]
        profile["_window_bounds"] = {k: winfo[k] for k in ("x", "y", "w", "h")}
        _log(f"[1] Window id={winfo['id']} bounds={profile['_window_bounds']}")


def _ensure_frontmost_step(plat: str, proc_name: str, open_name: str, bundle_id: str, _log):
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
        chat_apps = [k for k, v in APP_PROFILES.items() if v.get("category") == "chat" and not k.isascii()]
        app_key = chat_apps[0] if chat_apps else "wechat"

    wait_search = float(args.get("wait_search", 1.5))
    wait_chat = float(args.get("wait_chat", 0.8))

    _validate_send_args(contact_name, message)

    profile = APP_PROFILES.get(app_key)
    if not profile:
        known = sorted({k for k, v in APP_PROFILES.items() if v.get("category") == "chat"})
        raise Exception(f"Unknown app '{app_key}'. Known chat apps: {', '.join(known)}.")

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
    handle_open_app({"app_name": actual_app, "open_name": open_name, "bundle_id": bundle_id})
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
    adapter.select_search_result(contact_name, search_sect, profile, proc_name, plat, _log)
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

    return [{"type": "text", "text": f"✅ Sent to '{contact_name}' via {actual_app}\n\n" + "\n".join(steps)}]
