import uuid

import pytest
from django.urls import reverse

from app.product_moderation.models import (
    ProductModeration,
    ProductModerationFieldReport,
)
from app.product_moderation.views import DeclineProductView


@pytest.mark.django_db
def test_decline_product_success(
    api_client,
    create_moderation,
    create_blocking_reason,
    successful_decline_b2b_client_class,
):
    moderation = create_moderation()
    reason = create_blocking_reason()
    stale_report = ProductModerationFieldReport.objects.create(
        product_moderation=moderation,
        field_name=ProductModerationFieldReport.FieldName.TITLE,
        comment="Old issue",
    )
    response = api_client.post(
        reverse("block-ticket", kwargs={"ticket_id": moderation.id}),
        {
            "blocking_reason_ids": [str(reason.id)],
            "field_reports": [
                {
                    "field_path": "description",
                    "message": "Текст описания скопирован с другого товара",
                    "severity": "ERROR",
                },
                {
                    "field_path": "sku_price",
                    "message": "Цена подозрительно низкая для данного бренда",
                    "severity": "WARNING",
                },
            ],
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(moderation.id)
    assert body["product_id"] == str(moderation.product_id)
    assert body["seller_id"] == str(moderation.seller_id)
    assert body["kind"] == "CREATE"
    assert body["status"] == ProductModeration.Status.BLOCKED
    assert body["queue_priority"] == moderation.queue_priority
    assert body["created_at"] is not None

    moderation.refresh_from_db()
    assert moderation.status == ProductModeration.Status.BLOCKED
    assert moderation.date_moderation is not None
    assert moderation.blocking_reason == reason
    assert moderation.moderator_comment is None
    assert not ProductModerationFieldReport.objects.filter(id=stale_report.id).exists()

    reports = list(moderation.field_reports.order_by("date_created"))
    assert len(reports) == 2
    assert reports[0].field_name == ProductModerationFieldReport.FieldName.DESCRIPTION
    assert reports[0].field_path == "description"
    assert reports[0].message == "Текст описания скопирован с другого товара"
    assert reports[0].severity == "ERROR"
    assert reports[1].field_name == ProductModerationFieldReport.FieldName.SKU_PRICE
    assert reports[1].field_path == "sku_price"
    assert reports[1].message == "Цена подозрительно низкая для данного бренда"
    assert reports[1].severity == "WARNING"

    assert successful_decline_b2b_client_class.events == [
        {
            "product_id": str(moderation.product_id),
            "event_type": ProductModeration.Status.BLOCKED,
        }
    ]


@pytest.mark.django_db
def test_decline_product_not_found(api_client, create_blocking_reason):
    reason = create_blocking_reason()

    response = api_client.post(
        reverse("block-ticket", kwargs={"ticket_id": uuid.uuid4()}),
        {
            "blocking_reason_ids": [str(reason.id)],
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(uuid.uuid4()),
    )

    assert response.status_code == 404
    assert response.json() == {
        "code": "TICKET_NOT_FOUND",
        "message": "Ticket not found",
    }


@pytest.mark.django_db
def test_decline_product_rejects_hard_blocked_status(
    api_client,
    create_moderation,
    create_blocking_reason,
):
    moderation = create_moderation(status=ProductModeration.Status.HARD_BLOCKED)
    reason = create_blocking_reason()

    response = api_client.post(
        reverse("block-ticket", kwargs={"ticket_id": moderation.id}),
        {
            "blocking_reason_ids": [str(reason.id)],
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "TICKET_PERMANENTLY_BLOCKED",
        "message": "Product is permanently blocked",
    }


@pytest.mark.django_db
def test_decline_product_rejects_other_moderator(
    api_client,
    create_moderation,
    create_blocking_reason,
):
    moderation = create_moderation()
    reason = create_blocking_reason()

    response = api_client.post(
        reverse("block-ticket", kwargs={"ticket_id": moderation.id}),
        {
            "blocking_reason_ids": [str(reason.id)],
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(uuid.uuid4()),
    )

    assert response.status_code == 403
    assert response.json() == {
        "code": "TICKET_NOT_ASSIGNED_TO_YOU",
        "message": "This ticket is not assigned to you",
    }


@pytest.mark.django_db
def test_decline_product_rejects_not_in_review(
    api_client,
    create_moderation,
    create_blocking_reason,
):
    moderation = create_moderation(status=ProductModeration.Status.PENDING)
    reason = create_blocking_reason()

    response = api_client.post(
        reverse("block-ticket", kwargs={"ticket_id": moderation.id}),
        {
            "blocking_reason_ids": [str(reason.id)],
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "TICKET_WRONG_STATUS",
        "message": "Ticket is not in review status",
    }


@pytest.mark.django_db
def test_decline_product_rejects_unknown_blocking_reason(api_client, create_moderation):
    moderation = create_moderation()

    response = api_client.post(
        reverse("block-ticket", kwargs={"ticket_id": moderation.id}),
        {
            "blocking_reason_ids": [str(uuid.uuid4())],
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "BLOCKING_REASON_NOT_FOUND",
        "message": "Blocking reason not found",
    }


@pytest.mark.django_db
def test_decline_product_uses_hard_block_reason(
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
    assert response.json()["status"] == ProductModeration.Status.HARD_BLOCKED
    moderation.refresh_from_db()
    assert moderation.status == ProductModeration.Status.HARD_BLOCKED
    assert successful_decline_b2b_client_class.events[0]["event_type"] == (
        ProductModeration.Status.BLOCKED
    )


@pytest.mark.django_db
def test_decline_product_uses_empty_field_reports_by_default(
    api_client,
    create_moderation,
    create_blocking_reason,
    successful_decline_b2b_client_class,
):
    moderation = create_moderation()
    reason = create_blocking_reason()
    ProductModerationFieldReport.objects.create(
        product_moderation=moderation,
        field_name=ProductModerationFieldReport.FieldName.TITLE,
        comment="Old issue",
    )

    response = api_client.post(
        reverse("block-ticket", kwargs={"ticket_id": moderation.id}),
        {
            "blocking_reason_ids": [str(reason.id)],
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 200

    moderation.refresh_from_db()
    assert moderation.field_reports.count() == 0


@pytest.mark.django_db
def test_decline_product_rolls_back_when_event_fails(
    api_client,
    create_moderation,
    create_blocking_reason,
    event_error_decline_b2b_client_class,
):
    DeclineProductView.b2b_client_class = event_error_decline_b2b_client_class
    moderation = create_moderation()
    reason = create_blocking_reason()

    response = api_client.post(
        reverse("block-ticket", kwargs={"ticket_id": moderation.id}),
        {
            "blocking_reason_ids": [str(reason.id)],
            "field_reports": [
                {
                    "field_path": "title",
                    "message": "Wrong title",
                    "severity": "ERROR",
                }
            ],
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 500

    moderation.refresh_from_db()
    assert moderation.status == ProductModeration.Status.IN_REVIEW
    assert moderation.date_moderation is None
    assert moderation.blocking_reason is None
    assert moderation.moderator_comment is None
    assert moderation.field_reports.count() == 0
