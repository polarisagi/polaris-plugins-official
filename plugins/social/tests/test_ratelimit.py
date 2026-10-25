"""站点限速器单元测试。

验证内容：
1. hour / day 上限拦截
2. min_interval 间隔等待
3. active_hours 跨午夜判定
4. cooldown 风控熔断
5. 多进程并发 acquire 串行安全性
"""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

import pytest
from src.ratelimit import (
    Limits,
    acquire,
    get_site_status,
    init_db,
    is_in_active_hours,
    mark_blocked,
)
from src.utils.browser_hub import HubError


def test_active_hours() -> None:
    # 模拟本地时间戳：设置特定小时与分钟
    base_tm = time.localtime(1700000000.0)

    # 1. 普通时间段 08:00-23:30
    normal_hours = "08:00-23:30"
    # 构造 10:00 的时间戳
    t_10am = time.mktime(
        (base_tm.tm_year, base_tm.tm_mon, base_tm.tm_mday, 10, 0, 0, 0, 0, -1)
    )
    assert is_in_active_hours(normal_hours, t_10am) is True

    # 构造 07:00 的时间戳
    t_7am = time.mktime(
        (base_tm.tm_year, base_tm.tm_mon, base_tm.tm_mday, 7, 0, 0, 0, 0, -1)
    )
    assert is_in_active_hours(normal_hours, t_7am) is False

    # 2. 跨午夜时间段 22:00-04:00
    cross_hours = "22:00-04:00"
    t_23pm = time.mktime(
        (base_tm.tm_year, base_tm.tm_mon, base_tm.tm_mday, 23, 0, 0, 0, 0, -1)
    )
    assert is_in_active_hours(cross_hours, t_23pm) is True

    t_3am = time.mktime(
        (base_tm.tm_year, base_tm.tm_mon, base_tm.tm_mday, 3, 0, 0, 0, 0, -1)
    )
    assert is_in_active_hours(cross_hours, t_3am) is True

    t_12pm = time.mktime(
        (base_tm.tm_year, base_tm.tm_mon, base_tm.tm_mday, 12, 0, 0, 0, 0, -1)
    )
    assert is_in_active_hours(cross_hours, t_12pm) is False


@pytest.mark.asyncio
async def test_ratelimit_limits_and_cooldown(tmp_path: Path) -> None:
    db_file = tmp_path / "test_rl.db"
    limits = Limits(
        min_interval_s=1.0,
        jitter_s=(0.1, 0.1),
        max_per_hour=3,
        max_per_day=5,
        active_hours="00:00-24:00",
        cooldown_on_block_h=2.0,
    )

    current_t = 1000.0

    def fake_now() -> float:
        return current_t

    # 前 3 次请求均应成功
    for _ in range(3):
        await acquire("site_a", limits, db_path=db_file, now=fake_now)
        current_t += 2.0

    # 第 4 次请求因 max_per_hour=3 被拦截
    with pytest.raises(HubError) as exc_info:
        await acquire("site_a", limits, db_path=db_file, now=fake_now)
    assert exc_info.value.code == "rate_limited"

    # 跨过 1 小时后应可再次请求
    current_t += 3601.0
    await acquire("site_a", limits, db_path=db_file, now=fake_now)

    # 触发风控熔断
    mark_blocked("site_a", "遭遇验证码", hours=2.0, db_path=db_file, now=fake_now)

    with pytest.raises(HubError) as exc_info:
        await acquire("site_a", limits, db_path=db_file, now=fake_now)
    assert exc_info.value.code == "cooling_down"

    status = get_site_status("site_a", limits, db_path=db_file, now=fake_now)
    assert status["cooling_until"] == current_t + 7200.0


def _worker_proc(db_file: str, return_list: list) -> None:
    """多进程并发 acquire 辅助函数。"""
    limits = Limits(
        min_interval_s=0.2,
        jitter_s=(0.05, 0.1),
        max_per_hour=100,
        max_per_day=1000,
        active_hours="00:00-24:00",
    )

    async def run() -> None:
        for _ in range(3):
            t0 = time.time()
            await acquire("concurrent_site", limits, db_path=Path(db_file))
            return_list.append((os.getpid(), t0, time.time()))

    asyncio.run(run())


def test_multiprocessing_acquire() -> None:
    # 断言数据库中的计划时间戳而非墙钟唤醒时间：后者受进程调度延迟影响，机器繁忙时会误报。
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        manager = multiprocessing.Manager()
        results = manager.list()

        p1 = multiprocessing.Process(target=_worker_proc, args=(db_path, results))
        p2 = multiprocessing.Process(target=_worker_proc, args=(db_path, results))

        p1.start()
        p2.start()
        p1.join(timeout=30)
        p2.join(timeout=30)

        assert p1.exitcode == 0, f"子进程 1 异常退出，exitcode={p1.exitcode}"
        assert p2.exitcode == 0, f"子进程 2 异常退出，exitcode={p2.exitcode}"
        assert len(results) == 6

        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT ts FROM site_requests WHERE site = 'concurrent_site' ORDER BY ts"
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 6
        scheduled = [row[0] for row in rows]
        for i in range(1, len(scheduled)):
            # min_interval_s=0.2；jitter 只会让间隔更大
            assert scheduled[i] - scheduled[i - 1] >= 0.2 - 1e-6
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_init_db_waits_for_wal_lock(tmp_path: Path) -> None:
    # 另一连接持有写锁（RESERVED）时，新库的 WAL 切换不经过 busy handler、会立即 locked；
    # init_db 必须重试到锁释放而不是报错。（BEGIN EXCLUSIVE 会走 busy handler，无法复现。）
    db = tmp_path / "locked.db"
    holder = sqlite3.connect(str(db), isolation_level=None, check_same_thread=False)
    holder.execute("BEGIN IMMEDIATE;")
    released = threading.Event()

    def release() -> None:
        time.sleep(0.3)
        holder.execute("COMMIT;")
        holder.close()
        released.set()

    t = threading.Thread(target=release)
    t.start()
    try:
        conn = init_db(db)
        try:
            assert conn.execute("PRAGMA journal_mode;").fetchone()[0].lower() == "wal"
        finally:
            conn.close()
    finally:
        t.join(timeout=5)
    assert released.is_set()
