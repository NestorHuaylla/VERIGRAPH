from __future__ import annotations

from typing import Any

import httpx

from worker.config import WorkerSettings
from worker.services.external_sources import (
    PHISHTANK_CHECK_URL_ENDPOINT,
    SAFE_BROWSING_ENDPOINT,
    URLHAUS_HOST_ENDPOINT,
    URLHAUS_URL_ENDPOINT,
    URLSCAN_SEARCH_ENDPOINT,
    VIRUSTOTAL_API_URL,
    check_external_reputation,
    check_google_safe_browsing,
    check_phishtank,
    check_urlscan,
    check_urlhaus,
    check_virustotal,
    virustotal_url_id,
)


class FakeHttpClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append(("GET", url, kwargs))
        response = self.responses.pop(0)
        response.request = httpx.Request("GET", url)
        return response

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append(("POST", url, kwargs))
        response = self.responses.pop(0)
        response.request = httpx.Request("POST", url)
        return response


def make_settings(**overrides: str) -> WorkerSettings:
    values = {
        "celery_broker_url": "redis://redis:6379/1",
        "celery_result_backend": "redis://redis:6379/2",
        "redis_url": "redis://redis:6379/0",
        "api_base_url": "http://api:8000",
        "virustotal_api_key": "",
        "google_safe_browsing_api_key": "",
        "phishtank_api_key": "",
        "urlhaus_auth_key": "",
        "urlscan_api_key": "",
        "slack_webhook_url": "",
    }
    values.update(overrides)
    return WorkerSettings(**values)


def test_urlhaus_url_match_returns_malicious_result() -> None:
    client = FakeHttpClient(
        [
            httpx.Response(
                200,
                json={
                    "query_status": "ok",
                    "urlhaus_reference": "https://urlhaus.abuse.ch/url/1/",
                    "url": "https://bad.test/payload.exe",
                    "url_status": "online",
                    "host": "bad.test",
                    "threat": "malware_download",
                },
            )
        ]
    )

    result = check_urlhaus(
        "https://bad.test/payload.exe",
        "url",
        client,
        app_settings=make_settings(urlhaus_auth_key="urlhaus-key"),
    )

    assert result.status == "malicious"
    assert result.malicious is True
    assert result.severity == "high"
    assert result.reference == "https://urlhaus.abuse.ch/url/1/"
    assert client.calls[0][0] == "POST"
    assert client.calls[0][1] == URLHAUS_URL_ENDPOINT
    assert client.calls[0][2]["data"] == {"url": "https://bad.test/payload.exe"}
    assert client.calls[0][2]["headers"] == {"Auth-Key": "urlhaus-key"}


def test_urlhaus_domain_match_uses_host_endpoint() -> None:
    client = FakeHttpClient(
        [
            httpx.Response(
                200,
                json={
                    "query_status": "ok",
                    "urlhaus_reference": "https://urlhaus.abuse.ch/host/bad.test/",
                    "host": "bad.test",
                    "url_count": "7",
                },
            )
        ]
    )

    result = check_urlhaus(
        "bad.test",
        "domain",
        client,
        app_settings=make_settings(urlhaus_auth_key="urlhaus-key"),
    )

    assert result.status == "malicious"
    assert result.severity == "high"
    assert "7 URLs" in result.summary
    assert client.calls[0][1] == URLHAUS_HOST_ENDPOINT
    assert client.calls[0][2]["data"] == {"host": "bad.test"}


def test_urlhaus_no_results_returns_clean_result() -> None:
    client = FakeHttpClient([httpx.Response(200, json={"query_status": "no_results"})])

    result = check_urlhaus(
        "https://clean.test/",
        "url",
        client,
        app_settings=make_settings(urlhaus_auth_key="urlhaus-key"),
    )

    assert result.status == "clean"
    assert result.malicious is False
    assert result.severity == "none"


