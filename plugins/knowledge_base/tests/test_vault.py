"""资料库（Vault）核心单元测试：保存 / 去重 / 更新、路径沙盒、FTS、标签、移动、front matter。"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from src import vault as v
from src.vault import Vault, VaultError


class Clock:
    """可控时钟，便于断言 saved_at / updated_at。"""

    def __init__(self) -> None:
        self.t = datetime(2026, 10, 14, 8, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.t

    def tick(self, seconds: int = 60) -> None:
        self.t = datetime.fromtimestamp(self.t.timestamp() + seconds, tz=UTC)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def vault(tmp_path: Path, clock: Clock) -> Vault:
    return Vault(tmp_path / "Vault", now=clock)


def doc(url: str = "https://www.zhihu.com/question/1", **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "url": url,
        "title": "如何构建 Agent 系统",
        "content": "智能体系统需要工具调用、记忆与评估。\n\n第二段讨论 retrieval augmented generation。",
        "source": "zhihu",
        "author": "张三",
        "published_at": "2026-09-30T08:00:00Z",
        "tags": ["ai", "agent"],
    }
    base.update(kw)
    return base


# ── 保存 / 去重 / 更新 ────────────────────────────────────────────────────────


def test_save_layout_and_front_matter(vault: Vault) -> None:
    res = vault.save([doc()])
    assert res["failed"] == [] and res["updated"] == [] and res["unchanged"] == []
    (path,) = res["saved"]
    p = Path(path)
    assert p.is_file()
    assert p.relative_to(vault.real_root).parts[:3] == ("zhihu", "2026", "09")
    assert p.suffix == ".md" and p.stem == "如何构建-Agent-系统"

    meta, body = v.parse_front_matter(p.read_text(encoding="utf-8"))
    assert meta["title"] == "如何构建 Agent 系统"
    assert meta["url"] == "https://www.zhihu.com/question/1"
    assert meta["source"] == "zhihu"
    assert meta["author"] == "张三"
    assert meta["published_at"] == "2026-09-30T08:00:00Z"
    assert meta["saved_at"] == "2026-10-14T08:00:00Z"
    assert meta["tags"] == ["ai", "agent"]
    assert meta["kind"] == "raw"
    assert "retrieval augmented generation" in body
    assert (vault.real_root / ".polaris" / "index.sqlite").is_file()


def test_dedup_unchanged_then_update(vault: Vault, clock: Clock) -> None:
    first = vault.save([doc()])["saved"][0]
    clock.tick(3600)

    again = vault.save([doc(url="https://www.zhihu.com/question/1#section")])
    assert again["unchanged"] == [first]
    assert again["saved"] == [] and again["updated"] == []

    changed = vault.save([doc(content="全新的正文内容", tags=["extra"])])
    assert changed["updated"] == [first] and changed["saved"] == []
    meta, body = v.parse_front_matter(Path(first).read_text(encoding="utf-8"))
    assert body.strip() == "全新的正文内容"
    assert meta["saved_at"] == "2026-10-14T08:00:00Z"
    assert meta["updated_at"] == "2026-10-14T09:00:00Z"
    assert meta["tags"] == ["ai", "agent", "extra"]  # 保留已有标签并并入新标签
    assert len(vault.list_docs()["items"]) == 1


def test_recreated_when_file_deleted(vault: Vault) -> None:
    first = Path(vault.save([doc()])["saved"][0])
    first.unlink()
    res = vault.save([doc()])
    assert len(res["saved"]) == 1
    assert len(vault.list_docs()["items"]) == 1


def test_tracking_params_are_ignored_for_dedup(vault: Vault) -> None:
    vault.save([doc(url="https://example.com/a?id=1&utm_source=x")])
    res = vault.save([doc(url="https://EXAMPLE.com/a?id=1&utm_medium=y#top")])
    assert len(res["unchanged"]) == 1
    res2 = vault.save([doc(url="https://example.com/a?id=2")])
    assert len(res2["saved"]) == 1


def test_digest_layout_and_urlless_dedup(vault: Vault) -> None:
    d = {"title": "每日摘要 10/14", "content": "今天的要点：A、B、C"}
    res = vault.save([d], kind="digest")
    (path,) = res["saved"]
    rel = Path(path).relative_to(vault.real_root)
    assert rel.parts[0] == "digests"
    assert rel.name == "2026-10-14-每日摘要-10-14.md"
    meta, _ = v.parse_front_matter(Path(path).read_text(encoding="utf-8"))
    assert meta["kind"] == "digest"
    assert vault.save([d], kind="digest")["unchanged"] == [path]
    assert vault.list_docs(kind="digest")["count"] == 1
    assert vault.list_docs(kind="raw")["count"] == 0


def test_collection_prefix(vault: Vault) -> None:
    raw = vault.save([doc()], collection="每日/AI")["saved"][0]
    assert Path(raw).relative_to(vault.real_root).parts[:2] == ("每日", "AI")
    dig = vault.save(
        [{"title": "t", "content": "c"}], kind="digest", collection="周报"
    )["saved"][0]
    assert Path(dig).relative_to(vault.real_root).parts[:2] == ("digests", "周报")


def test_pipeline_compat_excerpt_and_missing_fields(vault: Vault) -> None:
    item = {
        "id": "42",
        "url": "https://x.com/OpenAI/status/1",
        "title": "",
        "excerpt": "Hello from the pipeline",
        "metrics": {"likes": 3},
        "unknown_field": "ignored",
    }
    res = vault.save([item])
    (path,) = res["saved"]
    meta, body = v.parse_front_matter(Path(path).read_text(encoding="utf-8"))
    assert body.strip() == "Hello from the pipeline"
    assert meta["title"] == "Hello from the pipeline"
    assert meta["source"] == "x.com"  # 缺省取域名
    assert meta["metrics"] == {"likes": 3}


def test_failed_items_do_not_block_others(vault: Vault) -> None:
    res = vault.save(
        [
            {"title": "no url", "content": "c"},  # raw 缺 url
            doc(url="ftp://bad", title="bad scheme"),
            doc(url="https://example.com/empty", content="", title="empty"),
            doc(),
        ]
    )
    assert len(res["saved"]) == 1
    assert [f["code"] for f in res["failed"]] == [
        "missing_url",
        "invalid_url",
        "empty_content",
    ]


def test_limits_and_bad_kind(vault: Vault) -> None:
    with pytest.raises(VaultError) as ei:
        vault.save([doc(url=f"https://e.com/{i}") for i in range(101)])
    assert ei.value.code == "too_many_docs"
    with pytest.raises(VaultError):
        vault.save([doc()], kind="other")
    with pytest.raises(VaultError):
        vault.save([])


def test_oversize_is_truncated_and_flagged(vault: Vault) -> None:
    big = "字" * 300_000  # 900KB UTF-8
    (path,) = vault.save([doc(content=big)])["saved"]
    meta, body = v.parse_front_matter(Path(path).read_text(encoding="utf-8"))
    assert meta["truncated"] is True
    assert len(body.strip().encode("utf-8")) <= v.MAX_DOC_BYTES
    assert len(body.strip()) > 100_000


# ── slug ─────────────────────────────────────────────────────────────────────


def test_slugify_chinese_and_illegal_chars() -> None:
    assert v.slugify("中文标题：测试/非法?字符*") == "中文标题：测试-非法-字符"
    assert v.slugify("   ") == "untitled"
    assert v.slugify("../../etc/passwd") == "etc-passwd"
    assert v.slugify("a" * 200) == "a" * 80
    assert len(v.slugify("长" * 200)) == 80
    assert v.slugify("CON") == "CON-"
    assert "/" not in v.slugify("a/b\\c") and "\\" not in v.slugify("a/b\\c")


def test_slug_collision_adds_short_hash(vault: Vault) -> None:
    a = vault.save([doc(url="https://example.com/1", title="同名文章", source="blog")])[
        "saved"
    ][0]
    b = vault.save([doc(url="https://example.com/2", title="同名文章", source="blog")])[
        "saved"
    ][0]
    assert a != b
    assert Path(a).stem == "同名文章"
    assert Path(b).stem.startswith("同名文章-")
    assert len(Path(b).stem) <= v.MAX_SLUG_LEN
    long_title = "很" * 120
    p1 = vault.save(
        [doc(url="https://example.com/3", title=long_title, source="blog")]
    )["saved"][0]
    p2 = vault.save(
        [doc(url="https://example.com/4", title=long_title, source="blog")]
    )["saved"][0]
    assert len(Path(p1).stem) <= 80 and len(Path(p2).stem) <= 80 and p1 != p2


def test_source_cannot_escape(vault: Vault) -> None:
    (path,) = vault.save([doc(source="../../evil", url="https://example.com/e")])[
        "saved"
    ]
    assert Path(path).resolve().is_relative_to(vault.real_root)
    (hidden,) = vault.save([doc(source=".polaris", url="https://example.com/h")])[
        "saved"
    ]
    assert Path(hidden).relative_to(vault.real_root).parts[0] != ".polaris"


# ── 路径沙盒 ──────────────────────────────────────────────────────────────────


def test_collection_traversal_rejected(vault: Vault) -> None:
    for bad in ("../x", "/abs", "~/x", "a/../b", "a\\b"):
        with pytest.raises(VaultError):
            vault.save([doc()], collection=bad)


def test_read_rejects_outside_dotdot_and_absolute(vault: Vault, tmp_path: Path) -> None:
    vault.save([doc()])
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")
    for bad in (
        "../secret.txt",
        f"{vault.real_root}/../secret.txt",
        str(secret),
        "/etc/passwd",
    ):
        with pytest.raises(VaultError) as ei:
            vault.read(bad)
        assert ei.value.code == "path_outside_vault"


def test_symlink_escape_rejected(vault: Vault, tmp_path: Path) -> None:
    vault.save([doc()])
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.md").write_text("leaked")
    (vault.real_root / "link-file.md").symlink_to(outside / "leak.md")
    (vault.real_root / "link-dir").symlink_to(outside, target_is_directory=True)

    with pytest.raises(VaultError):
        vault.read("link-file.md")
    with pytest.raises(VaultError):
        vault.read("link-dir/leak.md")
    with pytest.raises(VaultError):
        vault.move("link-file.md", "x")
    inside = Path(vault.save([doc(url="https://example.com/m")])["saved"][0])
    with pytest.raises(VaultError):
        vault.move(str(inside), "link-dir")
    assert not (outside / inside.name).exists()


def test_save_through_symlinked_source_dir_rejected(
    vault: Vault, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    vault.real_root.mkdir(parents=True, exist_ok=True)
    (vault.real_root / "evilsrc").symlink_to(outside, target_is_directory=True)
    res = vault.save([doc(source="evilsrc", url="https://example.com/s")])
    assert res["saved"] == [] and res["failed"][0]["code"] == "path_outside_vault"
    assert list(outside.iterdir()) == []


def test_index_dir_is_off_limits(vault: Vault) -> None:
    vault.save([doc()])
    with pytest.raises(VaultError) as ei:
        vault.read(".polaris/index.sqlite")
    assert ei.value.code == "path_forbidden"
    p = Path(vault.save([doc(url="https://example.com/i")])["saved"][0])
    with pytest.raises(VaultError):
        vault.move(str(p), ".polaris")


# ── 检索 ─────────────────────────────────────────────────────────────────────


def test_fts_chinese_and_english(vault: Vault) -> None:
    vault.save(
        [
            doc(
                url="https://example.com/1",
                title="智能体评估",
                content="我们讨论评估方法与基准测试。" + "填充" * 200,
            ),
            doc(
                url="https://example.com/2",
                title="Vector databases",
                content="Notes about embeddings and retrieval.",
            ),
            doc(
                url="https://example.com/3",
                title="无关",
                content="完全不同的话题：烹饪与旅行",
            ),
        ]
    )
    cn = vault.search("基准")
    assert [r["title"] for r in cn["results"]] == ["智能体评估"]
    assert "基准" in cn["results"][0]["snippet"]
    assert len(cn["results"][0]["snippet"]) <= 200

    assert vault.search("体评")["count"] == 1  # 子串
    assert [r["title"] for r in vault.search("embeddings retrieval")["results"]] == [
        "Vector databases"
    ]
    assert vault.search("embeddings 烹饪")["count"] == 0  # 多词 AND
    assert vault.search("not-there")["count"] == 0
    assert (
        vault.search('quote"inside "unbalanced')["count"] == 0
    )  # 特殊字符不致语法错误
    with pytest.raises(VaultError):
        vault.search("   ")


def test_search_drops_deleted_files(vault: Vault) -> None:
    p = Path(vault.save([doc()])["saved"][0])
    assert vault.search("智能体")["count"] == 1
    p.unlink()
    assert vault.search("智能体")["count"] == 0
    assert vault.list_docs()["count"] == 0


def test_search_reflects_updates(vault: Vault) -> None:
    vault.save([doc(content="旧内容 alpha")])
    vault.save([doc(content="新内容 bravo")])
    assert vault.search("alpha")["count"] == 0
    assert vault.search("bravo")["count"] == 1


def test_list_filters(vault: Vault, clock: Clock) -> None:
    vault.save([doc(url="https://example.com/1", source="zhihu", tags=["ai"])])
    clock.tick(86400)
    vault.save(
        [doc(url="https://example.com/2", source="x", title="second", tags=["news"])]
    )
    assert [i["source"] for i in vault.list_docs()["items"]] == ["x", "zhihu"]
    assert vault.list_docs(source="x")["count"] == 1
    assert vault.list_docs(tag="ai")["count"] == 1
    assert vault.list_docs(tag="#news")["count"] == 1
    assert vault.list_docs(since="2026-10-15")["count"] == 1
    assert vault.list_docs(limit=1)["count"] == 1
    assert vault.list_docs()["items"][0]["path"].startswith(str(vault.real_root))


def test_empty_vault_reads_do_not_create_anything(tmp_path: Path) -> None:
    vv = Vault(tmp_path / "never")
    assert vv.list_docs()["count"] == 0
    assert vv.search("x")["count"] == 0
    assert not (tmp_path / "never").exists()


# ── 标签 / 移动 / 读取 ───────────────────────────────────────────────────────


def test_tag_add_remove_updates_file_and_index(vault: Vault) -> None:
    p = Path(vault.save([doc()])["saved"][0])
    text = p.read_text(encoding="utf-8")
    p.write_text(
        text.replace("kind: raw\n", "kind: raw\ncssclass: wide\n"), encoding="utf-8"
    )

    res = vault.tag(str(p), add=["#新标签", "ai"], remove=["agent"])
    assert res["tags"] == ["ai", "新标签"]
    meta, body = v.parse_front_matter(p.read_text(encoding="utf-8"))
    assert meta["tags"] == ["ai", "新标签"]
    assert meta["cssclass"] == "wide"  # 用户自加的属性原样保留
    assert meta["title"] == "如何构建 Agent 系统"
    assert "retrieval augmented generation" in body
    assert vault.list_docs(tag="新标签")["count"] == 1
    assert vault.list_docs(tag="agent")["count"] == 0


def test_tag_on_obsidian_style_block_list(vault: Vault) -> None:
    p = Path(vault.save([doc()])["saved"][0])
    text = p.read_text(encoding="utf-8")
    start = text.index("tags:")
    end = text.index("\n", start)
    p.write_text(
        text[:start] + "tags:\n  - ai\n  - agent" + text[end:], encoding="utf-8"
    )
    assert v.parse_front_matter(p.read_text(encoding="utf-8"))[0]["tags"] == [
        "ai",
        "agent",
    ]
    vault.tag(str(p), add=["x"])
    meta, _ = v.parse_front_matter(p.read_text(encoding="utf-8"))
    assert meta["tags"] == ["ai", "agent", "x"]
    assert p.read_text(encoding="utf-8").count("tags:") == 1


def test_move_within_vault_updates_index(vault: Vault) -> None:
    p = Path(vault.save([doc()])["saved"][0])
    res = vault.move(str(p), "归档/2026")
    dest = Path(res["path"])
    assert dest.is_file() and not p.exists()
    assert dest.relative_to(vault.real_root).parts[:2] == ("归档", "2026")
    assert vault.list_docs()["items"][0]["path"] == str(dest)
    assert vault.search("智能体")["results"][0]["path"] == str(dest)
    # 再存同 url：命中新位置，不重复生成
    assert vault.save([doc()])["unchanged"] == [str(dest)]
    with pytest.raises(VaultError):
        vault.move(str(vault.root / "nope.md"), "归档")


def test_move_conflict_rejected(vault: Vault) -> None:
    a = Path(vault.save([doc(url="https://example.com/a", title="same")])["saved"][0])
    b_path = vault.real_root / "box" / a.name
    b_path.parent.mkdir()
    b_path.write_text("existing")
    with pytest.raises(VaultError) as ei:
        vault.move(str(a), "box")
    assert ei.value.code == "exists"
    assert a.exists()


def test_read_pagination(vault: Vault) -> None:
    p = vault.save([doc(content="0123456789" * 100)])["saved"][0]
    r1 = vault.read(p, max_chars=300)
    assert r1["meta"]["title"] == "如何构建 Agent 系统"
    assert len(r1["content"]) == 300
    assert r1["truncated"] is True and r1["next_offset"] == 300
    r2 = vault.read(p, max_chars=300, offset=900)
    assert r2["truncated"] is False and r2["next_offset"] is None
    assert r1["content_hash"] == r2["content_hash"]
    rel = Path(p).relative_to(vault.real_root)
    assert vault.read(str(rel))["path"] == p  # 相对路径同样可读


# ── front matter 往返 ─────────────────────────────────────────────────────────


def test_front_matter_roundtrip_special_characters() -> None:
    meta = {
        "title": '带"引号"、冒号: 与 # 井号\\反斜杠 😀',
        "url": "https://example.com/?a=1&b=2",
        "author": "o'brien",
        "tags": ["a", "中文", "x/y"],
        "kind": "digest",
        "truncated": True,
        "metrics": {"likes": 3, "name": "n"},
        "multi": "line1\nline2 sep",
        "n": 5,
        "none": None,
    }
    text = v.render_front_matter(meta) + "\n正文 --- 里有分隔线\n---\n仍是正文\n"
    parsed, body = v.parse_front_matter(text)
    assert parsed == meta
    assert body == "\n正文 --- 里有分隔线\n---\n仍是正文\n"
    assert " " not in text.split("---")[1]  # 已转义，YAML 不会当作换行


def test_parse_front_matter_tolerates_obsidian_forms() -> None:
    text = (
        "---\n"
        "title: 'it''s fine'\n"
        'tags: [a, b, "c d"]\n'
        "draft: false\n"
        "rating: 4\n"
        "aliases:\n  - one\n  - two\n"
        "plain: 裸字符串\n"
        "---\nbody"
    )
    meta, body = v.parse_front_matter(text)
    assert meta["title"] == "it's fine"
    assert meta["tags"] == ["a", "b", "c d"]
    assert meta["draft"] is False and meta["rating"] == 4
    assert meta["aliases"] == ["one", "two"]
    assert meta["plain"] == "裸字符串"
    assert body == "body"
    assert v.parse_front_matter("no front matter") == ({}, "no front matter")
    unterminated = "---\nunterminated: 1\nbody"
    assert v.parse_front_matter(unterminated) == ({}, unterminated)


def test_default_vault_dir_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("POLARIS_VAULT_DIR", str(tmp_path / "envvault"))
    assert v.resolve_vault_root() == tmp_path / "envvault"
    monkeypatch.setenv("POLARIS_VAULT_DIR", "")
    assert v.resolve_vault_root() == Path(os.path.expanduser("~/Polaris/Vault"))
    assert v.DEFAULT_VAULT_DIR == "~/Polaris/Vault"
