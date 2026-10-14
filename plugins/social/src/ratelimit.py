"""跨进程 SQLite 站点限速器与风控熔断。

为何需要该模块：
1. 采集（harvest）操作复用用户的日常或托管浏览器，必须严格规避目标站点的频次风控。
2. 多个进程（例如不同自动化管线、多任务 Agent）可能同时并发访问同一站点，
   必须基于 SQLite WAL 模式与 BEGIN IMMEDIATE 事务实现跨进程串行限速。
3. 提供主动与被动风控熔断（cooldown_on_block），遭遇拦截时立即全进程避让。
"""

from __future__ import annotations

import asyncio
import random
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .utils.browser_hub import HubError
from .utils.cfg import CFG


class Limits(BaseModel):
    """站点频次限制与活跃时间配置。"""

    min_interval_s: float = Field(default=4.0, description="单次请求最小间隔秒数")
    jitter_s: tuple[float, float] = Field(
        default=(0.5, 1.5), description="随机抖动区间"
    )
    max_per_hour: int = Field(default=60, description="每小时最大请求数")
    max_per_day: int = Field(default=300, description="每天最大请求数")
    active_hours: str = Field(
        default="08:00-23:30", description="本地活跃时间段，支持跨午夜"
    )
    cooldown_on_block_h: float = Field(
        default=6.0, description="遭遇风控时的封禁冷却小时数"
    )


