"""One-process startup: Flask/Waitress plus a single periodic collector thread."""
import argparse
import json
import logging
import threading

from waitress import serve
from nabari import create_app
from nabari.collector import collect_source


def collect_loop(database, interval, limit, stop):
    while not stop.is_set():
        for source in ("city", "tourism"):
            if stop.is_set():
                return
            try:
                result = collect_source(database, source, limit)
                logging.info("collection %s", json.dumps(result, ensure_ascii=False))
            except Exception:
                logging.exception("収集処理でエラーが発生しました。保存済み記事は保持します。")
        stop.wait(interval)


def main():
    parser = argparse.ArgumentParser(description="名張市役所・名張市観光協会の情報を収集し、Flaskで表示")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--interval", type=int, default=1800, help="収集間隔（秒）。900以上")
    parser.add_argument("--limit", type=int, default=12, help="各新着一覧から取得する件数（1〜20）。市の定番7ページは別途取得")
    parser.add_argument("--no-collect", action="store_true", help="閲覧サーバだけ起動（デモまたは別の定期収集を利用）")
    args = parser.parse_args()
    if args.interval < 900 or not 1 <= args.limit <= 20:
        parser.error("interval は900以上、limit は1〜20で指定してください")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = create_app()
    stop = threading.Event()
    if not args.no_collect:
        threading.Thread(target=collect_loop, args=(app.config["DATABASE"], args.interval, args.limit, stop), daemon=True).start()
    logging.info("http://%s:%s  /status で収集履歴を確認できます", args.host, args.port)
    try:
        serve(app, host=args.host, port=args.port, threads=4, channel_timeout=30)
    finally:
        stop.set()


if __name__ == "__main__":
    main()
