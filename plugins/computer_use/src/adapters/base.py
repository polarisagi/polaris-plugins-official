"""
BaseAdapter — generic search-result selection for chat apps.

Uses Universal OCR-based Visual Selection (Strategy A) as the primary method, 
with Keyboard navigation (Strategy B) as a guaranteed fallback.
"""

import time
import os
import sys

import utils

# Add src to path so we can import ocr
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import ocr


class BaseAdapter:
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
        """
        Select a contact from search results using OCR+CV.
        """
        match_index = int(profile.get("result_match_index", 0) or 0)
        
        # Strategy A — Visual OCR click
        coords = self._find_via_ocr(contact_name, section, profile, proc_name, match_index, log)
        if coords:
            abs_x, abs_y = coords
            log(f"[4A] OCR identified target, clicking at ({abs_x}, {abs_y})")
            open_name = profile.get("open_name", profile.get("app_name", proc_name))
            bundle_id = profile.get("bundle_id", "")
            if not utils.safe_click(abs_x, abs_y, proc_name, open_name, bundle_id):
                log("[4A] OCR identified target, but failed to restore focus before clicking")
                return False
            return True
            
        log("[4A] Target not found via OCR, falling back to keyboard")

        # Strategy B — Keyboard navigation (Down + Enter)
        self._keyboard_select(proc_name, plat, log)
        return True

    def _find_via_ocr(self, contact_name: str, section: str | None, profile: dict, proc_name: str, match_index: int, log) -> tuple | None:
        """Take screenshot and use OCR to find contact_name. Filters by section if provided."""
        # Grab window bounds to crop screenshot
        open_name = profile.get("open_name", profile.get("app_name", proc_name))
        bundle_id = profile.get("bundle_id", "")
        
        utils.ensure_frontmost(proc_name, open_name, bundle_id)
        time.sleep(0.5) # Wait for search results to render
        
        bounds = utils.get_frontmost_window_bounds()
        tmp_path, x_off, y_off = utils.capture_screen(bounds=bounds)
        if not (tmp_path and os.path.exists(tmp_path)):
            log("Failed to capture screen for OCR")
            return None
            
        try:
            blocks = ocr.get_all_ocr_text(tmp_path)
            if not blocks:
                return None
                
            # If section is provided, find its Y coordinate
            section_y_min = -1
            if section:
                for b in blocks:
                    if b["text"] == section:
                        section_y_min = b["mid_y"]
                        break
            
            # Find all matching candidates
            candidates = []
            for b in blocks:
                # If section is defined, candidate MUST be physically below the section header
                if section_y_min >= 0 and b["mid_y"] <= section_y_min:
                    continue
                    
                # Exact match
                if b["text"] == contact_name:
                    candidates.append(b)
                # Substring/prefix match fallback
                elif b["text"].startswith(contact_name):
                    candidates.append(b)
                    
            if not candidates:
                return None
                
            # Sort by Y coordinate (top to bottom)
            candidates.sort(key=lambda x: x["mid_y"])
            
            # Select based on match_index
            if match_index < len(candidates):
                best = candidates[match_index]
            else:
                best = candidates[-1] # Fallback to last if index is out of bounds
                
            return best["mid_x"] + x_off, best["mid_y"] + y_off
        except Exception as e:
            log(f"OCR Exception: {e}")
            return None
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass

    def _keyboard_select(self, proc_name: str, plat: str, log):
        if plat == "Darwin":
            utils.osa_send_key(proc_name, "down")
            time.sleep(0.25)
            utils.osa_send_key(proc_name, "enter")
        else:
            utils.press_shortcut("down")
            time.sleep(0.25)
            utils.press_shortcut("enter")
        log("[4B] Selected via keyboard Down+Enter")

    def press_search_shortcut(self, proc_name: str, plat: str, search_sc: str):
        """Press the shortcut to open the global search box."""
        utils.press_shortcut(search_sc)

    def press_escape(self, proc_name: str, plat: str):
        """Press Escape to close dropdowns or reset state."""
        utils.press_shortcut("esc")

    def press_send_shortcut(self, proc_name: str, plat: str, send_sc: str):
        """Press the shortcut to send a chat message."""
        utils.press_shortcut(send_sc)
