import json
import os
from pathlib import Path

import click
from flask import Flask

from .db import export_snapshot, import_snapshot, init_db


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.environ.get("NABARI_DATABASE", str(Path(app.instance_path) / "nabari.sqlite3")),
        MAX_CONTENT_LENGTH=16384,
    )
    if test_config:
        app.config.update(test_config)
    init_db(app.config["DATABASE"])
    from .routes import bp
    app.register_blueprint(bp)

    @app.cli.command("collect")
    @click.option("--source", type=click.Choice(["all", "city", "tourism"]), default="all")
    @click.option("--limit", type=click.IntRange(1, 20), default=12, show_default=True)
    def collect_command(source, limit):
        """Collect public news once. Each source has a 15-minute cooldown."""
        from .collector import collect_source
        keys = ["city", "tourism"] if source == "all" else [source]
        failed = False
        for key in keys:
            result = collect_source(app.config["DATABASE"], key, limit)
            click.echo(json.dumps(result, ensure_ascii=False))
            failed |= result["status"] in ("failed", "partial")
        if failed:
            raise click.ClickException("一部の収集に失敗しました。/status で履歴を確認してください。")

    @app.cli.command("export-data")
    @click.argument("destination", type=click.Path())
    def export_command(destination):
        """Export the collected public dataset and collection history."""
        export_snapshot(app.config["DATABASE"], destination)
        click.echo(destination)

    @app.cli.command("import-demo")
    def demo_command():
        """Load the bundled dated snapshot into an empty database only."""
        try:
            n = import_snapshot(app.config["DATABASE"], Path(app.root_path).parent / "data/collected_snapshot.json")
        except (ValueError, KeyError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"取得済みのスナップショット {n} 件を読み込みました（今回の新規収集ではありません）。")

    return app
