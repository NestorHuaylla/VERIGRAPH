import app.core.security as security_module


def _reset_jwks_cache() -> None:
    security_module._jwks_cache["payload"] = None
    security_module._jwks_cache["fetched_at"] = 0.0


def test_get_oidc_jwks_refetches_after_ttl_expires(monkeypatch) -> None:
    _reset_jwks_cache()
    monkeypatch.setattr(security_module.settings, "keycloak_issuer", "https://kc.example.com/realms/verigraph")

    calls: list[int] = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def fake_get(url: str, timeout: int = 5) -> FakeResponse:
        calls.append(1)
        return FakeResponse({"keys": [{"kid": f"key-{len(calls)}"}]})

    monkeypatch.setattr(security_module.httpx, "get", fake_get)

    # tiempo simulado: primera llamada cachea, segunda dentro del TTL reusa cache
    fake_time = [1000.0]
    monkeypatch.setattr(security_module, "monotonic", lambda: fake_time[0])

    first = security_module.get_oidc_jwks()
    second = security_module.get_oidc_jwks()
    assert first == second
    assert len(calls) == 1  # la segunda llamada uso el cache, no volvio a pedir a Keycloak

    # avanzamos el tiempo mas alla del TTL: debe refrescar solo
    fake_time[0] += security_module._JWKS_CACHE_TTL_SECONDS + 1
    third = security_module.get_oidc_jwks()
    assert len(calls) == 2
    assert third != first


def test_find_jwks_key_forces_refresh_when_kid_rotated(monkeypatch) -> None:
    _reset_jwks_cache()
    monkeypatch.setattr(security_module.settings, "keycloak_issuer", "https://kc.example.com/realms/verigraph")

    responses = [
        {"keys": [{"kid": "old-key"}]},
        {"keys": [{"kid": "new-key"}]},
    ]

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def fake_get(url: str, timeout: int = 5) -> FakeResponse:
        return FakeResponse(responses.pop(0) if responses else {"keys": [{"kid": "new-key"}]})

    monkeypatch.setattr(security_module.httpx, "get", fake_get)
    monkeypatch.setattr(security_module, "monotonic", lambda: 1000.0)

    # Primera consulta cachea la llave vieja.
    security_module.get_oidc_jwks()

    # Keycloak roto sus llaves: el kid que llega ya no esta en el cache.
    # Sin el fix, esto devolveria None (login roto hasta reiniciar el server).
    key = security_module.find_jwks_key({"kid": "new-key"})

    assert key == {"kid": "new-key"}
