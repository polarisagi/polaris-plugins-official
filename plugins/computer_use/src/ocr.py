import os
import subprocess
import logging

def get_all_ocr_text(screenshot_path: str) -> list[dict]:
    """
    Calls describe_screen.swift to extract all text from the image.
    Returns a list of dicts: 
    [{"text": str, "min_x": int, "mid_x": int, "mid_y": int}, ...]
    """
    _DESCRIBE_BIN = os.path.join(os.path.dirname(__file__), "describe_screen")
    _DESCRIBE_SRC = os.path.join(os.path.dirname(__file__), "describe_screen.swift")
    
    import utils
    if not utils.compile_swift_binary(_DESCRIBE_SRC, _DESCRIBE_BIN):
        logging.error("Failed to compile or find describe_screen binary")
        return []
        
    try:
        out = (
            subprocess.check_output([_DESCRIBE_BIN, screenshot_path], timeout=15)
            .decode()
            .strip()
        )
    except Exception as e:
        logging.error(f"OCR execution failed: {e}")
        return []
        
    results = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) >= 4:
            text = parts[0]
            try:
                min_x = int(parts[1])
                mid_x = int(parts[2])
                mid_y = int(parts[3])
                results.append({
                    "text": text,
                    "min_x": min_x,
                    "mid_x": mid_x,
                    "mid_y": mid_y
                })
            except ValueError:
                pass
        # Fallback for old binary format just in case (text|x|y)
        elif len(parts) == 3:
            text = parts[0]
            try:
                mid_x = int(parts[1])
                mid_y = int(parts[2])
                results.append({
                    "text": text,
                    "min_x": mid_x,
                    "mid_x": mid_x,
                    "mid_y": mid_y
                })
            except ValueError:
                pass
                
    return results
