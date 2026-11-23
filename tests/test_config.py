"""設定（config.py）と、create_app() が設定をどう使うかのテスト。

このファイルのテストは DB に接続しないので、make_app フィクスチャではなく
create_app() を直接呼んでいる（DB に接続するアプリは make_app で作る。docs/04.md）。
"""

from pathlib import Path

import pytest

from fl_demonstro import create_app
from fl_demonstro.config import (
    Config,
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    _env_int,
    get_config,
)


# parametrize：同じテストを、引数の組み合わせを変えて何回も実行する
# （ここでは name="development" と name="production" の2回）
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("development", DevelopmentConfig),
        ("production", ProductionConfig),
    ],
)
def test_get_config_by_name(name: str, expected: type[Config]) -> None:
    # クラスそのものが返ることを確かめる（is は「同じオブジェクトか」を比べる）
    assert get_config(name) is expected


def test_get_config_defaults_to_production(monkeypatch: pytest.MonkeyPatch) -> None:
    # monkeypatch：このテストの間だけ環境変数などを書き換える（終わると元に戻る）
    # raising=False：もともと設定されていなくてもエラーにしない
    monkeypatch.delenv("APP_ENV", raising=False)

    assert get_config() is ProductionConfig


def test_get_config_reads_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")

    # 名前を渡さないと、環境変数 APP_ENV から選ぶ
    assert get_config() is DevelopmentConfig


@pytest.mark.parametrize(
    "name",
    [
        "staging",  # 存在しない名前
        "testing",  # テスト用の設定は、まちがって本番で使われないように選べない
    ],
)
def test_get_config_rejects_unknown_name(name: str) -> None:
    # pytest.raises：この with の中でエラーが起きることを確かめる
    # match：エラーメッセージに含まれているはずの文字（正規表現で探す）
    with pytest.raises(ValueError, match="APP_ENV"):
        get_config(name)


def test_create_app_requires_secret_key() -> None:
    # テストの中で子クラスを作り、確かめたい設定だけを変える
    # （TestingConfig の SECRET_KEY は文字列なので、None を入れると mypy がエラーにする。
    #   わざとなので type: ignore で知らせる）
    class NoSecretConfig(TestingConfig):
        SECRET_KEY = None  # type: ignore[assignment]  # わざと未設定にする

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(NoSecretConfig)


def test_instance_path_is_project_root(monkeypatch: pytest.MonkeyPatch) -> None:
    # INSTANCE_PATH がないときは、既定の場所（プロジェクト直下の instance/）になる
    monkeypatch.delenv("INSTANCE_PATH", raising=False)
    app = create_app(TestingConfig)

    # このテストファイル（tests/test_config.py）の1つ上がプロジェクト直下。
    # フォルダ名で比べないので、どんな名前のフォルダに置いても通る。
    project_root = Path(__file__).resolve().parents[1]
    assert app.instance_path == str(project_root / "instance")


# (環境変数の値, 期待する結果) の組み合わせ。
# None は「環境変数を設定しない」、" 2 " は前後の空白が無視されることを確かめる。
@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 0), ("", 0), ("1", 1), (" 2 ", 2)],
)
def test_env_int(
    monkeypatch: pytest.MonkeyPatch, value: str | None, expected: int
) -> None:
    # 環境変数の名前は何でもよいが、実際に _env_int() で読んでいる名前を使う
    if value is None:
        monkeypatch.delenv("TRUSTED_PROXY_COUNT", raising=False)
    else:
        monkeypatch.setenv("TRUSTED_PROXY_COUNT", value)

    assert _env_int("TRUSTED_PROXY_COUNT", 0) == expected


# 負の数・数字以外・小数・全角の数字は、どれもエラーにする
@pytest.mark.parametrize("value", ["-1", "abc", "1.5", "２"])
def test_env_int_rejects_invalid_value(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", value)

    # エラーメッセージに環境変数の名前が入り、どの設定が悪いか分かる
    with pytest.raises(ValueError, match="TRUSTED_PROXY_COUNT"):
        _env_int("TRUSTED_PROXY_COUNT", 0)


def test_instance_path_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # tmp_path：テストごとに pytest が用意する一時フォルダ（実際のフォルダを汚さない）
    monkeypatch.setenv("INSTANCE_PATH", str(tmp_path))

    # INSTANCE_PATH があれば、その場所が instance フォルダになる（Docker ではこちら）
    assert create_app(TestingConfig).instance_path == str(tmp_path)
