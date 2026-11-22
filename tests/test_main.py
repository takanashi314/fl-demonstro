from flask.testing import FlaskClient


def test_index_shows_signup_link(client: FlaskClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "ようこそ" in html
    assert 'href="/accounts/signup"' in html


def test_navbar_highlights_current_page(client: FlaskClient) -> None:
    html = client.get("/accounts/signup").get_data(as_text=True)

    assert "navbar" in html
    assert "nav-link active" in html


def test_footer_is_shown(client: FlaskClient) -> None:
    html = client.get("/").get_data(as_text=True)

    assert "<footer" in html
