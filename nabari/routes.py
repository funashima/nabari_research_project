import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Blueprint, abort, current_app, g, jsonify, render_template, request, send_from_directory, url_for

from .db import connect, normalize
from .sources import CATEGORIES, SOURCES

bp = Blueprint("web", __name__)
JST = timezone(timedelta(hours=9), "JST")


def today():
    return datetime.now(JST).date().isoformat()


def database():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


@bp.teardown_app_request
def close_database(_error=None):
    db = g.pop("db", None)
    if db:
        db.close()


@bp.app_template_filter("jst")
def format_jst(value):
    if not value:
        return "未取得"
    return datetime.fromisoformat(value).astimezone(JST).strftime("%Y/%m/%d %H:%M")


@bp.app_context_processor
def common():
    return {"sources": SOURCES, "categories": CATEGORIES, "today": today(),
            "status_labels": {"running": "収集中", "success": "完了", "partial": "一部失敗", "failed": "失敗"}}


@bp.after_app_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'"
    )
    if not request.path.startswith(("/static/", "/research/")):
        response.headers["Cache-Control"] = "no-store"
    return response


def query_articles():
    query = request.args.get("q", "").strip()[:100]
    category = request.args.get("category", "")
    source = request.args.get("source", "")
    if category and category not in CATEGORIES or source and source not in SOURCES:
        abort(400, "検索条件を選び直してください。")
    try:
        page = max(1, min(int(request.args.get("page", 1)), 10000))
    except ValueError:
        abort(400, "ページ番号が不正です。")
    conditions = ["(source_date IS NULL OR source_date<=?)"]
    params = [today()]
    for field, value in (("category", category), ("source_key", source)):
        if value:
            conditions.append(field + "=?")
            params.append(value)
    for term in normalize(query).split()[:10]:
        conditions.append("search_text LIKE ? ESCAPE '\\'")
        params.append("%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    where = " AND ".join(conditions)
    db = database()
    total = db.execute("SELECT COUNT(*) FROM articles WHERE " + where, params).fetchone()[0]
    per_page = 12
    pages = max(1, math.ceil(total / per_page))
    page = min(page, pages)
    rows = [dict(r) for r in db.execute("SELECT * FROM articles WHERE " + where +
        " ORDER BY COALESCE(source_date,'0000-00-00') DESC,title ASC LIMIT ? OFFSET ?", params + [per_page, (page - 1) * per_page])]
    return {"items": rows, "total": total, "page": page, "pages": pages, "per_page": per_page,
            "query": query, "category": category, "source": source}


def source_statuses():
    db = database()
    out = []
    for key, source in SOURCES.items():
        run = db.execute("SELECT * FROM collection_runs WHERE source_key=? ORDER BY id DESC LIMIT 1", (key,)).fetchone()
        summary = db.execute("""SELECT COUNT(*) AS total,MAX(fetched_at) AS last_fetched,
          SUM(CASE WHEN source_date>? THEN 1 ELSE 0 END) AS future FROM articles WHERE source_key=?""", (today(), key)).fetchone()
        last = summary["last_fetched"]
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() if last else None
        out.append({"key": key, "name": source.name, "listing": source.listing,
                    "run": dict(run) if run else None, "total": summary["total"],
                    "future": summary["future"] or 0, "last_fetched": last, "stale": age is None or age > 86400})
    return out


@bp.get("/")
def index():
    result = query_articles()
    def page_url(number):
        return url_for("web.index", q=result["query"], category=result["category"], source=result["source"], page=number)
    return render_template("index.html", **result, source_states=source_statuses(), page_url=page_url)


@bp.get("/articles/<article_id>")
def detail(article_id):
    row = database().execute("SELECT * FROM articles WHERE id=? AND (source_date IS NULL OR source_date<=?)", (article_id, today())).fetchone()
    if row is None:
        abort(404)
    # Recreate a local return URL only; never accept an arbitrary redirect URL.
    back = url_for("web.index", q=request.args.get("q", "")[:100],
        source=request.args.get("source", "") if request.args.get("source", "") in SOURCES else "",
        category=request.args.get("category", "") if request.args.get("category", "") in CATEGORIES else "",
        page=request.args.get("page", "1") if request.args.get("page", "1").isdigit() else "1")
    a = dict(row)
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(a["fetched_at"])).total_seconds()
    return render_template("detail.html", article=a, back=back, stale=age > 86400)


@bp.get("/status")
def status():
    runs = [dict(r) for r in database().execute("SELECT * FROM collection_runs ORDER BY id DESC LIMIT 20")]
    for r in runs:
        r["errors"] = json.loads(r["errors_json"])
    return render_template("status.html", source_states=source_statuses(), runs=runs)


@bp.get("/about")
def about():
    return render_template("about.html")


@bp.get("/api/articles")
def api_articles():
    result = query_articles()
    for a in result["items"]:
        a.pop("search_text", None)
        a["source_name"] = SOURCES[a["source_key"]].name
        a["category_label"] = CATEGORIES[a["category"]]
        a["classification"] = "automatic_keywords"
        a["event_date"] = None
    return jsonify(result | {"as_of_jst": today(), "date_note": "source_date is a publication/update date, not an event date"})


@bp.get("/api/collection-status")
def api_status():
    return jsonify({"sources": source_statuses(), "as_of_jst": today()})


@bp.get("/healthz")
def health():
    database().execute("SELECT 1")
    return jsonify({"status": "ok"})


@bp.get("/research/")
@bp.get("/research/<path:filename>")
def research(filename="study.html"):
    # send_from_directory prevents path traversal. This fixed study dataset is
    # deliberately isolated from the changing production collection.
    return send_from_directory(Path(current_app.root_path).parent / "dist", filename)


@bp.app_errorhandler(400)
@bp.app_errorhandler(404)
def error_page(error):
    message = "お探しのページはありません。" if error.code == 404 else str(error.description)
    return render_template("error.html", message=message), error.code
