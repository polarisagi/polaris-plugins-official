"""
WeChatAdapter — search-result selection for WeChat / 微信.

Why a custom adapter is needed:

  1. Separate NSWindow for the search dropdown
     WeChat renders search results in a SEPARATE NSWindow (not windows()[0]).
     The generic BaseAdapter only inspects the main window's accessibility tree.

  2. Search results mix content types
     Typing a query and pressing Enter opens a full global-search page that
     includes news articles, public accounts, Moments, etc. We must select
     the result WITHOUT pressing Enter in the search box.

  3. Multi-section support
     Search results are grouped by type: 联系人 (Contacts) for direct contacts,
     群聊 (Group Chats) for group conversations. Both must be tried in order so
     that the adapter handles both individual and group chat targets correctly.

  4. Visual-first strategy
     After the inline suggestion dropdown renders, we take a screenshot and
     use Vision-framework OCR to find the section header and the target below it.
     This is robust against accessibility tree incompleteness and requires no
     hardcoded coordinates.

Selection strategy (in order):
  A  Screenshot + OCR: try each section header → find contact below it → click
     Fallback: find contact name anywhere on screen (no section constraint)
  B  Accessibility tree across all windows at depth 15, per section
  C  Keyboard Down+Enter on inline suggestions (safe last resort)
"""

import json
import os
import subprocess
import time


from adapters.base import BaseAdapter
import utils


# Locale-aware sections WeChat may show in search results, tried in order.
# 联系人 (Contacts) is tried first because direct contacts are the most common target.
_WECHAT_SECTIONS = {
    "zh": ["最常使用", "联系人", "群聊"],
    "en": ["Top Contacts", "Contacts", "Group Chats"],
}

# Absolute path to the Swift OCR binary (compiled on first use).
# __file__ is  src/adapters/chat/wechat.py → go up two levels to reach src/
_SRC_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_OCR_SRC = os.path.join(_SRC_DIR, "find_text_on_screen.swift")
_OCR_BIN = os.path.join(_SRC_DIR, "find_text_on_screen")


