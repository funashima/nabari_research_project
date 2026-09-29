# なばり くらしの案内 — Flask版

名張市役所と名張市観光協会から公開情報を収集し、SQLiteに保存して、Flaskで検索・一覧・詳細ページを動的に生成する高専研究用システムです。外部APIキーは不要です。

## 起動（Python 3.11以上）

ZIPを展開し、このREADMEがあるフォルダで実行してください。依存のダウンロードと公式情報の収集にはインターネット接続が必要です。

```bash
python -m venv .venv
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Windows（コマンドプロンプト）:

```bat
.venv\Scripts\activate.bat
```

続けて:

```bash
python -m pip install -r requirements.txt
python run.py
```

ブラウザで **http://127.0.0.1:8000/** を開きます。起動直後に両方の出典を収集し、その後30分おきに更新します。初回は収集に時間がかかります。`/status` で進行・取得件数・エラーを確認できます。ページを開き直すと最新の保存内容が表示されます。Ctrl+Cで終了します。

収集先は以下に限定しています。

| 出典 | 新着一覧 | 標準の取得範囲 |
| --- | --- | --- |
| 名張市役所 | https://www.city.nabari.lg.jp/news.html | 先頭12件＋ごみ・保健・相談など定番7ページ |
| 名張市観光協会 | https://kankou-nabari.jp/news | 先頭12件 |

記事の冒頭180文字と題名・出典・掲載／更新日・取得日時を保存します。画像・PDF・本文全文は配信しません。分類は題名等のキーワードによる自動判定です。掲載日から開催日を推定しません。出典の日付が日本時間の本日より未来の記事は、日付の到来まで一覧・詳細・APIから除外し、収集状況で件数を示します。

## 通信せずに動作を確認する

```bash
python -m flask --app nabari import-demo
python run.py --no-collect
```

同梱の取得済みスナップショットを空のDBに読み込みます。これは過去に取得した実データで、実行時点の最新情報を装うものではありません。記事の取得日時は元のまま表示されます。すでにデータがあるDBへの取込は拒否します。通常運用へ移る場合は `python run.py` を起動し直します。

## 主な画面・API

| パス | 内容 |
| --- | --- |
| `/` | 市役所・観光協会を横断する検索、出典・カテゴリ絞り込み、ページ送り |
| `/articles/<id>` | 短い抜粋、出典リンク、取得日時、変更検出、読み上げ・印刷 |
| `/status` | 出典別の取得件数、直近20回の履歴、失敗・未来日記事の件数 |
| `/about` | 情報の範囲、日付の意味、研究上の限界 |
| `/api/articles?q=祭り&source=tourism` | 閲覧画面と同じ条件のJSON。`category`、`page`も利用可 |
| `/api/collection-status` | 出典別の収集状況JSON |
| `/healthz` | アプリ・DB疎通確認。外部サイトの到達性は表しません |
| `/research/` | 市役所10件を固定した旧試作UIによる予備実験 |

検索は題名・抜粋を対象に、全角半角・ひらがなカタカナを正規化し、複数語をAND条件として照合します。本文全体の検索や意味検索はしません。記事は掲載／更新日の新しい順です。古い記事も保存するため、イベントの「開催中」を保証しません。

## 収集を個別に実行する

```bash
python -m flask --app nabari collect
python -m flask --app nabari collect --source tourism --limit 8
python -m flask --app nabari export-data data/my_snapshot.json
```

同一出典への再収集は前回完了から15分以上空けます。`--limit` は新着一覧の先頭件数で1〜20です。市役所の定番7ページは別途取得します。1秒以上の通信間隔、robots.txt、接続／受信タイムアウト、2MiBの応答上限を設けています。429・403やrobots拒否でその出典の収集を止めます。robots.txtの404/410はルールなし、通信失敗・5xxは収集中止として扱います。

```bash
python run.py --interval 3600 --limit 10
```

この設定では約1時間ごとに更新します。サーバを止めると定期収集も止まります。独立したcron等で収集する場合、閲覧サーバを `--no-collect` で起動してください。Flaskの `--debug` に収集スレッドを組み込んでいないため、開発リローダーによる重複収集は起こしません。

## 保存・障害対応

- DBは `instance/nabari.sqlite3` に自動作成されます。`NABARI_DATABASE` 環境変数で保存先を指定できます。
- 同一URLは1件として保存します。抽出本文等のSHA-256が変わった場合のみ版を増やします。
- 本文の後半の変更もハッシュで検出します。過去の版には短い抜粋と題名等だけを残します。
- 記事単位でコミットし、後続の記事や片方の出典が失敗しても保存済み記事を削除しません。
- 新着一覧から外れた記事は保持しますが、定番ページを除き、更新を追い続けません。24時間以上未取得の詳細には注意表示します。
- DBロックと実行中の出典の一意制約で重複実行を抑止します。30分以上進行のない実行を中断扱いにし、15分後から再実行できます。
- `instance/` に利用者の実験記録は保存しません。実験JSONは手元で保存してください。

バックアップはサーバを停止してDBを複製するか、SQLiteのbackup APIを使います。稼働中に`.sqlite3`だけをコピーするとWAL内の更新を取り落とす可能性があります。

## 公開サーバへの配置

同梱の起動コマンドはFlaskアプリをWaitressで配信し、既定で自分のPCからだけ接続できます。外部公開する場合はHTTPSのリバースプロキシ、アクセス制御、永続ディスク、バックアップをサーバ側で設定してください。例は `deploy/README.md` にあります。今回、Flaskサーバの外部ホスティングは行っていません。

## テストと研究

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

固定予備実験UIのJavaScriptテストだけ、Node.js 20以上を使います。アプリの運用にNode.jsは不要です。

```bash
npm ci
npm test
```

`results/verification_summary.json` に検証結果、`docs/nabari_research_report.tex` とPDFに到達点と限界をまとめています。別冊の `docs/nabari_student_guide.tex` は、高校2年生程度向けに入力・設定・結果・コードを説明します。2冊ともLuaLaTeX形式です。コンパイル方法は `docs/BUILD_LATEX.md` を参照してください。対象者による実験は未実施です。固定UIの結果を、そのままFlask画面・観光協会情報の有用性に置き換えることはできません。

予備実験手順は `docs/experiment_protocol.md`、評価票は `docs/evaluation_sheet.md`、集計は `tools/analyze_study.py` にあります。練習データは本実験に混ぜず、氏名等を記録しません。

## 構成

```text
nabari/                 Flaskアプリ、収集、DB、Jinjaテンプレート
run.py                  Waitress＋定期収集の起動
data/                   実際に取得した短い抜粋のスナップショット
dist/                   予備実験用に固定した旧試作UIと10件のデータ
tests/                  Flask・収集・集計・固定UIの自動テスト
docs/                   報告書、運用・実験手順、評価票、出典
results/                実行ログ・集計結果
report_assets/          PDF用Noto Sans JPとOFLライセンス
tools/                  実験結果の集計、報告書の生成
```

アプリ部分は本研究用に作成したコードです。出典記事は各発行元に権利があり、再配布・商用化・収集範囲拡大時には各サイトの条件を確認してください。フォントは `report_assets/OFL.txt` に従います。
