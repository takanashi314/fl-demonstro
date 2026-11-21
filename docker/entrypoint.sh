#!/bin/sh
# コンテナ起動時に毎回実行される。
# データベースを最新の形に更新してから、本来のコマンド（gunicorn）を起動する。
set -e

flask db upgrade

exec "$@"
