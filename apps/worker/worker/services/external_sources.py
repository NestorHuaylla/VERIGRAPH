from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from worker.config import WorkerSettings, settings


URLHAUS_URL_ENDPOINT = "https://urlhaus-api.abuse.ch/v1/url/"
URLHAUS_HOST_ENDPOINT = "https://urlhaus-api.abuse.ch/v1/host/"
SAFE_BROWSING_ENDPOINT = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
VIRUSTOTAL_API_URL = "https://www.virustotal.com/api/v3"
PHISHTANK_CHECK_URL_ENDPOINT = "http://checkurl.dev.phishtank.com/checkurl/"
URLSCAN_SEARCH_ENDPOINT = "https://urlscan.io/api/v1/search/"

SAFE_BROWSING_THREAT_TYPES = [
    "MALWARE",
    "SOCIAL_ENGINEERING",
    "UNWANTED_SOFTWARE",
    "POTENTIALLY_HARMFUL_APPLICATION",
]


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        pass

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        pass


@dataclass(frozen=True)
class SourceResult:
    source: str
    status: str
    malicious: bool
    severity: str
    summary: str
    reference: str | None = None
    raw: dict[str, Any] | None = None


def check_external_reputation(
    entity_id: str,
    value: str,
    entity_type: str,
    *,
    http_client: HttpClient | None = None,
    app_settings: WorkerSettings = settings,
) -> dict[str, Any]:
    checked_at = datetime.now(UTC).isoformat()
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=15)

    try:
        results = [
            check_urlhaus(value, entity_type, client, app_settings=app_settings),
            check_google_safe_browsing(value, entity_type, client, app_settings=app_settings),
            check_virustotal(value, entity_type, client, app_settings=app_settings),
            check_phishtank(value, entity_type, client, app_settings=app_settings),
            check_urlscan(value, entity_type, client, app_settings=app_settings),
        ]
    finally:
        if owns_client and isinstance(client, httpx.Client):
            client.close()

    return {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "value": value,
        "checked_at": checked_at,
        "sources": {result.source: asdict(result) for result in results},
        "summary": summarize_results(results),
    }