def test_safe_browsing_match_returns_malicious_result() -> None:
    client = FakeHttpClient(
        [
            httpx.Response(
                200,
                json={
                    "matches": [
                        {
                            "threatType": "SOCIAL_ENGINEERING",
                            "platformType": "ANY_PLATFORM",
                            "threat": {"url": "https://bad.test/"},
                        }
                    ]
                },
            )
        ]
    )

    result = check_google_safe_browsing(
        "https://bad.test/",
        "url",
        client,
        app_settings=make_settings(google_safe_browsing_api_key="google-key"),
    )

    assert result.status == "malicious"
    assert result.malicious is True
    assert result.severity == "high"
    assert "SOCIAL_ENGINEERING" in result.summary
    assert client.calls[0][1] == SAFE_BROWSING_ENDPOINT
    assert client.calls[0][2]["params"] == {"key": "google-key"}
    assert client.calls[0][2]["json"]["threatInfo"]["threatEntries"] == [{"url": "https://bad.test/"}]


def test_safe_browsing_domain_is_checked_as_https_url() -> None:
    client = FakeHttpClient([httpx.Response(200, json={})])

    result = check_google_safe_browsing(
        "clean.test",
        "domain",
        client,
        app_settings=make_settings(google_safe_browsing_api_key="google-key"),
    )

    assert result.status == "clean"
    assert client.calls[0][2]["json"]["threatInfo"]["threatEntries"] == [{"url": "https://clean.test"}]


def test_virustotal_url_match_returns_malicious_result() -> None:
    client = FakeHttpClient(
        [
            httpx.Response(
                200,
                json={
                    "data": {
                        "attributes": {
                            "last_analysis_stats": {
                                "malicious": 6,
                                "suspicious": 1,
                                "harmless": 70,
                            }
                        }
                    }
                },
            )
        ]
    )

    result = check_virustotal(
        "https://bad.test/",
        "url",
        client,
        app_settings=make_settings(virustotal_api_key="vt-key"),
    )

    assert result.status == "malicious"
    assert result.malicious is True
    assert result.severity == "critical"
    assert "6 malicious" in result.summary
    assert client.calls[0][0] == "GET"
    assert client.calls[0][1] == f"{VIRUSTOTAL_API_URL}/urls/{virustotal_url_id('https://bad.test/')}"
    assert client.calls[0][2]["headers"] == {"x-apikey": "vt-key"}


def test_virustotal_domain_clean_result() -> None:
    client = FakeHttpClient(
        [
            httpx.Response(
                200,
                json={"data": {"attributes": {"last_analysis_stats": {"malicious": 0, "suspicious": 0}}}},
            )
        ]
    )

    result = check_virustotal(
        "https://clean.test/path",
        "domain",
        client,
        app_settings=make_settings(virustotal_api_key="vt-key"),
    )

    assert result.status == "clean"
    assert result.malicious is False
    assert client.calls[0][1] == f"{VIRUSTOTAL_API_URL}/domains/clean.test"


def test_phishtank_verified_active_match_returns_malicious_result() -> None:
    client = FakeHttpClient(
        [
            httpx.Response(
                200,
                json={
                    "results": {
                        "in_database": True,
                        "verified": "y",
                        "valid": "y",
                        "phish_id": "123",
                        "phish_detail_page": "https://phishtank.org/phish_detail.php?phish_id=123",
                    }
                },
            )
        ]
    )

    result = check_phishtank(
        "https://bad.test/login",
        "url",
        client,
        app_settings=make_settings(phishtank_api_key="pt-key"),
    )

    assert result.status == "malicious"
    assert result.malicious is True
    assert result.severity == "high"
    assert result.reference == "https://phishtank.org/phish_detail.php?phish_id=123"
    assert client.calls[0][1] == PHISHTANK_CHECK_URL_ENDPOINT
    assert client.calls[0][2]["data"]["url"] == "https://bad.test/login"
    assert client.calls[0][2]["data"]["app_key"] == "pt-key"


