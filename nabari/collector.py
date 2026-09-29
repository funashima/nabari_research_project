"""Bounded, polite collectors. HTML is parsed but never executed or republished."""
import hashlib
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from .db import connect, save_article, utc_now
from .sources import SOURCES, safe_url

USER_AGENT = "NabariResearchCollector/2.0 (+student research; public news excerpts)"
MAX_BYTES = 2 * 1024 * 1024
MIN_RUN_INTERVAL = 900


class CollectionError(Exception):
    pass


class PublicClient:
    def __init__(self, source, delay=1.0):
        self.source = source
        self.delay = max(1.0, delay)
        self.last_request = 0.0
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9"})
        self.robots = None

    def close(self):
        self.session.close()

    def _request(self, url, is_robots=False):
        for _ in range(4):
            url = safe_url(url, self.source)
            if self.robots and not is_robots and not self.robots.can_fetch(USER_AGENT, url):
                raise CollectionError("robots_denied")
            time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                with self.session.get(url, timeout=(15, 25), allow_redirects=False, stream=True) as r:
                    if r.status_code in (301, 302, 303, 307, 308):
                        url = safe_url(r.headers.get("Location", ""), self.source, url)
                        continue
                    if is_robots and r.status_code in (404, 410):
                        return "", url
                    if r.status_code != 200:
                        raise CollectionError(f"http_{r.status_code}")
                    if not is_robots and "text/html" not in r.headers.get("Content-Type", "").lower():
                        raise CollectionError("not_html")
                    if int(r.headers.get("Content-Length", 0)) > MAX_BYTES:
                        raise CollectionError("page_too_large")
                    chunks, length = [], 0
                    for chunk in r.iter_content(16384):
                        length += len(chunk)
                        if length > MAX_BYTES or time.monotonic() - self.last_request > 45:
                            raise CollectionError("page_limit")
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    # Both observed official sites publish UTF-8. BeautifulSoup can
                    # also detect a declared legacy charset from the raw bytes.
                    return raw, url
            except requests.RequestException as exc:
                raise CollectionError("network_error") from exc
        raise CollectionError("too_many_redirects")

    def prepare(self):
        raw, _ = self._request(self.source.origin + "/robots.txt", is_robots=True)
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        if "<html" in text.lower():
            raise CollectionError("invalid_robots")
        parser = RobotFileParser()
        parser.parse(text.splitlines())
        self.robots = parser
        delay = parser.crawl_delay(USER_AGENT)
        rate = parser.request_rate(USER_AGENT)
        if delay:
            self.delay = max(self.delay, delay)
        if rate and rate.requests:
            self.delay = max(self.delay, rate.seconds / rate.requests)
        if self.delay > 60:
            raise CollectionError("crawl_delay_too_long")

    def html(self, url):
        if self.robots is None:
            raise CollectionError("robots_not_checked")
        return self._request(url)


def plain(node):
    if node is None:
        return ""
    for tag in node.select("script,style,form,nav,iframe,.back-link,.wp-back-link"):
        tag.decompose()
    return " ".join(node.get_text(" ", strip=True).split())


def parse_date(text):
    match = re.search(r"(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})", text)
    if match:
        try:
            return date(*map(int, match.groups())).isoformat()
        except ValueError:
            pass
    return None


def parse_listing(raw, source, limit=12):
    soup = BeautifulSoup(raw, "html.parser")
    selector = "dl.news dd a" if source.key == "city" else ".news-list-item h2 a"
    links = soup.select(selector)
    if not links:
        raise CollectionError("listing_structure_changed")
    urls = []
    for link in links:
        try:
            url = safe_url(link.get("href", ""), source, source.listing)
        except ValueError:
            continue
        if source.key == "tourism" and not re.search(r"/news/[^/]+/?$", url):
            continue
        if source.key == "city" and not url.endswith(".html"):
            continue
        if url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break
    if not urls:
        raise CollectionError("no_allowed_article_links")
    for value in source.evergreen:
        url = safe_url(value, source)
        if url not in urls:
            urls.append(url)
    return urls


def classify(title, source_key, url=""):
    # Transparent deterministic rules: these are suggestions, not human review.
    if any(w in title for w in ("ごみ", "ゴミ", "電池", "資源", "リサイクル")):
        return "waste"
    if any(w in title for w in ("避難", "防災", "災害", "防火", "警報")):
        return "disaster"
    if any(w in title for w in ("相談", "困り")):
        return "consult"
    if any(w in title for w in ("健康", "保健", "福祉", "介護", "予防", "医療", "ウォーク")):
        return "health"
    if source_key == "tourism":
        return "tourism"
    if any(w in title for w in ("祭", "展覧", "イベント", "フェス", "講演", "研修", "学習", "開催", "作品展")):
        return "event"
    return "city"


