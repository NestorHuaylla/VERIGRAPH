from __future__ import annotations

from typing import Any

import httpx

from worker.config import settings


def post_external_reputation_result(
    entity_id: str,
    reputation_result: dict[str, Any],
    *,
    task_id: str | None = None,
) -> dict[str, Any]:
    if not settings.worker_api_token:
        return {"status": "skipped", "reason": "WORKER_API_TOKEN is not configured."}

    checks = []
    for source_result in reputation_result.get("sources", {}).values():
        if source_result.get("status") in {"not_configured", "not_implemented", "skipped"}:
            continue
        checks.append(
            {
                "source": source_result["source"],
                "status": source_result["status"],
                "malicious": source_result["malicious"],
                "severity": source_result["severity"],
                "summary": source_result["summary"],
                "reference": source_result.get("reference"),
                "raw": source_result.get("raw") or {},
                "metadata": {"checked_at": reputation_result.get("checked_at")},
            }
        )

    if not checks:
        return {"status": "skipped", "reason": "No completed source checks to persist."}

    payload = {
        "checks": checks,
        "metadata": {
            "task_id": task_id,
            "entity_type": reputation_result.get("entity_type"),
            "value": reputation_result.get("value"),
            "summary": reputation_result.get("summary", {}),
        },
    }
    url = f"{settings.api_base_url.rstrip('/')}/api/v1/entities/{entity_id}/external-reputation"
    with httpx.Client(timeout=15) as client:
        response = client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.worker_api_token}"},
        )
        response.raise_for_status()
        return response.json()
