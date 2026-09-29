import hashlib
import json
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
 id TEXT PRIMARY KEY, source_key TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
 title TEXT NOT NULL, excerpt TEXT NOT NULL, category TEXT NOT NULL,
 source_date TEXT, date_kind TEXT NOT NULL, content_hash TEXT NOT NULL,
 first_seen_at TEXT NOT NULL, fetched_at TEXT NOT NULL, changed_at TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 1, search_text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS articles_source ON articles(source_key, source_date);
CREATE TABLE IF NOT EXISTS collection_runs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, source_key TEXT NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT, heartbeat_at TEXT, status TEXT NOT NULL,
 discovered INTEGER NOT NULL DEFAULT 0, fetched INTEGER NOT NULL DEFAULT 0,
 new INTEGER NOT NULL DEFAULT 0, updated INTEGER NOT NULL DEFAULT 0,
 unchanged INTEGER NOT NULL DEFAULT 0, errors_json TEXT NOT NULL DEFAULT '[]'
);
CREATE UNIQUE INDEX IF NOT EXISTS one_collector_per_source
 ON collection_runs(source_key) WHERE status='running';
CREATE TABLE IF NOT EXISTS revisions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, article_id TEXT NOT NULL,
 revision INTEGER NOT NULL, changed_at TEXT NOT NULL, content_hash TEXT NOT NULL,
 title TEXT NOT NULL, excerpt TEXT NOT NULL, source_date TEXT,
 UNIQUE(article_id, revision)
);
PRAGMA user_version=2;
"""


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join("".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text).split())


def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    return db


def init_db(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = connect(path)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
        if "heartbeat_at" not in {r[1] for r in db.execute("PRAGMA table_info(collection_runs)")}:
            db.execute("ALTER TABLE collection_runs ADD COLUMN heartbeat_at TEXT")
            db.commit()
    finally:
        db.close()


def save_article(db, article, timestamp):
    """Commit per article: a later network failure cannot remove good data."""
    a = dict(article)
    a["id"] = hashlib.sha256(a["url"].encode()).hexdigest()[:24]
    a["search_text"] = normalize(" ".join([a["title"], a["excerpt"], a["category"]]))
    old = db.execute("SELECT * FROM articles WHERE url=?", (a["url"],)).fetchone()
    if old and old["content_hash"] == a["content_hash"]:
        db.execute("UPDATE articles SET fetched_at=? WHERE id=?", (timestamp, old["id"]))
        db.commit()
        return "unchanged"
    revision = old["revision"] + 1 if old else 1
    db.execute("""INSERT INTO articles VALUES
        (:id,:source_key,:url,:title,:excerpt,:category,:source_date,:date_kind,:content_hash,
         :first_seen_at,:fetched_at,:changed_at,:revision,:search_text)
        ON CONFLICT(url) DO UPDATE SET title=excluded.title, excerpt=excluded.excerpt,
          category=excluded.category, source_date=excluded.source_date, date_kind=excluded.date_kind,
          content_hash=excluded.content_hash, fetched_at=excluded.fetched_at,
          changed_at=excluded.changed_at, revision=excluded.revision, search_text=excluded.search_text""",
        a | {"first_seen_at": timestamp, "fetched_at": timestamp, "changed_at": timestamp, "revision": revision})
    db.execute("""INSERT INTO revisions
        (article_id,revision,changed_at,content_hash,title,excerpt,source_date) VALUES (?,?,?,?,?,?,?)""",
        (a["id"], revision, timestamp, a["content_hash"], a["title"], a["excerpt"], a["source_date"]))
    db.commit()
    return "updated" if old else "new"


def export_snapshot(path, destination):
    db = connect(path)
    try:
        payload = {"schemaVersion": 1, "exportedAt": utc_now(), "mode": "collected_snapshot",
                   "articles": [dict(r) for r in db.execute("SELECT * FROM articles ORDER BY source_key,url")],
                   "runs": [dict(r) for r in db.execute("SELECT * FROM collection_runs ORDER BY id")]}
        Path(destination).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        db.close()


def import_snapshot(path, filename):
    """Explicit offline-demo import; never overwrite a database containing live data."""
    from .sources import SOURCES, CATEGORIES, safe_url
    data = json.loads(Path(filename).read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1 or data.get("mode") != "collected_snapshot":
        raise ValueError("未対応のスナップショットです")
    rows = data["articles"]
    if not isinstance(rows, list) or len(rows) > 1000:
        raise ValueError("件数が不正です")
    # Validate the entire import before the first write.
    seen = set()
    for a in rows:
        s = SOURCES[a["source_key"]]
        if safe_url(a["url"], s) != a["url"] or a["url"] in seen:
            raise ValueError("URLが不正または重複しています")
        seen.add(a["url"])
        if a["category"] not in CATEGORIES or not 1 <= len(a["title"]) <= 300 or len(a["excerpt"]) > 181:
            raise ValueError("記事形式が不正です")
        if a["source_date"]:
            datetime.strptime(a["source_date"], "%Y-%m-%d")
        datetime.fromisoformat(a["fetched_at"])
    db = connect(path)
    try:
        if db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]:
            raise ValueError("データのあるDBへのデモ取込はできません")
        for a in rows:
            save_article(db, a, a["fetched_at"])
    finally:
        db.close()
    return len(rows)
