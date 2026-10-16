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

import os
import time

import utils

from adapters.base import BaseAdapter

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
        ocr_result = self._find_via_ocr(
            contact_name, sections, proc_name, profile, log, contact_type
        )
        if ocr_result:
            abs_x, abs_y, target_global_idx = ocr_result

            # The user correctly observed that the search dropdown disappears during OCR on their system.
            # We MUST retype the search to restore the UI state before clicking or keyboard navigating.
            log("[4A] OCR identified target, retyping search to restore UI state")
            self._retype_search(
                contact_name, profile, proc_name, open_name, bundle_id, log
            )

            # The user requested to keep both methods with an if-else.
            # Keyboard navigation is preferred because it's native and safe from OS security quirks.
            use_mouse = str(profile.get("use_mouse_click", "true")).lower() == "true"

            if use_mouse:
                log(f"[4A] WeChat OCR: direct-clicked at ({abs_x}, {abs_y})")
                _direct_click(abs_x, abs_y)
            else:
                log("[4A] OCR identified target, navigating via keyboard")
                from pynput.keyboard import Controller as KBCtrl
                from pynput.keyboard import Key

                log(
                    f"[4A] WeChat OCR: target is at GLOBAL index {target_global_idx}, navigating via keyboard"
                )

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
        from pynput.keyboard import Controller as _KBCtrl
        from pynput.keyboard import Key as _Key

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

            boundaries = _section_boundaries(_detect_headers(all_text_blocks))
            candidates = _assign_sections(all_text_blocks, contact_name, boundaries)
            if not candidates:
                log("[4A] OCR: no valid candidates found in targeted sections")
                return None

            chosen_hit, log_reason = _choose_hit(candidates, contact_type)
            abs_x = int(chosen_hit["mid_x"]) + x_off
            abs_y = int(chosen_hit["mid_y"]) + y_off
            target_global_idx = _global_index(all_text_blocks, chosen_hit, boundaries)

            log(
                f"[4A] OCR logic: selected '{contact_name}' via {log_reason} → global_index {target_global_idx}"
            )
            return (abs_x, abs_y, target_global_idx)

        finally:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)


# ---------------------------------------------------------------------------
# OCR 搜索结果解析（纯函数，便于单独验证）
# ---------------------------------------------------------------------------

# 微信搜索下拉框中的分组标题
_KNOWN_HEADERS = [
    "最常使用",
    "联系人",
    "群聊",
    "聊天记录",
    "收藏",
    "功能",
    "小程序",
    "公众号",
    "更多",
    "搜一搜",
    "搜索网络结果",
]
# 只有这些分组里的命中才可能是要找的会话
_VALID_SECTIONS = ["最常使用", "联系人", "群聊"]


def _detect_headers(blocks: list[dict]) -> list[dict]:
    """找出分组标题块（会把块文本规范化为标准标题），按纵坐标排序返回。

    子串匹配容忍 OCR 噪声（如「联系人.」）；要求左对齐（x < 110）以排除聊天内容，
    并限制长度，避免误匹配恰好包含标题词的长副标题。
    """
    present = []
    for b in blocks:
        t = b["text"].strip()
        matched = next(
            (h for h in _KNOWN_HEADERS if h in t and len(t) <= len(h) + 4), None
        )
        if matched and b["min_x"] < 110:
            b["text"] = matched
            present.append(b)
    present.sort(key=lambda b: b["mid_y"])
    return present


def _section_boundaries(headers: list[dict]) -> dict[str, tuple]:
    """每个分组的 (起始 y, 结束 y, 标题 min_x)；结束 y 为下一个标题的 y 或无穷大。"""
    out: dict[str, tuple] = {}
    for i, h in enumerate(headers):
        end_y = headers[i + 1]["mid_y"] if i + 1 < len(headers) else float("inf")
        out[h["text"].strip()] = (h["mid_y"], end_y, h["min_x"])
    return out


def _assign_sections(
    blocks: list[dict], contact_name: str, boundaries: dict[str, tuple]
) -> list[dict]:
    """把与联系人名完全匹配的文本块归入所在分组，只保留有效分组中的候选。"""
    target = contact_name.replace(" ", "")
    candidates = []
    for hit in blocks:
        if hit["text"].replace(" ", "") != target:
            continue
        hy = hit["mid_y"]
        section = next(
            (
                name
                for name, (start_y, end_y, h_min_x) in boundaries.items()
                if start_y + 15 < hy < end_y and hit["min_x"] < h_min_x + 100
            ),
            None,
        )
        if section:
            candidates.append({"hit": hit, "section": section})
    return [c for c in candidates if c["section"] in _VALID_SECTIONS]


def _pick_from_recent(candidates: list[dict], want_second: bool) -> tuple:
    """从「最常使用」分组按纵坐标取命中：群聊取第 2 个，联系人取第 1 个。"""
    recent = sorted(
        (c["hit"] for c in candidates if c["section"] == "最常使用"),
        key=lambda b: b["mid_y"],
    )
    if len(recent) >= 2:
        if want_second:
            return recent[1], "2nd match in '最常使用'"
        return recent[0], "1st match in '最常使用'"
    if len(recent) == 1:
        return recent[0], "only match in '最常使用'"
    return None, ""


def _choose_hit(candidates: list[dict], contact_type: str) -> tuple[dict, str]:
    """按会话类型挑选命中：优先对应分组，其次「最常使用」，最后退回第一个有效候选。"""
    chosen, reason = None, ""
    if contact_type in ("contact", "group"):
        section = "联系人" if contact_type == "contact" else "群聊"
        exact = [c["hit"] for c in candidates if c["section"] == section]
        if exact:
            chosen, reason = exact[0], f"exact match in '{section}'"
        else:
            chosen, reason = _pick_from_recent(
                candidates, want_second=contact_type == "group"
            )
    if not chosen:
        chosen, reason = candidates[0]["hit"], "fallback to first valid candidate"
    return chosen, reason


def _group_rows(blocks: list[dict]) -> list[list[dict]]:
    """把已按 y 排序的文本块按行聚合（与行首块 y 差 < 20 视为同一行）。"""
    rows: list[list[dict]] = []
    curr: list[dict] = []
    for b in blocks:
        if curr and abs(b["mid_y"] - curr[0]["mid_y"]) >= 20:
            rows.append(curr)
            curr = []
        curr.append(b)
    if curr:
        rows.append(curr)
    return rows


def _global_index(
    blocks: list[dict], chosen_hit: dict, boundaries: dict[str, tuple]
) -> int:
    """命中项在整个下拉列表中的全局序号：统计其上方（含自身）非标题、非副标题的行数。"""
    sec_min_x = boundaries["最常使用"][2] if "最常使用" in boundaries else 0
    above = sorted(
        (b for b in blocks if 50 < b["mid_y"] <= chosen_hit["mid_y"] + 10),
        key=lambda b: b["mid_y"],
    )
    count = 0
    for row in _group_rows(above):
        is_header = any(b["text"].strip() in _KNOWN_HEADERS for b in row)
        is_subtitle = bool(sec_min_x) and all(b["min_x"] > sec_min_x + 50 for b in row)
        if not is_header and not is_subtitle:
            count += 1
    return max(0, count - 1)


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
    from pynput.mouse import Button as _Btn
    from pynput.mouse import Controller as _MC

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
