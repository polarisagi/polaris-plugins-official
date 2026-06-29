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

import ocr


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
        contact_type: str = "any",
    ) -> bool:
        if plat != "Darwin":
            return super().select_search_result(
                contact_name, section, profile, proc_name, plat, log, contact_type
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
            
        # Filter sections based on contact_type to avoid clicking a contact 
        # when a group was requested (or vice-versa) if they share the same name.
        if contact_type == "contact":
            sections = [s for s in sections if s not in ("群聊", "Group Chats")]
        elif contact_type == "group":
            sections = [s for s in sections if s not in ("联系人", "Contacts")]

        open_name = profile.get("open_name", profile.get("app_name", proc_name))
        bundle_id = profile.get("bundle_id", "")

        # ── Strategy A: Screenshot + OCR (tries all sections, then no-section) ──
        ocr_result = self._find_via_ocr(contact_name, sections, proc_name, profile, log, contact_type)
        if ocr_result:
            abs_x, abs_y, target_global_idx = ocr_result
            
            # The user correctly observed that the search dropdown disappears during OCR on their system.
            # We MUST retype the search to restore the UI state before clicking or keyboard navigating.
            log("[4A] OCR identified target, retyping search to restore UI state")
            self._retype_search(contact_name, profile, proc_name, open_name, bundle_id, log)
            
            # The user requested to keep both methods with an if-else.
            # Keyboard navigation is preferred because it's native and safe from OS security quirks.
            use_mouse = str(profile.get("use_mouse_click", "true")).lower() == "true"
            
            if use_mouse:
                log(f"[4A] WeChat OCR: direct-clicked at ({abs_x}, {abs_y})")
                _direct_click(abs_x, abs_y)
            else:
                log("[4A] OCR identified target, navigating via keyboard")
                from pynput.keyboard import Controller as KBCtrl, Key
                log(f"[4A] WeChat OCR: target is at GLOBAL index {target_global_idx}, navigating via keyboard")
                
                kb = KBCtrl()
                for _ in range(target_global_idx):
                    kb.tap(Key.down)
                    time.sleep(0.1)
                kb.tap(Key.enter)
            
            # Give WeChat time to switch chat view
            time.sleep(1.0)
            
            return True

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
        contact_type: str = "any",
    ) -> tuple[int, int, int] | None:
        bounds = profile.get("_window_bounds")
        log("[4A] mss 屏幕区域截图中...")
        tmp, x_off, y_off = _screenshot_window(profile)


        try:
            if not tmp or not os.path.exists(tmp):
                log("[4A] OCR: screenshot failed, skipping OCR")
                return None

            log(f"[4A] OCR: window offset ({x_off},{y_off})")

            all_text_blocks = ocr.get_all_ocr_text(tmp)
            if not all_text_blocks:
                log("[4A] OCR: no text found or execution failed")
                return None
                
            KNOWN_HEADERS = [
                "最常使用", "联系人", "群聊", "聊天记录", "收藏", "功能", 
                "小程序", "公众号", "更多", "搜一搜", "搜索网络结果"
            ]

            present_headers = []
            for b in all_text_blocks:
                t = b["text"].strip()
                # Use substring match to tolerate OCR noise (e.g., "联系人.")
                # Enforce left-alignment (x < 110) to avoid matching chat messages
                # Enforce length check to avoid matching long subtitles that happen to contain the header word
                matched_header = None
                for h in KNOWN_HEADERS:
                    if h in t and len(t) <= len(h) + 4:
                        matched_header = h
                        break
                
                if matched_header and b["min_x"] < 110:
                    b["text"] = matched_header  # normalize
                    present_headers.append(b)
            
            present_headers.sort(key=lambda b: b["mid_y"])
            
            header_boundaries = {}
            for i in range(len(present_headers)):
                h = present_headers[i]
                start_y = h["mid_y"]
                end_y = present_headers[i+1]["mid_y"] if i + 1 < len(present_headers) else float('inf')
                header_boundaries[h["text"].strip()] = (start_y, end_y, h["min_x"])

            contact_hits = [b for b in all_text_blocks if b["text"].replace(" ", "") == contact_name.replace(" ", "")]
            
            candidates = []
            for hit in contact_hits:
                hy = hit["mid_y"]
                assigned_section = None
                for h_text, (start_y, end_y, h_min_x) in header_boundaries.items():
                    if start_y + 15 < hy < end_y:
                        if hit["min_x"] < h_min_x + 100:
                            assigned_section = h_text
                            break
                if assigned_section:
                    candidates.append({"hit": hit, "section": assigned_section})

            valid_sections = ["最常使用", "联系人", "群聊"]
            candidates = [c for c in candidates if c["section"] in valid_sections]
            
            if not candidates:
                log("[4A] OCR: no valid candidates found in targeted sections")
                return None
                
            chosen_hit = None
            log_reason = ""
            
            if contact_type == "contact":
                contact_sec_hits = [c["hit"] for c in candidates if c["section"] == "联系人"]
                if contact_sec_hits:
                    chosen_hit = contact_sec_hits[0]
                    log_reason = "exact match in '联系人'"
                else:
                    recent_hits = [c["hit"] for c in candidates if c["section"] == "最常使用"]
                    recent_hits.sort(key=lambda b: b["mid_y"])
                    if len(recent_hits) >= 2:
                        chosen_hit = recent_hits[0]
                        log_reason = "1st match in '最常使用'"
                    elif len(recent_hits) == 1:
                        chosen_hit = recent_hits[0]
                        log_reason = "only match in '最常使用'"
                        
            elif contact_type == "group":
                group_sec_hits = [c["hit"] for c in candidates if c["section"] == "群聊"]
                if group_sec_hits:
                    chosen_hit = group_sec_hits[0]
                    log_reason = "exact match in '群聊'"
                else:
                    recent_hits = [c["hit"] for c in candidates if c["section"] == "最常使用"]
                    recent_hits.sort(key=lambda b: b["mid_y"])
                    if len(recent_hits) >= 2:
                        chosen_hit = recent_hits[1]
                        log_reason = "2nd match in '最常使用'"
                    elif len(recent_hits) == 1:
                        chosen_hit = recent_hits[0]
                        log_reason = "only match in '最常使用'"
                        
            if not chosen_hit:
                chosen_hit = candidates[0]["hit"]
                log_reason = "fallback to first valid candidate"

            abs_x = int(chosen_hit["mid_x"]) + x_off
            abs_y = int(chosen_hit["mid_y"]) + y_off
            
            sec_min_x = header_boundaries.get("最常使用", (0, 0, 0))[2] if "最常使用" in header_boundaries else 0
            blocks_above = [b for b in all_text_blocks if 50 < b["mid_y"] <= chosen_hit["mid_y"] + 10]
            blocks_above.sort(key=lambda b: b["mid_y"])
            
            rows = []
            curr_row = []
            for b in blocks_above:
                if not curr_row:
                    curr_row.append(b)
                else:
                    if abs(b["mid_y"] - curr_row[0]["mid_y"]) < 20:
                        curr_row.append(b)
                    else:
                        rows.append(curr_row)
                        curr_row = [b]
            if curr_row:
                rows.append(curr_row)
                
            valid_row_count = 0
            for row in rows:
                is_header = any(any(h == b["text"].strip() for h in KNOWN_HEADERS) for b in row)
                is_subtitle = all(b["min_x"] > sec_min_x + 50 for b in row) if sec_min_x else False
                if not is_header and not is_subtitle:
                    valid_row_count += 1
                    
            target_global_idx = max(0, valid_row_count - 1)
            
            log(f"[4A] OCR logic: selected '{contact_name}' via {log_reason} → global_index {target_global_idx}")
            return (abs_x, abs_y, target_global_idx)

        finally:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)

    

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _screenshot_window(profile: dict) -> tuple:
    """
    Capture WeChat's window using mss region crop.
    Returns (tmp_path, x_offset, y_offset).
    """
    import utils

    bounds = profile.get("_window_bounds", {})
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
