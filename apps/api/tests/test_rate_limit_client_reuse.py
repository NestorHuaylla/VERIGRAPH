from app.core.rate_limit import get_redis_client


def test_get_redis_client_returns_same_instance_across_calls() -> None:
    first = get_redis_client()
    second = get_redis_client()

    # Antes, cada llamada a enforce_rate_limit creaba un cliente Redis nuevo
    # (una conexion TCP nueva) por request. Ahora debe reutilizarse el mismo
    # cliente (y su pool de conexiones interno) durante toda la vida del proceso.
    assert first is second
