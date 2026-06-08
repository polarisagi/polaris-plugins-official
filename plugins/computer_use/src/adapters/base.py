"""
BaseAdapter — generic search-result selection for chat apps.

Works out of the box for apps where the search dropdown is part of the
main window's accessibility tree (Slack, Feishu, DingTalk, Telegram, etc.).

Override select_search_result() in an app-specific subclass when the app's
UI behaviour differs (e.g. separate NSWindow dropdown, deeper hierarchy).
"""
import platform
import time

from pynput.mouse import Button

import utils


class BaseAdapter:

    def select_search_result(
        self,
        contact_name: str,
        section: str | None,
        profile: dict,
        proc_name: str,
        plat: str,
        log,
    ) -> bool:
        """
        Try to click the correct search result after the user typed a query.
        Returns True (always — Strategy C is a guaranteed keyboard fallback).

        Strategy A — section-aware accessibility click:
            Finds the section header (e.g. "Group Chats") in the main window
            and clicks the first matching item below it.

        Strategy B — bounded accessibility click:
            Finds the element by name anywhere in the main window (no OCR,
            no full-screen search — cannot accidentally click another app).

        Strategy C — keyboard navigation (Down + Enter):
            Selects the first inline suggestion without opening the full
            global-search page. Safe last resort for any app.
        """
        match_index = int(profile.get("result_match_index", 0) or 0)

        # Strategy A
        if plat == "Darwin" and section:
            coords = utils.find_in_section(contact_name, section)
            if coords:
                utils.mouse.position = coords
                utils.mouse.click(Button.left)
                log(f"[4A] Clicked in '{section}' section at {coords}")
                return True
            log(f"[4A] Section '{section}' not found in main window")

        # Strategy B
        if plat == "Darwin":
            coords = utils.find_element_in_window(contact_name, match_index)
            if coords:
                utils.mouse.position = coords
                utils.mouse.click(Button.left)
                log(f"[4B] Clicked via window accessibility at {coords}")
                return True
            log("[4B] Element not found in window accessibility tree")

        # Strategy C — keyboard
        self._keyboard_select(proc_name, plat, log)
        return True

    def _keyboard_select(self, proc_name: str, plat: str, log):
        if plat == "Darwin":
            utils.osa_send_key(proc_name, "down")
            time.sleep(0.25)
            utils.osa_send_key(proc_name, "enter")
        else:
            utils.press_shortcut("down")
            time.sleep(0.25)
            utils.press_shortcut("enter")
        log("[4C] Selected via keyboard Down+Enter")

    def press_search_shortcut(self, proc_name: str, plat: str, search_sc: str):
        """Press the shortcut to open the global search box."""
        utils.press_shortcut(search_sc)

    def press_escape(self, proc_name: str, plat: str):
        """Press Escape to close dropdowns or reset state."""
        utils.press_shortcut("esc")

    def press_send_shortcut(self, proc_name: str, plat: str, send_sc: str):
        """Press the shortcut to send a chat message."""
        utils.press_shortcut(send_sc)
