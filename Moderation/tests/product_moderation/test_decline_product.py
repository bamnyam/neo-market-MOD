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
    sku_id = uuid.uuid4()

    response = api_client.post(
        reverse("decline-product", kwargs={"product_id": moderation.product_id}),
        {
            "blocking_reason_id": str(reason.id),
            "moderator_comment": "Описание и фото не соответствуют товару",
            "field_reports": [
                {
                    "field_name": "description",
                    "sku_id": None,
                    "comment": "Текст описания скопирован с другого товара",
                },
                {
                    "field_name": "skuPrice",
                    "sku_id": str(sku_id),
                    "comment": "Цена подозрительно низкая для данного бренда",
                },
            ],
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 200
    assert response.json() == {
        "product_id": str(moderation.product_id),
        "status": ProductModeration.Status.BLOCKED,
    }

    moderation.refresh_from_db()
    assert moderation.status == ProductModeration.Status.BLOCKED
    assert moderation.date_moderation is not None
    assert moderation.blocking_reason == reason
    assert moderation.moderator_comment == "Описание и фото не соответствуют товару"
    assert not ProductModerationFieldReport.objects.filter(id=stale_report.id).exists()

    reports = list(moderation.field_reports.order_by("date_created"))
    assert len(reports) == 2
    assert reports[0].field_name == ProductModerationFieldReport.FieldName.DESCRIPTION
    assert reports[0].sku_id is None
    assert reports[1].field_name == ProductModerationFieldReport.FieldName.SKU_PRICE
    assert reports[1].sku_id == sku_id

    assert successful_decline_b2b_client_class.events == [
        {
            "product_id": str(moderation.product_id),
            "status": ProductModeration.Status.BLOCKED,
            "hard_block": False,
            "blocking_reason": {
                "id": str(reason.id),
                "title": reason.title,
                "comment": "Описание и фото не соответствуют товару",
            },
            "field_reports": [
                {
                    "field_name": "description",
                    "sku_id": None,
                    "comment": "Текст описания скопирован с другого товара",
                },
                {
                    "field_name": "sku_price",
                    "sku_id": str(sku_id),
                    "comment": "Цена подозрительно низкая для данного бренда",
                },
            ],
        }
    ]


@pytest.mark.django_db
def test_decline_product_not_found(api_client, create_blocking_reason):
    reason = create_blocking_reason()

    response = api_client.post(
        reverse("decline-product", kwargs={"product_id": uuid.uuid4()}),
        {
            "blocking_reason_id": str(reason.id),
            "moderator_comment": "Bad product",
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(uuid.uuid4()),
    )

    assert response.status_code == 404
    assert response.json() == {"error": "Product not found in moderation queue"}


@pytest.mark.django_db
def test_decline_product_rejects_hard_blocked_status(
    api_client,
    create_moderation,
    create_blocking_reason,
):
    moderation = create_moderation(status=ProductModeration.Status.HARD_BLOCKED)
    reason = create_blocking_reason()

    response = api_client.post(
        reverse("decline-product", kwargs={"product_id": moderation.product_id}),
        {
            "blocking_reason_id": str(reason.id),
            "moderator_comment": "Bad product",
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 409
    assert response.json() == {"error": "Product is permanently blocked"}


@pytest.mark.django_db
def test_decline_product_rejects_other_moderator(
    api_client,
    create_moderation,
    create_blocking_reason,
):
    moderation = create_moderation()
    reason = create_blocking_reason()

    response = api_client.post(
        reverse("decline-product", kwargs={"product_id": moderation.product_id}),
        {
            "blocking_reason_id": str(reason.id),
            "moderator_comment": "Bad product",
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(uuid.uuid4()),
    )

    assert response.status_code == 403
    assert response.json() == {"error": "This moderation card is not assigned to you"}


@pytest.mark.django_db
def test_decline_product_rejects_not_in_review(
    api_client,
    create_moderation,
    create_blocking_reason,
):
    moderation = create_moderation(status=ProductModeration.Status.PENDING)
    reason = create_blocking_reason()

    response = api_client.post(
        reverse("decline-product", kwargs={"product_id": moderation.product_id}),
        {
            "blocking_reason_id": str(reason.id),
            "moderator_comment": "Bad product",
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 409
    assert response.json() == {"error": "Product is not in review"}


@pytest.mark.django_db
def test_decline_product_rejects_unknown_blocking_reason(api_client, create_moderation):
    moderation = create_moderation()

    response = api_client.post(
        reverse("decline-product", kwargs={"product_id": moderation.product_id}),
        {
            "blocking_reason_id": str(uuid.uuid4()),
            "moderator_comment": "Bad product",
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 400
    assert response.json() == {"error": "Blocking reason not found"}


@pytest.mark.django_db
def test_decline_product_rejects_hard_block_reason(
    api_client,
    create_moderation,
    create_blocking_reason,
):
    moderation = create_moderation()
    reason = create_blocking_reason(hard_block=True)

    response = api_client.post(
        reverse("decline-product", kwargs={"product_id": moderation.product_id}),
        {
            "blocking_reason_id": str(reason.id),
            "moderator_comment": "Bad product",
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 400
    assert response.json() == {"error": "Blocking reason requires hard block flow"}


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
        reverse("decline-product", kwargs={"product_id": moderation.product_id}),
        {
            "blocking_reason_id": str(reason.id),
            "moderator_comment": "Bad product",
        },
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 200

    moderation.refresh_from_db()
    assert moderation.field_reports.count() == 0
    assert successful_decline_b2b_client_class.events[0]["field_reports"] == []


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
        reverse("decline-product", kwargs={"product_id": moderation.product_id}),
        {
            "blocking_reason_id": str(reason.id),
            "moderator_comment": "Bad product",
            "field_reports": [
                {
                    "field_name": "title",
                    "comment": "Wrong title",
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
