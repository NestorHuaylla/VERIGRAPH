from typing import Any

from worker.services.api_client import post_external_reputation_result


def test_post_external_reputation_result_skips_without_token(monkeypatch: Any) -> None:
    monkeypatch.setattr("worker.services.api_client.settings.worker_api_token", "")

    result = post_external_reputation_result(
        "entity-1",
        {"sources": {}, "summary": {}},
    )

    assert result == {"status": "skipped", "reason": "WORKER_API_TOKEN is not configured."}


def test_post_external_reputation_result_skips_without_completed_checks(monkeypatch: Any) -> None:
    monkeypatch.setattr("worker.services.api_client.settings.worker_api_token", "token")

    result = post_external_reputation_result(
        "entity-1",
        {
            "sources": {
                "urlhaus": {
                    "source": "urlhaus",
                    "status": "not_configured",
                    "malicious": False,
                    "severity": "none",
                    "summary": "missing key",
                }
            },
            "summary": {},
        },
    )

    assert result == {"status": "skipped", "reason": "No completed source checks to persist."}
