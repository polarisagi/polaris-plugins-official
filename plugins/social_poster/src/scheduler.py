"""File-based post scheduler — stores pending tasks in ~/.polaris_scheduler.json."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

SCHEDULE_FILE = Path.home() / ".polaris_social_scheduler.json"


def _load() -> list:
    if SCHEDULE_FILE.exists():
        try:
            return json.loads(SCHEDULE_FILE.read_text("utf-8"))
        except Exception:
            return []
    return []


def _save(tasks: list):
    SCHEDULE_FILE.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), "utf-8")


def add_task(
    platform: str,
    content: str,
    media_paths: list,
    scheduled_time: str,
    post_type: str = "post",
    extra: Optional[dict] = None,
) -> str:
    """Schedule a post. scheduled_time must be ISO-8601 (e.g. '2025-07-01T09:00:00').
    Returns the task_id."""
    tasks = _load()
    task_id = f"sp_{int(datetime.now().timestamp() * 1000)}"
    tasks.append(
        {
            "id": task_id,
            "platform": platform,
            "content": content,
            "media_paths": media_paths or [],
            "scheduled_time": scheduled_time,
            "post_type": post_type,  # post | video | story | thread
            "extra": extra or {},
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }
    )
    _save(tasks)
    return task_id


def list_tasks(platform: Optional[str] = None, status: str = "pending") -> list:
    tasks = _load()
    if platform:
        tasks = [t for t in tasks if t["platform"] == platform]
    return [t for t in tasks if t.get("status") == status]


def cancel_task(task_id: str) -> bool:
    tasks = _load()
    for t in tasks:
        if t["id"] == task_id and t["status"] == "pending":
            t["status"] = "cancelled"
            _save(tasks)
            return True
    return False


def get_due_tasks() -> list:
    """Return all pending tasks whose scheduled_time has passed."""
    now = datetime.now().isoformat()
    return [
        t
        for t in _load()
        if t.get("status") == "pending" and t["scheduled_time"] <= now
    ]


def mark_done(task_id: str, success: bool, error: str = ""):
    tasks = _load()
    for t in tasks:
        if t["id"] == task_id:
            t["status"] = "done" if success else "failed"
            t["error"] = error
            t["completed_at"] = datetime.now().isoformat()
            break
    _save(tasks)