def test_phishtank_database_record_without_verified_active_returns_unknown() -> None:
    client = FakeHttpClient([httpx.Response(200, json={"results": {"in_database": "true", "verified": "n", "valid": "n"}})])

    result = check_phishtank(
        "https://unknown.test/",
        "url",
        client,
        app_settings=make_settings(phishtank_api_key="pt-key"),
    )

    assert result.status == "unknown"
    assert result.malicious is False
    assert result.severity == "low"


def test_urlscan_search_malicious_result() -> None:
    client = FakeHttpClient(
        [
            httpx.Response(
                200,
                json={
                    "total": 1,
                    "results": [
                        {
                            "result": "https://urlscan.io/result/scan-id/",
                            "verdicts": {
                                "overall": {"malicious": True, "score": 90},
                                "urlscan": {"malicious": True, "score": 90},
                            },
                        }
                    ],
                },
            )
        ]
    )

    result = check_urlscan(
        "https://bad.test/",
        "url",
        client,
        app_settings=make_settings(urlscan_api_key="urlscan-key"),
    )

    assert result.status == "malicious"
    assert result.malicious is True
    assert result.severity == "critical"
    assert result.reference == "https://urlscan.io/result/scan-id/"
    assert client.calls[0][1] == URLSCAN_SEARCH_ENDPOINT
    assert client.calls[0][2]["headers"] == {"API-Key": "urlscan-key"}
    assert client.calls[0][2]["params"]["size"] == 10


def test_urlscan_search_clean_result() -> None:
    client = FakeHttpClient([httpx.Response(200, json={"total": 1, "results": [{"verdicts": {"overall": {"malicious": False}}}]})])

    result = check_urlscan(
        "clean.test",
        "domain",
        client,
        app_settings=make_settings(urlscan_api_key="urlscan-key"),
    )

    assert result.status == "clean"
    assert result.malicious is False
    assert "page.domain:clean.test" in client.calls[0][2]["params"]["q"]


def test_check_external_reputation_summarizes_configured_sources() -> None:
    client = FakeHttpClient(
        [
            httpx.Response(200, json={"query_status": "no_results"}),
            httpx.Response(200, json={"matches": [{"threatType": "MALWARE"}]}),
            httpx.Response(200, json={"data": {"attributes": {"last_analysis_stats": {"malicious": 0, "suspicious": 0}}}}),
            httpx.Response(200, json={"results": {"in_database": False}}),
            httpx.Response(200, json={"total": 0, "results": []}),
        ]
    )

    result = check_external_reputation(
        "entity-1",
        "https://bad.test/",
        "url",
        http_client=client,
        app_settings=make_settings(
            urlhaus_auth_key="urlhaus-key",
            google_safe_browsing_api_key="google-key",
            virustotal_api_key="vt-key",
            phishtank_api_key="pt-key",
            urlscan_api_key="urlscan-key",
        ),
    )

    assert result["entity_id"] == "entity-1"
    assert result["sources"]["urlhaus"]["status"] == "clean"
    assert result["sources"]["safe_browsing"]["status"] == "malicious"
    assert result["sources"]["virustotal"]["status"] == "clean"
    assert result["sources"]["phishtank"]["status"] == "clean"
    assert result["sources"]["urlscan"]["status"] == "clean"
    assert result["summary"]["malicious"] is True
    assert result["summary"]["malicious_sources"] == ["safe_browsing"]
    assert result["summary"]["highest_severity"] == "high"


def test_check_external_reputation_reports_missing_keys_without_http_calls() -> None:
    client = FakeHttpClient([])

    result = check_external_reputation(
        "entity-1",
        "https://unknown.test/",
        "url",
        http_client=client,
        app_settings=make_settings(),
    )

    assert result["sources"]["urlhaus"]["status"] == "not_configured"
    assert result["sources"]["safe_browsing"]["status"] == "not_configured"
    assert result["sources"]["virustotal"]["status"] == "not_configured"
    assert result["sources"]["phishtank"]["status"] == "not_configured"
    assert result["sources"]["urlscan"]["status"] == "not_configured"
    assert client.calls == []
