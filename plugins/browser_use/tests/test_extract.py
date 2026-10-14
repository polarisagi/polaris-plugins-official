"""browser_use 正文分页与 ref 正则单元测试（全部离线）。"""

from __future__ import annotations

from src.extract import paginate_content
from src.tools_browser import REF_PATTERN


def test_paginate_content() -> None:
    text = "abcdefghijklmnopqrstuvwxyz"
    content, chash, truncated, next_off = paginate_content(text, offset=0, max_chars=10)
    assert content == "abcdefghij"
    assert truncated is True
    assert next_off == 10
    assert len(chash) == 16

    content2, _, truncated2, next_off2 = paginate_content(text, offset=20, max_chars=10)
    assert content2 == "uvwxyz"
    assert truncated2 is False
    assert next_off2 is None


def test_ref_pattern() -> None:
    assert REF_PATTERN.match("e1") is not None
    assert REF_PATTERN.match("e80") is not None
    assert REF_PATTERN.match("e99999") is not None
    assert REF_PATTERN.match("e") is None
    assert REF_PATTERN.match("e123456") is None
    assert REF_PATTERN.match("e1; rm -rf /") is None
    assert REF_PATTERN.match("button") is None
