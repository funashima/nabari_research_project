# Flaskサーバでの運用

この成果物はローカルで動くFlaskアプリです。外部公開URLは同梱していません。

小規模な研究運用では `python run.py` でWaitressと単一の定期収集スレッドを起動できます。外部公開時は永続ディスク上にコード・DBを置き、HTTPSのリバースプロキシを前段に設けます。書き込み用のWeb APIは提供しません。

## Linuxサービス例

配置先 `/opt/nabari`、専用ユーザー `nabari` を管理者が作成済みである場合の例です。コマンドは環境に合わせて変更してください。ここにパスワード等の秘密情報は不要です。

```ini
[Unit]
Description=Nabari Flask research service
After=network-online.target
Wants=network-online.target

[Service]
User=nabari
WorkingDirectory=/opt/nabari
Environment=NABARI_DATABASE=/opt/nabari/instance/nabari.sqlite3
ExecStart=/opt/nabari/.venv/bin/python run.py --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=20

[Install]
WantedBy=multi-user.target
```

nginx等から `http://127.0.0.1:8000` に転送します。独自ドメインのTLS証明書・認証・アクセスログの保存期間は配置先で設定してください。提供元のIP制限やアクセス制限を回避しないでください。

## 閲覧と収集を分離する場合

閲覧: `python run.py --no-collect`。

cronの例（30分ごと）:

```cron
*/30 * * * * cd /opt/nabari && /opt/nabari/.venv/bin/python -m flask --app nabari collect >> /opt/nabari/instance/collector.log 2>&1
```

cronを使う場合はアプリの収集スレッドを止めます。DBの実行中制約と15分の間隔制限は補助的な保護です。日常監視では `/healthz` だけでなく `/api/collection-status` の最終取得日時と結果も確認します。DBバックアップ・ログローテーションを設定してください。

## 取得先の形式が変わった場合

`listing_structure_changed` / `article_structure_changed` を確認したら、そのサイトのHTML構造を調査し、`collector.py` の該当パーサとテスト用HTMLを一緒に更新します。空の結果を「成功」として公開しません。robotsや利用条件が変更された場合は収集を停止して設定を見直します。
