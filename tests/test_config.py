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


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("development", DevelopmentConfig),
        ("production", ProductionConfig),
    ],
)
def test_get_config_by_name(name: str, expected: type[Config]) -> None:
    assert get_config(name) is expected


def test_get_config_defaults_to_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)

    assert get_config() is ProductionConfig


def test_get_config_reads_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")

    assert get_config() is DevelopmentConfig


@pytest.mark.parametrize(
    "name",
    [
        "staging",  # 存在しない名前
        "testing",  # テスト用の設定は、まちがって本番で使われないように選べない
    ],
)
def test_get_config_rejects_unknown_name(name: str) -> None:
    with pytest.raises(ValueError, match="APP_ENV"):
        get_config(name)


def test_create_app_requires_secret_key() -> None:
    class NoSecretConfig(TestingConfig):
        SECRET_KEY = None  # type: ignore[assignment]  # わざと未設定にする

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(NoSecretConfig)


def test_instance_path_is_project_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INSTANCE_PATH", raising=False)
    app = create_app(TestingConfig)

    # このテストファイル（tests/test_config.py）の1つ上がプロジェクト直下。
    # フォルダ名で比べないので、どんな名前のフォルダに置いても通る。
    project_root = Path(__file__).resolve().parents[1]
    assert app.instance_path == str(project_root / "instance")


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 0), ("", 0), ("1", 1), (" 2 ", 2)],
)
def test_env_int(
    monkeypatch: pytest.MonkeyPatch, value: str | None, expected: int
) -> None:
    if value is None:
        monkeypatch.delenv("TRUSTED_PROXY_COUNT", raising=False)
    else:
        monkeypatch.setenv("TRUSTED_PROXY_COUNT", value)

    assert _env_int("TRUSTED_PROXY_COUNT", 0) == expected


@pytest.mark.parametrize("value", ["-1", "abc", "1.5", "２"])
def test_env_int_rejects_invalid_value(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", value)

    with pytest.raises(ValueError, match="TRUSTED_PROXY_COUNT"):
        _env_int("TRUSTED_PROXY_COUNT", 0)


def test_instance_path_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("INSTANCE_PATH", str(tmp_path))

    assert create_app(TestingConfig).instance_path == str(tmp_path)
