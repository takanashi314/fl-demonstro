"""アプリ全体で使う小さな便利関数。"""

from typing import TypeIs
from urllib.parse import urlsplit


def is_safe_redirect_url(target: str | None) -> TypeIs[str]:
    """リダイレクト先として安全な URL（このサイト内のパス）かどうかを判定する。

    ログイン後の ?next=... に外部サイトの URL を入れて、利用者を偽サイトへ
    誘導する攻撃（オープンリダイレクト）を防ぐために使う。
    """
    if not target:
        return False
    # バックスラッシュや制御文字は、ブラウザによって別サイトとして解釈されることがある
    if "\\" in target or any(ord(char) < 32 for char in target):
        return False
    parts = urlsplit(target)
    return (
        not parts.scheme
        and not parts.netloc
        and target.startswith("/")
        and not target.startswith("//")
    )