def _ensure_ocr_binary() -> bool:
    """Compile the Swift OCR tool if not already built. Returns True on success."""
    if os.path.exists(_OCR_BIN):
        return True
    if not os.path.exists(_OCR_SRC):
        return False
    try:
        subprocess.run(
            ["swiftc", _OCR_SRC, "-o", _OCR_BIN],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return True
    except Exception:
        return False


def _ocr_find(screenshot_path: str, text: str) -> list:
    """
    Run the Vision-framework OCR tool against `screenshot_path` searching for `text`.
    Returns a list of (x, y) tuples in logical screen coordinates, sorted top-to-bottom.
    """
    try:
        out = (
            subprocess.check_output([_OCR_BIN, screenshot_path, text], timeout=12)
            .decode()
            .strip()
        )
    except Exception:
        return []
    results = []
    for line in out.splitlines():
        if "," in line:
            try:
                x, y = map(float, line.split(","))
                results.append((x, y))
            except ValueError:
                pass
    return results


class WeChatAdapter(BaseAdapter):
    def press_search_shortcut(self, proc_name: str, plat: str, search_sc: str):
        if plat == "Darwin":
            utils.osa_send_key(proc_name, search_sc)
        else:
            super().press_search_shortcut(proc_name, plat, search_sc)

    def press_escape(self, proc_name: str, plat: str):
        if plat == "Darwin":
            utils.osa_send_key(proc_name, "esc")
        else:
            super().press_escape(proc_name, plat)

    def press_send_shortcut(self, proc_name: str, plat: str, send_sc: str):
        if plat == "Darwin":
            utils.osa_send_key(proc_name, send_sc)
        else:
            super().press_send_shortcut(proc_name, plat, send_sc)

    def select_search_result(
        self,
        contact_name: str,
        section: str | None,
        profile: dict,
        proc_name: str,
        plat: str,
        log,
    ) -> bool:
        if plat != "Darwin":
            return super().select_search_result(
                contact_name, section, profile, proc_name, plat, log
            )

        # WeChat renders search in two phases: Phase 1 shows inline 群聊 suggestions
        # within ~1 s; Phase 2 shows the full results panel (with section headers such
        # as 群聊 and 聊天记录) after 1-3 s more.  We must wait for Phase 2 before
        # taking the OCR screenshot so the coordinates are stable.
        wait_ocr = float(profile.get("wait_before_ocr", 1.5))
        if wait_ocr > 0:
            log(f"[4A] Waiting {wait_ocr}s for Phase-2 search results to stabilise")
            time.sleep(wait_ocr)

        # Build ordered list of sections to try.
        # Put the profile-specified section first, then append the defaults so we
        # always cover both direct contacts (联系人) and group chats (群聊).
        loc = utils.detect_locale()
        default_sections = _WECHAT_SECTIONS.get(loc, _WECHAT_SECTIONS["en"])
        if section:
            sections = [section] + [s for s in default_sections if s != section]
        else:
            sections = default_sections

        open_name = profile.get("open_name", profile.get("app_name", proc_name))
        bundle_id = profile.get("bundle_id", "")

        # ── Strategy A: Screenshot + OCR (tries all sections, then no-section) ──
        if _ensure_ocr_binary():
            coords = self._find_via_ocr(contact_name, sections, proc_name, profile, log)
            if coords:
                log("[4A] OCR identified target, retyping search to restore UI state")
                self._retype_search(
                    contact_name, profile, proc_name, open_name, bundle_id, log
                )
                _direct_click(coords[0], coords[1])
                log(f"[4A] WeChat OCR: direct-clicked at {coords}")
                return True
        else:
            log("[4A] WeChat OCR: binary unavailable, skipping")

        # ── Strategy B: Accessibility tree across all NSWindows (single JXA call) ─
        coords = self._find_in_all_windows(contact_name, sections)
        if coords:
            if utils.safe_click(coords[0], coords[1], proc_name, open_name, bundle_id):
                log(f"[4B] WeChat accessibility: clicked at {coords}")
                return True
            log(
                "[4B] WeChat accessibility: safe_click failed (focus lost), falling through"
            )
        else:
            log("[4B] WeChat accessibility: not found in any section")

        # ── Strategy C: keyboard inline suggestion ────────────────────────────
        # Down selects the first inline suggestion; Enter opens it.
        # This deliberately avoids pressing Enter in the search box first,
        # which would open the global search page (with news / articles).
        self._keyboard_select(proc_name, plat, log)
        return True

    # -------------------------------------------------------------------------
    # Search-box restore helper
    # -------------------------------------------------------------------------

    def _retype_search(
        self,
        contact_name: str,
        profile: dict,
        proc_name: str,
        open_name: str,
        bundle_id: str,
        log,
    ) -> None:
        """
        Re-open WeChat's search box and retype the query using clipboard_type.
        """
        from pynput.keyboard import Controller as _KBCtrl, Key as _Key

        utils.ensure_frontmost(proc_name, open_name, bundle_id)
        kb = _KBCtrl()

        shortcut = profile.get("search_shortcut", "cmd+f")
        if "cmd" in shortcut and "f" in shortcut:
            with kb.pressed(_Key.cmd):
                kb.tap("f")
        time.sleep(0.3)

        # Clear any leftover content in the search box.
        with kb.pressed(_Key.cmd):
            kb.tap("a")
        time.sleep(0.08)
        kb.tap(_Key.delete)
        time.sleep(0.1)

        # Retype the query via clipboard (much faster and avoids IME issues)
        utils.clipboard_type(contact_name)

        wait_ocr = float(profile.get("wait_before_ocr", 1.5))
        log(f"[4A] Re-typed search, waiting {wait_ocr:.1f}s for UI to stabilize")
        time.sleep(wait_ocr)

    # -------------------------------------------------------------------------
    # Strategy A implementation
    # -------------------------------------------------------------------------

    def _find_via_ocr(
        self,
        contact_name: str,
        sections: list,
        proc_name: str,
        profile: dict,
        log,
    ) -> tuple | None:
        """
        Capture the WeChat window using pre-cached bounds (stored in profile by
        main.py BEFORE any search action), run OCR, and return absolute screen
        coordinates of contact_name inside the best section.

        Why cached bounds instead of calling get_largest_window_bounds() here:
          JXA/osascript subprocesses steal focus from WeChat for a brief instant,
          causing WeChat to clear its search input and hide the result list.
          main.py captures the bounds right after activation (step 1), before the
          search box is opened, so no focus disruption occurs during OCR.

          mss.grab() uses CoreGraphics read-only APIs — it never changes focus.
          OCR coordinates are window-relative; we add the stored (x, y) offset to
          convert to absolute screen coordinates before returning.
        """
        profile.get("_window_bounds")
        log("[4A] mss 屏幕区域截图中...")
        tmp, x_off, y_off = _screenshot_window(profile)
        try:
            if not tmp or not os.path.exists(tmp):
                log("[4A] OCR: screenshot failed, skipping OCR")
                return None

            log(f"[4A] OCR: window offset ({x_off},{y_off})")

            # ── try each section header in order ───────────────────────────
            for section in sections:
                sec_hits = _ocr_find(tmp, section)
                if not sec_hits:
                    log(f"[4A] OCR: '{section}' not found, trying next section")
                    continue

                sec_x, sec_y = sec_hits[0]
                log(f"[4A] OCR: '{section}' at window({sec_x:.0f},{sec_y:.0f})")

                contact_hits = _ocr_find(tmp, contact_name)
                for hx, hy in contact_hits:
                    if hy > sec_y:
                        abs_x = int(hx) + x_off
                        abs_y = int(hy) + y_off
                        log(
                            f"[4A] OCR: '{contact_name}' below '{section}' → screen({abs_x},{abs_y})"
                        )
                        return (abs_x, abs_y)

                # Section found but contact not visible — estimate one row below header
                est_x = int(sec_x) + x_off
                est_y = int(sec_y) + y_off + 45
                log(
                    f"[4A] OCR: estimating row below '{section}' → screen({est_x},{est_y})"
                )
                return (est_x, est_y)

            # ── no section header — search for contact name anywhere in window ──
            contact_hits = _ocr_find(tmp, contact_name)
            if contact_hits:
                hx, hy = contact_hits[0]
                abs_x = int(hx) + x_off
                abs_y = int(hy) + y_off
                log(
                    f"[4A] OCR: '{contact_name}' (no section) → screen({abs_x},{abs_y})"
                )
                return (abs_x, abs_y)

            log(f"[4A] OCR: '{contact_name}' not found in window screenshot")
            return None

        finally:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)

    # -------------------------------------------------------------------------
    # Strategy B implementation
    # -------------------------------------------------------------------------

    def _find_in_all_windows(self, contact: str, sections: list) -> tuple | None:
        """
        Search every NSWindow of the frontmost WeChat process (depth 15) in a
        single JXA call, trying each section header in order.
        The search-results dropdown is often a separate window (not windows()[0]).
        """
        js_contact = json.dumps(contact)
        js_sections = json.dumps(sections)
        jxa = f"""
        function run() {{
            const se = Application('System Events');
            const procs = se.processes.whose({{frontmost: true}})();
            if (!procs.length) return "null";
            const needle   = {js_contact};
            const secNames = {js_sections};
            let elems = [];
            function collect(el, d) {{
                if (d > 15) return;
                try {{
                    const pos = el.position(), sz = el.size();
                    if (pos && sz && sz[0] > 5)
                        elems.push({{
                            name: el.name() || '',
                            cx: Math.round(pos[0] + sz[0]/2),
                            cy: Math.round(pos[1] + sz[1]/2),
                            top: pos[1]
                        }});
                    const kids = el.uiElements();
                    for (let i = 0; i < kids.length; i++) collect(kids[i], d + 1);
                }} catch(e) {{}}
            }}
            const wins = procs[0].windows();
            for (let w = 0; w < wins.length; w++) collect(wins[w], 0);
            for (const secName of secNames) {{
                let secTop = -1;
                for (const e of elems) {{
                    if (e.name === secName) {{ secTop = e.top; break; }}
                }}
                if (secTop < 0) continue;
                let best = null;
                for (const e of elems) {{
                    if (e.top > secTop && e.name.indexOf(needle) !== -1)
                        if (!best || e.top < best.top) best = e;
                }}
                if (best) return best.cx + "," + best.cy;
            }}
            return "null";
        }}
        """
        try:
            out = (
                subprocess.check_output(
                    ["osascript", "-l", "JavaScript", "-e", jxa], timeout=15
                )
                .decode()
                .strip()
            )
            if out and out != "null" and "," in out:
                return tuple(map(int, out.split(",")))
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _screenshot_window(profile: dict) -> tuple:
    """
    Capture WeChat's window using `screencapture -l <id> -o`.
    Returns (tmp_path, x_offset, y_offset).

    Why screencapture -l instead of mss:
      - Captures the ACTUAL window even when it is behind other windows.
        mss/screencapture -R grab whatever is visually on screen at the given
        coordinates, which may be a different app lying on top of WeChat.
      - The -o flag removes the drop-shadow; the resulting image is exactly
        2× the logical window size on Retina (scale=2.0) displays.
      - screencapture is a passive read — it does NOT touch System Events and
        does NOT cause WeChat to lose focus (unlike osascript/JXA).

    Coordinate mapping:
      The Swift OCR binary divides Vision pixel coords by NSScreen.backingScaleFactor
      (2.0 on Retina), returning logical coords within the window.
      Adding the stored window (x, y) offset converts them to absolute screen coords.
    """
    profile.get("_window_id")
    bounds = profile.get("_window_bounds", {})
    int(bounds.get("x", 0))
    int(bounds.get("y", 0))

    # Use mss to capture the screen region.
    # We DO NOT use screencapture -l <id> because on macOS, WeChat renders
    # the search dropdown in a separate NSWindow. Capturing the main window ID
    # excludes the dropdown entirely.
    # Fallback: mss window crop using stored bounds
    import utils

    return utils.capture_screen(bounds=bounds)


def _direct_click(x: int, y: int) -> None:
    """
    Click at (x, y) using pynput only — no subprocess, no AppleScript, no JXA.

    WeChat clears its search input the moment it loses focus.  Any osascript or
    JXA subprocess (even a read-only 'is WeChat frontmost?' query) can steal
    focus for a brief instant, which is enough for WeChat to wipe the search
    results before the click lands.  Using pynput directly avoids all subprocess
    spawning and keeps the current focus owner unchanged.
    """
    from pynput.mouse import Controller as _MC, Button as _Btn

    m = _MC()
    m.position = (x, y)
    time.sleep(0.05)
    m.click(_Btn.left)


def _within(x: float, y: float, bounds: dict | None) -> bool:
    """True if (x, y) is inside the window bounds dict, or if bounds is empty."""
    if not bounds:
        return True
    return (
        bounds["x"] <= x <= bounds["x"] + bounds["w"]
        and bounds["y"] <= y <= bounds["y"] + bounds["h"]
    )
