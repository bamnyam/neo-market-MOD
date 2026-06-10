import uuid

import pytest
from django.test import override_settings
from django.urls import reverse

from app.product_moderation.models import ProductModeration


@pytest.mark.django_db
@override_settings(B2B_TO_MOD_KEY="b2b-to-mod")
def test_product_event_contract_accepts_product_edited(
    api_client,
    create_moderation,
):
    moderation = create_moderation(
        status=ProductModeration.Status.APPROVED,
        json_after={"title": "Before"},
        total_active_quantity=1,
    )
    api_client.credentials(HTTP_X_SERVICE_KEY="b2b-to-mod")

    response = api_client.post(
        "/api/v1/b2b/events",
        {
            "event_type": "PRODUCT_EDITED",
            "idempotency_key": str(uuid.uuid4()),
            "occurred_at": "2026-03-15T14:30:00.000Z",
            "payload": {
                "product_id": str(moderation.product_id),
                "seller_id": str(moderation.seller_id),
            },
        },
        format="json",
    )

    assert response.status_code == 202
    assert reverse("product-event") == "/api/v1/b2b/events"
    moderation.refresh_from_db()
    assert moderation.status == ProductModeration.Status.PENDING


@pytest.mark.django_db
@override_settings(B2B_TO_MOD_KEY="b2b-to-mod")
def test_product_event_rejects_duplicate_idempotency_key(
    api_client,
    create_moderation,
):
    moderation = create_moderation(status=ProductModeration.Status.HARD_BLOCKED)
    idempotency_key = str(uuid.uuid4())
    api_client.credentials(HTTP_X_SERVICE_KEY="b2b-to-mod")
    payload = {
        "event_type": "PRODUCT_EDITED",
        "idempotency_key": idempotency_key,
        "occurred_at": "2026-03-15T14:30:00.000Z",
        "payload": {
            "product_id": str(moderation.product_id),
            "seller_id": str(moderation.seller_id),
        },
    }

    first_response = api_client.post(reverse("product-event"), payload, format="json")
    second_response = api_client.post(reverse("product-event"), payload, format="json")

    assert first_response.status_code == 202
    assert second_response.status_code == 409
    assert second_response.json() == {
        "code": "IDEMPOTENCY_KEY_CONFLICT",
        "message": "Idempotency key already processed",
    }
