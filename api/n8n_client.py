from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

import requests


@dataclass(frozen=True)
class N8NWebhookConfig:
    base_url: str
    webhook_edi_tracking: str = "/webhook/edi-tracking"


class N8NClient:
    """HTTP client for calling n8n webhooks."""

    def __init__(self, config: Optional[N8NWebhookConfig] = None, timeout_s: Optional[int] = None):
        if config is None:
            config = N8NWebhookConfig(
                base_url=(os.getenv("N8N_BASE_URL", "https://n8ndev.nitco.io") or "").rstrip("/"),
                webhook_edi_tracking=os.getenv("N8N_WEBHOOK_EDI_TRACKING", "/webhook/edi-tracking"),
            )
        self.config = config
        if timeout_s is None:
            raw_timeout = (os.getenv("N8N_TIMEOUT_S", "") or "").strip()
            if raw_timeout.isdigit():
                timeout_s = int(raw_timeout)
            else:
                timeout_s = 90
        self.timeout_s = timeout_s
        self._session = requests.Session()

    def _abs_url(self, path: str) -> str:
        base = self.config.base_url.rstrip("/")
        return f"{base}/{path.lstrip('/')}"

    def _json_or_text(self, resp: requests.Response) -> Dict[str, Any]:
        if not resp.content:
            return {}
        try:
            payload = resp.json()
            if isinstance(payload, dict):
                return payload
            return {"data": payload}
        except ValueError:
            return {"text": resp.text}

    def _post_json(self, url: str, payload: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        resp = self._session.post(url, json=payload, timeout=self.timeout_s)
        resp.raise_for_status()
        return self._json_or_text(resp)

    def edi_document_tracking(
        self,
        document_id: str,
        *,
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetches EDI document tracking data (output + actual) via webhook."""
        url = (webhook_url or os.getenv("N8N_EDI_TRACKING_URL", "") or "").strip()
        payload: Dict[str, Any] = {
            "document_id": document_id,
            "doc_id": document_id,
            "documentId": document_id,
        }
        if url:
            return self._post_json(url, payload)
        return self._post_json(self._abs_url(self.config.webhook_edi_tracking), payload)