def parse_article(raw, url, source):
    url = safe_url(url, source)
    soup = BeautifulSoup(raw, "html.parser")
    if source.key == "city":
        header = soup.select_one("article.article h1")
        body_nodes = soup.select("article.article .txtbox")
        date_node = soup.select_one("article.article p.right")
        date_kind = "updated"
    else:
        header = soup.select_one("article.news-post h1.wp-entry-title")
        body_nodes = soup.select("article.news-post .wp-entry-content")
        date_node = soup.select_one("article.news-post time")
        date_kind = "published"
    title = plain(header)
    body = " ".join(plain(n) for n in body_nodes)
    if not title or not body or len(title) > 300:
        raise CollectionError("article_structure_changed")
    source_date = parse_date(date_node.get("datetime", "") or plain(date_node)) if date_node else None
    category = classify(title, source.key, url)
    # Store only a short extract, not the full article. Hash the complete parsed
    # body so updates after the first 180 characters still create a revision.
    digest = hashlib.sha256(json.dumps([title, body, source_date, category], ensure_ascii=False).encode()).hexdigest()
    return {"source_key": source.key, "url": url, "title": title,
            "excerpt": body[:180] + ("…" if len(body) > 180 else ""), "category": category,
            "source_date": source_date, "date_kind": date_kind, "content_hash": digest}


def acquire_run(db, source_key, now):
    db.execute("BEGIN IMMEDIATE")
    try:
        stale = (now - timedelta(minutes=30)).isoformat(timespec="seconds")
        db.execute("""UPDATE collection_runs SET status='failed',finished_at=?,errors_json=?
          WHERE source_key=? AND status='running' AND COALESCE(heartbeat_at,started_at)<?""",
          (now.isoformat(timespec="seconds"), '[{"error":"interrupted_run"}]', source_key, stale))
        previous = db.execute("SELECT * FROM collection_runs WHERE source_key=? ORDER BY id DESC LIMIT 1", (source_key,)).fetchone()
        if previous:
            reference = previous["finished_at"] or previous["started_at"]
            if previous["status"] == "running" or (now - datetime.fromisoformat(reference)).total_seconds() < MIN_RUN_INTERVAL:
                # Persist stale-run recovery even when the cooldown suppresses
                # the next crawl; rollback would leave it running forever.
                db.commit()
                return None
        stamp = now.isoformat(timespec="seconds")
        cur = db.execute("INSERT INTO collection_runs(source_key,started_at,heartbeat_at,status) VALUES (?,?,?,'running')", (source_key, stamp, stamp))
        db.commit()
        return cur.lastrowid
    except Exception:
        db.rollback()
        raise


def collect_source(path, source_key, limit=12, client=None, now=None):
    if source_key not in SOURCES or not 1 <= limit <= 20:
        raise ValueError("収集元または件数が不正です")
    source = SOURCES[source_key]
    now = now or datetime.now(timezone.utc)
    db = connect(path)
    run_id = acquire_run(db, source_key, now)
    if run_id is None:
        db.close()
        return {"source": source_key, "status": "skipped", "reason": "running_or_cooldown"}
    client = client or PublicClient(source)
    counts = {"discovered": 0, "fetched": 0, "new": 0, "updated": 0, "unchanged": 0}
    errors = []
    try:
        client.prepare()
        listing, _ = client.html(source.listing)
        urls = parse_listing(listing, source, limit)
        counts["discovered"] = len(urls)
        for url in urls:
            db.execute("UPDATE collection_runs SET heartbeat_at=? WHERE id=?", (utc_now(), run_id))
            db.commit()
            try:
                raw, final_url = client.html(url)
                article = parse_article(raw, final_url, source)
                result = save_article(db, article, utc_now())
                counts[result] += 1
                counts["fetched"] += 1
            except (CollectionError, ValueError) as exc:
                errors.append({"url": url, "error": str(exc)[:120]})
                # A rate limit or explicit denial ends this source's batch.
                if str(exc) in ("http_429", "http_403", "robots_denied"):
                    break
    except (CollectionError, ValueError) as exc:
        errors.append({"url": source.listing, "error": str(exc)[:120]})
    except Exception:
        # Programming/storage failures remain visible, but cannot leave a
        # falsely successful run or delete previously stored articles.
        errors.append({"error": "internal_error"})
        raise
    finally:
        status = ("partial" if counts["fetched"] else "failed") if errors else "success"
        db.execute("""UPDATE collection_runs SET finished_at=?,status=?,discovered=?,fetched=?,new=?,updated=?,unchanged=?,errors_json=? WHERE id=?""",
            (utc_now(), status, counts["discovered"], counts["fetched"], counts["new"], counts["updated"], counts["unchanged"], json.dumps(errors, ensure_ascii=False), run_id))
        db.commit()
        db.close()
        client.close()
    return {"id": run_id, "source": source_key, "status": status, **counts, "errors": errors}
