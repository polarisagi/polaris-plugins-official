"""资料库（Vault）核心：路径沙盒、YAML front matter、SQLite 索引（FTS5）。

为何独立为纯标准库模块：
1. 写入严格限定在资料库根目录内（resolve 后包含判断，拒绝 `..` 与符号链接越界）；
2. 内核以 ObsidianConnector 把资料库目录同步进 RAG，本模块只负责把内容落成带 front matter 的
   Markdown，不做任何入库逻辑；
3. 仅依赖标准库，真机冒烟脚本可按文件路径直接加载本模块而无需插件环境。

布局：
  原文  <vault>/[<collection>/]<source>/<YYYY>/<MM>/<slug>.md
  摘要  <vault>/digests/[<collection>/]<YYYY-MM-DD>-<slug>.md
  索引  <vault>/.polaris/index.sqlite（WAL；docs 表 + docs_fts 虚表）
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import unicodedata
import uuid
from collections.abc import Callable, Iterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ENV_VAULT_DIR = "POLARIS_VAULT_DIR"
DEFAULT_VAULT_DIR = "~/Polaris/Vault"
INDEX_DIR = ".polaris"
INDEX_FILE = "index.sqlite"
DIGEST_DIR = "digests"

MAX_DOCS_PER_CALL = 100
MAX_DOC_BYTES = 500 * 1024
MAX_SLUG_LEN = 80
MAX_TAGS = 30
MAX_TAG_LEN = 50
KINDS = ("raw", "digest")

_ILLEGAL_NAME_CHARS = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f\x7f]')
_WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
_CJK_RE = re.compile(r"([぀-ヿ㐀-䶿一-鿿豈-﫿])")
_TRACKING_PARAMS = {"spm", "from", "share_token", "fbclid", "gclid", "igshid"}


class VaultError(Exception):
    """资料库操作的标准错误（code 供调用方分支，message 供人阅读）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


# ── 时间与哈希 ────────────────────────────────────────────────────────────────


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_hex(text: str, n: int = 32) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


# ── 文件名 / 目录名 / URL / 标签清洗 ──────────────────────────────────────────


def slugify(title: str, max_len: int = MAX_SLUG_LEN) -> str:
    """由标题生成文件名：保留中文，去除文件名非法字符，长度 ≤ max_len。"""
    s = unicodedata.normalize("NFC", title or "").strip()
    s = _ILLEGAL_NAME_CHARS.sub(" ", s)
    s = re.sub(r"\s+", "-", s).strip("-. ")
    s = s[:max_len].rstrip("-. ")
    if not s:
        return "untitled"
    if s.lower() in _WINDOWS_RESERVED:
        s = f"{s}-"
    return s


def safe_dirname(name: str, default: str) -> str:
    """目录名清洗：不得以 '.' 开头（避免写入 .polaris 等隐藏目录），不含分隔符。"""
    s = slugify(name, 60).lstrip(".")
    return s if s and s != "untitled" else default


def safe_collection(collection: str) -> list[str]:
    """collection 允许用 '/' 分层，每段独立清洗；拒绝 '..' 与绝对路径。"""
    c = (collection or "").strip()
    if not c:
        return []
    if c.startswith(("/", "~")) or "\\" in c:
        raise VaultError("invalid_args", "collection 必须是资料库内的相对目录名")
    parts = [p for p in c.split("/") if p.strip()]
    if any(p.strip() in ("..", ".") for p in parts):
        raise VaultError("invalid_args", "collection 不得包含 '.' 或 '..'")
    if len(parts) > 4:
        raise VaultError("invalid_args", "collection 层级不得超过 4 层")
    return [safe_dirname(p, "collection") for p in parts]


def normalize_url(url: str) -> str:
    """去重用的规范 URL：小写 scheme/host、去 fragment 与常见追踪参数。"""
    u = url.strip()
    parts = urlsplit(u)
    if not parts.scheme or not parts.netloc:
        return u
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    ]
    path = parts.path if parts.path != "/" else ""
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), "")
    )


def host_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def clean_tag(tag: str) -> str:
    t = unicodedata.normalize("NFC", str(tag)).strip().lstrip("#")
    t = re.sub(r"[\s,\[\]\"'`]+", "-", t).strip("-")
    return t[:MAX_TAG_LEN]


