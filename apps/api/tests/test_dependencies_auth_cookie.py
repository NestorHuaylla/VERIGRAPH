from app.core.config import settings
from app.core.dependencies import get_token_from_request


class FakeRequest:
    def __init__(self, cookies: dict[str, str] | None = None) -> None:
        self.cookies = cookies or {}


def test_get_token_from_request_prefers_authorization_header() -> None:
    request = FakeRequest(cookies={settings.auth_cookie_name: "cookie-token"})

    token = get_token_from_request(request, header_token="header-token")  # type: ignore[arg-type]

    assert token == "header-token"


def test_get_token_from_request_falls_back_to_cookie() -> None:
    request = FakeRequest(cookies={settings.auth_cookie_name: "cookie-token"})

    token = get_token_from_request(request, header_token=None)  # type: ignore[arg-type]

    assert token == "cookie-token"


def test_get_token_from_request_returns_none_without_header_or_cookie() -> None:
    request = FakeRequest(cookies={})

    token = get_token_from_request(request, header_token=None)  # type: ignore[arg-type]

    assert token is None
