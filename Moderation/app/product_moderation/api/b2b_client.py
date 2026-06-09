import json
import logging
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


class B2BClientError(Exception):
    pass


class B2BClient:
    timeout_seconds = 5

    def _base_url(self) -> str:
        if not settings.B2B_URL:
            raise B2BClientError("B2B_URL is not configured")
        return settings.B2B_URL

    def get_product(self, product_id: str) -> dict[str, Any]:
        request = Request(
            f"{self._base_url()}/api/v1/products/{product_id}",
            method="GET",
            headers={"Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status >= 400:
                    raise B2BClientError(f"B2B product check failed: {response.status}")
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.exception("Failed to get product %s from B2B", product_id)
            raise B2BClientError("Failed to get product from B2B") from exc

    def send_moderation_event(
        self,
        product_id: str,
        status: str,
        *,
        hard_block: bool | None = None,
        blocking_reason: dict[str, Any] | None = None,
        field_reports: list[dict[str, Any]] | None = None,
    ) -> None:
        payload_data: dict[str, Any] = {
            "product_id": product_id,
            "status": status,
        }
        if hard_block is None and blocking_reason is None and field_reports is None:
            payload_data["idempotency_key"] = str(uuid.uuid4())
        if hard_block is not None:
            payload_data["hard_block"] = hard_block
        if blocking_reason is not None:
            payload_data["blocking_reason"] = blocking_reason
        if field_reports is not None:
            payload_data["field_reports"] = field_reports

        payload = json.dumps(payload_data).encode("utf-8")
        request = Request(
            f"{self._base_url()}/api/v1/events/moderation",
            method="POST",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Service-Key": settings.MOD_TO_B2B_KEY,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status >= 400:
                    raise B2BClientError(f"B2B moderation event failed: {response.status}")
        except (HTTPError, URLError, TimeoutError) as exc:
            logger.exception(
                "Failed to send moderation event for product %s to B2B", product_id
            )
            raise B2BClientError("Failed to send moderation event to B2B") from exc
