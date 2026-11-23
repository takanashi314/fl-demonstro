# fl-demonstro

## フォルダ構成

```
src/fl_demonstro/
├── __init__.py        … create_app()（アプリを組み立てる関数）
├── config.py          … 設定（開発用・本番用・テスト用）
├── extensions.py      … データベースなどの拡張機能
├── security.py        … セキュリティ用ヘッダー
├── errors.py          … エラー画面（404 など）
├── utils.py           … 便利関数（安全なリダイレクト先の判定など）
├── main/              … 一般ページ（トップページ）
├── accounts/          … アカウント（サインアップ・ログイン・ログアウト）
│   ├── forms.py       … 入力フォーム
│   ├── models.py      … User モデル
│   ├── passwords.py   … パスワードの保存（Argon2id）とパスワードポリシー
│   ├── data/          … よく使われるパスワードの一覧
│   └── views.py       … 画面の処理
└── templates/         … HTML テンプレート
    ├── base.html      … 全ページ共通の土台（partials/ の部品を組み立てる）
    ├── partials/      … base.html が読み込む部品（ナビゲーションバー・flash メッセージ・フッター）
    ├── macros/        … マクロ（forms.html：フォーム部品）
    └── <ブループリント名>/...
tests/                 … 自動テスト
migrations/            … データベースの形の変更履歴
instance/              … データベースとセッションのファイル（Git には入れない）
```

## 使っているFlask拡張

| 拡張 | 役割 |
|---|---|
| Flask-SQLAlchemy / Flask-Migrate | データベースとテーブルの形の変更管理 |
| Flask-WTF | フォームとCSRF対策 |
| Flask-Login | ログイン状態の管理 |
| Flask-Limiter | 送信回数の制限 |
| Flask-Session | セッションをサーバー側（Redisまたはinstance/sessions）に保存 |
| Flask-DebugToolbar | 開発時のデバッグ用ツールバー（`FLASK_DEBUG=1`のときだけ表示） |

パスワードはargon2-cffiでArgon2idとしてハッシュ化して保存する。

## ユーザー名のルール

- 3〜32文字の半角英小文字（a〜z）と数字だけ（大文字・記号・全角は使えない）
- ログインでは、大文字で入力しても小文字として扱う（スマートフォンで先頭が大文字になってもログインできる）

## パスワードポリシー

米国NIST SP 800-63Bの考え方に沿って、記号や大文字は必須にせず、推測されやすいものを弾く。

- 8〜128文字
- よく使われているパスワード（約4.6万件の一覧）は使えない
- ユーザー名を含むもの、同じ文字の繰り返し、連続した文字（`12345678`など）は使えない

## 準備

ひな形の`.env.example`を`.env`という名前でコピーし、`SECRET_KEY`を書き込む（`.env`はGitにコミットしない）。

```
cp .env.example .env
```

最低限、次の内容があればよい（ほかの設定は`.env.example`のコメントを参照）。

```
FLASK_APP=fl_demonstro
APP_ENV=development
FLASK_DEBUG=1
SECRET_KEY=（ランダムな長い文字列）
```

- `APP_ENV` … 使う設定（`development` / `production`）。未設定なら`production`。テスト用の設定はCSRF対策などを切ってあるため、まちがって本番で使わないよう`APP_ENV`では選べない（自動テストの中だけで使う）。
- `SECRET_KEY`は次のコマンドで作れる。

```
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

## ローカルで動かす（開発用）

```
uv sync
uv run flask db upgrade
uv run flask run
```

http://localhost:5000を開く。画面の右側に出るデバッグツールバーで、
実行されたSQLやテンプレート、セッションの中身などを確認できる。

## テストとコードチェック

```
uv run pytest            # 自動テスト
uv run ruff check .      # 書き方のチェック（--fix で自動修正）
uv run ruff format .     # 書き方をそろえる
uv run mypy              # 型のチェック（src/ と tests/）
uv run djlint --check src  # テンプレートの整形チェック（--reformat で自動整形）
```

最初に一度だけ、次のコマンドでpre-commit（コミット・プッシュの前に自動でチェックする仕組み）を有効にする。コミットの前にruff・djlint・mypy、プッシュの前にpytestが自動で動く。

```
uv run pre-commit install
```

## Dockerで動かす

```
docker compose up -d --build   # 起動（初回や変更後は --build を付ける）
docker compose logs -f web     # ログを見る
docker compose down            # 停止（データベースは残る）
```

http://localhost:8000を開く。データベースは起動時に自動で最新の形に更新される。

- 開けるのは自分のパソコンからだけ（同じネットワークの他の機器からは見えない）。
- データの置き場所（ボリューム）の名前は、`compose.yaml`の`name: fl-demonstro`で固定している。フォルダ名を変えても、前のデータがそのまま使われる。
- ローカルのDockerでは仕組み上、アプリからは全員が同じIPアドレス（Dockerの中継役）から来たように見える。IPアドレスごとの回数制限が全員で1つになるが、1人で試す分には問題ない。

## インターネットに公開するとき

今の`compose.yaml`は、自分のパソコンのhttp://localhostで試すための設定。公開するときは、次の対応が必要。

1. **HTTPSにする**：gunicornを直接外に出さず、前にnginxやCaddyなどのリバースプロキシ（受付役のサーバー）を置いてHTTPSにする。RenderやFly.ioなどのサービスを使う場合は、サービス側がこの役をしてくれる。
2. **`SESSION_COOKIE_SECURE: "false"`の行を消す**：CookieがHTTPSのときだけ送られるようになる。
3. **`TRUSTED_PROXY_COUNT`を設定する**：アプリの前にあるリバースプロキシの数（ふつうは`1`）。設定しないと、アプリからは全員が「プロキシのIPアドレス」から来たように見え、IPアドレスごとの回数制限が全員で1つになってしまう。ただし、プロキシを通さずに直接つながる状態では設定しないこと（ヘッダーを偽って、回数制限をすり抜けられてしまう）。

nginxを使う場合は、次のヘッダーを付けてアプリに渡す。

```
proxy_set_header Host $host;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
```

利用者が増えて同時の書き込みが多くなったら、SQLiteからPostgreSQLなどへの移行も考える。

## データベースの形を変えたとき

```
uv run flask db migrate -m "変更内容"
# migrations/versions/ にできたファイルを確認してから
uv run flask db upgrade
uv run pytest tests/test_migrations.py   # マイグレーションを実際に流して確認する
```

式を使ったインデックス（`lower(username)`など）は使わない。SQLiteでテーブルを作り直す変更をすると、黙って消えてしまうため。
