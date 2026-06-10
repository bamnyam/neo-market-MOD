import uuid

import pytest
from django.test import override_settings
from django.urls import reverse

from app.product_moderation.models import (
    ProductModeration,
    ProductModerationFieldReport,
)


@pytest.mark.django_db
def test_hard_block_transitions_to_terminal_and_emits_event(
    api_client,
    create_moderation,
    create_blocking_reason,
    successful_decline_b2b_client_class,
):
    moderation = create_moderation()
    reason = create_blocking_reason(
        title="Контрафактный товар",
        hard_block=True,
    )

    response = api_client.post(
        reverse("block-ticket", kwargs={"ticket_id": moderation.id}),
        {
            "blocking_reason_ids": [str(reason.id)],
            "field_reports": [],
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 200
    assert response.json()["status"] == ProductModeration.Status.HARD_BLOCKED

    moderation.refresh_from_db()
    assert moderation.status == ProductModeration.Status.HARD_BLOCKED
    assert moderation.date_moderation is not None
    assert moderation.blocking_reason == reason
    assert moderation.moderator_comment is None
    assert successful_decline_b2b_client_class.events == [
        {
            "product_id": str(moderation.product_id),
            "event_type": ProductModeration.Status.BLOCKED,
        }
    ]


@pytest.mark.django_db
def test_hard_block_decline_requires_service_key(
    api_client,
    create_moderation,
    create_blocking_reason,
    successful_decline_b2b_client_class,
):
    moderation = create_moderation()
    reason = create_blocking_reason(hard_block=True)
    api_client.credentials()

    response = api_client.post(
        reverse("block-ticket", kwargs={"ticket_id": moderation.id}),
        {
            "blocking_reason_ids": [str(reason.id)],
            "field_reports": [],
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 401
    assert response.json() == {
        "code": "UNAUTHORIZED",
        "message": "Invalid service key",
    }
    moderation.refresh_from_db()
    assert moderation.status == ProductModeration.Status.IN_REVIEW
    assert successful_decline_b2b_client_class.events == []


@pytest.mark.django_db
def test_hard_block_event_carries_hard_block_true(
    api_client,
    create_moderation,
    create_blocking_reason,
    successful_decline_b2b_client_class,
):
    moderation = create_moderation()
    reason = create_blocking_reason(hard_block=True)

    response = api_client.post(
        reverse("block-ticket", kwargs={"ticket_id": moderation.id}),
        {
            "blocking_reason_ids": [str(reason.id)],
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 200
    event = successful_decline_b2b_client_class.events[0]
    assert event["event_type"] == ProductModeration.Status.BLOCKED


@pytest.mark.django_db
def test_any_modify_on_hard_blocked_returns_403(
    api_client,
    create_moderation,
    create_blocking_reason,
):
    moderation = create_moderation(status=ProductModeration.Status.HARD_BLOCKED)
    reason = create_blocking_reason()

    approve_response = api_client.post(
        reverse("approve-product", kwargs={"ticket_id": moderation.id}),
        {},
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )
    decline_response = api_client.post(
        reverse("block-ticket", kwargs={"ticket_id": moderation.id}),
        {
            "blocking_reason_ids": [str(reason.id)],
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert approve_response.status_code == 409
    assert decline_response.status_code == 409
    moderation.refresh_from_db()
    assert moderation.status == ProductModeration.Status.HARD_BLOCKED


@pytest.mark.django_db
@override_settings(B2B_TO_MOD_KEY="b2b-to-mod")
def test_edited_event_on_hard_blocked_is_ignored(api_client, create_moderation):
    moderation = create_moderation(
        status=ProductModeration.Status.HARD_BLOCKED,
        json_after={"title": "Before"},
        total_active_quantity=7,
    )
    api_client.credentials(HTTP_X_SERVICE_KEY="b2b-to-mod")

    response = api_client.post(
        reverse("product-event"),
        {
            "event": "EDITED",
            "product_id": str(moderation.product_id),
            "seller_id": str(moderation.seller_id),
            "date": "2026-03-15T14:30:00.000Z",
        },
        format="json",
    )

    assert response.status_code == 200
    moderation.refresh_from_db()
    assert moderation.status == ProductModeration.Status.HARD_BLOCKED
    assert moderation.json_after == {"title": "Before"}
    assert moderation.total_active_quantity == 7


@pytest.mark.django_db
@override_settings(B2B_TO_MOD_KEY="b2b-to-mod")
def test_deleted_event_removes_hard_blocked(api_client, create_moderation):
    moderation = create_moderation(status=ProductModeration.Status.HARD_BLOCKED)
    ProductModerationFieldReport.objects.create(
        product_moderation=moderation,
        field_name=ProductModerationFieldReport.FieldName.TITLE,
        comment="Counterfeit title",
    )
    api_client.credentials(HTTP_X_SERVICE_KEY="b2b-to-mod")

    response = api_client.post(
        reverse("product-event"),
        {
            "event": "DELETED",
            "product_id": str(moderation.product_id),
            "seller_id": str(uuid.uuid4()),
            "date": "2026-03-15T14:30:00.000Z",
        },
        format="json",
    )

    assert response.status_code == 200
    assert not ProductModeration.objects.filter(id=moderation.id).exists()
    assert not ProductModerationFieldReport.objects.filter(
        product_moderation_id=moderation.id
    ).exists()