def clean_tags(tags: list[str] | None) -> list[str]:
    out: list[str] = []
    for raw in tags or []:
        t = clean_tag(raw)
        if t and t not in out:
            out.append(t)
    return out[:MAX_TAGS]


def truncate_utf8(text: str, max_bytes: int) -> tuple[str, bool]:
    """按 UTF-8 字节上限截断（不切断多字节字符），返回 (文本, 是否截断)。"""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text, False
    return raw[:max_bytes].decode("utf-8", errors="ignore"), True


def _date_parts(published_at: str, fallback: datetime) -> tuple[str, str]:
    """用 published_at 的年月作目录；解析不了或年份离谱则回退到保存时间。"""
    m = re.match(r"^\s*(\d{4})-(\d{2})", published_at or "")
    if m and 1990 <= int(m.group(1)) <= 2100 and 1 <= int(m.group(2)) <= 12:
        return m.group(1), m.group(2)
    return f"{fallback.year:04d}", f"{fallback.month:02d}"


# ── front matter ──────────────────────────────────────────────────────────────


def _yaml_scalar(value: Any) -> str:
    """渲染为合法 YAML 的行内值：字符串 / 列表 / 映射一律用 JSON 语法（YAML 的子集）。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    text = json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
    # YAML 把 U+0085 / U+2028 / U+2029 当作换行，必须转义
    return (
        text.replace("\u0085", "\\u0085")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def render_front_matter(meta: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if key == "kind" and isinstance(value, str) and value in KINDS:
            lines.append(f"kind: {value}")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _split_front_matter(text: str) -> tuple[list[str] | None, str]:
    """返回 (front matter 行列表 | None, 正文)。"""
    if not text.startswith(("---\n", "---\r\n")):
        return None, text
    lines = text.splitlines(keepends=True)
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            return [ln.rstrip("\r\n") for ln in lines[1:i]], "".join(lines[i + 1 :])
    return None, text


def _parse_scalar(raw: str) -> Any:
    s = raw.strip()
    if s == "":
        return ""
    try:
        return json.loads(s)
    except ValueError:
        pass
    if s[0] == "'" and s[-1] == "'" and len(s) >= 2:
        return s[1:-1].replace("''", "'")
    if s[0] == "[" and s[-1] == "]":
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(x) for x in inner.split(",")]
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


_KEY_RE = re.compile(r"^([A-Za-z_][\w\-]*)\s*:(.*)$")


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """解析 front matter（支持本模块写出的 JSON 风格值，以及 Obsidian 常见的块列表 / 单引号 / 裸值）。"""
    fm, body = _split_front_matter(text)
    if fm is None:
        return {}, text
    meta: dict[str, Any] = {}
    i = 0
    while i < len(fm):
        m = _KEY_RE.match(fm[i])
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest == "":
            items: list[Any] = []
            j = i + 1
            while j < len(fm) and re.match(r"^\s*-\s+", fm[j]):
                items.append(_parse_scalar(re.sub(r"^\s*-\s+", "", fm[j])))
                j += 1
            meta[key] = items if items else ""
            i = j
        else:
            meta[key] = _parse_scalar(rest)
            i += 1
    return meta, body


def set_front_matter_key(text: str, key: str, value: Any) -> str:
    """只替换（或追加）单个 front matter 键，保留其余内容原样（含用户在 Obsidian 里加的属性）。"""
    fm, body = _split_front_matter(text)
    if fm is None:
        return render_front_matter({key: value}) + text
    new_line = f"{key}: {_yaml_scalar(value)}"
    start = next(
        (i for i, ln in enumerate(fm) if re.match(rf"^{re.escape(key)}\s*:", ln)), None
    )
    if start is None:
        fm.append(new_line)
    else:
        end = start + 1
        while end < len(fm) and re.match(r"^(\s+|-\s)", fm[end]):
            end += 1
        fm[start:end] = [new_line]
    return "---\n" + "\n".join(fm) + "\n---\n" + body


# ── 全文检索辅助（CJK 逐字切分，使 unicode61 分词器也能检索中文）─────────────


def cjk_split(text: str) -> str:
    return _CJK_RE.sub(r" \1 ", text)


def build_match_query(query: str) -> str:
    """把自然语言查询转成 FTS5 MATCH 表达式：每个词作为短语，词间 AND。"""
    phrases = []
    for tok in query.split():
        spaced = " ".join(cjk_split(tok).split())
        if spaced:
            phrases.append('"' + spaced.replace('"', '""') + '"')
    return " ".join(phrases)


def make_snippet(body: str, query: str, width: int = 200) -> str:
    """从原文中截取包含首个命中词的片段（≤ width 字）。"""
    flat = re.sub(r"\s+", " ", body).strip()
    if not flat:
        return ""
    lower = flat.lower()
    pos = -1
    for tok in query.split():
        pos = lower.find(tok.lower())
        if pos >= 0:
            break
    if pos < 0:
        return flat[:width]
    start = max(0, pos - width // 3)
    prefix = "…" if start > 0 else ""
    return (prefix + flat[start : start + width])[:width]


# ── 路径沙盒 ──────────────────────────────────────────────────────────────────


def resolve_vault_root(vault_dir: str | os.PathLike[str] | None = None) -> Path:
    raw = str(vault_dir) if vault_dir else os.environ.get(ENV_VAULT_DIR, "").strip()
    return Path(raw or DEFAULT_VAULT_DIR).expanduser().absolute()


class Vault:
    """一个资料库实例（根目录 + 索引）。"""

    def __init__(
        self,
        root: str | os.PathLike[str] | None = None,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.root = resolve_vault_root(root)
        self._now = now

    # -- 路径 --

    @property
    def real_root(self) -> Path:
        return self.root.resolve()

    @property
    def index_path(self) -> Path:
        return self.real_root / INDEX_DIR / INDEX_FILE

    def resolve_inside(
        self, p: str | os.PathLike[str], *, allow_index: bool = False
    ) -> Path:
        """把相对 / 绝对路径解析为资料库内的真实路径；越界、含 '..'、经符号链接逃逸一律拒绝。"""
        try:
            raw = Path(str(p)).expanduser()
            if any(part == ".." for part in raw.parts):
                raise VaultError("path_outside_vault", "路径不得包含 '..'")
            real_root = self.real_root
            candidate = raw if raw.is_absolute() else real_root / raw
            real = candidate.resolve()
        except (OSError, ValueError, RuntimeError) as e:
            raise VaultError("invalid_path", f"无效路径: {e}") from e
        if real != real_root and real_root not in real.parents:
            raise VaultError("path_outside_vault", "路径位于资料库目录之外")
        rel = real.relative_to(real_root)
        if not allow_index and rel.parts and rel.parts[0] == INDEX_DIR:
            raise VaultError("path_forbidden", "不允许访问资料库内部索引目录")
        return real

    def _rel(self, real: Path) -> str:
        return real.relative_to(self.real_root).as_posix()

    # -- 索引 --

    def _connect(self, create: bool) -> sqlite3.Connection | None:
        path = self.index_path
        if not path.exists():
            if not create:
                return None
            # .polaris 必须是真实目录而非指向外部的符号链接
            self.resolve_inside(INDEX_DIR, allow_index=True)
            path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS docs(
                path TEXT PRIMARY KEY,
                url TEXT UNIQUE,
                url_hash TEXT,
                title TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '',
                published_at TEXT NOT NULL DEFAULT '',
                saved_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                content_hash TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'raw',
                collection TEXT NOT NULL DEFAULT ''
            );"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_saved ON docs(saved_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_source ON docs(source);")
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(title, content);"
            )
        except sqlite3.OperationalError as e:
            conn.close()
            raise VaultError("fts5_unavailable", f"当前 SQLite 不支持 FTS5: {e}") from e
        return conn

    def _upsert_index(
        self, conn: sqlite3.Connection, rel: str, row: dict[str, Any], body: str
    ) -> None:
        conn.execute("BEGIN IMMEDIATE;")
        try:
            # url 唯一：若别的路径占着同一 url（文件被用户移走又重存），先清掉旧行
            if row["url"] is not None:
                old = conn.execute(
                    "SELECT rowid FROM docs WHERE url = ? AND path != ?;",
                    (row["url"], rel),
                ).fetchall()
                for r in old:
                    conn.execute("DELETE FROM docs_fts WHERE rowid = ?;", (r[0],))
                conn.execute(
                    "DELETE FROM docs WHERE url = ? AND path != ?;", (row["url"], rel)
                )
            conn.execute(
                """INSERT INTO docs(path, url, url_hash, title, source, author,
                       published_at, saved_at, updated_at, tags, content_hash, kind, collection)
                   VALUES(:path, :url, :url_hash, :title, :source, :author,
                       :published_at, :saved_at, :updated_at, :tags, :content_hash, :kind, :collection)
                   ON CONFLICT(path) DO UPDATE SET
                       url=excluded.url, url_hash=excluded.url_hash, title=excluded.title,
                       source=excluded.source, author=excluded.author,
                       published_at=excluded.published_at, saved_at=excluded.saved_at,
                       updated_at=excluded.updated_at, tags=excluded.tags,
                       content_hash=excluded.content_hash, kind=excluded.kind,
                       collection=excluded.collection;""",
                {**row, "path": rel},
            )
            rowid = conn.execute(
                "SELECT rowid FROM docs WHERE path = ?;", (rel,)
            ).fetchone()[0]
            conn.execute("DELETE FROM docs_fts WHERE rowid = ?;", (rowid,))
            conn.execute(
                "INSERT INTO docs_fts(rowid, title, content) VALUES(?, ?, ?);",
                (rowid, cjk_split(row["title"]), cjk_split(body)),
            )
            conn.execute("COMMIT;")
        except BaseException:
            conn.execute("ROLLBACK;")
            raise

    # -- 写入 --

    def _write_atomic(self, target: Path, text: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        # mkdir 之后再次校验，防止中途被换成指向外部的符号链接
        self.resolve_inside(target)
        tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            with tmp.open("x", encoding="utf-8", newline="\n") as f:
                f.write(text)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)

    def _target_path(
        self,
        kind: str,
        collection: list[str],
        source: str,
        published_at: str,
        slug: str,
        saved: datetime,
    ) -> Path:
        base = self.real_root
        if kind == "digest":
            rel_dir = Path(DIGEST_DIR, *collection)
            name = f"{saved.strftime('%Y-%m-%d')}-{slug}"
        else:
            yyyy, mm = _date_parts(published_at, saved)
            rel_dir = Path(*collection, safe_dirname(source, "misc"), yyyy, mm)
            name = slug
        # 目录名中的 slug 长度已限制；冲突时用短 hash 区分
        return base / rel_dir / f"{name}.md"

    def _unique_path(self, path: Path, seed: str) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = f"-{sha256_hex(seed, 6)}"
        cut = max(1, MAX_SLUG_LEN - len(suffix))
        # 日期前缀（digest）不计入 slug 的 80 字限制，这里只截断 slug 部分
        m = re.match(r"^(\d{4}-\d{2}-\d{2}-)(.*)$", stem)
        if m:
            cand = path.with_name(f"{m.group(1)}{m.group(2)[:cut]}{suffix}.md")
        else:
            cand = path.with_name(f"{stem[:cut]}{suffix}.md")
        n = 1
        while cand.exists():
            n += 1
            cand = cand.with_name(f"{cand.stem}-{n}.md")
        return cand

    @staticmethod
    def _body_of(doc: dict[str, Any]) -> tuple[str, bool]:
        """取正文（excerpt 回退）、规整换行并按 500KB 截断，返回 (正文, 是否截断)。"""
        content = str(doc.get("content") or "") or str(doc.get("excerpt") or "")
        content = content.replace("\r\n", "\n").strip("\n")
        if not content.strip():
            raise VaultError("empty_content", "content 为空（excerpt 回退后仍为空）")
        return truncate_utf8(content, MAX_DOC_BYTES)

    @staticmethod
    def _title_of(doc: dict[str, Any], content: str) -> str:
        title = " ".join(str(doc.get("title") or "").split())
        if title:
            return title[:500]
        first = next((ln.strip() for ln in content.splitlines() if ln.strip()), "")
        return re.sub(r"^#+\s*", "", first)[:60] or "untitled"

    def _prepare(self, doc: dict[str, Any], kind: str) -> dict[str, Any]:
        url_raw = str(doc.get("url") or "").strip()
        if kind == "raw" and not url_raw:
            raise VaultError("missing_url", "raw 文档必须提供 url（用于去重）")
        if url_raw and not re.match(r"^https?://", url_raw, re.IGNORECASE):
            raise VaultError("invalid_url", "url 必须以 http:// 或 https:// 开头")
        content, truncated = self._body_of(doc)
        published = doc.get("published_at")
        meta: dict[str, Any] = {
            "title": self._title_of(doc, content),
            "url": url_raw or None,
            "source": str(doc.get("source") or "").strip()[:100]
            or host_of(url_raw)
            or "misc",
            "author": str(doc.get("author") or "").strip()[:200],
            "published_at": str(published).strip()[:64]
            if published is not None
            else "",
            "tags": clean_tags(doc.get("tags")),
        }
        metrics = doc.get("metrics")
        return {
            "meta": meta,
            "content": content,
            "content_hash": sha256_hex(content),
            "truncated": truncated,
            "metrics": metrics if isinstance(metrics, dict) and metrics else None,
        }

    def _save_one(
        self,
        conn: sqlite3.Connection,
        doc: dict[str, Any],
        kind: str,
        collection: list[str],
    ) -> tuple[str, Path]:
        """返回 (saved|updated|unchanged, 绝对路径)。"""
        p = self._prepare(doc, kind)
        meta, content = p["meta"], p["content"]
        norm_url = normalize_url(meta["url"]) if meta["url"] else None
        url_hash = sha256_hex(norm_url, 16) if norm_url else ""
        now = self._now()
        now_iso = _iso(now)

        if norm_url:
            existing = conn.execute(
                "SELECT * FROM docs WHERE url = ?;", (norm_url,)
            ).fetchone()
        else:
            existing = conn.execute(
                "SELECT * FROM docs WHERE url IS NULL AND kind = ? AND title = ? AND content_hash = ?;",
                (kind, meta["title"], p["content_hash"]),
            ).fetchone()

        if existing is not None:
            old_path = self.resolve_inside(existing["path"])
            if old_path.is_file():
                if existing["content_hash"] == p["content_hash"]:
                    return "unchanged", old_path
                old_meta, _ = parse_front_matter(old_path.read_text(encoding="utf-8"))
                saved_at = str(
                    old_meta.get("saved_at") or existing["saved_at"] or now_iso
                )
                merged_tags = clean_tags(
                    [*(old_meta.get("tags") or []), *meta["tags"]]
                    if isinstance(old_meta.get("tags"), list)
                    else meta["tags"]
                )
                return self._write_doc(
                    conn,
                    old_path,
                    meta,
                    content,
                    p,
                    kind,
                    collection,
                    saved_at,
                    now_iso,
                    merged_tags,
                    norm_url,
                    url_hash,
                    "updated",
                )
            # 文件已被用户删除 / 移走：按新文档重写
        slug = slugify(meta["title"])
        target = self._unique_path(
            self._target_path(
                kind, collection, meta["source"], meta["published_at"], slug, now
            ),
            f"{norm_url or ''}|{meta['title']}|{p['content_hash']}",
        )
        self.resolve_inside(target)
        return self._write_doc(
            conn,
            target,
            meta,
            content,
            p,
            kind,
            collection,
            now_iso,
            now_iso,
            meta["tags"],
            norm_url,
            url_hash,
            "saved",
        )

    def _write_doc(
        self,
        conn: sqlite3.Connection,
        target: Path,
        meta: dict[str, Any],
        content: str,
        prepared: dict[str, Any],
        kind: str,
        collection: list[str],
        saved_at: str,
        updated_at: str,
        tags: list[str],
        norm_url: str | None,
        url_hash: str,
        status: str,
    ) -> tuple[str, Path]:
        fm: dict[str, Any] = {
            "title": meta["title"],
            "url": meta["url"] or "",
            "source": meta["source"],
            "author": meta["author"],
            "published_at": meta["published_at"],
            "saved_at": saved_at,
            "updated_at": updated_at,
            "tags": tags,
            "kind": kind,
        }
        if collection:
            fm["collection"] = "/".join(collection)
        if prepared["truncated"]:
            fm["truncated"] = True
        if prepared["metrics"]:
            fm["metrics"] = prepared["metrics"]
        self._write_atomic(target, render_front_matter(fm) + "\n" + content + "\n")
        self._upsert_index(
            conn,
            self._rel(target),
            {
                "url": norm_url,
                "url_hash": url_hash,
                "title": meta["title"],
                "source": meta["source"],
                "author": meta["author"],
                "published_at": meta["published_at"],
                "saved_at": saved_at,
                "updated_at": updated_at,
                "tags": json.dumps(tags, ensure_ascii=False),
                "content_hash": prepared["content_hash"],
                "kind": kind,
                "collection": "/".join(collection),
            },
            content,
        )
        return status, target

    def save(
        self,
        docs: list[dict[str, Any]],
        kind: str = "raw",
        collection: str = "",
    ) -> dict[str, Any]:
        """批量保存。单篇失败只进 failed，不影响其余；返回绝对路径。"""
        if kind not in KINDS:
            raise VaultError("invalid_args", f"kind 必须是 {' / '.join(KINDS)}")
        if not docs:
            raise VaultError("invalid_args", "docs 不能为空")
        if len(docs) > MAX_DOCS_PER_CALL:
            raise VaultError(
                "too_many_docs",
                f"单次最多保存 {MAX_DOCS_PER_CALL} 条，收到 {len(docs)} 条",
            )
        coll = safe_collection(collection)
        self.root.mkdir(parents=True, exist_ok=True)
        # 根目录本身可以是符号链接（用户自己的选择），但之后所有写入都必须落在其真实路径内
        result: dict[str, Any] = {
            "saved": [],
            "updated": [],
            "unchanged": [],
            "failed": [],
        }
        conn = self._connect(create=True)
        assert conn is not None
        with closing(conn):
            for doc in docs:
                try:
                    status, path = self._save_one(conn, doc, kind, coll)
                    result[status].append(str(path))
                except VaultError as e:
                    result["failed"].append(self._fail(doc, e.code, e.message))
                except (OSError, sqlite3.Error, ValueError) as e:
                    result["failed"].append(self._fail(doc, "write_failed", str(e)))
        return {"vault": str(self.real_root), **result}

    @staticmethod
    def _fail(doc: dict[str, Any], code: str, message: str) -> dict[str, Any]:
        return {
            "url": doc.get("url") or "",
            "title": str(doc.get("title") or "")[:80],
            "code": code,
            "error": message,
        }

    # -- 读取 --

    def _live_rows(
        self, conn: sqlite3.Connection, rows: list[sqlite3.Row]
    ) -> Iterator[sqlite3.Row]:
        """过滤掉文件已被删除的陈旧索引行（并顺手清理）。"""
        for r in rows:
            if (self.real_root / r["path"]).is_file():
                yield r
            else:
                conn.execute("DELETE FROM docs_fts WHERE rowid = ?;", (r["rowid"],))
                conn.execute("DELETE FROM docs WHERE rowid = ?;", (r["rowid"],))

    def _item(self, r: sqlite3.Row) -> dict[str, Any]:
        try:
            tags = json.loads(r["tags"])
        except ValueError:
            tags = []
        return {
            "path": str(self.real_root / r["path"]),
            "title": r["title"],
            "url": r["url"] or "",
            "source": r["source"],
            "author": r["author"],
            "published_at": r["published_at"],
            "saved_at": r["saved_at"],
            "updated_at": r["updated_at"],
            "tags": tags,
            "kind": r["kind"],
        }

    def list_docs(
        self,
        source: str = "",
        tag: str = "",
        since: str = "",
        kind: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        if kind and kind not in KINDS:
            raise VaultError("invalid_args", f"kind 必须是 {' / '.join(KINDS)}")
        conn = self._connect(create=False)
        if conn is None:
            return {"vault": str(self.real_root), "items": [], "count": 0}
        where, args = ["1=1"], []
        if source:
            where.append("source = ?")
            args.append(source)
        if tag:
            where.append("instr(tags, ?) > 0")
            args.append(json.dumps(clean_tag(tag), ensure_ascii=False))
        if since:
            where.append("saved_at >= ?")
            args.append(since.strip())
        if kind:
            where.append("kind = ?")
            args.append(kind)
        sql = (
            "SELECT rowid, * FROM docs WHERE "  # nosec B608 - 仅拼接固定片段，值全部走参数绑定
            + " AND ".join(where)
            + " ORDER BY saved_at DESC, path LIMIT ?;"
        )
        with closing(conn):
            rows = conn.execute(sql, [*args, max(1, min(limit, 200))]).fetchall()
            items = [self._item(r) for r in self._live_rows(conn, rows)]
        return {"vault": str(self.real_root), "items": items, "count": len(items)}

    def search(self, query: str, limit: int = 20) -> dict[str, Any]:
        match = build_match_query(query)
        if not match:
            raise VaultError("invalid_args", "query 不能为空")
        conn = self._connect(create=False)
        if conn is None:
            return {"vault": str(self.real_root), "results": [], "count": 0}
        with closing(conn):
            try:
                rows = conn.execute(
                    """SELECT d.rowid AS rowid, d.* FROM docs_fts f
                       JOIN docs d ON d.rowid = f.rowid
                       WHERE docs_fts MATCH ? ORDER BY bm25(docs_fts) LIMIT ?;""",
                    (match, max(1, min(limit, 100))),
                ).fetchall()
            except sqlite3.OperationalError as e:
                raise VaultError("invalid_query", f"检索语法错误: {e}") from e
            results = []
            for r in self._live_rows(conn, rows):
                path = self.real_root / r["path"]
                _, body = parse_front_matter(path.read_text(encoding="utf-8"))
                item = self._item(r)
                item["snippet"] = make_snippet(body, query)[:200]
                results.append(item)
        return {"vault": str(self.real_root), "results": results, "count": len(results)}

    def read(
        self, path: str, max_chars: int = 20000, offset: int = 0
    ) -> dict[str, Any]:
        real = self.resolve_inside(path)
        if not real.is_file():
            raise VaultError("not_found", f"文件不存在: {path}")
        try:
            text = real.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise VaultError("not_text", "文件不是 UTF-8 文本") from e
        meta, body = parse_front_matter(text)
        start = max(0, offset)
        end = start + max(1, max_chars)
        return {
            "path": str(real),
            "meta": meta,
            "content": body[start:end],
            "content_hash": sha256_hex(body, 16),
            "total_chars": len(body),
            "truncated": end < len(body),
            "next_offset": end if end < len(body) else None,
        }

    # -- 修改 --

    def tag(
        self, path: str, add: list[str] | None = None, remove: list[str] | None = None
    ) -> dict[str, Any]:
        real = self.resolve_inside(path)
        if not real.is_file():
            raise VaultError("not_found", f"文件不存在: {path}")
        text = real.read_text(encoding="utf-8")
        meta, _ = parse_front_matter(text)
        cur = meta.get("tags")
        tags = clean_tags([str(t) for t in cur]) if isinstance(cur, list) else []
        drop = set(clean_tags(remove))
        tags = [t for t in tags if t not in drop]
        tags = clean_tags([*tags, *clean_tags(add)])
        self._write_atomic(real, set_front_matter_key(text, "tags", tags))
        conn = self._connect(create=False)
        if conn is not None:
            with closing(conn):
                conn.execute(
                    "UPDATE docs SET tags = ? WHERE path = ?;",
                    (json.dumps(tags, ensure_ascii=False), self._rel(real)),
                )
        return {"path": str(real), "tags": tags}

    def move(self, path: str, folder: str) -> dict[str, Any]:
        src = self.resolve_inside(path)
        if not src.is_file():
            raise VaultError("not_found", f"文件不存在: {path}")
        dest_dir = self.resolve_inside(folder)
        if dest_dir.exists() and not dest_dir.is_dir():
            raise VaultError("invalid_args", "folder 不是目录")
        dest = self.resolve_inside(dest_dir / src.name)
        if dest == src:
            return {"path": str(src), "moved": False}
        if dest.exists():
            raise VaultError("exists", f"目标已存在同名文件: {dest.name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.resolve_inside(dest)
        os.replace(src, dest)
        conn = self._connect(create=False)
        if conn is not None:
            with closing(conn):
                conn.execute(
                    "UPDATE docs SET path = ? WHERE path = ?;",
                    (self._rel(dest), self._rel(src)),
                )
        return {"path": str(dest), "moved": True, "from": str(src)}


def save_docs(
    docs: list[dict[str, Any]],
    kind: str = "raw",
    collection: str = "",
    vault_dir: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """便捷入口（供脚本 / 冒烟测试使用）：保存文档到指定或默认资料库。"""
    return Vault(vault_dir).save(docs, kind=kind, collection=collection)
