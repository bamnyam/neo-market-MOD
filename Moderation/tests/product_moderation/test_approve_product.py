import uuid

import pytest
from django.urls import reverse

from app.product_moderation.models import (
    ProductModeration,
    ProductModerationFieldReport,
)
from app.product_moderation.views import ApproveProductView


@pytest.mark.django_db
def test_approve_product_success(api_client, create_moderation):
    moderation = create_moderation(blocking_reason_id=None)
    ProductModerationFieldReport.objects.create(
        product_moderation=moderation,
        field_name=ProductModerationFieldReport.FieldName.TITLE,
        comment="Fix title",
    )

    response = api_client.post(
        reverse("approve-product", kwargs={"ticket_id": moderation.id}),
        {"comment": "Product meets requirements"},
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(moderation.id)
    assert body["product_id"] == str(moderation.product_id)
    assert body["seller_id"] == str(moderation.seller_id)
    assert body["kind"] == "CREATE"
    assert body["status"] == ProductModeration.Status.APPROVED
    assert body["queue_priority"] == moderation.queue_priority
    assert body["assigned_moderator_id"] == str(moderation.moderator_id)
    assert body["decision_at"] is not None
    assert body["created_at"] is not None

    moderation.refresh_from_db()
    assert moderation.status == ProductModeration.Status.APPROVED
    assert moderation.date_moderation is not None
    assert moderation.moderator_comment == "Product meets requirements"
    assert moderation.blocking_reason_id is None
    assert moderation.field_reports.count() == 0


@pytest.mark.django_db
def test_approve_product_not_found(api_client):
    response = api_client.post(
        reverse("approve-product", kwargs={"ticket_id": uuid.uuid4()}),
        {},
        format="json",
        HTTP_X_MODERATOR_ID=str(uuid.uuid4()),
    )

    assert response.status_code == 404
    assert response.json() == {
        "code": "TICKET_NOT_FOUND",
        "message": "Ticket not found",
    }


@pytest.mark.django_db
def test_approve_product_rejects_hard_blocked(api_client, create_moderation):
    moderation = create_moderation(status=ProductModeration.Status.HARD_BLOCKED)

    response = api_client.post(
        reverse("approve-product", kwargs={"ticket_id": moderation.id}),
        {},
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "TICKET_PERMANENTLY_BLOCKED",
        "message": "Product is permanently blocked",
    }


@pytest.mark.django_db
def test_approve_product_rejects_not_in_review(api_client, create_moderation):
    moderation = create_moderation(status=ProductModeration.Status.PENDING)

    response = api_client.post(
        reverse("approve-product", kwargs={"ticket_id": moderation.id}),
        {},
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "TICKET_WRONG_STATUS",
        "message": "Ticket is not in review status",
    }


@pytest.mark.django_db
def test_approve_product_rejects_other_moderator(api_client, create_moderation):
    moderation = create_moderation()

    response = api_client.post(
        reverse("approve-product", kwargs={"ticket_id": moderation.id}),
        {},
        format="json",
        HTTP_X_MODERATOR_ID=str(uuid.uuid4()),
    )

    assert response.status_code == 403
    assert response.json() == {
        "code": "TICKET_NOT_ASSIGNED_TO_YOU",
        "message": "This ticket is not assigned to you",
    }


@pytest.mark.django_db
def test_approve_product_rejects_product_without_skus(
    api_client,
    create_moderation,
    no_sku_b2b_client_class,
):
    ApproveProductView.b2b_client_class = no_sku_b2b_client_class
    moderation = create_moderation()

    response = api_client.post(
        reverse("approve-product", kwargs={"ticket_id": moderation.id}),
        {},
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "PRODUCT_HAS_NO_SKUS",
        "message": "Product has no SKUs, cannot approve",
    }


@pytest.mark.django_db
def test_approve_product_rolls_back_when_event_fails(
    api_client,
    create_moderation,
    event_error_approve_b2b_client_class,
):
    ApproveProductView.b2b_client_class = event_error_approve_b2b_client_class
    moderation = create_moderation()
    ProductModerationFieldReport.objects.create(
        product_moderation=moderation,
        field_name=ProductModerationFieldReport.FieldName.TITLE,
        comment="Fix title",
    )

    response = api_client.post(
        reverse("approve-product", kwargs={"ticket_id": moderation.id}),
        {"comment": "Ok"},
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 500
    assert response.json() == {
        "code": "B2B_EVENT_FAILED",
        "message": "Failed to send moderation event to B2B",
    }

    moderation.refresh_from_db()
    assert moderation.status == ProductModeration.Status.IN_REVIEW
    assert moderation.date_moderation is None
    assert moderation.moderator_comment is None
    assert moderation.field_reports.count() == 1
