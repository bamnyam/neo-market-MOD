import uuid
from json import loads

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from app.product_moderation.api import B2BClient, B2BClientError
from app.product_moderation.api import b2b_client as b2b_client_module
from app.product_moderation.models import (
    ProductModeration,
    ProductModerationFieldReport,
)
from app.product_moderation.views import ApproveProductView


class SuccessfulB2BClient:
    def get_product(self, product_id: str) -> dict:
        return {"id": product_id, "skus": [{"id": str(uuid.uuid4())}]}

    def send_moderation_event(self, product_id: str, status: str) -> None:
        return None


class NoSkuB2BClient(SuccessfulB2BClient):
    def get_product(self, product_id: str) -> dict:
        return {"id": product_id, "skus": []}


class EventErrorB2BClient(SuccessfulB2BClient):
    def send_moderation_event(self, product_id: str, status: str) -> None:
        raise B2BClientError("event failed")


class FakeB2BResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None


@pytest.fixture(autouse=True)
def reset_b2b_client():
    ApproveProductView.b2b_client_class = SuccessfulB2BClient
    yield
    ApproveProductView.b2b_client_class = SuccessfulB2BClient


@pytest.fixture
def api_client():
    return APIClient()


def create_moderation(**kwargs) -> ProductModeration:
    defaults = {
        "product_id": uuid.uuid4(),
        "seller_id": uuid.uuid4(),
        "status": ProductModeration.Status.IN_REVIEW,
        "queue_priority": ProductModeration.QueuePriority.NEW_PRODUCTS,
        "json_after": {"title": "Product"},
        "moderator_id": uuid.uuid4(),
    }
    defaults.update(kwargs)
    return ProductModeration.objects.create(**defaults)


@pytest.mark.django_db
def test_approve_product_success(api_client):
    moderation = create_moderation(blocking_reason_id=None)
    ProductModerationFieldReport.objects.create(
        product_moderation=moderation,
        field_name=ProductModerationFieldReport.FieldName.TITLE,
        comment="Fix title",
    )

    response = api_client.post(
        reverse("approve-product", kwargs={"product_id": moderation.product_id}),
        {"moderator_comment": "Product meets requirements"},
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 200
    assert response.json() == {
        "product_id": str(moderation.product_id),
        "status": ProductModeration.Status.MODERATED,
    }

    moderation.refresh_from_db()
    assert moderation.status == ProductModeration.Status.MODERATED
    assert moderation.date_moderation is not None
    assert moderation.moderator_comment == "Product meets requirements"
    assert moderation.blocking_reason_id is None
    assert moderation.field_reports.count() == 0


@pytest.mark.django_db
def test_approve_product_not_found(api_client):
    response = api_client.post(
        reverse("approve-product", kwargs={"product_id": uuid.uuid4()}),
        {},
        format="json",
        HTTP_X_MODERATOR_ID=str(uuid.uuid4()),
    )

    assert response.status_code == 404
    assert response.json() == {"error": "Product not found in moderation queue"}


@pytest.mark.django_db
def test_approve_product_rejects_hard_blocked(api_client):
    moderation = create_moderation(status=ProductModeration.Status.HARD_BLOCKED)

    response = api_client.post(
        reverse("approve-product", kwargs={"product_id": moderation.product_id}),
        {},
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 409
    assert response.json() == {"error": "Product is permanently blocked"}


@pytest.mark.django_db
def test_approve_product_rejects_not_in_review(api_client):
    moderation = create_moderation(status=ProductModeration.Status.PENDING)

    response = api_client.post(
        reverse("approve-product", kwargs={"product_id": moderation.product_id}),
        {},
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 409
    assert response.json() == {"error": "Product is not in review status"}


@pytest.mark.django_db
def test_approve_product_rejects_other_moderator(api_client):
    moderation = create_moderation()

    response = api_client.post(
        reverse("approve-product", kwargs={"product_id": moderation.product_id}),
        {},
        format="json",
        HTTP_X_MODERATOR_ID=str(uuid.uuid4()),
    )

    assert response.status_code == 403
    assert response.json() == {"error": "This moderation card is not assigned to you"}


@pytest.mark.django_db
def test_approve_product_rejects_product_without_skus(api_client):
    ApproveProductView.b2b_client_class = NoSkuB2BClient
    moderation = create_moderation()

    response = api_client.post(
        reverse("approve-product", kwargs={"product_id": moderation.product_id}),
        {},
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 409
    assert response.json() == {"error": "Product has no SKUs, cannot approve"}


@pytest.mark.django_db
def test_approve_product_rolls_back_when_event_fails(api_client):
    ApproveProductView.b2b_client_class = EventErrorB2BClient
    moderation = create_moderation()
    ProductModerationFieldReport.objects.create(
        product_moderation=moderation,
        field_name=ProductModerationFieldReport.FieldName.TITLE,
        comment="Fix title",
    )

    response = api_client.post(
        reverse("approve-product", kwargs={"product_id": moderation.product_id}),
        {"moderator_comment": "Ok"},
        format="json",
        HTTP_X_MODERATOR_ID=str(moderation.moderator_id),
    )

    assert response.status_code == 500

    moderation.refresh_from_db()
    assert moderation.status == ProductModeration.Status.IN_REVIEW
    assert moderation.date_moderation is None
    assert moderation.moderator_comment is None
    assert moderation.field_reports.count() == 1


@override_settings(B2B_URL="http://b2b.example", MOD_TO_B2B_KEY="secret")
def test_b2b_client_sends_moderated_event_contract(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return FakeB2BResponse()

    monkeypatch.setattr(b2b_client_module, "urlopen", fake_urlopen)

    product_id = str(uuid.uuid4())
    B2BClient().send_moderation_event(product_id, ProductModeration.Status.MODERATED)

    request = requests[0]
    payload = loads(request.data.decode("utf-8"))

    assert request.full_url == "http://b2b.example/api/v1/events/moderation"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("X-service-key") == "secret"
    assert uuid.UUID(payload["idempotency_key"])
    assert payload["product_id"] == product_id
    assert payload["status"] == "MODERATED"
