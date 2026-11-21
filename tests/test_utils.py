import pytest

from fl_demonstro.utils import is_safe_redirect_url


@pytest.mark.parametrize(
    "url",
    ["/", "/accounts/signup", "/path?x=1#top"],
)
def test_safe_urls(url: str) -> None:
    assert is_safe_redirect_url(url)


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "https://evil.example.com/",
        "http://localhost/",
        "//evil.example.com",
        "///evil.example.com",
        "/\\evil.example.com",
        "\\\\evil.example.com",
        "javascript:alert(1)",
        "relative/path",
        "/\tevil",
        "/\nevil",
    ],
)
def test_unsafe_urls(url: str | None) -> None:
    assert not is_safe_redirect_url(url)