def check_urlhaus(
    value: str,
    entity_type: str,
    http_client: HttpClient,
    *,
    app_settings: WorkerSettings = settings,
) -> SourceResult:
    if not app_settings.urlhaus_auth_key:
        return not_configured_source("urlhaus", "URLHAUS_AUTH_KEY is not configured.")

    if entity_type == "url":
        endpoint = URLHAUS_URL_ENDPOINT
        data = {"url": value}
    elif entity_type == "domain":
        endpoint = URLHAUS_HOST_ENDPOINT
        data = {"host": value}
    else:
        return skipped_source("urlhaus", f"Entity type {entity_type} is not supported by this check.")

    try:
        response = http_client.post(
            endpoint,
            data=data,
            headers={"Auth-Key": app_settings.urlhaus_auth_key},
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return error_source("urlhaus", str(exc))

    query_status = str(payload.get("query_status") or payload.get("query_staus") or "")
    if query_status == "no_results":
        return SourceResult(
            source="urlhaus",
            status="clean",
            malicious=False,
            severity="none",
            summary="URLhaus did not return matches.",
            raw=minimize_payload(payload),
        )
    if query_status != "ok":
        return SourceResult(
            source="urlhaus",
            status="unknown",
            malicious=False,
            severity="unknown",
            summary=f"URLhaus returned query_status={query_status or 'missing'}.",
            raw=minimize_payload(payload),
        )

    url_status = str(payload.get("url_status") or "")
    url_count = payload.get("url_count")
    severity = "high" if url_status == "online" else "medium"
    if entity_type == "domain" and int_from_unknown(url_count) >= 5:
        severity = "high"

    return SourceResult(
        source="urlhaus",
        status="malicious",
        malicious=True,
        severity=severity,
        summary=build_urlhaus_summary(payload, entity_type),
        reference=payload.get("urlhaus_reference"),
        raw=minimize_payload(payload),
    )


def check_google_safe_browsing(
    value: str,
    entity_type: str,
    http_client: HttpClient,
    *,
    app_settings: WorkerSettings = settings,
) -> SourceResult:
    if not app_settings.google_safe_browsing_api_key:
        return not_configured_source("safe_browsing", "GOOGLE_SAFE_BROWSING_API_KEY is not configured.")

    if entity_type not in {"url", "domain"}:
        return skipped_source("safe_browsing", f"Entity type {entity_type} is not supported by this check.")

    url = value if entity_type == "url" else f"https://{value}"
    request_body = {
        "client": {
            "clientId": "verigraph",
            "clientVersion": "0.1.0",
        },
        "threatInfo": {
            "threatTypes": SAFE_BROWSING_THREAT_TYPES,
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url}],
        },
    }

    try:
        response = http_client.post(
            SAFE_BROWSING_ENDPOINT,
            params={"key": app_settings.google_safe_browsing_api_key},
            json=request_body,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return error_source("safe_browsing", str(exc))

    matches = payload.get("matches") or []
    if not matches:
        return SourceResult(
            source="safe_browsing",
            status="clean",
            malicious=False,
            severity="none",
            summary="Google Safe Browsing did not return matches.",
            raw=minimize_payload(payload),
        )

    threat_types = sorted({str(match.get("threatType")) for match in matches if match.get("threatType")})
    return SourceResult(
        source="safe_browsing",
        status="malicious",
        malicious=True,
        severity="high",
        summary=f"Google Safe Browsing matched: {', '.join(threat_types) or 'unsafe URL'}.",
        raw=minimize_payload(payload),
    )


def check_virustotal(
    value: str,
    entity_type: str,
    http_client: HttpClient,
    *,
    app_settings: WorkerSettings = settings,
) -> SourceResult:
    if not app_settings.virustotal_api_key:
        return not_configured_source("virustotal", "VIRUSTOTAL_API_KEY is not configured.")

    if entity_type == "url":
        resource_id = virustotal_url_id(value)
        endpoint = f"{VIRUSTOTAL_API_URL}/urls/{resource_id}"
        reference = f"https://www.virustotal.com/gui/url/{resource_id}"
    elif entity_type == "domain":
        domain = normalize_domain_value(value)
        if not domain:
            return skipped_source("virustotal", "Domain value could not be parsed.")
        endpoint = f"{VIRUSTOTAL_API_URL}/domains/{domain}"
        reference = f"https://www.virustotal.com/gui/domain/{domain}"
    else:
        return skipped_source("virustotal", f"Entity type {entity_type} is not supported by this check.")

    try:
        response = http_client.get(
            endpoint,
            headers={"x-apikey": app_settings.virustotal_api_key},
        )
        if response.status_code == 404:
            return SourceResult(
                source="virustotal",
                status="clean",
                malicious=False,
                severity="none",
                summary="VirusTotal did not return a known report for this indicator.",
                reference=reference,
                raw={"status_code": 404},
            )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return error_source("virustotal", str(exc))

    stats = extract_virustotal_stats(payload)
    malicious_count = int_from_unknown(stats.get("malicious"))
    suspicious_count = int_from_unknown(stats.get("suspicious"))
    if malicious_count == 0 and suspicious_count == 0:
        return SourceResult(
            source="virustotal",
            status="clean",
            malicious=False,
            severity="none",
            summary="VirusTotal engines did not mark this indicator as malicious.",
            reference=reference,
            raw=minimize_payload(payload),
        )

    severity = "critical" if malicious_count >= 5 else "high" if malicious_count > 0 else "medium"
    return SourceResult(
        source="virustotal",
        status="malicious",
        malicious=True,
        severity=severity,
        summary=(
            "VirusTotal matched this indicator: "
            f"{malicious_count} malicious, {suspicious_count} suspicious engines."
        ),
        reference=reference,
        raw=minimize_payload(payload),
    )


def check_phishtank(
    value: str,
    entity_type: str,
    http_client: HttpClient,
    *,
    app_settings: WorkerSettings = settings,
) -> SourceResult:
    if not app_settings.phishtank_api_key:
        return not_configured_source("phishtank", "PHISHTANK_API_KEY is not configured.")

    if entity_type != "url":
        return skipped_source("phishtank", f"Entity type {entity_type} is not supported by this check.")

    try:
        response = http_client.post(
            PHISHTANK_CHECK_URL_ENDPOINT,
            data={"url": value, "format": "json", "app_key": app_settings.phishtank_api_key},
            headers={"User-Agent": "verigraph/0.1.0"},
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return error_source("phishtank", str(exc))

    results = payload.get("results") or {}
    in_database = truthy_external_flag(results.get("in_database"))
    verified = truthy_external_flag(results.get("verified"))
    valid = truthy_external_flag(results.get("valid"))
    reference = results.get("phish_detail_page")

    if not in_database:
        return SourceResult(
            source="phishtank",
            status="clean",
            malicious=False,
            severity="none",
            summary="PhishTank did not return a database match.",
            raw=minimize_payload(payload),
        )

    if verified and valid:
        return SourceResult(
            source="phishtank",
            status="malicious",
            malicious=True,
            severity="high",
            summary=f"PhishTank lists this URL as a verified active phish #{results.get('phish_id')}.",
            reference=reference,
            raw=minimize_payload(payload),
        )

    return SourceResult(
        source="phishtank",
        status="unknown",
        malicious=False,
        severity="low",
        summary="PhishTank has a record for this URL, but it is not both verified and active.",
        reference=reference,
        raw=minimize_payload(payload),
    )


def check_urlscan(
    value: str,
    entity_type: str,
    http_client: HttpClient,
    *,
    app_settings: WorkerSettings = settings,
) -> SourceResult:
    if not app_settings.urlscan_api_key:
        return not_configured_source("urlscan", "URLSCAN_API_KEY is not configured.")

    if entity_type == "url":
        query = f'task.url.keyword:"{escape_urlscan_query_value(value)}" OR page.url.keyword:"{escape_urlscan_query_value(value)}"'
    elif entity_type == "domain":
        domain = normalize_domain_value(value)
        if not domain:
            return skipped_source("urlscan", "Domain value could not be parsed.")
        query = f"task.domain:{domain} OR page.domain:{domain}"
    else:
        return skipped_source("urlscan", f"Entity type {entity_type} is not supported by this check.")

    try:
        response = http_client.get(
            URLSCAN_SEARCH_ENDPOINT,
            params={"q": query, "size": 10},
            headers={"API-Key": app_settings.urlscan_api_key},
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return error_source("urlscan", str(exc))

    results = payload.get("results") or []
    malicious_results = [result for result in results if urlscan_result_is_malicious(result)]
    if not malicious_results:
        return SourceResult(
            source="urlscan",
            status="clean",
            malicious=False,
            severity="none",
            summary=f"urlscan.io returned {len(results)} archived scans and no malicious verdict.",
            raw=minimize_payload(payload),
        )

    max_score = max(urlscan_result_score(result) for result in malicious_results)
    severity = "critical" if max_score >= 80 else "high"
    return SourceResult(
        source="urlscan",
        status="malicious",
        malicious=True,
        severity=severity,
        summary=f"urlscan.io found {len(malicious_results)} archived malicious scan(s), max score {max_score}.",
        reference=malicious_results[0].get("result"),
        raw=minimize_payload(payload),
    )


def build_urlhaus_summary(payload: dict[str, Any], entity_type: str) -> str:
    if entity_type == "domain":
        url_count = payload.get("url_count") or len(payload.get("urls") or [])
        return f"URLhaus has observed {url_count} URLs for this host."

    threat = payload.get("threat") or "malware"
    status = payload.get("url_status") or "unknown"
    host = payload.get("host") or host_from_url(str(payload.get("url") or ""))
    return f"URLhaus matched {threat} on {host or 'the URL'} with status {status}."


def summarize_results(results: list[SourceResult]) -> dict[str, Any]:
    malicious_sources = [result.source for result in results if result.malicious]
    checked_sources = [
        result.source
        for result in results
        if result.status not in {"not_configured", "not_implemented", "skipped"}
    ]
    highest_severity = highest_result_severity(results)
    return {
        "malicious": bool(malicious_sources),
        "malicious_sources": malicious_sources,
        "checked_sources": checked_sources,
        "highest_severity": highest_severity,
    }


def highest_result_severity(results: list[SourceResult]) -> str:
    order = {"none": 0, "unknown": 1, "low": 2, "medium": 3, "high": 4, "critical": 5}
    selected = "none"
    for result in results:
        if order.get(result.severity, 0) > order[selected]:
            selected = result.severity
    return selected


def not_configured_source(source: str, summary: str) -> SourceResult:
    return SourceResult(
        source=source,
        status="not_configured",
        malicious=False,
        severity="none",
        summary=summary,
    )


def not_implemented_source(source: str) -> SourceResult:
    return SourceResult(
        source=source,
        status="not_implemented",
        malicious=False,
        severity="none",
        summary=f"{source} integration is declared but not implemented yet.",
    )


def skipped_source(source: str, summary: str) -> SourceResult:
    return SourceResult(
        source=source,
        status="skipped",
        malicious=False,
        severity="none",
        summary=summary,
    )


def error_source(source: str, summary: str) -> SourceResult:
    return SourceResult(
        source=source,
        status="error",
        malicious=False,
        severity="unknown",
        summary=summary,
    )


def minimize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "query_status",
        "query_staus",
        "data",
        "id",
        "urlhaus_reference",
        "url",
        "url_status",
        "host",
        "url_count",
        "date_added",
        "last_online",
        "threat",
        "blacklists",
        "tags",
        "matches",
        "results",
        "total",
        "has_more",
    }
    return {key: value for key, value in payload.items() if key in allowed_keys}


def virustotal_url_id(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def extract_virustotal_stats(payload: dict[str, Any]) -> dict[str, Any]:
    attributes = ((payload.get("data") or {}).get("attributes") or {})
    return attributes.get("last_analysis_stats") or {}


def normalize_domain_value(value: str) -> str:
    parsed_host = host_from_url(value)
    return (parsed_host or value).strip().lower().removeprefix("www.")


def truthy_external_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def escape_urlscan_query_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return escaped


def urlscan_result_is_malicious(result: dict[str, Any]) -> bool:
    verdicts = result.get("verdicts") or {}
    if truthy_external_flag(verdicts.get("malicious")):
        return True

    for verdict in verdicts.values():
        if isinstance(verdict, dict) and truthy_external_flag(verdict.get("malicious")):
            return True
    return False


def urlscan_result_score(result: dict[str, Any]) -> int:
    verdicts = result.get("verdicts") or {}
    scores = []
    if "score" in verdicts:
        scores.append(int_from_unknown(verdicts.get("score")))
    for verdict in verdicts.values():
        if isinstance(verdict, dict) and "score" in verdict:
            scores.append(int_from_unknown(verdict.get("score")))
    return max(scores) if scores else 100


def host_from_url(value: str) -> str:
    try:
        return urlparse(value).hostname or ""
    except ValueError:
        return ""


def int_from_unknown(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