def get_db_path() -> Path:
    """获取限速 SQLite 数据库路径。"""
    return CFG / "ratelimit.db"


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    """初始化数据库并应用 WAL 模式与表结构。"""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS site_requests(
            site TEXT NOT NULL,
            ts REAL NOT NULL
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sr ON site_requests(site, ts);")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS site_state(
            site TEXT PRIMARY KEY,
            cooldown_until REAL NOT NULL DEFAULT 0,
            last_block_reason TEXT NOT NULL DEFAULT ''
        );
        """
    )
    return conn


def is_in_active_hours(active_hours: str, ts: float) -> bool:
    """判断给定时间戳是否位于设定的活跃时间段内（本地时区）。"""
    active = active_hours.strip()
    if active in ("00:00-24:00", "00:00-23:59", ""):
        return True

    try:
        start_str, end_str = active.split("-", 1)
        sh, sm = map(int, start_str.split(":", 1))
        eh, em = map(int, end_str.split(":", 1))
        start_m = sh * 60 + sm
        end_m = eh * 60 + em
    except (ValueError, TypeError):
        # 解析异常时宽松放行，避免配置笔误导致彻底拒绝
        return True

    tm = time.localtime(ts)
    curr_m = tm.tm_hour * 60 + tm.tm_min

    if start_m <= end_m:
        return start_m <= curr_m <= end_m
    # 跨午夜场景，如 22:00-04:00
    return curr_m >= start_m or curr_m <= end_m


def mark_blocked(
    site: str,
    reason: str,
    hours: float = 6.0,
    db_path: Path | None = None,
    now: Callable[[], float] = time.time,
) -> None:
    """将站点标记为风控冷却状态。"""
    current_ts = now()
    cooldown_until = current_ts + hours * 3600.0
    conn = init_db(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE;")
        conn.execute(
            """
            INSERT INTO site_state(site, cooldown_until, last_block_reason)
            VALUES(?, ?, ?)
            ON CONFLICT(site) DO UPDATE SET
                cooldown_until = excluded.cooldown_until,
                last_block_reason = excluded.last_block_reason;
            """,
            (site, cooldown_until, reason),
        )
        conn.execute("COMMIT;")
    finally:
        conn.close()


async def acquire(
    site: str,
    limits: Limits,
    db_path: Path | None = None,
    now: Callable[[], float] = time.time,
) -> None:
    """获取站点访问许可，超出配额或在风控期则抛出 HubError。

    并发安全性：
    在 BEGIN IMMEDIATE 事务中计算并锁定计划请求时间，
    即使多进程同时请求，也能计算出严格递增的调度时间戳并交错等待，
    同时在释放事务锁后执行非阻塞 asyncio.sleep。
    """
    current_ts = now()

    # 1. 检查活跃时间
    if not is_in_active_hours(limits.active_hours, current_ts):
        raise HubError(
            "out_of_hours",
            f"站点 {site} 当前不在允许采集时间段 ({limits.active_hours})",
        )

    conn = init_db(db_path)
    sleep_needed: float = 0.0
    try:
        conn.execute("BEGIN IMMEDIATE;")

        # 2. 检查风控冷却状态
        cursor = conn.execute(
            "SELECT cooldown_until, last_block_reason FROM site_state WHERE site = ?;",
            (site,),
        )
        row = cursor.fetchone()
        if row:
            cooldown_until, reason = row
            if cooldown_until > current_ts:
                rem_m = int((cooldown_until - current_ts) / 60)
                raise HubError(
                    "cooling_down",
                    f"站点 {site} 处于风控冷却期（还剩 {rem_m} 分钟，原因: {reason}）",
                    extra={"until": cooldown_until},
                )

        # 3. 检查近 1 小时频次限制
        cursor = conn.execute(
            "SELECT COUNT(*) FROM site_requests WHERE site = ? AND ts >= ?;",
            (site, current_ts - 3600.0),
        )
        count_1h = cursor.fetchone()[0]
        if count_1h >= limits.max_per_hour:
            raise HubError(
                "rate_limited",
                f"站点 {site} 达到每小时请求上限 ({limits.max_per_hour}/h)",
            )

        # 4. 检查近 24 小时频次限制
        cursor = conn.execute(
            "SELECT COUNT(*) FROM site_requests WHERE site = ? AND ts >= ?;",
            (site, current_ts - 86400.0),
        )
        count_24h = cursor.fetchone()[0]
        if count_24h >= limits.max_per_day:
            raise HubError(
                "rate_limited", f"站点 {site} 达到每日请求上限 ({limits.max_per_day}/d)"
            )

        # 5. 检查最小间隔与抖动
        cursor = conn.execute(
            "SELECT MAX(ts) FROM site_requests WHERE site = ?;", (site,)
        )
        last_ts_row = cursor.fetchone()[0]
        last_ts = float(last_ts_row) if last_ts_row is not None else 0.0

        jitter = random.uniform(limits.jitter_s[0], limits.jitter_s[1])
        scheduled_ts = max(current_ts, last_ts + limits.min_interval_s + jitter)
        delay = scheduled_ts - current_ts

        if delay > 60.0:
            raise HubError(
                "rate_limited", f"站点 {site} 排队需等待 {delay:.1f}s，超过 60s 阈值"
            )

        if delay > 0:
            sleep_needed = delay

        # 记录本次调度时间戳
        conn.execute(
            "INSERT INTO site_requests(site, ts) VALUES(?, ?);", (site, scheduled_ts)
        )

        # 顺带清理 2 天前的过期记录，保持数据库轻量
        conn.execute(
            "DELETE FROM site_requests WHERE ts < ?;", (current_ts - 172800.0,)
        )

        conn.execute("COMMIT;")
    except Exception:
        # 遇错误主动回滚事务
        try:
            conn.execute("ROLLBACK;")
        except sqlite3.OperationalError:
            pass
        raise
    finally:
        conn.close()

    if sleep_needed > 0:
        await asyncio.sleep(sleep_needed)


def get_site_status(
    site: str,
    limits: Limits | None = None,
    db_path: Path | None = None,
    now: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """查询指定站点的当前限速与风控剩余指标。"""
    current_ts = now()
    conn = init_db(db_path)
    try:
        # 查询冷却
        cursor = conn.execute(
            "SELECT cooldown_until FROM site_state WHERE site = ?;", (site,)
        )
        row = cursor.fetchone()
        cooling_until = float(row[0]) if (row and row[0] > current_ts) else 0.0

        cursor = conn.execute(
            "SELECT COUNT(*) FROM site_requests WHERE site = ? AND ts >= ?;",
            (site, current_ts - 3600.0),
        )
        used_1h = cursor.fetchone()[0]

        cursor = conn.execute(
            "SELECT COUNT(*) FROM site_requests WHERE site = ? AND ts >= ?;",
            (site, current_ts - 86400.0),
        )
        used_24h = cursor.fetchone()[0]

        max_1h = limits.max_per_hour if limits else 60
        max_24h = limits.max_per_day if limits else 300

        return {
            "site": site,
            "cooling_until": cooling_until,
            "remaining_hour": max(0, max_1h - used_1h),
            "remaining_day": max(0, max_24h - used_24h),
        }
    finally:
        conn.close()
