"""マイグレーション（データベースの形の変更履歴）のテスト。

ほかのテストは db.create_all() でモデルから直接テーブルを作るので、
migrations/ の中身は使われない。ここで実際にマイグレーションを流し、
本番（Docker の起動時の flask db upgrade）と同じ手順でも正しい形になるかを確かめる。
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask import Flask
from flask_migrate import downgrade, upgrade
from sqlalchemy.exc import IntegrityError

from fl_demonstro import create_app
from fl_demonstro.config import TestingConfig
from fl_demonstro.extensions import db

MIGRATIONS_DIR = str(Path(__file__).resolve().parents[1] / "migrations")

# ユーザー名を小文字にそろえるマイグレーションの、1つ前の版
BEFORE_LOWERCASE_USERNAMES = "e7469dcb534f"

INSERT_USER = sa.text(
    "INSERT INTO users (username, password_hash, created_at)"
    " VALUES (:name, 'x', '2026-01-01 00:00:00')"
)


@pytest.fixture
def migration_app(tmp_path: Path) -> Iterator[Flask]:
    """一時フォルダのデータベースファイルを使うアプリ（中身は空）。"""

    class Config(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'migration.db'}"

    app = create_app(Config)
    with app.app_context():
        yield app
        db.session.remove()
        db.engine.dispose()


def test_upgrade_creates_same_tables_as_models(migration_app: Flask) -> None:
    upgrade(directory=MIGRATIONS_DIR)

    with db.engine.connect() as connection:
        differences = compare_metadata(
            MigrationContext.configure(connection), db.metadata
        )
    # モデル（models.py）とマイグレーション後のデータベースに違いがない
    assert differences == []


def test_duplicate_username_is_rejected_after_upgrade(migration_app: Flask) -> None:
    # マイグレーションのあとも、ユーザー名の重複禁止が働いている
    # （SQLite でテーブルを作り直す変更をすると、インデックスが消えることがあるため）
    upgrade(directory=MIGRATIONS_DIR)
    db.session.execute(INSERT_USER, {"name": "taro"})
    db.session.commit()

    # 重複のエラーは INSERT を実行した時点で起きる
    with pytest.raises(IntegrityError):
        db.session.execute(INSERT_USER, {"name": "taro"})


def test_upgrade_lowercases_existing_usernames(migration_app: Flask) -> None:
    upgrade(directory=MIGRATIONS_DIR, revision=BEFORE_LOWERCASE_USERNAMES)
    db.session.execute(INSERT_USER, {"name": "Taro"})
    db.session.commit()

    upgrade(directory=MIGRATIONS_DIR)

    assert db.session.scalars(sa.text("SELECT username FROM users")).all() == ["taro"]


def test_downgrade_and_upgrade_again(migration_app: Flask) -> None:
    # 一番最初まで戻して、もう一度最新にできる（マイグレーションの書き間違いの確認）
    upgrade(directory=MIGRATIONS_DIR)
    downgrade(directory=MIGRATIONS_DIR, revision="base")
    upgrade(directory=MIGRATIONS_DIR)

    assert "users" in sa.inspect(db.engine).get_table_names()
