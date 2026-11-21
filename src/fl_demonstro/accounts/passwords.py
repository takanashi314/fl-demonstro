"""パスワードの保存（ハッシュ化）と、パスワードポリシー（強度チェック）。

保存: Argon2id（OWASP が第一に推奨する方式）でハッシュ化する。
      以前の方式（Werkzeug の scrypt）で保存されたものも照合でき、
      ログイン成功時に Argon2id で保存し直す（再ハッシュ）。
ポリシー: 米国 NIST SP 800-63B の考え方に沿い、記号や大文字は必須にしない代わりに、
      よく使われるパスワードや推測しやすいパスワードを弾く。
"""

import gzip
from functools import cache
from importlib.resources import files
from itertools import pairwise

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from flask import current_app
from werkzeug.security import check_password_hash

PASSWORD_MIN = 8
PASSWORD_MAX = 128  # 極端に長いパスワードでサーバーに負荷をかけられるのを防ぐ

ARGON2ID_PREFIX = "$argon2id$"


# ---------- 保存（ハッシュ化）と照合 ----------


@cache
def _make_hasher(time_cost: int, memory_cost: int, parallelism: int) -> PasswordHasher:
    return PasswordHasher(
        time_cost=time_cost, memory_cost=memory_cost, parallelism=parallelism
    )


def _hasher() -> PasswordHasher:
    """設定（ARGON2_*）に合わせた Argon2id のハッシュ化の道具を返す。"""
    config = current_app.config
    return _make_hasher(
        config["ARGON2_TIME_COST"],
        config["ARGON2_MEMORY_COST"],
        config["ARGON2_PARALLELISM"],
    )


def hash_password(password: str) -> str:
    """パスワードを Argon2id でハッシュ化する（ソルトは自動で付く）。"""
    return _hasher().hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """保存されたハッシュとパスワードが一致するか確かめる。"""
    if password_hash.startswith("$argon2"):
        try:
            return _hasher().verify(password_hash, password)
        except VerificationError, InvalidHashError:
            return False
    # 以前の方式（Werkzeug の scrypt）で保存されたパスワード
    try:
        return check_password_hash(password_hash, password)
    except ValueError:  # 壊れた値
        return False


def needs_rehash(password_hash: str) -> bool:
    """今の方式・設定で保存し直したほうがよいか（古い方式や弱い設定なら True）。"""
    if not password_hash.startswith(ARGON2ID_PREFIX):
        return True
    try:
        return _hasher().check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


@cache
def _dummy_hash(time_cost: int, memory_cost: int, parallelism: int) -> str:
    return _make_hasher(time_cost, memory_cost, parallelism).hash("dummy-password")


def verify_dummy_password(password: str) -> None:
    """存在しないユーザーでログインされたときに、同じだけ時間をかけるための照合。"""
    config = current_app.config
    verify_password(
        _dummy_hash(
            config["ARGON2_TIME_COST"],
            config["ARGON2_MEMORY_COST"],
            config["ARGON2_PARALLELISM"],
        ),
        password,
    )


# ---------- パスワードポリシー（強度チェック） ----------


@cache
def common_passwords() -> frozenset[str]:
    """よく使われているパスワードの一覧（小文字）。最初に使うときに一度だけ読み込む。"""
    data = (
        files("fl_demonstro.accounts")
        .joinpath("data", "common_passwords.txt.gz")
        .read_bytes()
    )
    return frozenset(gzip.decompress(data).decode().splitlines())


def _is_sequential(text: str) -> bool:
    """「abcdefgh」「12345678」「87654321」のような連続した文字か。"""
    steps = {ord(b) - ord(a) for a, b in pairwise(text)}
    return steps in ({1}, {-1})


def password_policy_error(password: str, username: str | None = None) -> str | None:
    """パスワードポリシーに合わなければ、その理由を返す（合えば None）。

    文字数のチェックはフォーム側で行うので、ここでは中身だけを見る。
    """
    lowered = password.lower()
    if username and username.lower() in lowered:
        return "ユーザー名を含むパスワードは使えません。"
    if len(set(lowered)) <= 2:
        return "同じ文字の繰り返しのような、単純なパスワードは使えません。"
    if _is_sequential(lowered):
        return "「abcdefgh」「12345678」のような連続した文字は使えません。"
    if lowered in common_passwords():
        return "よく使われているパスワードのため使えません。推測されにくいものにしてください。"
    return None
